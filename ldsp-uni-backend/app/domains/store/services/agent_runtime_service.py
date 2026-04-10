"""Unified store agent runtime orchestration.

Phase 1 runtime goals:
- unify manual/internal execution of product review, comment review and reports
- persist run metadata consistently
- provide a single place for future schedulers/jobs to call
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.domains.store.services.ai_capability_service import AICapabilityService
from app.gateway.agents.registry import registry


def _db() -> sqlite3.Connection:
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _safe_json_loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _resolve_agent_result(agent_result: dict[str, Any]) -> dict[str, Any]:
    data = agent_result.get("data") if isinstance(agent_result, dict) else None
    metrics = data.get("metrics") if isinstance(data, dict) else {}
    scores = data.get("scores") if isinstance(data, dict) else {}
    trace_ref = data.get("trace_ref") if isinstance(data, dict) else {}
    trace_steps = trace_ref.get("trace") if isinstance(trace_ref, dict) else []
    final_decision = str((data or {}).get("final_decision") or "manual_review")
    return {
        "success": bool(agent_result.get("success", True)),
        "decision": final_decision,
        "final_decision": final_decision,
        "decision_source": str((data or {}).get("decision_source") or "fallback"),
        "reason": str((data or {}).get("final_reason") or ""),
        "suggested_action": str(
            (data or {}).get("suggested_action") or "manual_review"
        ),
        "confidence": float((scores or {}).get("confidence") or 0),
        "risk_score": float((scores or {}).get("risk_score") or 0),
        "latency_ms": int((metrics or {}).get("latency_ms") or 0),
        "token_input": int((metrics or {}).get("token_input") or 0),
        "token_output": int((metrics or {}).get("token_output") or 0),
        "token_used": int((metrics or {}).get("token_total") or 0),
        "model_used": str((metrics or {}).get("model_used") or ""),
        "trace": trace_steps if isinstance(trace_steps, list) else [],
        "trace_ref": trace_ref if isinstance(trace_ref, dict) else {},
        "raw": data if isinstance(data, dict) else {},
        "error_message": str(agent_result.get("error") or "")
        if not agent_result.get("success", True)
        else "",
    }


class AgentRuntimeService:
    def __init__(self) -> None:
        self.capability_service = AICapabilityService()
        self.capability_service.ensure_ready()

    async def run_product_review(
        self,
        product_id: int,
        review_config_id: int | None = None,
        trigger_source: str = "manual",
        operator: dict | None = None,
    ) -> dict:
        conn = _db()
        try:
            capability = self.capability_service.resolve_capability(
                "shop_product_review"
            )
            product = _row_to_dict(
                conn.execute(
                    "SELECT * FROM shop_products WHERE id = ?", (product_id,)
                ).fetchone()
            )
            if not product:
                raise ValueError("商品不存在")
            content = json.dumps(
                {
                    "name": product.get("name"),
                    "description": product.get("description"),
                    "price": product.get("price"),
                    "discount": product.get("discount"),
                    "category_id": product.get("category_id"),
                    "product_type": product.get("product_type"),
                    "seller_username": product.get("seller_username"),
                    "stock": product.get("stock"),
                },
                ensure_ascii=False,
            )
            agent = registry.get("shop_product_review")
            raw_result = await agent.run(
                content=content,
                target_id=str(product_id),
                context={
                    "review_config_id": review_config_id,
                    "category_id": product.get("category_id"),
                    "product_name": product.get("name"),
                },
            )
            result = _resolve_agent_result(raw_result)
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            final_action = str(result.get("decision") or "manual_review")
            product_status = (
                "ai_approved"
                if final_action == "approve"
                else "ai_rejected"
                if final_action == "reject"
                else "pending_manual"
            )
            conn.execute(
                """
                UPDATE shop_products SET
                    status = ?,
                    reviewed_at = ?,
                    reviewed_by = ?,
                    reject_reason = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    product_status,
                    now_ms,
                    str((operator or {}).get("username") or "AI"),
                    result.get("reason") if final_action != "approve" else None,
                    now_ms,
                    product_id,
                ),
            )
            conn.execute(
                "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    product_id,
                    final_action,
                    str((operator or {}).get("username") or "AI"),
                    result.get("reason") or None,
                    now_ms,
                ),
            )
            conn.execute(
                """
                INSERT INTO ai_review_logs (
                    product_id, category_id, config_id,
                    snapshot_product_name, snapshot_seller_username, snapshot_product_status,
                    snapshot_product_price, snapshot_product_description, snapshot_product_deleted,
                    snapshot_category_name, snapshot_config_name, snapshot_api_config_name, snapshot_api_model, snapshot_api_config_id,
                    request_prompt, request_product_json,
                    response_raw, response_decision, response_confidence,
                    response_reason, response_suggestions, response_user_feedback,
                    final_action, final_reason,
                    latency_ms, token_used,
                    error_type, error_message,
                    decision_source, agent_trace_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    product.get("category_id"),
                    review_config_id,
                    product.get("name"),
                    product.get("seller_username"),
                    product.get("status"),
                    product.get("price"),
                    product.get("description"),
                    product.get("is_deleted"),
                    None,
                    None,
                    result.get("api_config_name"),
                    result.get("model_used"),
                    result.get("api_config_id"),
                    content,
                    content,
                    json.dumps(raw_result, ensure_ascii=False),
                    final_action,
                    result.get("confidence"),
                    result.get("reason"),
                    "",
                    "",
                    final_action,
                    result.get("reason"),
                    result.get("latency_ms"),
                    result.get("token_used"),
                    None if result.get("success") else "agent_error",
                    result.get("error_message") or None,
                    result.get("decision_source"),
                    json.dumps(
                        {"trace": result.get("trace") or []}, ensure_ascii=False
                    ),
                    now_ms,
                ),
            )
            conn.commit()
            return {
                **result,
                "capability_key": "shop_product_review",
                "provider_type": result.get("provider_type")
                or ((capability or {}).get("primary") or {}).get("provider_type")
                or "openai_compatible",
                "gateway_route": result.get("gateway_route")
                or ((capability or {}).get("primary") or {}).get("gateway_route")
                or "",
                "trigger_source": trigger_source,
                "operator": operator or {},
            }
        finally:
            conn.close()

    async def run_comment_review(
        self,
        content: str,
        target_id: str,
        context: dict | None = None,
        trigger_source: str = "manual",
        operator: dict | None = None,
    ) -> dict:
        capability = self.capability_service.resolve_capability("shop_comment_review")
        agent = registry.get("shop_comment_review")
        context = context or {}
        raw_result = await agent.run(
            content=content,
            target_id=str(target_id),
            context=context,
        )
        result = _resolve_agent_result(raw_result)
        enriched = {
            **result,
            "capability_key": "shop_comment_review",
            "provider_type": result.get("provider_type")
            or ((capability or {}).get("primary") or {}).get("provider_type")
            or "openai_compatible",
            "gateway_route": result.get("gateway_route")
            or ((capability or {}).get("primary") or {}).get("gateway_route")
            or "",
            "capability_snapshot": (capability or {}).get("capability") or {},
            "trigger_source": trigger_source,
            "operator": operator or {},
        }
        comment_id = context.get("comment_id")
        reply_id = context.get("reply_id")
        if comment_id or reply_id:
            conn = _db()
            try:
                now = int(datetime.now(timezone.utc).timestamp() * 1000)
                parsed = result.get("parsed") or {}
                final_status = (
                    "ai_approved"
                    if result.get("decision") == "approve"
                    else "ai_rejected"
                    if result.get("decision") == "reject"
                    else "pending_manual"
                )
                target_table = (
                    "shop_product_comment_replies"
                    if reply_id
                    else "shop_product_comments"
                )
                target_pk = int(reply_id or comment_id)
                target_row = _row_to_dict(
                    conn.execute(
                        f"SELECT * FROM {target_table} WHERE id = ? LIMIT 1",
                        (target_pk,),
                    ).fetchone()
                )
                if target_row:
                    conn.execute(
                        f"""UPDATE {target_table} SET
                            status = ?,
                            ai_decision = ?,
                            ai_confidence = ?,
                            ai_risk_score = ?,
                            ai_reason = ?,
                            ai_suggestion = ?,
                            ai_error = ?,
                            ai_model = ?,
                            ai_reviewed_at = ?,
                            updated_at = ?
                           WHERE id = ?""",
                        (
                            final_status,
                            result.get("decision"),
                            result.get("confidence"),
                            parsed.get("risk_score")
                            if isinstance(parsed, dict)
                            else None,
                            result.get("reason"),
                            parsed.get("suggestion")
                            if isinstance(parsed, dict)
                            else "",
                            result.get("error_message") or None,
                            result.get("model_used"),
                            now,
                            now,
                            target_pk,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO shop_comment_ai_review_logs (
                            target_type, comment_id, reply_id, root_comment_id, product_id,
                            username, nickname, comment_content, parent_comment_content,
                            api_config_id, api_config_name, api_model,
                            request_prompt, request_comment_json, review_criteria_json,
                            response_raw, response_decision, response_confidence, response_risk_score,
                            response_reason, response_suggestion,
                            final_status, final_reason, decision_source, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            "reply" if reply_id else "comment",
                            int(
                                comment_id or target_row.get("comment_id") or target_pk
                            ),
                            int(reply_id or 0) if reply_id else None,
                            int(target_row.get("comment_id") or target_pk),
                            int(
                                target_row.get("product_id")
                                or context.get("product_id")
                                or 0
                            ),
                            target_row.get("username") or context.get("username") or "",
                            target_row.get("nickname")
                            or target_row.get("username")
                            or context.get("username")
                            or "",
                            target_row.get("content") or content,
                            target_row.get("status") or "",
                            final_status,
                            result.get("api_config_id"),
                            result.get("api_config_name"),
                            result.get("model_used"),
                            content,
                            json.dumps(context or {}, ensure_ascii=False),
                            json.dumps({}, ensure_ascii=False),
                            json.dumps(raw_result, ensure_ascii=False),
                            result.get("api_config_id"),
                            result.get("decision"),
                            result.get("confidence"),
                            parsed.get("risk_score")
                            if isinstance(parsed, dict)
                            else None,
                            result.get("reason"),
                            parsed.get("suggestion")
                            if isinstance(parsed, dict)
                            else "",
                            final_status,
                            result.get("reason"),
                            result.get("decision_source") or "llm",
                            now,
                        ),
                    )
                    conn.commit()
            finally:
                conn.close()
        return enriched

    def create_report_run(
        self,
        report_type: str,
        payload: dict | None = None,
        trigger_source: str = "manual_generate",
        operator: dict | None = None,
    ) -> dict:
        capability_key = {
            "daily": "shop_ops_daily_report",
            "weekly": "shop_ops_weekly_report",
            "monthly": "shop_ops_monthly_report",
        }[report_type]
        capability = self.capability_service.resolve_capability(capability_key)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        run_id = f"shop_ops_{report_type}_{now}"
        input_json = json.dumps(
            {"reportMeta": {"reportType": report_type}, "payload": payload or {}},
            ensure_ascii=False,
        )
        output_json = json.dumps(
            {
                "report": {
                    "summary": f"{report_type} report queued",
                    "reportMeta": {"reportType": report_type},
                },
                "capability_key": capability_key,
                "provider_type": ((capability or {}).get("primary") or {}).get(
                    "provider_type"
                )
                or "openai_compatible",
                "gateway_route": ((capability or {}).get("primary") or {}).get(
                    "gateway_route"
                )
                or "",
                "capability_snapshot": (capability or {}).get("capability") or {},
            },
            ensure_ascii=False,
        )
        conn = _db()
        try:
            agent_row = conn.execute(
                "SELECT d.id, v.version FROM agent_definitions d LEFT JOIN agent_versions v ON v.agent_id = d.id AND v.is_current = 1 WHERE d.agent_key = 'ops_copilot' LIMIT 1"
            ).fetchone()
            agent_id = agent_row["id"] if agent_row else None
            agent_version = (agent_row["version"] if agent_row else None) or "v1"
            conn.execute(
                """INSERT INTO agent_runs (
                    run_id, agent_id, agent_key, agent_version, trigger_source, mode, status,
                    input_json, output_json, trace_json, error_type, error_message,
                    decision, decision_source, latency_ms, token_used, cost_micros, risk_score,
                    operator_id, operator_name, started_at, ended_at, created_at, updated_at
                ) VALUES (?, ?, 'ops_copilot', ?, ?, 'prod', 'queued', ?, ?, ?, NULL, NULL, 'queued', 'ops_copilot_runtime', 0, 0, 0, 0, ?, ?, ?, NULL, ?, ?)""",
                (
                    run_id,
                    agent_id,
                    agent_version,
                    trigger_source,
                    input_json,
                    output_json,
                    json.dumps(
                        {"queued": True, "reportType": report_type}, ensure_ascii=False
                    ),
                    str((operator or {}).get("user_id") or "system"),
                    (operator or {}).get("username") or "system",
                    now,
                    now,
                    str((operator or {}).get("user_id") or "system"),
                    now,
                ),
            )
            conn.commit()
            return {
                "runId": run_id,
                "status": "queued",
                "capabilityKey": capability_key,
            }
        finally:
            conn.close()
