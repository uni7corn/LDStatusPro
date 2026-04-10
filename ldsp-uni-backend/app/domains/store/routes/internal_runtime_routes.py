"""Internal runtime trigger routes for store AI capabilities.

These routes also provide legacy-compatible internal endpoints used by the
previous Node.js backends so old services can switch to the unified backend
without changing their callback contracts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.common.utils.response import error_response, success_response
from app.config import settings
from app.domains.store.services.agent_runtime_service import AgentRuntimeService

router = APIRouter(tags=["store-internal-runtime"])


def _db() -> sqlite3.Connection:
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _decrypt_legacy_ai_key(ciphertext: str) -> str:
    raw = str(ciphertext or "")
    if not raw:
        return ""
    if not raw.startswith("ENC:"):
        return raw
    encryption_key = str(settings.encryption_key or "").strip()
    if not encryption_key:
        return ""
    try:
        decoded = __import__("base64").b64decode(raw[4:]).decode("latin1")
        chars = []
        for index, char in enumerate(decoded):
            chars.append(
                chr(ord(char) ^ ord(encryption_key[index % len(encryption_key)]))
            )
        return "".join(chars)
    except Exception:
        return ""


def _internal_token() -> str:
    return (
        settings.image_ai_internal_key
        or settings.tg_bot_internal_key
        or settings.tg_bot_internal_token
        or settings.store_internal_token
        or settings.gateway_internal_token
        or settings.admin_secret
        or ""
    ).strip()


def _tg_bot_internal_token() -> str:
    return (
        settings.tg_bot_internal_key
        or settings.tg_bot_internal_token
        or settings.admin_secret
        or ""
    ).strip()


def _check_specific_internal_auth(
    request: Request, expected: str, missing_message: str
):
    expected_value = (expected or "").strip()
    if not expected_value:
        return error_response("INTERNAL_KEY_MISSING", missing_message, 500)
    actual = (
        request.headers.get("X-Internal-Key")
        or request.headers.get("X-Internal-Token")
        or ""
    ).strip()
    if actual != expected_value:
        return error_response("FORBIDDEN", "内部鉴权失败", 403)
    return None


def _check_internal_auth(request: Request):
    expected = _internal_token()
    if not expected:
        return error_response("INTERNAL_KEY_MISSING", "服务端未配置内部运行 token", 500)
    actual = (
        request.headers.get("X-Internal-Key")
        or request.headers.get("X-Internal-Token")
        or ""
    ).strip()
    if actual != expected:
        return error_response("FORBIDDEN", "内部鉴权失败", 403)
    return None


class InternalCapabilityRunPayload(BaseModel):
    capabilityKey: str = ""
    targetId: str = ""
    content: str = ""
    context: dict = {}
    triggerSource: str = "internal"
    operator: dict = {}


class InternalReportRunPayload(BaseModel):
    reportType: str = "daily"
    payload: dict = {}
    triggerSource: str = "internal"
    operator: dict = {}


class LegacyImageApiInvokePayload(BaseModel):
    prompt: str = ""
    source_type: str = "image_review"
    source_id: str | None = None
    source_site: str | None = None
    request_payload: dict | None = None


class LegacyTgReviewActionPayload(BaseModel):
    targetType: str | None = None
    target: str | None = None
    targetId: int = 0
    action: str = ""
    reason: str = ""
    operator: dict = {}


class LegacyInternalAgentRunPayload(BaseModel):
    mode: str | None = None
    triggerSource: str | None = None
    status: str | None = None
    decision: str | None = None
    decisionSource: str | None = None
    confidence: float | None = None
    reason: str | None = None
    riskScore: float | None = None
    tokenUsed: int | None = None
    costMicros: int | None = None
    latencyMs: int | None = None
    startedAt: int | None = None
    endedAt: int | None = None
    errorType: str | None = None
    errorMessage: str | None = None
    input: dict | None = None
    output: dict | None = None
    trace: dict | None = None
    steps: list[dict] | None = None
    inputText: str | None = None
    operatorId: str | None = None
    operatorName: str | None = None


def _normalize_tg_target_type(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw == "product":
        return "product"
    if raw == "comment":
        return "comment"
    if raw in {"buy_request", "buy-request", "buyrequest"}:
        return "buy_request"
    return ""


def _build_tg_reviewer_name(operator: dict | None = None) -> str:
    operator = operator or {}
    reviewer_name = str(operator.get("reviewerName") or "").strip()
    if reviewer_name:
        return reviewer_name[:80]
    username = str(operator.get("tgUsername") or "").strip()
    if username:
        return f"TG@{username}"[:80]
    display_name = str(operator.get("tgDisplayName") or "").strip()
    if display_name:
        return f"TG {display_name}"[:80]
    user_id = str(operator.get("tgUserId") or "").strip()
    if user_id:
        return f"TG#{user_id}"[:80]
    return "TG Bot"


async def _invoke_legacy_api_config(
    api_config_id: int, payload: LegacyImageApiInvokePayload
) -> dict:
    conn = _db()
    try:
        config = _row_to_dict(
            conn.execute(
                "SELECT * FROM ai_api_config WHERE id = ? LIMIT 1", (api_config_id,)
            ).fetchone()
        )
        if not config:
            raise ValueError("api config not found")
        if int(config.get("is_enabled") or 0) != 1:
            raise ValueError("api config disabled")

        prompt = str(payload.prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")

        request_payload = (
            payload.request_payload if isinstance(payload.request_payload, dict) else {}
        )
        image_url = ""
        for key in ("image_url", "imageUrl", "url"):
            candidate = str(request_payload.get(key) or "").strip()
            if candidate:
                image_url = candidate
                break
        if (
            str(payload.source_type or "image_review").strip().lower() == "image_review"
            and not image_url
        ):
            raise ValueError("image_url is required for image_review")

        api_key_encrypted = str(config.get("llm_api_key_encrypted") or "").strip()
        if not api_key_encrypted:
            raise ValueError("api key not configured")

        api_key = _decrypt_legacy_ai_key(api_key_encrypted)
        if not api_key:
            raise ValueError("api key not configured")

        llm_url = str(config.get("llm_url") or "").strip()
        llm_model = str(config.get("llm_model") or "").strip()
        if not llm_url or not llm_model:
            raise ValueError("api config not complete")

        timeout_ms = int(config.get("timeout_ms") or 30000)
        temperature = float(config.get("temperature") or 0.3)
        max_tokens = int(config.get("max_tokens") or 1024)
        messages: list[dict] = [
            {
                "role": "system",
                "content": "You are a product moderation assistant. Return JSON only.",
            }
        ]
        if image_url:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": prompt})

        request_body = {
            "model": llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens > 0:
            request_body["max_tokens"] = max_tokens

        start_at = datetime.now(timezone.utc)
        response_raw = ""
        error_type = None
        error_message = None
        parsed: dict | None = None
        model_used = llm_model
        latency_ms: int | None = None
        token_used = 0

        try:
            async with httpx.AsyncClient(
                timeout=max(timeout_ms, 1000) / 1000
            ) as client:
                response = await client.post(
                    llm_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "LDStatusPro-AIReview/1.0",
                    },
                    json=request_body,
                )
                latency_ms = max(
                    0,
                    int((datetime.now(timezone.utc) - start_at).total_seconds() * 1000),
                )
                response_raw = response.text or ""
                response.raise_for_status()
                payload_json = response.json()
                response_raw = json.dumps(payload_json, ensure_ascii=False)
                model_used = str(payload_json.get("model") or llm_model)
                token_used = int(
                    (payload_json.get("usage") or {}).get("total_tokens") or 0
                )
                content = (
                    ((payload_json.get("choices") or [{}])[0]).get("message") or {}
                ).get("content") or ""
                text = str(content or "")
                fence = __import__("re").search(r"```(?:json)?\s*([\s\S]*?)```", text)
                if fence:
                    text = fence.group(1).strip()
                match = __import__("re").search(r"\{[\s\S]*\}", text)
                if match:
                    text = match.group(0)
                parsed = json.loads(text)
                if str(parsed.get("decision") or "") not in {
                    "approve",
                    "reject",
                    "manual_review",
                }:
                    raise ValueError("invalid decision")
            success = True
        except Exception as exc:
            success = False
            if latency_ms is None:
                latency_ms = max(
                    0,
                    int((datetime.now(timezone.utc) - start_at).total_seconds() * 1000),
                )
            error_type = "request_error"
            error_message = str(exc)
            parsed = {
                "decision": "manual_review",
                "confidence": 0,
                "reason": "parse failed, manual review required",
                "suggestions": "",
                "user_feedback": "",
            }

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            """
            INSERT INTO ai_api_call_logs (
                source_type, source_id, source_site,
                api_config_id, api_config_name, api_model,
                request_prompt, request_payload_json,
                response_raw, response_decision, response_confidence, response_reason,
                latency_ms, token_used,
                error_type, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.source_type or "image_review").strip().lower()
                or "image_review",
                str(payload.source_id or "").strip() or None,
                str(payload.source_site or "").strip() or None,
                api_config_id,
                str(config.get("name") or "").strip() or None,
                model_used,
                prompt,
                json.dumps(request_payload, ensure_ascii=False)
                if request_payload
                else None,
                response_raw or None,
                str((parsed or {}).get("decision") or "manual_review"),
                float((parsed or {}).get("confidence") or 0),
                str((parsed or {}).get("reason") or ""),
                latency_ms,
                token_used,
                error_type,
                error_message,
                now_ms,
            ),
        )
        conn.commit()
        return {
            "success": success,
            "api_config_id": api_config_id,
            "api_config_name": str(config.get("name") or ""),
            "decision": str((parsed or {}).get("decision") or "manual_review"),
            "confidence": float((parsed or {}).get("confidence") or 0),
            "reason": str((parsed or {}).get("reason") or ""),
            "suggestions": str((parsed or {}).get("suggestions") or ""),
            "user_feedback": str((parsed or {}).get("user_feedback") or ""),
            "model": model_used,
            "latency_ms": latency_ms,
            "token_used": token_used,
            "error_type": error_type,
            "error_message": error_message,
            "response_raw": response_raw or None,
        }
    finally:
        conn.close()


@router.post("/api/internal/store/ai/run-capability")
async def run_store_capability(
    payload: InternalCapabilityRunPayload,
    request: Request,
):
    auth_error = _check_internal_auth(request)
    if auth_error:
        return auth_error

    service = AgentRuntimeService()
    capability_key = str(payload.capabilityKey or "").strip()
    if capability_key == "shop_product_review":
        if not payload.targetId:
            return error_response("INVALID_TARGET", "商品审核必须提供 targetId", 400)
        result = await service.run_product_review(
            int(payload.targetId),
            review_config_id=(payload.context or {}).get("review_config_id"),
            trigger_source=payload.triggerSource or "internal",
            operator=payload.operator or {},
        )
        return success_response(data=result)

    if capability_key == "shop_comment_review":
        if not payload.content:
            return error_response("INVALID_CONTENT", "评论审核必须提供 content", 400)
        result = await service.run_comment_review(
            content=payload.content,
            target_id=payload.targetId or "comment-runtime",
            context=payload.context or {},
            trigger_source=payload.triggerSource or "internal",
            operator=payload.operator or {},
        )
        return success_response(data=result)

    return error_response(
        "UNSUPPORTED_CAPABILITY", f"暂不支持 capability: {capability_key}", 400
    )


@router.post("/api/internal/store/reports/generate")
async def generate_store_report(
    payload: InternalReportRunPayload,
    request: Request,
):
    auth_error = _check_internal_auth(request)
    if auth_error:
        return auth_error

    safe_type = str(payload.reportType or "daily").strip().lower()
    if safe_type not in {"daily", "weekly", "monthly"}:
        return error_response("INVALID_REPORT_TYPE", "仅支持 daily/weekly/monthly", 400)

    result = AgentRuntimeService().create_report_run(
        safe_type,
        payload=payload.payload or {},
        trigger_source=payload.triggerSource or "internal",
        operator=payload.operator or {},
    )
    return success_response(data=result, status_code=202)


@router.post("/api/internal/tg-bot/review-action")
async def legacy_tg_bot_review_action(
    payload: LegacyTgReviewActionPayload,
    request: Request,
):
    auth_error = _check_specific_internal_auth(
        request,
        _tg_bot_internal_token(),
        "服务端未配置 TG 内部鉴权密钥",
    )
    if auth_error:
        return auth_error

    target_type = _normalize_tg_target_type(payload.targetType or payload.target)
    if payload.targetId <= 0 or not target_type:
        return error_response("INVALID_PARAMS", "targetType 或 targetId 无效", 400)
    action = str(payload.action or "").strip().lower()
    if action not in {"approve", "reject"}:
        return error_response("INVALID_PARAMS", "action 必须为 approve 或 reject", 400)

    reviewer_name = _build_tg_reviewer_name(payload.operator)
    reason = str(payload.reason or "").strip() or (
        "TG Bot 快捷审批通过" if action == "approve" else "TG Bot 快捷审批拒绝"
    )
    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if target_type == "product":
            current = conn.execute(
                "SELECT id, status FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
                (payload.targetId,),
            ).fetchone()
            if not current:
                return error_response("NOT_FOUND", "商品不存在", 404)
            next_status = (
                "manual_approved" if action == "approve" else "manual_rejected"
            )
            conn.execute(
                "UPDATE shop_products SET status = ?, reject_reason = ?, reviewed_at = ?, reviewed_by = ?, updated_at = ? WHERE id = ?",
                (
                    next_status,
                    reason if action == "reject" else None,
                    now_ms,
                    reviewer_name,
                    now_ms,
                    payload.targetId,
                ),
            )
            conn.execute(
                "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (payload.targetId, action, reviewer_name, reason or None, now_ms),
            )
            conn.commit()
            return success_response(
                data={"product_id": payload.targetId, "status": next_status}
            )

        if target_type == "comment":
            current = conn.execute(
                "SELECT id FROM shop_product_comments WHERE id = ? LIMIT 1",
                (payload.targetId,),
            ).fetchone()
            if not current:
                return error_response("NOT_FOUND", "评论不存在", 404)
            next_status = (
                "manual_approved" if action == "approve" else "manual_rejected"
            )
            conn.execute(
                "UPDATE shop_product_comments SET status = ?, manual_reason = ?, manual_reviewer = ?, manual_reviewed_at = ?, updated_at = ? WHERE id = ?",
                (
                    next_status,
                    reason,
                    reviewer_name,
                    now_ms,
                    now_ms,
                    payload.targetId,
                ),
            )
            conn.commit()
            return success_response(
                data={"comment_id": payload.targetId, "status": next_status}
            )

        current = conn.execute(
            "SELECT id FROM shop_buy_requests WHERE id = ? LIMIT 1", (payload.targetId,)
        ).fetchone()
        if not current:
            return error_response("NOT_FOUND", "求购记录不存在", 404)
        next_status = "open" if action == "approve" else "blocked"
        conn.execute(
            "UPDATE shop_buy_requests SET status = ?, updated_at = ? WHERE id = ?",
            (next_status, now_ms, payload.targetId),
        )
        conn.commit()
        return success_response(
            data={
                "request_id": payload.targetId,
                "status": next_status,
                "reviewer": reviewer_name,
                "reason": reason,
            }
        )
    finally:
        conn.close()


@router.post("/api/internal/ai-review/api-configs/{config_id}/invoke")
async def legacy_invoke_ai_api_config(
    config_id: int,
    payload: LegacyImageApiInvokePayload,
    request: Request,
):
    auth_error = _check_internal_auth(request)
    if auth_error:
        return auth_error
    if config_id <= 0:
        return error_response("INVALID_PARAMS", "api config id 无效", 400)
    try:
        result = await _invoke_legacy_api_config(config_id, payload)
        return success_response(data=result)
    except ValueError as exc:
        return error_response("REVIEW_FAILED", str(exc), 400)
    except Exception as exc:
        return error_response("REVIEW_FAILED", str(exc), 500)


@router.post("/api/internal/agents/{agent_key}/run")
async def legacy_internal_agent_run(
    agent_key: str,
    payload: LegacyInternalAgentRunPayload,
    request: Request,
):
    auth_error = _check_internal_auth(request)
    if auth_error:
        return auth_error

    normalized_agent_key = str(agent_key or "").strip().lower()
    if not normalized_agent_key:
        return error_response("INVALID_PARAMS", "agentKey 无效", 400)

    conn = _db()
    try:
        entry = conn.execute(
            "SELECT id FROM agent_definitions WHERE agent_key = ? LIMIT 1",
            (normalized_agent_key,),
        ).fetchone()
        if not entry:
            now = int(datetime.now(timezone.utc).timestamp() * 1000)
            created = conn.execute(
                "INSERT INTO agent_definitions (agent_key, name, description, domain, status, owner_team, created_at, updated_at) VALUES (?, ?, ?, 'shop', 'draft', 'agent-core', ?, ?)",
                (
                    normalized_agent_key,
                    normalized_agent_key.replace("_", " ").title() or "Agent",
                    "自动创建的 Agent 定义",
                    now,
                    now,
                ),
            )
            agent_id = int(created.lastrowid or 0)
            conn.execute(
                "INSERT INTO agent_versions (agent_id, version, runtime_config_json, release_notes, is_current, is_candidate, created_at, updated_at) VALUES (?, 'v1', ?, '自动创建初始版本', 1, 0, ?, ?)",
                (
                    agent_id,
                    json.dumps({"source": "legacy_internal_run"}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
            entry = conn.execute(
                "SELECT id FROM agent_definitions WHERE agent_key = ? LIMIT 1",
                (normalized_agent_key,),
            ).fetchone()

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        run_id = (
            f"arun_{normalized_agent_key}_{now_ms}"
            if normalized_agent_key
            else f"arun_{now_ms}"
        )
        mode = str(payload.mode or "prod").strip().lower() or "prod"
        status = str(payload.status or "queued").strip().lower() or "queued"
        trigger_source = (
            str(payload.triggerSource or "external_event").strip() or "external_event"
        )
        decision = (
            str(
                payload.decision
                or ("" if status in {"queued", "running"} else "approve")
            ).strip()
            or None
        )
        decision_source = str(payload.decisionSource or "agent_runtime").strip() or None
        started_at = int(payload.startedAt or now_ms)
        ended_at = int(payload.endedAt or 0) or None
        if status not in {"queued", "running"} and ended_at is None:
            ended_at = started_at + int(payload.latencyMs or 0)
        input_json = json.dumps(
            payload.input or {"text": payload.inputText or "Agent 生产输入样例"},
            ensure_ascii=False,
        )
        output_json = json.dumps(
            payload.output
            or {
                "decision": decision,
                "decision_source": decision_source,
                "confidence": payload.confidence,
                "reason": payload.reason,
            },
            ensure_ascii=False,
        )
        trace_json = json.dumps(payload.trace or {}, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO agent_runs (
                run_id, agent_id, agent_key, agent_version, trigger_source, mode, status,
                input_json, output_json, trace_json, error_type, error_message,
                decision, decision_source, latency_ms, token_used, cost_micros, risk_score,
                operator_id, operator_name, started_at, ended_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'v1', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                int(entry["id"]),
                normalized_agent_key,
                trigger_source,
                mode,
                status,
                input_json,
                output_json,
                trace_json,
                str(payload.errorType or "").strip() or None,
                str(payload.errorMessage or "").strip() or None,
                decision,
                decision_source,
                int(payload.latencyMs or 0),
                int(payload.tokenUsed or 0),
                int(payload.costMicros or 0),
                float(payload.riskScore or 0),
                str(payload.operatorId or "internal").strip() or "internal",
                str(payload.operatorName or "InternalAgentReporter").strip()
                or "InternalAgentReporter",
                started_at,
                ended_at,
                now_ms,
                now_ms,
            ),
        )
        if isinstance(payload.steps, list):
            for index, step in enumerate(payload.steps, start=1):
                step = step if isinstance(step, dict) else {}
                conn.execute(
                    """
                    INSERT INTO agent_run_steps (
                        run_id, step_index, step_type, step_name, status,
                        input_json, output_json, error_type, error_message,
                        latency_ms, tool_name, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        index,
                        str(step.get("stepType") or step.get("type") or "step"),
                        str(
                            step.get("stepName") or step.get("name") or f"Step {index}"
                        ),
                        str(step.get("status") or "success"),
                        json.dumps(step.get("input"), ensure_ascii=False)
                        if step.get("input") is not None
                        else None,
                        json.dumps(step.get("output"), ensure_ascii=False)
                        if step.get("output") is not None
                        else None,
                        str(step.get("errorType") or "").strip() or None,
                        str(step.get("errorMessage") or "").strip() or None,
                        int(step.get("latencyMs") or step.get("latency") or 0),
                        str(step.get("toolName") or "").strip() or None,
                        now_ms,
                    ),
                )
        conn.commit()
        return success_response(
            data={
                "runId": run_id,
                "agentKey": normalized_agent_key,
                "agentVersion": "v1",
                "mode": mode,
                "status": status,
                "decision": decision,
                "replaySourceRunId": "",
                "replaySourceAgentKey": "",
                "steps": len(payload.steps or []),
                "message": "运行记录已创建",
            },
            status_code=201,
        )
    except Exception as exc:
        return error_response("CREATE_FAILED", str(exc), 500)
    finally:
        conn.close()
