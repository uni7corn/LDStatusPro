"""Comment Review Agent — LangGraph workflow for shop comment审核."""

from __future__ import annotations

import json
import time

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from app.config import settings
from app.config.constants import (
    DECISION_APPROVE,
    DECISION_REJECT,
    DECISION_MANUAL_REVIEW,
)
from app.gateway.agents.base_agent import AgentState, BaseAgent
from app.gateway.config_loader import build_llm_runtime_config
from app.gateway.agents.product_review import (
    rule_precheck as base_rule_precheck,
    _parse_llm_response,
    decision_fusion,
    ChatOpenAI_instance,
)

logger = structlog.get_logger(__name__)


def comment_rule_precheck(state: AgentState) -> dict:
    """Rule precheck for comments. Uses base precheck + comment-specific rules."""
    content = state.get("content", "")

    # Comment-specific rules
    forbidden = ["刷单", "淘宝", "拼多多", "京东", "闲鱼"]
    rules_hit = []
    for word in forbidden:
        if word in content:
            rules_hit.append(f"forbidden_word:{word}")

    # Run base precheck
    result = base_rule_precheck(state)
    if rules_hit:
        existing_rules = result.get("rule_precheck_result", {}).get("rules", [])
        existing_rules.extend(rules_hit)
        result["rule_precheck_result"]["rules"] = existing_rules
        if not result["rule_precheck_result"].get("short_circuit"):
            result["rule_precheck_result"]["risk_boost"] = (
                result.get("rule_precheck_result", {}).get("risk_boost", 0)
                + len(rules_hit) * 0.1
            )

    return result


class CommentReviewAgent(BaseAgent):
    """Agent for reviewing shop product comments."""

    agent_key = "shop_comment_review"
    agent_name = "评论审核智能体"
    agent_version = "1.0.0"
    target_type = "comment"
    description = "审核商品评论及回复内容"
    auto_approve_threshold = 0.85
    auto_reject_threshold = 0.85

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        workflow.add_node("rule_precheck", comment_rule_precheck)
        workflow.add_node("llm_invoke", self._llm_node)
        workflow.add_node("decision_fusion", decision_fusion)

        workflow.add_edge(START, "rule_precheck")

        def should_continue(state: AgentState) -> str:
            precheck = state.get("rule_precheck_result", {})
            if precheck.get("short_circuit"):
                return "decision_fusion"
            return "llm_invoke"

        workflow.add_conditional_edges(
            "rule_precheck",
            should_continue,
            {"llm_invoke": "llm_invoke", "decision_fusion": "decision_fusion"},
        )

        workflow.add_edge("llm_invoke", "decision_fusion")
        workflow.add_edge("decision_fusion", END)

        return workflow.compile()

    def _llm_node(self, state: AgentState) -> dict:
        """Call LLM for comment review."""
        step_start = time.monotonic()
        try:
            runtime = build_llm_runtime_config(
                state.get("context", {}).get("review_config_id"),
                state.get("context", {}).get("category_id"),
                capability_key="shop_comment_review",
            )
            primary = runtime["primary"]
            llm = ChatOpenAI(
                model=primary["model"],
                openai_api_key=primary["api_key"],
                openai_api_base=primary["base_url"],
                temperature=0.3,
                max_tokens=1024,
            )

            system_prompt = self._build_system_prompt(state)
            user_prompt = self._build_user_prompt(state)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            response = llm.invoke(messages)
            raw = response.content
            usage = response.response_metadata.get("token_usage", {})
            parsed = _parse_llm_response(raw)

            return {
                "llm_response": parsed,
                "model_used": primary["model"],
                "api_config_id": primary.get("id"),
                "api_config_name": primary.get("name"),
                "provider_type": primary.get("provider_type") or "openai_compatible",
                "gateway_route": primary.get("gateway_route") or "",
                "capability_key": runtime.get("capability_key")
                or "shop_comment_review",
                "token_input": usage.get("prompt_tokens", 0),
                "token_output": usage.get("completion_tokens", 0),
                "trace_steps": state.get("trace_steps", [])
                + [
                    {
                        "step": "llm_invoke",
                        "result": f"success, decision={parsed['decision']}",
                        "duration_ms": int((time.monotonic() - step_start) * 1000),
                        "token_usage": usage,
                    }
                ],
            }
        except Exception as e:
            logger.error("comment_llm_failed", error=str(e))
            return {
                "llm_response": None,
                "error_type": "llm_error",
                "error_message": str(e),
                "trace_steps": state.get("trace_steps", [])
                + [
                    {
                        "step": "llm_invoke",
                        "result": f"error: {str(e)}",
                        "duration_ms": int((time.monotonic() - step_start) * 1000),
                    }
                ],
            }

    def _build_system_prompt(self, state: AgentState) -> str:
        return """你是一个专业的电商评论审核智能体。你负责审核社区平台上用户发布的商品评论。

审核规则：
1. 评论不能包含攻击性、歧视性语言
2. 不能包含广告宣传或导流信息（QQ、微信、其他平台链接）
3. 不能刷单或发布虚假评论
4. 评论内容应与商品相关
5. 不能泄露个人隐私信息
6. 不能引导私下交易

请以 JSON 格式返回：
```json
{
    "decision": "approve or reject or manual_review",
    "confidence": 0.92,
    "risk_score": 0.15,
    "reason": "审核理由"
}
```""".strip()

    def _build_user_prompt(self, state: AgentState) -> str:
        content = state.get("content", "")
        context = state.get("context", {})
        parts = [f"评论内容：{content}"]
        if context.get("username"):
            parts.append(f"评论用户：{context['username']}")
        if context.get("product_name"):
            parts.append(f"商品：{context['product_name']}")
        if context.get("is_purchased") is not None:
            parts.append(f"是否已购买：{'是' if context['is_purchased'] else '否'}")
        return "\n".join(parts)
