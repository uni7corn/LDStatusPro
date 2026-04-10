"""Agent base class and state model for LangChain/LangGraph agents.

This module defines the unified agent state, base agent class,
and trace schema that all agents must follow.
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, TypedDict

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.config.constants import (
    AGENT_DECISION_APPROVE,
    AGENT_DECISION_REJECT,
    AGENT_DECISION_MANUAL_REVIEW,
    DECISION_APPROVE,
    DECISION_REJECT,
    DECISION_MANUAL_REVIEW,
    DECISION_SOURCES,
)
from app.gateway.config_loader import build_llm_runtime_config

logger = structlog.get_logger(__name__)


# ──────────────────────────────────────────
# Agent State (LangGraph TypedDict)
# ──────────────────────────────────────────


class AgentState(TypedDict, total=False):
    """Unified state for all agents."""

    # ── Input ──
    request_id: str
    agent_key: str
    agent_version: str
    target_type: str  # product, comment, image, buy_request, chat
    target_id: str
    content: str
    context: dict[str, Any]  # extra context (user info, category, etc.)
    config: dict[str, Any]  # runtime config (thresholds, model, etc.)

    # ── Processing ──
    rule_precheck_result: dict[str, Any]
    tool_results: list[dict[str, Any]]
    llm_response: dict[str, Any]
    similar_cases: list[dict[str, Any]]  # RAG results
    trace_steps: list[dict[str, Any]]

    # ── Output ──
    final_decision: str  # approve, reject, manual_review
    decision_source: str  # rule_engine, llm, fallback
    confidence: float
    risk_score: float
    reason: str
    suggested_action: str

    # ── Metrics ──
    model_used: str
    duration_ms: int
    token_input: int
    token_output: int
    cost_estimate: float

    # ── Error ──
    error_type: str | None
    error_message: str | None


# ──────────────────────────────────────────
# Base Agent
# ──────────────────────────────────────────


class BaseAgent(ABC):
    """Base class for all LangChain agents.

    Each agent subclass must:
    1. Set `agent_key` and `agent_name`
    2. Implement `_build_graph()` to define the LangGraph workflow
    3. Optionally override `_build_system_prompt()` and `_build_user_prompt()`
    """

    agent_key: str = ""
    agent_name: str = ""
    agent_version: str = "1.0.0"
    target_type: str = ""
    description: str = ""

    # Default thresholds
    auto_approve_threshold: float = 0.85
    auto_reject_threshold: float = 0.85

    def __init__(self):
        self._graph = self._build_graph()
        self._compile_graph()

    def _get_llm(self) -> ChatOpenAI:
        """Get the LLM instance from database-backed gateway config."""
        runtime = build_llm_runtime_config()
        primary = runtime["primary"]
        return ChatOpenAI(
            model=primary["model"],
            openai_api_key=primary["api_key"],
            openai_api_base=primary["base_url"],
            temperature=0.3,
            max_tokens=1024,
            streaming=False,
        )

    def _build_system_prompt(self, state: AgentState) -> str:
        """Build system prompt. Override in subclass for custom prompts."""
        return f"""你是一个专业的审核助手，负责审核{self.target_type}内容。
请根据以下规则进行判断：
1. 判断内容是否符合社区规范
2. 评估风险等级 (0-1)
3. 给出决策建议：approve（通过）/ reject（拒绝）/ manual_review（转人工）

请以 JSON 格式返回，包含以下字段：
{{
    "decision": "approve/reject/manual_review",
    "confidence": 0.0-1.0,
    "risk_score": 0.0-1.0,
    "reason": "审核理由"
}}"""

    def _build_user_prompt(self, state: AgentState) -> str:
        """Build user prompt from state."""
        content = state.get("content", "")
        context = state.get("context", {})
        similar = state.get("similar_cases", [])

        prompt_parts = [f"请审核以下内容：\n{content}"]

        if context:
            ctx_str = "\n".join(f"- {k}: {v}" for k, v in context.items())
            prompt_parts.append(f"\n上下文信息：\n{ctx_str}")

        if similar:
            prompt_parts.append("\n相似案例参考：")
            for i, case in enumerate(similar[:3], 1):
                prompt_parts.append(
                    f"{i}. 决策: {case.get('decision', '?')}, 理由: {case.get('reason', '?')}"
                )

        return "\n".join(prompt_parts)

    def _parse_llm_response(self, raw: str) -> dict[str, Any]:
        """Parse LLM JSON response."""
        import re

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```\s*json\s*\n(.*?)\n```", raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1)

        # Try JSON parsing
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            # Try to find JSON object in text
            json_match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError(f"Failed to parse LLM response as JSON: {raw[:200]}")

        return {
            "decision": data.get("decision", DECISION_MANUAL_REVIEW),
            "confidence": float(data.get("confidence", 0.5)),
            "risk_score": float(data.get("risk_score", 0.5)),
            "reason": data.get("reason", ""),
        }

    def compile(self) -> None:
        """Compile the graph. Called by registry."""
        self._compile_graph()

    def _compile_graph(self) -> None:
        """Internal compile."""
        self._graph = self._build_graph()

    @abstractmethod
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow. Must be implemented by subclass."""
        ...

    async def run(
        self,
        content: str,
        target_id: str,
        context: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run the agent with the given input.

        Returns a unified response dict matching Agent Runtime Spec v1.
        """
        start = time.monotonic()
        request_id = f"req_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        state: AgentState = {
            "request_id": request_id,
            "agent_key": self.agent_key,
            "agent_version": self.agent_version,
            "target_type": self.target_type,
            "target_id": str(target_id),
            "content": content,
            "context": context or {},
            "config": config or {},
            "trace_steps": [],
            "tool_results": [],
            "similar_cases": [],
            "error_type": None,
            "error_message": None,
        }

        try:
            result = await self._graph.ainvoke(state)
        except Exception as e:
            logger.error(
                "agent_execution_failed", agent_key=self.agent_key, error=str(e)
            )
            result = {
                **state,
                "final_decision": DECISION_MANUAL_REVIEW,
                "decision_source": "fallback",
                "confidence": 0.0,
                "risk_score": 0.0,
                "reason": f"执行失败: {str(e)}",
                "suggested_action": "manual_review",
                "error_type": "execution_error",
                "error_message": str(e),
            }

        duration_ms = int((time.monotonic() - start) * 1000)
        result["duration_ms"] = duration_ms
        if not result.get("model_used"):
            try:
                result["model_used"] = build_llm_runtime_config()["primary"]["model"]
            except Exception:
                result["model_used"] = ""

        return self._format_response(result)

    def _format_response(self, result: dict[str, Any]) -> dict[str, Any]:
        """Format the agent result into a unified response."""
        trace = self._build_trace(result)
        return {
            "success": not result.get("error_type"),
            "data": {
                "run_id": result.get("request_id", ""),
                "agent_key": self.agent_key,
                "agent_version": self.agent_version,
                "final_decision": result.get("final_decision", DECISION_MANUAL_REVIEW),
                "decision_source": result.get("decision_source", "llm"),
                "final_reason": result.get("reason", ""),
                "suggested_action": result.get("suggested_action", "manual_review"),
                "scores": {
                    "confidence": result.get("confidence", 0.0),
                    "risk_score": result.get("risk_score", 0.0),
                },
                "metrics": {
                    "latency_ms": result.get("duration_ms", 0),
                    "token_input": result.get("token_input", 0),
                    "token_output": result.get("token_output", 0),
                    "token_total": result.get("token_input", 0)
                    + result.get("token_output", 0),
                    "model_used": result.get("model_used", ""),
                },
                "trace_ref": {
                    "trace_id": trace.get("trace_id", ""),
                    "trace_schema_version": "v1",
                    "trace": trace.get("steps", []),
                },
                "actions": self._build_actions(result),
            },
        }

    def _build_trace(self, result: dict[str, Any]) -> dict[str, Any]:
        """Build trace from state."""
        steps = result.get("trace_steps", [])
        return {
            "trace_id": result.get("request_id", ""),
            "agent_key": self.agent_key,
            "agent_version": self.agent_version,
            "target_type": result.get("target_type", ""),
            "target_id": result.get("target_id", ""),
            "steps": steps,
            "final_decision": result.get("final_decision", ""),
            "decision_source": result.get("decision_source", ""),
        }

    def _build_actions(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        """Build recommended actions from result."""
        actions = []
        decision = result.get("final_decision", "")
        if decision == DECISION_APPROVE:
            actions.append({"type": "auto_approve", "note": result.get("reason", "")})
        elif decision == DECISION_REJECT:
            actions.append({"type": "auto_reject", "note": result.get("reason", "")})
        else:
            priority = "high" if result.get("risk_score", 0) > 0.7 else "normal"
            actions.append(
                {
                    "type": "manual_review",
                    "priority": priority,
                    "note": result.get("reason", ""),
                }
            )
        if result.get("error_type"):
            actions.append(
                {
                    "type": "error",
                    "note": result.get("error_message", ""),
                }
            )
        return actions
