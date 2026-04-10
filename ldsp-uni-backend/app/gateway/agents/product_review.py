"""Product Review Agent — LangGraph workflow for shop product审核.

Workflow: rule_precheck → (optional: rag_retrieve) → llm_invoke → decision_fusion → END
                                                        ↓ (on error)
                                                     fallback → END
"""

from __future__ import annotations

import json
import time
import sqlite3
from typing import Any

import structlog
from langgraph.graph import StateGraph, START, END

from app.config import settings
from app.config.constants import (
    DECISION_APPROVE,
    DECISION_REJECT,
    DECISION_MANUAL_REVIEW,
)
from app.gateway.agents.base_agent import AgentState, BaseAgent
from app.gateway.config_loader import build_llm_runtime_config

logger = structlog.get_logger(__name__)


# ──────────────────────────────────────────
# Node functions
# ──────────────────────────────────────────


def rule_precheck(state: AgentState) -> dict:
    """Rule-based pre-check. Can short-circuit to approve/reject."""
    content = state.get("content", "")
    context = state.get("context", {})
    step_start = time.monotonic()

    rules_hit: list[str] = []

    # Rule 1: Empty content → reject
    if not content or len(content.strip()) < 5:
        return {
            "rule_precheck_result": {
                "short_circuit": True,
                "decision": DECISION_MANUAL_REVIEW,
                "rules": ["empty_content"],
            },
            "trace_steps": state.get("trace_steps", [])
            + [
                {
                    "step": "rule_precheck",
                    "result": "short_circuit: empty",
                    "rules_hit": ["empty_content"],
                    "duration_ms": int((time.monotonic() - step_start) * 1000),
                }
            ],
        }

    # Rule 2: External link check (QQ/WeChat/Telegram mentions)
    forbidden_patterns = ["qq.com", "weixin.qq.com", "t.me/", "电报", "TG群"]
    for pat in forbidden_patterns:
        if pat.lower() in content.lower():
            rules_hit.append(f"forbidden_link:{pat}")

    # Rule 3: Blacklisted keywords
    blacklist_words = context.get("blacklist_words", [])
    for word in blacklist_words:
        if word.lower() in content.lower():
            rules_hit.append(f"blacklist_word:{word}")

    # Rule 4: Category-specific rules (query DB)
    category_id = context.get("category_id")
    if category_id:
        try:
            conn = sqlite3.connect(settings.store_database_path)
            cursor = conn.execute(
                "SELECT is_enabled FROM ai_review_category_config WHERE category_id = ? AND is_enabled = 1",
                (category_id,),
            )
            if not cursor.fetchone():
                # Category has AI review disabled → manual review
                conn.close()
                return {
                    "rule_precheck_result": {
                        "short_circuit": True,
                        "decision": DECISION_MANUAL_REVIEW,
                        "rules": ["ai_disabled_for_category"],
                    },
                    "trace_steps": state.get("trace_steps", [])
                    + [
                        {
                            "step": "rule_precheck",
                            "result": "short_circuit: ai_disabled_for_category",
                            "rules_hit": ["ai_disabled_for_category"],
                            "duration_ms": int((time.monotonic() - step_start) * 1000),
                        }
                    ],
                }
            conn.close()
        except Exception:
            pass

    if rules_hit:
        return {
            "rule_precheck_result": {
                "short_circuit": False,
                "decision": None,
                "rules": rules_hit,
                "risk_boost": len(rules_hit) * 0.15,
            },
            "trace_steps": state.get("trace_steps", [])
            + [
                {
                    "step": "rule_precheck",
                    "result": f"rules_hit: {rules_hit}",
                    "rules_hit": rules_hit,
                    "duration_ms": int((time.monotonic() - step_start) * 1000),
                }
            ],
        }

    return {
        "rule_precheck_result": {
            "short_circuit": False,
            "decision": None,
            "rules_hit": [],
        },
        "trace_steps": state.get("trace_steps", [])
        + [
            {
                "step": "rule_precheck",
                "result": "no_rules_hit",
                "duration_ms": int((time.monotonic() - step_start) * 1000),
            }
        ],
    }


def rag_retrieve(state: AgentState) -> dict:
    """Retrieve similar cases from RAG knowledge base."""
    step_start = time.monotonic()
    content = state.get("content", "")
    similar = []

    # In v1, query recent review logs for similar content
    try:
        conn = sqlite3.connect(settings.store_database_path)
        cursor = conn.execute(
            """SELECT snapshot_product_description, response_decision, response_reason, response_confidence
               FROM ai_review_logs
               WHERE response_decision IN (?, ?)
               ORDER BY created_at DESC
               LIMIT 3""",
            (DECISION_APPROVE, DECISION_REJECT),
        )
        for row in cursor.fetchall():
            similar.append(
                {
                    "content": row[0][:200] if row[0] else "",
                    "decision": row[1],
                    "reason": row[2],
                    "confidence": row[3],
                }
            )
        conn.close()
    except Exception as e:
        logger.warning("rag_retrieve_failed", error=str(e))

    return {
        "similar_cases": similar,
        "trace_steps": state.get("trace_steps", [])
        + [
            {
                "step": "rag_retrieve",
                "result": f"found {len(similar)} similar cases",
                "duration_ms": int((time.monotonic() - step_start) * 1000),
            }
        ],
    }


def llm_invoke(state: AgentState) -> dict:
    """Call LLM for review decision."""
    step_start = time.monotonic()
    start_t = time.monotonic()

    llm = state.get("_llm") or ChatOpenAI_instance()

    system_prompt = state.get("_system_prompt", "")
    user_prompt = state.get("_user_prompt", "")

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        runtime = build_llm_runtime_config(
            state.get("context", {}).get("review_config_id"),
            state.get("context", {}).get("category_id"),
            capability_key="shop_product_review",
        )
        primary = runtime["primary"]

        llm_instance = ChatOpenAI(
            model=primary["model"],
            openai_api_key=primary["api_key"],
            openai_api_base=primary["base_url"],
            temperature=0.3,
            max_tokens=1024,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = llm_instance.invoke(messages)
        raw = response.content
        usage = response.response_metadata.get("token_usage", {})

        parsed = _parse_llm_response(raw)
        rule_boost = state.get("rule_precheck_result", {}).get("risk_boost", 0)
        if rule_boost:
            parsed["risk_score"] = min(1.0, parsed["risk_score"] + rule_boost)

        duration_ms = int((time.monotonic() - step_start) * 1000)
        return {
            "llm_response": parsed,
            "model_used": primary["model"],
            "api_config_id": primary.get("id"),
            "api_config_name": primary.get("name"),
            "provider_type": primary.get("provider_type") or "openai_compatible",
            "gateway_route": primary.get("gateway_route") or "",
            "capability_key": runtime.get("capability_key") or "shop_product_review",
            "token_input": usage.get("prompt_tokens", 0),
            "token_output": usage.get("completion_tokens", 0),
            "trace_steps": state.get("trace_steps", [])
            + [
                {
                    "step": "llm_invoke",
                    "result": f"success, decision={parsed['decision']}",
                    "duration_ms": duration_ms,
                    "token_usage": usage,
                }
            ],
        }

    except Exception as e:
        logger.error("llm_invoke_failed", error=str(e))
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


def decision_fusion(state: AgentState) -> dict:
    """Fuse rule precheck + LLM decision into final output."""
    step_start = time.monotonic()
    precheck = state.get("rule_precheck_result", {})
    llm_result = state.get("llm_response")
    error_type = state.get("error_type")

    # If precheck short-circuited
    if precheck.get("short_circuit"):
        decision = precheck["decision"]
        return {
            "final_decision": decision,
            "decision_source": "rule_engine",
            "confidence": 1.0 if decision != DECISION_MANUAL_REVIEW else 0.0,
            "risk_score": 0.5
            if decision == DECISION_MANUAL_REVIEW
            else (1.0 if decision == DECISION_REJECT else 0.0),
            "reason": f"规则预审: {', '.join(precheck.get('rules', []))}",
            "suggested_action": "approve"
            if decision == DECISION_APPROVE
            else ("reject" if decision == DECISION_REJECT else "manual_review"),
            "trace_steps": state.get("trace_steps", [])
            + [
                {
                    "step": "decision_fusion",
                    "result": "precheck_short_circuit",
                    "duration_ms": int((time.monotonic() - step_start) * 1000),
                }
            ],
        }

    # LLM was successful
    if llm_result:
        decision = llm_result.get("decision", DECISION_MANUAL_REVIEW)
        confidence = llm_result.get("confidence", 0.5)
        risk_score = llm_result.get("risk_score", 0.5)

        # Apply threshold guards
        config = state.get("config", {})
        approve_threshold = config.get("auto_approve_threshold", 0.85)
        reject_threshold = config.get("auto_reject_threshold", 0.85)

        if decision == DECISION_APPROVE and confidence >= approve_threshold:
            final_decision = DECISION_APPROVE
            source = "llm"
        elif decision == DECISION_REJECT and confidence >= reject_threshold:
            final_decision = DECISION_REJECT
            source = "llm"
        elif decision == DECISION_REJECT and confidence < reject_threshold:
            final_decision = DECISION_MANUAL_REVIEW
            source = "llm"  # threshold_guardrail
            llm_result["reason"] += " (置信度低于阈值，转人工)"
        else:
            final_decision = DECISION_MANUAL_REVIEW
            source = "llm"

        return {
            "final_decision": final_decision,
            "decision_source": source,
            "confidence": confidence,
            "risk_score": risk_score,
            "reason": llm_result.get("reason", ""),
            "suggested_action": "approve"
            if final_decision == DECISION_APPROVE
            else ("reject" if final_decision == DECISION_REJECT else "manual_review"),
            "trace_steps": state.get("trace_steps", [])
            + [
                {
                    "step": "decision_fusion",
                    "result": final_decision,
                    "source": source,
                    "duration_ms": int((time.monotonic() - step_start) * 1000),
                }
            ],
        }

    # Fallback: LLM failed
    return {
        "final_decision": DECISION_MANUAL_REVIEW,
        "decision_source": "fallback",
        "confidence": 0.0,
        "risk_score": 0.5,
        "reason": f"LLM调用失败: {state.get('error_message', '未知错误')}",
        "suggested_action": "manual_review",
        "trace_steps": state.get("trace_steps", [])
        + [
            {
                "step": "decision_fusion",
                "result": "fallback",
                "duration_ms": int((time.monotonic() - step_start) * 1000),
            }
        ],
    }


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Parse LLM JSON response."""
    import re

    json_match = re.search(r"```\s*json\s*\n(.*?)\n```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        json_match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            raise ValueError(f"Failed to parse: {raw[:200]}")
    return {
        "decision": data.get("decision", DECISION_MANUAL_REVIEW),
        "confidence": float(data.get("confidence", 0.5)),
        "risk_score": float(data.get("risk_score", 0.5)),
        "reason": data.get("reason", ""),
    }


def ChatOpenAI_instance():
    """Lazy import for type checking."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI


# ──────────────────────────────────────────
# Product Review Agent
# ──────────────────────────────────────────


class ProductReviewAgent(BaseAgent):
    """Agent for reviewing shop products."""

    agent_key = "shop_product_review"
    agent_name = "商品审核智能体"
    agent_version = "1.0.0"
    target_type = "product"
    description = "审核商品发布内容，包括名称、描述、分类等字段"
    auto_approve_threshold = 0.85
    auto_reject_threshold = 0.85

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        # Nodes
        workflow.add_node("rule_precheck", rule_precheck)
        workflow.add_node("rag_retrieve", rag_retrieve)
        workflow.add_node("llm_invoke", llm_invoke)
        workflow.add_node("decision_fusion", decision_fusion)

        # Edges
        workflow.add_edge(START, "rule_precheck")

        # After rule_precheck, go to rag or skip
        def should_continue_to_rag(state: AgentState) -> str:
            precheck = state.get("rule_precheck_result", {})
            if precheck.get("short_circuit"):
                return "decision_fusion"
            return "rag_retrieve"

        workflow.add_conditional_edges(
            "rule_precheck",
            should_continue_to_rag,
            {"rag_retrieve": "rag_retrieve", "decision_fusion": "decision_fusion"},
        )

        workflow.add_edge("rag_retrieve", "llm_invoke")
        workflow.add_edge("llm_invoke", "decision_fusion")
        workflow.add_edge("decision_fusion", END)

        return workflow.compile()

    def _build_system_prompt(self, state: AgentState) -> str:
        similar = state.get("similar_cases", [])
        similar_section = ""
        if similar:
            similar_section = "\n\n相似案例参考：\n"
            for i, case in enumerate(similar, 1):
                similar_section += f"{i}. 决策: {case.get('decision')}, 风险分: {case.get('risk_score')}, 理由: {case.get('reason', '')}\n"

        return f"""你是一个专业的电商商品审核智能体。你负责审核用户在社区平台发布的商品/服务信息。

审核规则：
1. 商品信息不能包含虚假宣传、欺诈内容
2. 不能引导用户添加私人联系方式（QQ、微信、电报等）
3. 不能出售违禁品
4. 价格需合理，不能明显偏离市场
5. 内容需与发布的分类相符
6. 不能包含攻击性、歧视性语言

请以 JSON 格式返回，格式如下：
```json
{{
    "decision": "approve or reject or manual_review",
    "confidence": 0.92,
    "risk_score": 0.15,
    "reason": "详细的审核理由"
}}
{similar_section}""".strip()

    def _build_user_prompt(self, state: AgentState) -> str:
        content = state.get("content", "")
        context = state.get("context", {})
        parts = [f"商品名称：{context.get('product_name', '')}", f"商品描述：{content}"]
        if context.get("category_name"):
            parts.insert(0, f"分类：{context['category_name']}")
        if context.get("seller_username"):
            parts.append(f"卖家：{context['seller_username']}")
        if context.get("price"):
            parts.append(f"价格：{context['price']}")
        return "\n".join(parts)
