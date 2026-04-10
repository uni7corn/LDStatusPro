"""LD Store agent management routes - admin endpoints."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user
from app.domains.store.services.ai_capability_service import AICapabilityService

router = APIRouter(prefix="/api/admin/agents", tags=["store-admin-agents"])

AGENT_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
RUN_MODE_SET = {"test", "shadow", "prod", "replay"}
RUN_STATUS_SET = {"queued", "success", "failed", "fallback", "running", "cancelled"}
EVAL_MODE_SET = {"offline", "shadow", "online"}
EVAL_STATUS_SET = {"queued", "running", "success", "failed", "cancelled"}
EVAL_TEMPLATE_PROFILE_SET = {"standard", "high_risk", "borderline"}
EVAL_DECISION_SET = {"approve", "reject", "manual_review"}
AGENT_STATUS_SET = {"active", "draft", "disabled"}
RELEASE_TYPE_SET = {"canary", "full", "rollback"}
RELEASE_STATUS_SET = {
    "pending_approval",
    "approved",
    "rejected",
    "executed",
    "blocked",
    "cancelled",
}
DEFAULT_SHADOW_READINESS_AGENT_KEYS = ["buy_request_review", "buy_chat_patrol"]
DEFAULT_SHADOW_READINESS_CONFIG_KEY = "default"
DEFAULT_AGENT_SEEDS = [
    (
        "shop_product_review",
        "商品审核 Agent",
        "商品发布和编辑内容审核",
        "shop",
        "active",
    ),
    ("shop_comment_review", "评论审核 Agent", "评论与回复审核", "shop", "active"),
    ("image_review", "图片审核 Agent", "图片内容审核与兜底", "shop", "active"),
    ("buy_request_review", "求购信息巡查 Agent", "求购信息审核与巡查", "shop", "draft"),
    ("buy_chat_patrol", "求购聊天巡查 Agent", "求购聊天风险巡查", "shop", "draft"),
    ("ops_copilot", "运营分析 Copilot Agent", "运营数据分析和决策建议", "ops", "draft"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db() -> sqlite3.Connection:
    """Return a sqlite3 connection to the store database."""
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _page_params(page: int = 1, size: int = 20) -> tuple[int, int]:
    page = max(1, page)
    size = max(1, min(size, 100))
    return (page - 1) * size, size


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _safe_text(value: Any, max_length: int = 0) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if max_length > 0 and len(text) > max_length:
        return text[:max_length]
    return text


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except Exception:
        return fallback


def _safe_number(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except Exception:
        return fallback


def _clamp_number(
    value: Any, min_value: float, max_value: float, fallback: float
) -> float:
    number = _safe_number(value, fallback)
    if number < min_value:
        return min_value
    if number > max_value:
        return max_value
    return number


def _parse_json_safe(raw: Any, fallback: Any = None) -> Any:
    if raw in (None, ""):
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _stringify_json(value: Any, fallback: str = "{}") -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return fallback


def _normalize_boolean(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = _safe_text(value, 10).lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return fallback


def _normalize_agent_key(value: Any) -> str:
    key = _safe_text(value, 80).lower()
    return key if AGENT_KEY_PATTERN.fullmatch(key) else ""


def _normalize_agent_keys(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in (_normalize_agent_key(v) for v in value) if item]
    text = _safe_text(value, 500)
    if not text:
        return []
    return [item for item in (_normalize_agent_key(v) for v in text.split(",")) if item]


def _normalize_run_mode(value: Any, fallback: str = "test") -> str:
    mode = _safe_text(value, 20).lower()
    return mode if mode in RUN_MODE_SET else fallback


def _normalize_run_status(value: Any, fallback: str = "success") -> str:
    status = _safe_text(value, 20).lower()
    return status if status in RUN_STATUS_SET else fallback


def _is_terminal_run_status(status: Any) -> bool:
    return _normalize_run_status(status, "") in {
        "success",
        "failed",
        "fallback",
        "cancelled",
    }


def _is_pending_run_status(status: Any) -> bool:
    return _normalize_run_status(status, "") in {"queued", "running"}


def _normalize_eval_mode(value: Any, fallback: str = "offline") -> str:
    mode = _safe_text(value, 20).lower()
    return mode if mode in EVAL_MODE_SET else fallback


def _normalize_eval_status(value: Any, fallback: str = "success") -> str:
    status = _safe_text(value, 20).lower()
    return status if status in EVAL_STATUS_SET else fallback


def _normalize_eval_template_profile(value: Any, fallback: str = "standard") -> str:
    profile = _safe_text(value, 20).lower()
    return profile if profile in EVAL_TEMPLATE_PROFILE_SET else fallback


def _normalize_agent_status(value: Any, fallback: str = "draft") -> str:
    status = _safe_text(value, 20).lower()
    return status if status in AGENT_STATUS_SET else fallback


def _normalize_release_type(value: Any, fallback: str = "canary") -> str:
    release_type = _safe_text(value, 20).lower()
    return release_type if release_type in RELEASE_TYPE_SET else fallback


def _normalize_release_status(value: Any, fallback: str = "pending_approval") -> str:
    status = _safe_text(value, 30).lower()
    return status if status in RELEASE_STATUS_SET else fallback


def _to_date_key(ts: Any) -> str:
    base = _safe_int(ts, _now_ms())
    return datetime.fromtimestamp(base / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _create_run_id() -> str:
    return f"arun_{uuid4().hex[:20]}"


def _create_shadow_snapshot_id() -> str:
    return f"ashadow_{uuid4().hex[:20]}"


def _create_shadow_config_log_id() -> str:
    return f"ashadowcfg_{uuid4().hex[:20]}"


def _create_release_id() -> str:
    return f"arel_{uuid4().hex[:20]}"


def _create_eval_run_id() -> str:
    return f"aeval_{uuid4().hex[:20]}"


def _create_dataset_id() -> str:
    return f"ads_{uuid4().hex[:20]}"


def _default_agent_name(agent_key: str) -> str:
    parts = [part for part in re.split(r"[._-]+", _safe_text(agent_key, 80)) if part]
    if not parts:
        return "Agent"
    return " ".join(part[:1].upper() + part[1:] for part in parts) + " Agent"


def _default_trace(
    run_id: str,
    agent_key: str,
    mode: str,
    status: str,
    decision: str,
    decision_source: str,
    confidence: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "trace_id": f"{run_id}_trace",
        "run_id": run_id,
        "agent_key": agent_key,
        "mode": mode,
        "status": status,
        "final": {
            "decision": decision,
            "decision_source": decision_source,
            "confidence": confidence,
            "reason": reason,
        },
    }


def _operator_from_user(user: dict | None) -> dict[str, str]:
    user = user or {}
    return {
        "id": _safe_text(
            user.get("id")
            or user.get("user_id")
            or user.get("admin_id")
            or user.get("sub")
            or user.get("email"),
            80,
        ),
        "name": _safe_text(
            user.get("name")
            or user.get("username")
            or user.get("nickname")
            or user.get("email")
            or "Admin",
            80,
        )
        or "Admin",
    }


def _pick_percentile(values: list[Any], percentile: float = 0.5) -> float:
    numbers = sorted(_safe_number(item, float("nan")) for item in values)
    numbers = [item for item in numbers if item == item]
    if not numbers:
        return 0.0
    p = _clamp_number(percentile, 0, 1, 0.5)
    index = min(len(numbers) - 1, max(0, int((len(numbers) - 1) * p)))
    return numbers[index]


def _build_release_action_hints(reasons: list[Any]) -> list[str]:
    hints: set[str] = set()
    for reason in reasons or []:
        text = _safe_text(reason, 200)
        if not text:
            continue
        if "样本不足" in text:
            hints.add("补充 Shadow 样本后再申请 canary")
        if "fallback" in text or "failed" in text:
            hints.add("排查失败与兜底路径，降低 fallback/failed 比例")
        if "风险命中率偏高" in text:
            hints.add("校准规则或阈值，降低高风险命中比例")
    if not hints:
        hints.add("根据阻断原因补充样本并调整规则后重试")
    return sorted(hints)


def _normalize_shadow_config_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "configKey": _safe_text(config.get("configKey"), 40)
        or DEFAULT_SHADOW_READINESS_CONFIG_KEY,
        "minShadowRuns": max(1, _safe_int(config.get("minShadowRuns"), 100)),
        "maxFlaggedRate": _clamp_number(config.get("maxFlaggedRate"), 0, 1, 0.35),
        "maxFallbackRate": _clamp_number(config.get("maxFallbackRate"), 0, 1, 0.05),
        "defaultDays": min(max(_safe_int(config.get("defaultDays"), 7), 1), 90),
        "agentKeys": _normalize_agent_keys(
            config.get("agentKeys") or config.get("agentKeysText")
        ),
        "note": _safe_text(config.get("note"), 300),
    }


def _build_shadow_config_diff(
    before_config: dict[str, Any], after_config: dict[str, Any]
) -> dict[str, Any]:
    before = _normalize_shadow_config_snapshot(before_config)
    after = _normalize_shadow_config_snapshot(after_config)
    diff: dict[str, Any] = {}
    for key in (
        "minShadowRuns",
        "maxFlaggedRate",
        "maxFallbackRate",
        "defaultDays",
        "note",
    ):
        if before.get(key) != after.get(key):
            diff[key] = {"before": before.get(key), "after": after.get(key)}
    if before.get("agentKeys") != after.get("agentKeys"):
        diff["agentKeys"] = {
            "before": before.get("agentKeys"),
            "after": after.get("agentKeys"),
        }
    return diff


def _ensure_bootstrap_definitions(conn: sqlite3.Connection) -> None:
    now = _now_ms()
    for agent_key, name, description, domain, status in DEFAULT_AGENT_SEEDS:
        existed = conn.execute(
            "SELECT id FROM agent_definitions WHERE agent_key = ? LIMIT 1",
            (agent_key,),
        ).fetchone()
        agent_id = _safe_int(existed["id"], 0) if existed else 0
        if not agent_id:
            cursor = conn.execute(
                """
                INSERT INTO agent_definitions (
                    agent_key, name, description, domain, status, owner_team, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'agent-core', ?, ?)
                """,
                (agent_key, name, description, domain, status, now, now),
            )
            agent_id = int(cursor.lastrowid or 0)
        if not agent_id:
            continue
        current = conn.execute(
            "SELECT id FROM agent_versions WHERE agent_id = ? AND is_current = 1 LIMIT 1",
            (agent_id,),
        ).fetchone()
        if current:
            continue
        latest = conn.execute(
            "SELECT id FROM agent_versions WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        if latest:
            conn.execute(
                "UPDATE agent_versions SET is_current = 1, updated_at = ? WHERE id = ?",
                (now, latest["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO agent_versions (
                    agent_id, version, runtime_config_json, release_notes, is_current, is_candidate, created_at, updated_at
                ) VALUES (?, 'v1', ?, '初始化平台化版本', 1, 0, ?, ?)
                """,
                (agent_id, _stringify_json({"source": "phase1-bootstrap"}), now, now),
            )
    conn.commit()


def _ensure_agent_entry(
    conn: sqlite3.Connection, agent_key: str
) -> dict[str, Any] | None:
    normalized_key = _normalize_agent_key(agent_key)
    if not normalized_key:
        return None
    row = conn.execute(
        """
        SELECT d.id, d.agent_key, d.name, v.version AS current_version
        FROM agent_definitions d
        LEFT JOIN agent_versions v ON v.agent_id = d.id AND v.is_current = 1
        WHERE d.agent_key = ?
        LIMIT 1
        """,
        (normalized_key,),
    ).fetchone()
    if row:
        version = _safe_text(row["current_version"], 40)
        if not version:
            now = _now_ms()
            latest = conn.execute(
                "SELECT id, version FROM agent_versions WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            if latest:
                conn.execute(
                    "UPDATE agent_versions SET is_current = 1, updated_at = ? WHERE id = ?",
                    (now, latest["id"]),
                )
                conn.commit()
                version = _safe_text(latest["version"], 40) or "v1"
            else:
                conn.execute(
                    """
                    INSERT INTO agent_versions (
                        agent_id, version, runtime_config_json, release_notes, is_current, is_candidate, created_at, updated_at
                    ) VALUES (?, 'v1', ?, '自动补齐当前版本', 1, 0, ?, ?)
                    """,
                    (
                        row["id"],
                        _stringify_json({"source": "auto-fill-current-version"}),
                        now,
                        now,
                    ),
                )
                conn.commit()
                version = "v1"
        return {
            "id": row["id"],
            "agentKey": row["agent_key"],
            "name": row["name"],
            "version": version or "v1",
        }
    now = _now_ms()
    cursor = conn.execute(
        """
        INSERT INTO agent_definitions (
            agent_key, name, description, domain, status, owner_team, created_at, updated_at
        ) VALUES (?, ?, '自动创建的 Agent 定义', 'shop', 'draft', 'agent-core', ?, ?)
        """,
        (normalized_key, _default_agent_name(normalized_key), now, now),
    )
    agent_id = int(cursor.lastrowid or 0)
    if not agent_id:
        return None
    conn.execute(
        """
        INSERT INTO agent_versions (
            agent_id, version, runtime_config_json, release_notes, is_current, is_candidate, created_at, updated_at
        ) VALUES (?, 'v1', ?, '自动创建初始版本', 1, 0, ?, ?)
        """,
        (agent_id, _stringify_json({"source": "auto-create"}), now, now),
    )
    conn.commit()
    return {
        "id": agent_id,
        "agentKey": normalized_key,
        "name": _default_agent_name(normalized_key),
        "version": "v1",
    }


def _map_run_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "runId": row["run_id"],
        "agentKey": row["agent_key"],
        "agentVersion": _safe_text(row["agent_version"], 40),
        "triggerSource": _safe_text(row["trigger_source"], 40),
        "mode": _safe_text(row["mode"], 20) or "test",
        "status": _safe_text(row["status"], 20) or "success",
        "replaySourceRunId": _safe_text(row["replay_source_run_id"], 80),
        "replaySourceAgentKey": _safe_text(row["replay_source_agent_key"], 80),
        "replayReason": _safe_text(row["replay_reason"], 300),
        "decision": _safe_text(row["decision"], 40),
        "decisionSource": _safe_text(row["decision_source"], 40),
        "errorType": _safe_text(row["error_type"], 80),
        "errorMessage": _safe_text(row["error_message"], 300),
        "latencyMs": _safe_int(row["latency_ms"], 0),
        "tokenUsed": _safe_int(row["token_used"], 0),
        "costMicros": _safe_int(row["cost_micros"], 0),
        "riskScore": _safe_number(row["risk_score"], 0),
        "operatorId": _safe_text(row["operator_id"], 80),
        "operatorName": _safe_text(row["operator_name"], 80),
        "startedAt": row["started_at"],
        "endedAt": row["ended_at"],
        "createdAt": row["created_at"],
    }


def _map_release_request_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    blocked_reasons = _parse_json_safe(row["blocked_reasons_json"], []) or []
    return {
        "releaseId": _safe_text(row["release_id"], 80),
        "agentKey": _safe_text(row["agent_key"], 80),
        "targetVersion": _safe_text(row["target_version"], 40),
        "releaseType": _normalize_release_type(row["release_type"], "canary"),
        "status": _normalize_release_status(row["status"], "pending_approval"),
        "gateRequired": _safe_int(row["gate_required"], 0) == 1,
        "gatePassed": _safe_int(row["gate_passed"], 0) == 1,
        "gateSnapshot": _parse_json_safe(row["gate_snapshot_json"], {}) or {},
        "blockedReasons": blocked_reasons if isinstance(blocked_reasons, list) else [],
        "requestNote": _safe_text(row["request_note"], 300),
        "requestMeta": _parse_json_safe(row["request_meta_json"], {}) or {},
        "requestedById": _safe_text(row["requested_by_id"], 80),
        "requestedByName": _safe_text(row["requested_by_name"], 80),
        "approvedById": _safe_text(row["approved_by_id"], 80),
        "approvedByName": _safe_text(row["approved_by_name"], 80),
        "approvalNote": _safe_text(row["approval_note"], 300),
        "executedAt": _safe_int(row["executed_at"], 0),
        "createdAt": _safe_int(row["created_at"], 0),
        "updatedAt": _safe_int(row["updated_at"], 0),
    }


def _load_release_request_row(
    conn: sqlite3.Connection, release_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            release_id,
            agent_key,
            target_version,
            release_type,
            status,
            gate_required,
            gate_passed,
            gate_snapshot_json,
            blocked_reasons_json,
            request_note,
            request_meta_json,
            requested_by_id,
            requested_by_name,
            approved_by_id,
            approved_by_name,
            approval_note,
            executed_at,
            created_at,
            updated_at
        FROM agent_release_requests
        WHERE release_id = ?
        LIMIT 1
        """,
        (release_id,),
    ).fetchone()


def _load_shadow_readiness_config_data(conn: sqlite3.Connection) -> dict[str, Any]:
    defaults = {
        "configKey": DEFAULT_SHADOW_READINESS_CONFIG_KEY,
        "minShadowRuns": 100,
        "maxFlaggedRate": 0.35,
        "maxFallbackRate": 0.05,
        "defaultDays": 7,
        "agentKeys": list(DEFAULT_SHADOW_READINESS_AGENT_KEYS),
        "note": "",
        "operatorId": "",
        "operatorName": "",
        "createdAt": 0,
        "updatedAt": 0,
    }
    row = conn.execute(
        """
        SELECT
            config_key,
            min_shadow_runs,
            max_flagged_rate,
            max_fallback_rate,
            default_days,
            agent_keys_json,
            note,
            operator_id,
            operator_name,
            created_at,
            updated_at
        FROM agent_shadow_readiness_configs
        WHERE config_key = ?
        LIMIT 1
        """,
        (DEFAULT_SHADOW_READINESS_CONFIG_KEY,),
    ).fetchone()
    if row is None:
        now = _now_ms()
        conn.execute(
            """
            INSERT INTO agent_shadow_readiness_configs (
                config_key,
                min_shadow_runs,
                max_flagged_rate,
                max_fallback_rate,
                default_days,
                agent_keys_json,
                note,
                operator_id,
                operator_name,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_SHADOW_READINESS_CONFIG_KEY,
                defaults["minShadowRuns"],
                defaults["maxFlaggedRate"],
                defaults["maxFallbackRate"],
                defaults["defaultDays"],
                _stringify_json(defaults["agentKeys"], "[]"),
                defaults["note"],
                defaults["operatorId"],
                defaults["operatorName"],
                now,
                now,
            ),
        )
        conn.commit()
        defaults["createdAt"] = now
        defaults["updatedAt"] = now
        return defaults
    parsed_keys = _normalize_agent_keys(_parse_json_safe(row["agent_keys_json"], []))
    return {
        "configKey": _safe_text(row["config_key"], 40)
        or DEFAULT_SHADOW_READINESS_CONFIG_KEY,
        "minShadowRuns": max(
            1, _safe_int(row["min_shadow_runs"], defaults["minShadowRuns"])
        ),
        "maxFlaggedRate": _clamp_number(
            row["max_flagged_rate"], 0, 1, defaults["maxFlaggedRate"]
        ),
        "maxFallbackRate": _clamp_number(
            row["max_fallback_rate"], 0, 1, defaults["maxFallbackRate"]
        ),
        "defaultDays": min(
            max(_safe_int(row["default_days"], defaults["defaultDays"]), 1), 90
        ),
        "agentKeys": parsed_keys or list(DEFAULT_SHADOW_READINESS_AGENT_KEYS),
        "note": _safe_text(row["note"], 300),
        "operatorId": _safe_text(row["operator_id"], 80),
        "operatorName": _safe_text(row["operator_name"], 80),
        "createdAt": _safe_int(row["created_at"], 0),
        "updatedAt": _safe_int(row["updated_at"], 0),
    }


def _build_shadow_readiness_data(
    conn: sqlite3.Connection, options: dict[str, Any]
) -> dict[str, Any]:
    config = _load_shadow_readiness_config_data(conn)
    days = min(max(_safe_int(options.get("days"), config["defaultDays"]), 1), 90)
    since = _now_ms() - days * 24 * 60 * 60 * 1000
    candidate_keys = _normalize_agent_keys(options.get("agentKeys"))
    effective_agent_keys = (
        candidate_keys
        or config["agentKeys"]
        or list(DEFAULT_SHADOW_READINESS_AGENT_KEYS)
    )
    min_shadow_runs = max(
        1, _safe_int(options.get("minShadowRuns"), config["minShadowRuns"])
    )
    max_flagged_rate = _clamp_number(
        options.get("maxFlaggedRate"), 0, 1, config["maxFlaggedRate"]
    )
    max_fallback_rate = _clamp_number(
        options.get("maxFallbackRate"), 0, 1, config["maxFallbackRate"]
    )
    items: list[dict[str, Any]] = []
    for agent_key in effective_agent_keys:
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            continue
        summary = conn.execute(
            """
            SELECT
                COUNT(1) AS run_count,
                SUM(CASE WHEN mode = 'shadow' THEN 1 ELSE 0 END) AS shadow_run_count,
                SUM(CASE WHEN mode = 'shadow' AND decision <> 'approve' THEN 1 ELSE 0 END) AS shadow_flagged_count,
                SUM(CASE WHEN mode = 'shadow' AND status = 'fallback' THEN 1 ELSE 0 END) AS shadow_fallback_count,
                SUM(CASE WHEN mode = 'shadow' AND status = 'failed' THEN 1 ELSE 0 END) AS shadow_failed_count,
                SUM(CASE WHEN mode = 'shadow' AND decision = 'manual_review' THEN 1 ELSE 0 END) AS shadow_manual_review_count,
                SUM(CASE WHEN mode = 'shadow' AND decision = 'reject' THEN 1 ELSE 0 END) AS shadow_reject_count
            FROM agent_runs
            WHERE agent_key = ? AND started_at >= ?
            """,
            (normalized_key, since),
        ).fetchone()
        agent_info = conn.execute(
            "SELECT agent_key, name, status FROM agent_definitions WHERE agent_key = ? LIMIT 1",
            (normalized_key,),
        ).fetchone()
        shadow_rule_rows = conn.execute(
            """
            SELECT output_json, trace_json
            FROM agent_runs
            WHERE agent_key = ? AND started_at >= ? AND mode = 'shadow'
            ORDER BY started_at DESC
            LIMIT 1000
            """,
            (normalized_key, since),
        ).fetchall()
        shadow_rule_map: dict[str, int] = {}
        for row in shadow_rule_rows:
            output = _parse_json_safe(row["output_json"], None)
            trace = _parse_json_safe(row["trace_json"], None)
            rule = (
                _safe_text((output or {}).get("rule") or (trace or {}).get("rule"), 100)
                or "unknown"
            )
            shadow_rule_map[rule] = shadow_rule_map.get(rule, 0) + 1
        top_rules = [
            {"rule": rule, "runCount": count}
            for rule, count in sorted(
                shadow_rule_map.items(), key=lambda item: (-item[1], item[0])
            )[:5]
        ]
        total_runs = _safe_int(summary["run_count"] if summary else 0, 0)
        shadow_runs = _safe_int(summary["shadow_run_count"] if summary else 0, 0)
        flagged_runs = _safe_int(summary["shadow_flagged_count"] if summary else 0, 0)
        fallback_runs = _safe_int(summary["shadow_fallback_count"] if summary else 0, 0)
        failed_runs = _safe_int(summary["shadow_failed_count"] if summary else 0, 0)
        manual_review_runs = _safe_int(
            summary["shadow_manual_review_count"] if summary else 0, 0
        )
        reject_runs = _safe_int(summary["shadow_reject_count"] if summary else 0, 0)
        flagged_rate = round(flagged_runs / shadow_runs, 4) if shadow_runs > 0 else 0
        fallback_rate = round(fallback_runs / shadow_runs, 4) if shadow_runs > 0 else 0
        failed_rate = round(failed_runs / shadow_runs, 4) if shadow_runs > 0 else 0
        manual_review_rate = (
            round(manual_review_runs / shadow_runs, 4) if shadow_runs > 0 else 0
        )
        reject_rate = round(reject_runs / shadow_runs, 4) if shadow_runs > 0 else 0
        has_enough_shadow_samples = shadow_runs >= min_shadow_runs
        fallback_healthy = (
            fallback_rate <= max_fallback_rate and failed_rate <= max_fallback_rate
        )
        flagged_healthy = flagged_rate <= max_flagged_rate
        canary_ready = (
            has_enough_shadow_samples and fallback_healthy and flagged_healthy
        )
        status = "fail"
        recommendation = "继续 shadow 采样，暂不建议 canary"
        if canary_ready:
            status = "pass"
            recommendation = "满足准入阈值，建议进入小流量 canary"
        elif has_enough_shadow_samples or fallback_healthy or flagged_healthy:
            status = "warn"
            recommendation = "部分指标达标，建议先优化阈值/规则后再 canary"
        reasons: list[str] = []
        if not has_enough_shadow_samples:
            reasons.append(f"shadow 样本不足：{shadow_runs}/{min_shadow_runs}")
        if not fallback_healthy:
            reasons.append(
                f"fallback/failed 率偏高（fallback={(fallback_rate * 100):.2f}%，failed={(failed_rate * 100):.2f}%）"
            )
        if not flagged_healthy:
            reasons.append(f"风险命中率偏高（{(flagged_rate * 100):.2f}%）")
        if not reasons:
            reasons.append("关键指标满足阈值")
        items.append(
            {
                "agentKey": normalized_key,
                "agentName": _safe_text(agent_info["name"], 100)
                if agent_info
                else _default_agent_name(normalized_key),
                "agentStatus": _safe_text(agent_info["status"], 20)
                if agent_info
                else "draft",
                "totalRuns": total_runs,
                "shadowRuns": shadow_runs,
                "flaggedRuns": flagged_runs,
                "fallbackRuns": fallback_runs,
                "failedRuns": failed_runs,
                "manualReviewRuns": manual_review_runs,
                "rejectRuns": reject_runs,
                "flaggedRate": flagged_rate,
                "fallbackRate": fallback_rate,
                "failedRate": failed_rate,
                "manualReviewRate": manual_review_rate,
                "rejectRate": reject_rate,
                "topRules": top_rules,
                "readiness": {
                    "status": status,
                    "canaryReady": canary_ready,
                    "hasEnoughShadowSamples": has_enough_shadow_samples,
                    "fallbackHealthy": fallback_healthy,
                    "flaggedHealthy": flagged_healthy,
                    "recommendation": recommendation,
                    "reasons": reasons,
                },
            }
        )
    pass_count = sum(1 for item in items if item["readiness"]["status"] == "pass")
    warn_count = sum(1 for item in items if item["readiness"]["status"] == "warn")
    fail_count = sum(1 for item in items if item["readiness"]["status"] == "fail")
    return {
        "days": days,
        "thresholds": {
            "minShadowRuns": min_shadow_runs,
            "maxFlaggedRate": max_flagged_rate,
            "maxFallbackRate": max_fallback_rate,
        },
        "config": {
            "configKey": config["configKey"],
            "defaultDays": config["defaultDays"],
            "agentKeys": config["agentKeys"],
            "note": config["note"],
            "updatedAt": config["updatedAt"],
            "operatorName": config["operatorName"],
        },
        "summary": {
            "totalAgents": len(items),
            "passCount": pass_count,
            "warnCount": warn_count,
            "failCount": fail_count,
        },
        "items": items,
    }


def _evaluate_release_gate(
    conn: sqlite3.Connection, agent_key: str, release_type: str, options: dict[str, Any]
) -> dict[str, Any]:
    normalized_agent_key = _normalize_agent_key(agent_key)
    normalized_type = _normalize_release_type(release_type, "canary")
    evaluated_at = _now_ms()
    if normalized_type != "canary":
        return {
            "gateRequired": False,
            "gatePassed": True,
            "blockedItems": [],
            "reason": "非 canary 发布，无需 Shadow 准入门禁",
            "snapshot": {"evaluatedAt": evaluated_at, "releaseType": normalized_type},
        }
    config = _load_shadow_readiness_config_data(conn)
    gate_agent_keys = _normalize_agent_keys(config["agentKeys"]) or list(
        DEFAULT_SHADOW_READINESS_AGENT_KEYS
    )
    gate_required = normalized_agent_key in gate_agent_keys
    if not gate_required:
        return {
            "gateRequired": False,
            "gatePassed": True,
            "blockedItems": [],
            "reason": "该 Agent 不在 Shadow 门禁名单内",
            "snapshot": {
                "evaluatedAt": evaluated_at,
                "releaseType": normalized_type,
                "gateAgentKeys": gate_agent_keys,
            },
        }
    data = _build_shadow_readiness_data(
        conn,
        {
            "days": min(
                max(_safe_int(options.get("days"), config["defaultDays"]), 1), 90
            ),
            "agentKeys": gate_agent_keys,
        },
    )
    items = data.get("items") or []
    blocked_items = [
        {
            "agentKey": item.get("agentKey") or "",
            "agentName": item.get("agentName") or "",
            "status": ((item.get("readiness") or {}).get("status") or "fail"),
            "reasons": ((item.get("readiness") or {}).get("reasons") or []),
            "actionHints": _build_release_action_hints(
                ((item.get("readiness") or {}).get("reasons") or [])
            ),
            "recommendation": (
                (item.get("readiness") or {}).get("recommendation") or ""
            ),
        }
        for item in items
        if ((item.get("readiness") or {}).get("canaryReady") is not True)
    ]
    gate_passed = bool(items) and not blocked_items
    return {
        "gateRequired": True,
        "gatePassed": gate_passed,
        "blockedItems": blocked_items,
        "reason": "门禁通过，可执行 canary 发布"
        if gate_passed
        else "门禁阻断：仍有 Agent 未达标",
        "snapshot": {
            "evaluatedAt": evaluated_at,
            "releaseType": normalized_type,
            "days": data.get("days", 7),
            "gateAgentKeys": gate_agent_keys,
            "thresholds": data.get("thresholds") or {},
            "summary": data.get("summary") or {},
            "blockedItems": blocked_items,
        },
    }


def _normalize_steps(
    step_list: list[Any] | None, context: dict[str, Any]
) -> list[dict[str, Any]]:
    if not step_list:
        failed = context.get("status") == "failed"
        fallback = context.get("status") == "fallback"
        queued = context.get("status") == "queued"
        running = context.get("status") == "running"
        return [
            {
                "index": 1,
                "type": "prepare",
                "name": "准备输入",
                "status": "queued" if queued else ("running" if running else "success"),
                "input": {"mode": context.get("mode") or "test"},
                "output": {"queued": True}
                if queued
                else ({"started": True} if running else {"ok": True}),
                "errorType": "",
                "errorMessage": "",
                "latency": 0 if queued else 20,
                "toolName": "",
            },
            {
                "index": 2,
                "type": "inference",
                "name": "模型推理",
                "status": "queued"
                if queued
                else ("running" if running else ("failed" if failed else "success")),
                "input": {
                    "decision_source": context.get("decisionSource") or "manual_test"
                },
                "output": {"queued": True}
                if queued
                else (
                    {"started": True}
                    if running
                    else (
                        None
                        if failed
                        else {"decision": context.get("decision") or "approve"}
                    )
                ),
                "errorType": context.get("errorType")
                or ("manual_test_failed" if failed else ""),
                "errorMessage": context.get("errorMessage")
                or ("测试推理失败" if failed else ""),
                "latency": 0 if queued else 120,
                "toolName": "llm",
            },
            {
                "index": 3,
                "type": "postprocess",
                "name": "结果处理",
                "status": "queued"
                if queued
                else (
                    "running"
                    if running
                    else (
                        "failed" if failed else ("fallback" if fallback else "success")
                    )
                ),
                "input": {"status": context.get("status") or "success"},
                "output": {"status": "queued"}
                if queued
                else (
                    {"status": "running"}
                    if running
                    else {
                        "status": "failed"
                        if failed
                        else ("fallback" if fallback else "success")
                    }
                ),
                "errorType": context.get("errorType") or "",
                "errorMessage": context.get("errorMessage") or "",
                "latency": 0 if queued else 40,
                "toolName": "",
            },
        ]
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(step_list[:20], start=1):
        step = item if isinstance(item, dict) else {}
        normalized.append(
            {
                "index": idx,
                "type": _safe_text(
                    step.get("stepType") or step.get("step_type") or step.get("type"),
                    40,
                )
                or "step",
                "name": _safe_text(
                    step.get("stepName") or step.get("step_name") or step.get("name"),
                    100,
                )
                or f"步骤 {idx}",
                "status": _normalize_run_status(step.get("status"), "success"),
                "input": step.get("input")
                if isinstance(step.get("input"), dict)
                else None,
                "output": step.get("output")
                if isinstance(step.get("output"), dict)
                else None,
                "errorType": _safe_text(
                    step.get("errorType") or step.get("error_type"), 80
                ),
                "errorMessage": _safe_text(
                    step.get("errorMessage") or step.get("error_message"), 300
                ),
                "latency": max(
                    _safe_int(step.get("latencyMs") or step.get("latency_ms"), 0), 0
                ),
                "toolName": _safe_text(
                    step.get("toolName") or step.get("tool_name"), 80
                ),
            }
        )
    return normalized


def _upsert_daily_metric(
    conn: sqlite3.Connection,
    metric_date: str,
    agent_key: str,
    mode: str,
    status: str,
    decision: str,
    latency_ms: int,
    token_used: int,
    cost_micros: int,
    now: int,
) -> None:
    normalized_status = _normalize_run_status(status, "success")
    conn.execute(
        """
        INSERT INTO agent_metrics_daily (
            metric_date, agent_key, mode, run_count, success_count, failed_count,
            fallback_count, manual_review_count, avg_latency_ms, p95_latency_ms,
            token_used_total, cost_micros_total, updated_at
        ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        ON CONFLICT(metric_date, agent_key, mode) DO UPDATE SET
            run_count = agent_metrics_daily.run_count + 1,
            success_count = agent_metrics_daily.success_count + excluded.success_count,
            failed_count = agent_metrics_daily.failed_count + excluded.failed_count,
            fallback_count = agent_metrics_daily.fallback_count + excluded.fallback_count,
            manual_review_count = agent_metrics_daily.manual_review_count + excluded.manual_review_count,
            avg_latency_ms = ((COALESCE(agent_metrics_daily.avg_latency_ms, 0) * agent_metrics_daily.run_count + excluded.avg_latency_ms) / NULLIF(agent_metrics_daily.run_count + 1, 0)),
            token_used_total = agent_metrics_daily.token_used_total + excluded.token_used_total,
            cost_micros_total = agent_metrics_daily.cost_micros_total + excluded.cost_micros_total,
            updated_at = excluded.updated_at
        """,
        (
            metric_date,
            agent_key,
            mode,
            1 if normalized_status == "success" else 0,
            1 if normalized_status == "failed" else 0,
            1 if normalized_status == "fallback" else 0,
            1 if _safe_text(decision, 40) == "manual_review" else 0,
            latency_ms,
            token_used,
            cost_micros,
            now,
        ),
    )


def _create_run_record(
    conn: sqlite3.Connection,
    agent_key: str,
    payload: dict[str, Any],
    operator: dict[str, str],
    options: dict[str, Any],
) -> dict[str, Any]:
    _ensure_bootstrap_definitions(conn)
    entry = _ensure_agent_entry(conn, agent_key)
    if not entry:
        raise ValueError("无法创建 Agent 定义")
    now = _now_ms()
    run_id = _create_run_id()
    mode = _normalize_run_mode(
        payload.get("mode"), options.get("defaultMode") or "test"
    )
    status = _normalize_run_status(payload.get("status"), "success")
    trigger_source = (
        _safe_text(payload.get("triggerSource"), 40)
        or _safe_text(options.get("defaultTriggerSource"), 40)
        or "admin_test"
    )
    decision = _safe_text(payload.get("decision"), 40) or (
        "manual_review"
        if status == "failed"
        else ("" if _is_pending_run_status(status) else "approve")
    )
    decision_source = (
        _safe_text(payload.get("decisionSource"), 40)
        or _safe_text(options.get("defaultDecisionSource"), 40)
        or "manual_test"
    )
    confidence = _clamp_number(
        payload.get("confidence"), 0, 1, 0.25 if status == "failed" else 0.9
    )
    reason = _safe_text(payload.get("reason"), 300)
    if not reason:
        if status == "failed":
            reason = _safe_text(options.get("defaultFailedReason"), 300) or "运行失败"
        elif status == "queued":
            reason = "任务已加入队列"
        elif status == "running":
            reason = "任务执行中"
        else:
            reason = _safe_text(options.get("defaultSuccessReason"), 300) or "运行通过"
    risk_score = _clamp_number(
        payload.get("riskScore"),
        0,
        1,
        0 if _is_pending_run_status(status) else (0.8 if status == "failed" else 0.1),
    )
    token_used = max(
        _safe_int(
            payload.get("tokenUsed"),
            0 if status == "failed" or _is_pending_run_status(status) else 600,
        ),
        0,
    )
    cost_micros = max(_safe_int(payload.get("costMicros"), token_used * 3), 0)
    started_at = max(_safe_int(payload.get("startedAt"), now), 0)
    latency_ms = max(
        _safe_int(
            payload.get("latencyMs"),
            240
            if status == "failed"
            else (0 if _is_pending_run_status(status) else 180),
        ),
        0,
    )
    ended_at = _safe_int(payload.get("endedAt"), 0)
    if ended_at <= 0:
        ended_at = 0 if _is_pending_run_status(status) else started_at + latency_ms
    if ended_at > 0 and ended_at < started_at:
        ended_at = started_at
    error_type = ""
    error_message = ""
    if status in {"failed", "fallback"}:
        error_type = _safe_text(payload.get("errorType"), 80) or (
            "fallback_triggered" if status == "fallback" else "manual_test_failed"
        )
        error_message = _safe_text(payload.get("errorMessage"), 300) or (
            "测试触发兜底" if status == "fallback" else "测试运行失败"
        )
    input_value = (
        payload.get("input")
        if isinstance(payload.get("input"), dict)
        else {
            "text": _safe_text(payload.get("inputText"), 300)
            or _safe_text(options.get("defaultInputText"), 300)
            or "Agent 输入样例"
        }
    )
    output_value = (
        payload.get("output")
        if isinstance(payload.get("output"), dict)
        else {
            "decision": decision,
            "decision_source": decision_source,
            "confidence": confidence,
            "reason": reason,
        }
    )
    replay_source_run_id = _safe_text(
        payload.get("replaySourceRunId") or payload.get("sourceRunId"), 80
    )
    replay_source_agent_key = _normalize_agent_key(
        payload.get("replaySourceAgentKey") or payload.get("sourceAgentKey")
    )
    replay_reason = _safe_text(payload.get("replayReason"), 300)
    trace_value = (
        payload.get("trace")
        if isinstance(payload.get("trace"), dict)
        else _default_trace(
            run_id,
            entry["agentKey"],
            mode,
            status,
            decision,
            decision_source,
            confidence,
            reason,
        )
    )
    if replay_source_run_id:
        replay = (
            trace_value.get("replay")
            if isinstance(trace_value.get("replay"), dict)
            else {}
        )
        trace_value["replay"] = {
            **replay,
            "source_run_id": replay_source_run_id,
            "source_agent_key": replay_source_agent_key or entry["agentKey"],
            "reason": replay_reason or _safe_text(replay.get("reason"), 300),
        }
    steps = _normalize_steps(
        payload.get("steps") if isinstance(payload.get("steps"), list) else None,
        {
            "mode": mode,
            "status": status,
            "decision": decision,
            "decisionSource": decision_source,
            "errorType": error_type,
            "errorMessage": error_message,
        },
    )
    conn.execute(
        """
        INSERT INTO agent_runs (
            run_id, agent_id, agent_key, agent_version, trigger_source, mode, status,
            replay_source_run_id, replay_source_agent_key, replay_reason,
            input_json, output_json, trace_json, error_type, error_message,
            decision, decision_source, latency_ms, token_used, cost_micros, risk_score,
            operator_id, operator_name, started_at, ended_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            entry["id"],
            entry["agentKey"],
            entry["version"],
            trigger_source,
            mode,
            status,
            replay_source_run_id or None,
            replay_source_agent_key or None,
            replay_reason or None,
            _stringify_json(input_value),
            _stringify_json(output_value),
            _stringify_json(trace_value),
            error_type or None,
            error_message or None,
            decision or None,
            decision_source or None,
            latency_ms,
            token_used,
            cost_micros,
            risk_score,
            operator.get("id") or None,
            operator.get("name") or None,
            started_at,
            ended_at or None,
            now,
            now,
        ),
    )
    for step in steps:
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
                step["index"],
                step["type"],
                step["name"],
                step["status"],
                _stringify_json(step["input"]) if step["input"] is not None else None,
                _stringify_json(step["output"]) if step["output"] is not None else None,
                step["errorType"] or None,
                step["errorMessage"] or None,
                step["latency"],
                step["toolName"] or None,
                now,
            ),
        )
    if _is_terminal_run_status(status):
        metric_date = _to_date_key(started_at)
        _upsert_daily_metric(
            conn,
            metric_date,
            entry["agentKey"],
            mode,
            status,
            decision,
            latency_ms,
            token_used,
            cost_micros,
            now,
        )
        if mode != "all":
            _upsert_daily_metric(
                conn,
                metric_date,
                entry["agentKey"],
                "all",
                status,
                decision,
                latency_ms,
                token_used,
                cost_micros,
                now,
            )
    conn.commit()
    return {
        "runId": run_id,
        "agentKey": entry["agentKey"],
        "agentVersion": entry["version"],
        "mode": mode,
        "status": status,
        "decision": decision,
        "replaySourceRunId": replay_source_run_id,
        "replaySourceAgentKey": replay_source_agent_key,
        "steps": len(steps),
        "message": _safe_text(options.get("successMessage"), 80) or "运行记录已创建",
    }


def _get_run_detail(
    conn: sqlite3.Connection, run_id: str, agent_key: str | None = None
) -> dict[str, Any] | None:
    sql = """
        SELECT run_id, agent_key, agent_version, trigger_source, mode, status,
               replay_source_run_id, replay_source_agent_key, replay_reason,
               input_json, output_json, trace_json, error_type, error_message,
               decision, decision_source, latency_ms, token_used, cost_micros,
               risk_score, operator_id, operator_name, started_at, ended_at,
               created_at, updated_at
        FROM agent_runs
        WHERE run_id = ?
    """
    params: list[Any] = [run_id]
    if agent_key:
        sql += " AND agent_key = ?"
        params.append(agent_key)
    sql += " LIMIT 1"
    run = conn.execute(sql, params).fetchone()
    if run is None:
        return None
    steps = conn.execute(
        """
        SELECT step_index, step_type, step_name, status, input_json, output_json,
               error_type, error_message, latency_ms, tool_name, created_at
        FROM agent_run_steps
        WHERE run_id = ?
        ORDER BY step_index ASC
        """,
        (run_id,),
    ).fetchall()
    return {
        "run": {
            **_map_run_item(run),
            "input": _parse_json_safe(run["input_json"], None),
            "output": _parse_json_safe(run["output_json"], None),
            "trace": _parse_json_safe(run["trace_json"], None),
            "updatedAt": run["updated_at"],
        },
        "steps": [
            {
                "stepIndex": _safe_int(step["step_index"], 0),
                "stepType": _safe_text(step["step_type"], 40) or "step",
                "stepName": _safe_text(step["step_name"], 100),
                "status": _safe_text(step["status"], 20) or "success",
                "input": _parse_json_safe(step["input_json"], None),
                "output": _parse_json_safe(step["output_json"], None),
                "errorType": _safe_text(step["error_type"], 80),
                "errorMessage": _safe_text(step["error_message"], 300),
                "latencyMs": _safe_int(step["latency_ms"], 0),
                "toolName": _safe_text(step["tool_name"], 80),
                "createdAt": step["created_at"],
            }
            for step in steps
        ],
    }


def _apply_release_execution(
    conn: sqlite3.Connection, release_row: sqlite3.Row, now: int
) -> dict[str, Any]:
    release_id = _safe_text(release_row["release_id"], 80)
    agent_key = _normalize_agent_key(release_row["agent_key"])
    target_version = _safe_text(release_row["target_version"], 40)
    release_type = _normalize_release_type(release_row["release_type"], "canary")
    if not release_id or not agent_key or not target_version:
        return {"ok": False, "code": "INVALID_PARAMS", "message": "发布请求参数无效"}
    agent = conn.execute(
        "SELECT id FROM agent_definitions WHERE agent_key = ? LIMIT 1", (agent_key,)
    ).fetchone()
    if not agent:
        return {"ok": False, "code": "NOT_FOUND", "message": "Agent 定义不存在"}
    version = conn.execute(
        "SELECT id, version FROM agent_versions WHERE agent_id = ? AND version = ? LIMIT 1",
        (agent["id"], target_version),
    ).fetchone()
    if not version:
        return {"ok": False, "code": "NOT_FOUND", "message": "目标版本不存在"}
    if release_type == "canary":
        conn.execute(
            "UPDATE agent_versions SET is_candidate = CASE WHEN id = ? THEN 1 ELSE 0 END, updated_at = ? WHERE agent_id = ?",
            (version["id"], now, agent["id"]),
        )
    else:
        conn.execute(
            "UPDATE agent_versions SET is_current = CASE WHEN id = ? THEN 1 ELSE 0 END, is_candidate = 0, updated_at = ? WHERE agent_id = ?",
            (version["id"], now, agent["id"]),
        )
        conn.execute(
            "UPDATE agent_definitions SET status = 'active', updated_at = ? WHERE id = ?",
            (now, agent["id"]),
        )
    conn.commit()
    return {
        "ok": True,
        "releaseType": release_type,
        "agentKey": agent_key,
        "targetVersion": _safe_text(version["version"], 40),
        "executedAt": now,
    }


def _map_eval_run_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "evalRunId": row["eval_run_id"],
        "agentKey": row["agent_key"],
        "agentVersion": _safe_text(row["agent_version"], 40),
        "datasetName": _safe_text(row["dataset_name"], 80),
        "datasetVersion": _safe_text(row["dataset_version"], 40),
        "templateProfile": _safe_text(row["template_profile"], 20) or "standard",
        "triggerSource": _safe_text(row["trigger_source"], 40),
        "mode": _safe_text(row["mode"], 20) or "offline",
        "status": _safe_text(row["status"], 20) or "queued",
        "summary": _parse_json_safe(row["summary_json"], None),
        "totalCases": _safe_int(row["total_cases"], 0),
        "passedCases": _safe_int(row["passed_cases"], 0),
        "failedCases": _safe_int(row["failed_cases"], 0),
        "manualReviewCases": _safe_int(row["manual_review_cases"], 0),
        "precisionScore": _safe_number(row["precision_score"], 0),
        "recallScore": _safe_number(row["recall_score"], 0),
        "f1Score": _safe_number(row["f1_score"], 0),
        "falsePositiveRate": _safe_number(row["false_positive_rate"], 0),
        "avgLatencyMs": round(_safe_number(row["avg_latency_ms"], 0), 2),
        "tokenUsedTotal": _safe_int(row["token_used_total"], 0),
        "costMicrosTotal": _safe_int(row["cost_micros_total"], 0),
        "startedAt": row["started_at"],
        "endedAt": row["ended_at"],
        "operatorId": _safe_text(row["operator_id"], 80),
        "operatorName": _safe_text(row["operator_name"], 80),
        "notes": _safe_text(row["notes"], 500),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _build_auto_eval_cases(
    agent_key: str,
    dataset_name: str,
    template_profile: str,
    case_count: int,
    target_pass_rate: float,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    pattern = ["approve", "manual_review", "reject", "approve", "approve"]
    pass_cutoff = round(case_count * target_pass_rate)
    for idx in range(case_count):
        expected_decision = pattern[idx % len(pattern)]
        passed = idx < pass_cutoff
        actual_decision = (
            expected_decision
            if passed
            else ("reject" if expected_decision == "approve" else "approve")
        )
        token_used = 120 + (idx % 5) * 20
        latency_ms = 80 + (idx % 4) * 15
        cases.append(
            {
                "caseKey": f"{agent_key or 'agent'}_auto_case_{idx + 1}",
                "sourceType": "generated",
                "sourceRef": f"{agent_key or 'agent'}:{dataset_name}:{idx + 1}",
                "expectedDecision": expected_decision,
                "actualDecision": actual_decision,
                "passed": passed,
                "score": 1.0 if passed else 0.0,
                "input": {
                    "text": f"自动生成评测样例 #{idx + 1}",
                    "agent_key": agent_key,
                    "template_profile": template_profile,
                },
                "expected": {"decision": expected_decision},
                "actual": {"decision": actual_decision},
                "trace": {
                    "case_key": f"{agent_key}_auto_case_{idx + 1}",
                    "source": "auto_generator",
                },
                "errorType": "" if passed else "decision_mismatch",
                "errorMessage": "" if passed else "评测结果与期望不一致",
                "latencyMs": latency_ms,
                "tokenUsed": token_used,
                "costMicros": token_used * 3,
            }
        )
    return cases


def _create_eval_run_record(
    conn: sqlite3.Connection,
    agent_key: str,
    payload: dict[str, Any],
    operator: dict[str, str],
) -> dict[str, Any]:
    _ensure_bootstrap_definitions(conn)
    entry = _ensure_agent_entry(conn, agent_key)
    if not entry:
        raise ValueError("无法创建 Agent 定义")
    now = _now_ms()
    eval_run_id = _create_eval_run_id()
    mode = _normalize_eval_mode(payload.get("mode"), "offline")
    status = _normalize_eval_status(payload.get("status"), "success")
    dataset_name = _safe_text(payload.get("datasetName"), 80) or "agent_center_eval"
    dataset_version = _safe_text(
        payload.get("datasetVersion"), 40
    ) or datetime.fromtimestamp(now / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    template_profile = _normalize_eval_template_profile(
        payload.get("templateProfile"), "standard"
    )
    default_pass_rate = (
        0.72
        if template_profile == "high_risk"
        else (0.68 if template_profile == "borderline" else 0.85)
    )
    trigger_source = _safe_text(payload.get("triggerSource"), 40) or "admin_eval"
    case_list = payload.get("cases") if isinstance(payload.get("cases"), list) else None
    normalized_cases: list[dict[str, Any]] = []
    if case_list:
        for idx, item in enumerate(case_list[:500], start=1):
            case = item if isinstance(item, dict) else {}
            expected_decision = (
                _safe_text(
                    case.get("expectedDecision")
                    or ((case.get("expected") or {}).get("decision")),
                    40,
                )
                or "manual_review"
            )
            actual_decision = (
                _safe_text(
                    case.get("actualDecision")
                    or ((case.get("actual") or {}).get("decision")),
                    40,
                )
                or expected_decision
            )
            passed = (
                bool(case.get("passed"))
                if case.get("passed") is not None
                else actual_decision == expected_decision
            )
            token_used = max(_safe_int(case.get("tokenUsed"), 0), 0)
            latency_ms = max(_safe_int(case.get("latencyMs"), 0), 0)
            normalized_cases.append(
                {
                    "caseKey": _safe_text(case.get("caseKey"), 120) or f"case_{idx}",
                    "sourceType": _safe_text(case.get("sourceType"), 40) or "dataset",
                    "sourceRef": _safe_text(case.get("sourceRef"), 160),
                    "expectedDecision": expected_decision,
                    "actualDecision": actual_decision,
                    "passed": passed,
                    "score": _clamp_number(case.get("score"), 0, 1, 1 if passed else 0),
                    "input": case.get("input")
                    if isinstance(case.get("input"), dict)
                    else {"text": f"评测输入样例 #{idx}"},
                    "expected": case.get("expected")
                    if isinstance(case.get("expected"), dict)
                    else {"decision": expected_decision},
                    "actual": case.get("actual")
                    if isinstance(case.get("actual"), dict)
                    else {"decision": actual_decision},
                    "trace": case.get("trace")
                    if isinstance(case.get("trace"), dict)
                    else None,
                    "errorType": _safe_text(case.get("errorType"), 80)
                    or ("" if passed else "decision_mismatch"),
                    "errorMessage": _safe_text(case.get("errorMessage"), 300)
                    or ("" if passed else "评测结果与期望不一致"),
                    "latencyMs": latency_ms,
                    "tokenUsed": token_used,
                    "costMicros": max(
                        _safe_int(case.get("costMicros"), token_used * 3), 0
                    ),
                }
            )
    else:
        case_count = min(max(_safe_int(payload.get("caseCount"), 20), 1), 200)
        target_pass_rate = _clamp_number(
            payload.get("targetPassRate"), 0, 1, default_pass_rate
        )
        normalized_cases = _build_auto_eval_cases(
            entry["agentKey"],
            dataset_name,
            template_profile,
            case_count,
            target_pass_rate,
        )
    total_cases = len(normalized_cases)
    passed_cases = sum(1 for item in normalized_cases if item["passed"])
    failed_cases = max(total_cases - passed_cases, 0)
    manual_review_cases = sum(
        1 for item in normalized_cases if item["actualDecision"] == "manual_review"
    )
    total_latency = sum(
        max(_safe_int(item.get("latencyMs"), 0), 0) for item in normalized_cases
    )
    token_used_total = sum(
        max(_safe_int(item.get("tokenUsed"), 0), 0) for item in normalized_cases
    )
    cost_micros_total = sum(
        max(_safe_int(item.get("costMicros"), 0), 0) for item in normalized_cases
    )
    avg_latency_ms = total_latency / total_cases if total_cases > 0 else 0
    pass_rate = passed_cases / total_cases if total_cases > 0 else 0
    precision_score = _clamp_number(payload.get("precisionScore"), 0, 1, pass_rate)
    recall_score = _clamp_number(payload.get("recallScore"), 0, 1, pass_rate)
    f1_score = _clamp_number(
        payload.get("f1Score"),
        0,
        1,
        (2 * precision_score * recall_score / (precision_score + recall_score))
        if (precision_score + recall_score) > 0
        else 0,
    )
    false_positive_rate = _clamp_number(
        payload.get("falsePositiveRate"),
        0,
        1,
        failed_cases / total_cases if total_cases > 0 else 0,
    )
    started_at = max(_safe_int(payload.get("startedAt"), now), 0)
    ended_at = _safe_int(payload.get("endedAt"), 0)
    if ended_at <= 0:
        ended_at = (
            0 if status in {"queued", "running"} else started_at + int(total_latency)
        )
    summary = (
        payload.get("summary")
        if isinstance(payload.get("summary"), dict)
        else {
            "passRate": round(pass_rate, 4),
            "precisionScore": round(precision_score, 4),
            "recallScore": round(recall_score, 4),
            "f1Score": round(f1_score, 4),
            "falsePositiveRate": round(false_positive_rate, 4),
            "totalCases": total_cases,
            "passedCases": passed_cases,
            "failedCases": failed_cases,
        }
    )
    conn.execute(
        "INSERT INTO agent_eval_runs (eval_run_id, agent_id, agent_key, agent_version, dataset_name, dataset_version, template_profile, trigger_source, mode, status, summary_json, total_cases, passed_cases, failed_cases, manual_review_cases, precision_score, recall_score, f1_score, false_positive_rate, avg_latency_ms, token_used_total, cost_micros_total, started_at, ended_at, operator_id, operator_name, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            eval_run_id,
            entry["id"],
            entry["agentKey"],
            entry["version"],
            dataset_name,
            dataset_version,
            template_profile,
            trigger_source,
            mode,
            status,
            _stringify_json(summary),
            total_cases,
            passed_cases,
            failed_cases,
            manual_review_cases,
            precision_score,
            recall_score,
            f1_score,
            false_positive_rate,
            avg_latency_ms,
            token_used_total,
            cost_micros_total,
            started_at,
            ended_at or None,
            operator.get("id") or None,
            operator.get("name") or None,
            _safe_text(payload.get("notes"), 500) or None,
            now,
            now,
        ),
    )
    for item in normalized_cases:
        conn.execute(
            "INSERT INTO agent_eval_cases (eval_run_id, case_key, source_type, source_ref, expected_decision, actual_decision, passed, score, input_json, expected_json, actual_json, trace_json, error_type, error_message, latency_ms, token_used, cost_micros, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eval_run_id,
                item["caseKey"],
                item["sourceType"],
                item["sourceRef"] or None,
                item["expectedDecision"] or None,
                item["actualDecision"] or None,
                1 if item["passed"] else 0,
                item["score"],
                _stringify_json(item["input"])
                if item.get("input") is not None
                else None,
                _stringify_json(item["expected"])
                if item.get("expected") is not None
                else None,
                _stringify_json(item["actual"])
                if item.get("actual") is not None
                else None,
                _stringify_json(item["trace"])
                if item.get("trace") is not None
                else None,
                item["errorType"] or None,
                item["errorMessage"] or None,
                _safe_int(item.get("latencyMs"), 0),
                _safe_int(item.get("tokenUsed"), 0),
                _safe_int(item.get("costMicros"), 0),
                now,
                now,
            ),
        )
    conn.commit()
    return {
        "evalRunId": eval_run_id,
        "agentKey": entry["agentKey"],
        "agentVersion": entry["version"],
        "mode": mode,
        "status": status,
        "datasetName": dataset_name,
        "datasetVersion": dataset_version,
        "templateProfile": template_profile,
        "totalCases": total_cases,
        "passedCases": passed_cases,
        "failedCases": failed_cases,
        "manualReviewCases": manual_review_cases,
        "precisionScore": precision_score,
        "recallScore": recall_score,
        "f1Score": f1_score,
        "falsePositiveRate": false_positive_rate,
        "avgLatencyMs": round(avg_latency_ms, 2),
        "tokenUsedTotal": token_used_total,
        "costMicrosTotal": cost_micros_total,
        "startedAt": started_at,
        "endedAt": ended_at or None,
        "operatorId": operator.get("id") or "",
        "operatorName": operator.get("name") or "",
        "notes": _safe_text(payload.get("notes"), 500),
        "createdAt": now,
        "updatedAt": now,
    }


def _get_eval_run_detail(
    conn: sqlite3.Connection,
    eval_run_id: str,
    agent_key: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any] | None:
    sql = "SELECT * FROM agent_eval_runs WHERE eval_run_id = ?"
    params: list[Any] = [eval_run_id]
    if agent_key:
        sql += " AND agent_key = ?"
        params.append(agent_key)
    sql += " LIMIT 1"
    run = conn.execute(sql, params).fetchone()
    if run is None:
        return None
    offset = (page - 1) * page_size
    total = _safe_int(
        conn.execute(
            "SELECT COUNT(1) AS total FROM agent_eval_cases WHERE eval_run_id = ?",
            (eval_run_id,),
        ).fetchone()["total"],
        0,
    )
    by_source_type = conn.execute(
        "SELECT source_type, COUNT(1) AS total_count, SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passed_count, AVG(latency_ms) AS avg_latency_ms, SUM(token_used) AS token_used_total, SUM(cost_micros) AS cost_micros_total FROM agent_eval_cases WHERE eval_run_id = ? GROUP BY source_type ORDER BY total_count DESC",
        (eval_run_id,),
    ).fetchall()
    by_source_group = conn.execute(
        "SELECT CASE WHEN source_ref IS NULL OR trim(source_ref) = '' THEN 'unknown' WHEN instr(source_ref, ':') > 0 THEN substr(source_ref, 1, instr(source_ref, ':') - 1) ELSE source_ref END AS source_group, COUNT(1) AS total_count, SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passed_count, AVG(latency_ms) AS avg_latency_ms, SUM(token_used) AS token_used_total, SUM(cost_micros) AS cost_micros_total FROM agent_eval_cases WHERE eval_run_id = ? GROUP BY source_group ORDER BY total_count DESC LIMIT 20",
        (eval_run_id,),
    ).fetchall()
    rows = conn.execute(
        "SELECT * FROM agent_eval_cases WHERE eval_run_id = ? ORDER BY id ASC LIMIT ? OFFSET ?",
        (eval_run_id, page_size, offset),
    ).fetchall()
    return {
        "evalRun": _map_eval_run_row(run),
        "cases": [
            {
                "caseKey": row["case_key"],
                "sourceType": _safe_text(row["source_type"], 40) or "dataset",
                "sourceRef": _safe_text(row["source_ref"], 160),
                "expectedDecision": _safe_text(row["expected_decision"], 40),
                "actualDecision": _safe_text(row["actual_decision"], 40),
                "passed": _safe_int(row["passed"], 0) == 1,
                "score": _safe_number(row["score"], 0),
                "input": _parse_json_safe(row["input_json"], None),
                "expected": _parse_json_safe(row["expected_json"], None),
                "actual": _parse_json_safe(row["actual_json"], None),
                "trace": _parse_json_safe(row["trace_json"], None),
                "errorType": _safe_text(row["error_type"], 80),
                "errorMessage": _safe_text(row["error_message"], 300),
                "latencyMs": _safe_int(row["latency_ms"], 0),
                "tokenUsed": _safe_int(row["token_used"], 0),
                "costMicros": _safe_int(row["cost_micros"], 0),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ],
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": (total + page_size - 1) // page_size if total > 0 else 0,
        },
        "sourceSummary": {
            "bySourceType": [
                {
                    "sourceType": _safe_text(row["source_type"], 40) or "unknown",
                    "totalCount": _safe_int(row["total_count"], 0),
                    "passedCount": _safe_int(row["passed_count"], 0),
                    "failedCount": max(
                        _safe_int(row["total_count"], 0)
                        - _safe_int(row["passed_count"], 0),
                        0,
                    ),
                    "passRate": round(
                        _safe_int(row["passed_count"], 0)
                        / _safe_int(row["total_count"], 1),
                        4,
                    )
                    if _safe_int(row["total_count"], 0) > 0
                    else 0,
                    "avgLatencyMs": round(_safe_number(row["avg_latency_ms"], 0), 2),
                    "tokenUsedTotal": _safe_int(row["token_used_total"], 0),
                    "costMicrosTotal": _safe_int(row["cost_micros_total"], 0),
                }
                for row in by_source_type
            ],
            "bySourceGroup": [
                {
                    "sourceGroup": _safe_text(row["source_group"], 80) or "unknown",
                    "totalCount": _safe_int(row["total_count"], 0),
                    "passedCount": _safe_int(row["passed_count"], 0),
                    "failedCount": max(
                        _safe_int(row["total_count"], 0)
                        - _safe_int(row["passed_count"], 0),
                        0,
                    ),
                    "passRate": round(
                        _safe_int(row["passed_count"], 0)
                        / _safe_int(row["total_count"], 1),
                        4,
                    )
                    if _safe_int(row["total_count"], 0) > 0
                    else 0,
                    "avgLatencyMs": round(_safe_number(row["avg_latency_ms"], 0), 2),
                    "tokenUsedTotal": _safe_int(row["token_used_total"], 0),
                    "costMicrosTotal": _safe_int(row["cost_micros_total"], 0),
                }
                for row in by_source_group
            ],
        },
    }


def _normalize_steps(
    step_list: list[Any] | None, context: dict[str, Any]
) -> list[dict[str, Any]]:
    if not step_list:
        failed = context.get("status") == "failed"
        fallback = context.get("status") == "fallback"
        queued = context.get("status") == "queued"
        running = context.get("status") == "running"
        return [
            {
                "index": 1,
                "type": "prepare",
                "name": "准备输入",
                "status": "queued" if queued else ("running" if running else "success"),
                "input": {"mode": context.get("mode") or "test"},
                "output": {"queued": True}
                if queued
                else ({"started": True} if running else {"ok": True}),
                "errorType": "",
                "errorMessage": "",
                "latency": 0 if queued else 20,
                "toolName": "",
            },
            {
                "index": 2,
                "type": "inference",
                "name": "模型推理",
                "status": "queued"
                if queued
                else ("running" if running else ("failed" if failed else "success")),
                "input": {
                    "decision_source": context.get("decisionSource") or "manual_test"
                },
                "output": {"queued": True}
                if queued
                else (
                    {"started": True}
                    if running
                    else (
                        None
                        if failed
                        else {"decision": context.get("decision") or "approve"}
                    )
                ),
                "errorType": context.get("errorType")
                or ("manual_test_failed" if failed else ""),
                "errorMessage": context.get("errorMessage")
                or ("测试推理失败" if failed else ""),
                "latency": 0 if queued else 120,
                "toolName": "llm",
            },
            {
                "index": 3,
                "type": "postprocess",
                "name": "结果处理",
                "status": "queued"
                if queued
                else (
                    "running"
                    if running
                    else (
                        "failed" if failed else ("fallback" if fallback else "success")
                    )
                ),
                "input": {"status": context.get("status") or "success"},
                "output": {"status": "queued"}
                if queued
                else (
                    {"status": "running"}
                    if running
                    else {
                        "status": "failed"
                        if failed
                        else ("fallback" if fallback else "success")
                    }
                ),
                "errorType": context.get("errorType") or "",
                "errorMessage": context.get("errorMessage") or "",
                "latency": 0 if queued else 40,
                "toolName": "",
            },
        ]
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(step_list[:20], start=1):
        step = item if isinstance(item, dict) else {}
        normalized.append(
            {
                "index": idx,
                "type": _safe_text(
                    step.get("stepType") or step.get("step_type") or step.get("type"),
                    40,
                )
                or "step",
                "name": _safe_text(
                    step.get("stepName") or step.get("step_name") or step.get("name"),
                    100,
                )
                or f"步骤 {idx}",
                "status": _normalize_run_status(step.get("status"), "success"),
                "input": step.get("input")
                if isinstance(step.get("input"), dict)
                else None,
                "output": step.get("output")
                if isinstance(step.get("output"), dict)
                else None,
                "errorType": _safe_text(
                    step.get("errorType") or step.get("error_type"), 80
                ),
                "errorMessage": _safe_text(
                    step.get("errorMessage") or step.get("error_message"), 300
                ),
                "latency": max(
                    _safe_int(step.get("latencyMs") or step.get("latency_ms"), 0), 0
                ),
                "toolName": _safe_text(
                    step.get("toolName") or step.get("tool_name"), 80
                ),
            }
        )
    return normalized


def _upsert_daily_metric(
    conn: sqlite3.Connection,
    metric_date: str,
    agent_key: str,
    mode: str,
    status: str,
    decision: str,
    latency_ms: int,
    token_used: int,
    cost_micros: int,
    now: int,
) -> None:
    normalized_status = _normalize_run_status(status, "success")
    conn.execute(
        """
        INSERT INTO agent_metrics_daily (
            metric_date, agent_key, mode, run_count, success_count, failed_count,
            fallback_count, manual_review_count, avg_latency_ms, p95_latency_ms,
            token_used_total, cost_micros_total, updated_at
        ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        ON CONFLICT(metric_date, agent_key, mode) DO UPDATE SET
            run_count = agent_metrics_daily.run_count + 1,
            success_count = agent_metrics_daily.success_count + excluded.success_count,
            failed_count = agent_metrics_daily.failed_count + excluded.failed_count,
            fallback_count = agent_metrics_daily.fallback_count + excluded.fallback_count,
            manual_review_count = agent_metrics_daily.manual_review_count + excluded.manual_review_count,
            avg_latency_ms = ((COALESCE(agent_metrics_daily.avg_latency_ms, 0) * agent_metrics_daily.run_count + excluded.avg_latency_ms) / NULLIF(agent_metrics_daily.run_count + 1, 0)),
            token_used_total = agent_metrics_daily.token_used_total + excluded.token_used_total,
            cost_micros_total = agent_metrics_daily.cost_micros_total + excluded.cost_micros_total,
            updated_at = excluded.updated_at
        """,
        (
            metric_date,
            agent_key,
            mode,
            1 if normalized_status == "success" else 0,
            1 if normalized_status == "failed" else 0,
            1 if normalized_status == "fallback" else 0,
            1 if _safe_text(decision, 40) == "manual_review" else 0,
            latency_ms,
            token_used,
            cost_micros,
            now,
        ),
    )


def _create_run_record(
    conn: sqlite3.Connection,
    agent_key: str,
    payload: dict[str, Any],
    operator: dict[str, str],
    options: dict[str, Any],
) -> dict[str, Any]:
    _ensure_bootstrap_definitions(conn)
    entry = _ensure_agent_entry(conn, agent_key)
    if not entry:
        raise ValueError("无法创建 Agent 定义")
    now = _now_ms()
    run_id = _create_run_id()
    mode = _normalize_run_mode(
        payload.get("mode"), options.get("defaultMode") or "test"
    )
    status = _normalize_run_status(payload.get("status"), "success")
    trigger_source = (
        _safe_text(payload.get("triggerSource"), 40)
        or _safe_text(options.get("defaultTriggerSource"), 40)
        or "admin_test"
    )
    decision = _safe_text(payload.get("decision"), 40) or (
        "manual_review"
        if status == "failed"
        else ("" if _is_pending_run_status(status) else "approve")
    )
    decision_source = (
        _safe_text(payload.get("decisionSource"), 40)
        or _safe_text(options.get("defaultDecisionSource"), 40)
        or "manual_test"
    )
    confidence = _clamp_number(
        payload.get("confidence"), 0, 1, 0.25 if status == "failed" else 0.9
    )
    reason = _safe_text(payload.get("reason"), 300)
    if not reason:
        if status == "failed":
            reason = _safe_text(options.get("defaultFailedReason"), 300) or "运行失败"
        elif status == "queued":
            reason = "任务已加入队列"
        elif status == "running":
            reason = "任务执行中"
        else:
            reason = _safe_text(options.get("defaultSuccessReason"), 300) or "运行通过"
    risk_score = _clamp_number(
        payload.get("riskScore"),
        0,
        1,
        0 if _is_pending_run_status(status) else (0.8 if status == "failed" else 0.1),
    )
    token_used = max(
        _safe_int(
            payload.get("tokenUsed"),
            0 if status == "failed" or _is_pending_run_status(status) else 600,
        ),
        0,
    )
    cost_micros = max(_safe_int(payload.get("costMicros"), token_used * 3), 0)
    started_at = max(_safe_int(payload.get("startedAt"), now), 0)
    latency_ms = max(
        _safe_int(
            payload.get("latencyMs"),
            240
            if status == "failed"
            else (0 if _is_pending_run_status(status) else 180),
        ),
        0,
    )
    ended_at = _safe_int(payload.get("endedAt"), 0)
    if ended_at <= 0:
        ended_at = 0 if _is_pending_run_status(status) else started_at + latency_ms
    if ended_at > 0 and ended_at < started_at:
        ended_at = started_at
    error_type = ""
    error_message = ""
    if status in {"failed", "fallback"}:
        error_type = _safe_text(payload.get("errorType"), 80) or (
            "fallback_triggered" if status == "fallback" else "manual_test_failed"
        )
        error_message = _safe_text(payload.get("errorMessage"), 300) or (
            "测试触发兜底" if status == "fallback" else "测试运行失败"
        )
    input_value = (
        payload.get("input")
        if isinstance(payload.get("input"), dict)
        else {
            "text": _safe_text(payload.get("inputText"), 300)
            or _safe_text(options.get("defaultInputText"), 300)
            or "Agent 输入样例"
        }
    )
    output_value = (
        payload.get("output")
        if isinstance(payload.get("output"), dict)
        else {
            "decision": decision,
            "decision_source": decision_source,
            "confidence": confidence,
            "reason": reason,
        }
    )
    replay_source_run_id = _safe_text(
        payload.get("replaySourceRunId") or payload.get("sourceRunId"), 80
    )
    replay_source_agent_key = _normalize_agent_key(
        payload.get("replaySourceAgentKey") or payload.get("sourceAgentKey")
    )
    replay_reason = _safe_text(payload.get("replayReason"), 300)
    trace_value = (
        payload.get("trace")
        if isinstance(payload.get("trace"), dict)
        else _default_trace(
            run_id,
            entry["agentKey"],
            mode,
            status,
            decision,
            decision_source,
            confidence,
            reason,
        )
    )
    if replay_source_run_id:
        replay = (
            trace_value.get("replay")
            if isinstance(trace_value.get("replay"), dict)
            else {}
        )
        trace_value["replay"] = {
            **replay,
            "source_run_id": replay_source_run_id,
            "source_agent_key": replay_source_agent_key or entry["agentKey"],
            "reason": replay_reason or _safe_text(replay.get("reason"), 300),
        }
    steps = _normalize_steps(
        payload.get("steps") if isinstance(payload.get("steps"), list) else None,
        {
            "mode": mode,
            "status": status,
            "decision": decision,
            "decisionSource": decision_source,
            "errorType": error_type,
            "errorMessage": error_message,
        },
    )
    conn.execute(
        """
        INSERT INTO agent_runs (
            run_id, agent_id, agent_key, agent_version, trigger_source, mode, status,
            replay_source_run_id, replay_source_agent_key, replay_reason,
            input_json, output_json, trace_json, error_type, error_message,
            decision, decision_source, latency_ms, token_used, cost_micros, risk_score,
            operator_id, operator_name, started_at, ended_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            entry["id"],
            entry["agentKey"],
            entry["version"],
            trigger_source,
            mode,
            status,
            replay_source_run_id or None,
            replay_source_agent_key or None,
            replay_reason or None,
            _stringify_json(input_value),
            _stringify_json(output_value),
            _stringify_json(trace_value),
            error_type or None,
            error_message or None,
            decision or None,
            decision_source or None,
            latency_ms,
            token_used,
            cost_micros,
            risk_score,
            operator.get("id") or None,
            operator.get("name") or None,
            started_at,
            ended_at or None,
            now,
            now,
        ),
    )
    for step in steps:
        conn.execute(
            """
            INSERT INTO agent_run_steps (
                run_id, step_index, step_type, step_name, status, input_json,
                output_json, error_type, error_message, latency_ms, tool_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                step["index"],
                step["type"],
                step["name"],
                step["status"],
                _stringify_json(step["input"]) if step["input"] is not None else None,
                _stringify_json(step["output"]) if step["output"] is not None else None,
                step["errorType"] or None,
                step["errorMessage"] or None,
                step["latency"],
                step["toolName"] or None,
                now,
            ),
        )
    if _is_terminal_run_status(status):
        metric_date = _to_date_key(started_at)
        _upsert_daily_metric(
            conn,
            metric_date,
            entry["agentKey"],
            mode,
            status,
            decision,
            latency_ms,
            token_used,
            cost_micros,
            now,
        )
        if mode != "all":
            _upsert_daily_metric(
                conn,
                metric_date,
                entry["agentKey"],
                "all",
                status,
                decision,
                latency_ms,
                token_used,
                cost_micros,
                now,
            )
    conn.commit()
    return {
        "runId": run_id,
        "agentKey": entry["agentKey"],
        "agentVersion": entry["version"],
        "mode": mode,
        "status": status,
        "decision": decision,
        "replaySourceRunId": replay_source_run_id,
        "replaySourceAgentKey": replay_source_agent_key,
        "steps": len(steps),
        "message": _safe_text(options.get("successMessage"), 80) or "运行记录已创建",
    }


def _get_run_detail(
    conn: sqlite3.Connection, run_id: str, agent_key: str | None = None
) -> dict[str, Any] | None:
    sql = """
        SELECT run_id, agent_key, agent_version, trigger_source, mode, status,
               replay_source_run_id, replay_source_agent_key, replay_reason,
               input_json, output_json, trace_json, error_type, error_message,
               decision, decision_source, latency_ms, token_used, cost_micros,
               risk_score, operator_id, operator_name, started_at, ended_at,
               created_at, updated_at
        FROM agent_runs
        WHERE run_id = ?
    """
    params: list[Any] = [run_id]
    if agent_key:
        sql += " AND agent_key = ?"
        params.append(agent_key)
    sql += " LIMIT 1"
    run = conn.execute(sql, params).fetchone()
    if run is None:
        return None
    steps = conn.execute(
        """
        SELECT step_index, step_type, step_name, status, input_json, output_json,
               error_type, error_message, latency_ms, tool_name, created_at
        FROM agent_run_steps
        WHERE run_id = ?
        ORDER BY step_index ASC
        """,
        (run_id,),
    ).fetchall()
    return {
        "run": {
            **_map_run_item(run),
            "input": _parse_json_safe(run["input_json"], None),
            "output": _parse_json_safe(run["output_json"], None),
            "trace": _parse_json_safe(run["trace_json"], None),
            "updatedAt": run["updated_at"],
        },
        "steps": [
            {
                "stepIndex": _safe_int(step["step_index"], 0),
                "stepType": _safe_text(step["step_type"], 40) or "step",
                "stepName": _safe_text(step["step_name"], 100),
                "status": _safe_text(step["status"], 20) or "success",
                "input": _parse_json_safe(step["input_json"], None),
                "output": _parse_json_safe(step["output_json"], None),
                "errorType": _safe_text(step["error_type"], 80),
                "errorMessage": _safe_text(step["error_message"], 300),
                "latencyMs": _safe_int(step["latency_ms"], 0),
                "toolName": _safe_text(step["tool_name"], 80),
                "createdAt": step["created_at"],
            }
            for step in steps
        ],
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AgentControlConfigUpdate(BaseModel):
    config: dict = {}
    name: str | None = None
    description: str | None = None
    domain: str | None = None
    status: str | None = None
    ownerTeam: str | None = None
    owner_team: str | None = None
    version: str | None = None
    releaseNotes: str | None = None
    release_notes: str | None = None
    runtimeConfig: dict | None = None
    runtime_config: dict | None = None
    promptTemplate: str | None = None
    prompt_template: str | None = None


class ReleaseRequest(BaseModel):
    agent_key: str = ""
    version: str = ""
    notes: str = ""
    agentKey: str = ""
    targetVersion: str = ""
    releaseType: str = "canary"
    requestNote: str = ""
    requestMeta: dict = {}


class ShadowReadinessConfigUpdate(BaseModel):
    config: dict = {}
    minShadowRuns: int | None = None
    maxFlaggedRate: float | None = None
    maxFallbackRate: float | None = None
    defaultDays: int | None = None
    agentKeys: list[str] | None = None
    agentKeysText: str | None = None
    note: str | None = None
    changeSource: str | None = None
    changeNote: str | None = None


class ShadowSnapshotCreate(BaseModel):
    agent_key: str = ""
    config: dict = {}
    days: int | None = None
    agentKeys: str | list[str] | None = None
    source: str | None = None


class EvalRunCreate(BaseModel):
    agent_key: str = ""
    dataset_id: str = ""
    config: dict = {}
    mode: str | None = None
    datasetName: str | None = None
    datasetVersion: str | None = None
    caseCount: int | None = None
    templateProfile: str | None = None
    targetPassRate: float | None = None
    notes: str | None = None
    cases: list[dict] | None = None


class ReplayRequest(BaseModel):
    case_key: str = ""
    config: dict = {}
    sourceRunId: str | None = None
    runId: str | None = None
    replayReason: str | None = None


class AgentTestRequest(BaseModel):
    input: str = ""
    config: dict = {}
    mode: str | None = None
    reason: str | None = None
    inputText: str | None = None


class AgentRunRequest(BaseModel):
    input: str = ""
    config: dict = {}
    mode: str | None = None
    reason: str | None = None
    inputText: str | None = None


class EvalCaseUpdate(BaseModel):
    expected_output: str | None = None
    weight: float | None = None
    expectedDecision: str | None = None
    expected_decision: str | None = None
    riskLevel: str | None = None
    risk_level: str | None = None
    sourceRef: str | None = None
    source_ref: str | None = None
    input: dict | None = None
    expected: dict | None = None
    tags: list[str] | None = None
    note: str | None = None
    isActive: bool | None = None
    is_active: bool | None = None
    actionNote: str | None = None


class EvalDatasetImport(BaseModel):
    dataset: list[dict] = []
    name: str = ""
    datasetName: str = ""
    datasetVersion: str = ""
    importMode: str = "replace"
    cases: list[dict] = []
    autoRun: bool = True
    templateProfile: str = "standard"
    caseLimit: int = 500
    targetPassRate: float | None = None
    notes: str = ""
    autoRunNote: str = ""


class ProviderConfigUpdate(BaseModel):
    name: str = ""
    provider_type: str = "openai_compatible"
    base_url: str = ""
    api_key_encrypted: str = ""
    model: str = ""
    timeout_ms: int = 30000
    enabled: bool = True
    priority: int = 0
    gateway_route: str = ""
    gateway_workspace: str = ""
    extra_config_json: dict = {}


class CapabilityConfigUpdate(BaseModel):
    name: str = ""
    provider_config_id: int | None = None
    backup_provider_config_id: int | None = None
    prompt_template: str = ""
    review_criteria_json: dict = {}
    runtime_config_json: dict = {}
    enabled: bool = True
    version: str = "v1"


# ---------------------------------------------------------------------------
# Agent List
# ---------------------------------------------------------------------------


@router.get("/providers")
async def list_ai_providers(user: dict = Depends(get_current_user)):
    service = AICapabilityService()
    service.ensure_ready()
    conn = _db()
    try:
        rows = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM ai_provider_configs ORDER BY enabled DESC, priority ASC, created_at ASC"
            ).fetchall()
        )
        for row in rows:
            if row.get("extra_config_json"):
                try:
                    row["extra_config_json"] = json.loads(row["extra_config_json"])
                except Exception:
                    row["extra_config_json"] = {}
        return success_response(data={"items": rows, "total": len(rows)})
    finally:
        conn.close()


@router.get("/capabilities")
async def list_ai_capabilities(user: dict = Depends(get_current_user)):
    service = AICapabilityService()
    service.ensure_ready()
    conn = _db()
    try:
        rows = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM ai_capability_configs ORDER BY capability_key ASC"
            ).fetchall()
        )
        items = []
        for row in rows:
            row["review_criteria_json"] = (
                json.loads(row["review_criteria_json"])
                if row.get("review_criteria_json")
                else {}
            )
            row["runtime_config_json"] = (
                json.loads(row["runtime_config_json"])
                if row.get("runtime_config_json")
                else {}
            )
            primary = (
                conn.execute(
                    "SELECT id, name, provider_type, model, enabled FROM ai_provider_configs WHERE id = ?",
                    (row.get("provider_config_id"),),
                ).fetchone()
                if row.get("provider_config_id")
                else None
            )
            fallback = (
                conn.execute(
                    "SELECT id, name, provider_type, model, enabled FROM ai_provider_configs WHERE id = ?",
                    (row.get("backup_provider_config_id"),),
                ).fetchone()
                if row.get("backup_provider_config_id")
                else None
            )
            items.append(
                {
                    **row,
                    "primary_provider": dict(primary) if primary else None,
                    "backup_provider": dict(fallback) if fallback else None,
                }
            )
        return success_response(data={"items": items, "total": len(items)})
    finally:
        conn.close()


@router.put("/providers/{provider_id}")
async def update_ai_provider(
    provider_id: int,
    payload: ProviderConfigUpdate,
    user: dict = Depends(get_current_user),
):
    service = AICapabilityService()
    service.ensure_ready()
    conn = _db()
    try:
        conn.execute(
            """UPDATE ai_provider_configs SET
                name = ?, provider_type = ?, base_url = ?, api_key_encrypted = ?, model = ?,
                timeout_ms = ?, enabled = ?, priority = ?, gateway_route = ?, gateway_workspace = ?,
                extra_config_json = ?, updated_at = ?
               WHERE id = ?""",
            (
                payload.name,
                payload.provider_type,
                payload.base_url,
                payload.api_key_encrypted,
                payload.model,
                payload.timeout_ms,
                1 if payload.enabled else 0,
                payload.priority,
                payload.gateway_route,
                payload.gateway_workspace,
                json.dumps(payload.extra_config_json or {}, ensure_ascii=False),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                provider_id,
            ),
        )
        conn.commit()
        row = _row_to_dict(
            conn.execute(
                "SELECT * FROM ai_provider_configs WHERE id = ?", (provider_id,)
            ).fetchone()
        )
        return success_response(data=row or {"id": provider_id})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/capabilities/{capability_key}")
async def update_ai_capability(
    capability_key: str,
    payload: CapabilityConfigUpdate,
    user: dict = Depends(get_current_user),
):
    service = AICapabilityService()
    service.ensure_ready()
    conn = _db()
    try:
        conn.execute(
            """UPDATE ai_capability_configs SET
                name = ?, provider_config_id = ?, backup_provider_config_id = ?, prompt_template = ?,
                review_criteria_json = ?, runtime_config_json = ?, enabled = ?, version = ?, updated_at = ?
               WHERE capability_key = ?""",
            (
                payload.name,
                payload.provider_config_id,
                payload.backup_provider_config_id,
                payload.prompt_template,
                json.dumps(payload.review_criteria_json or {}, ensure_ascii=False),
                json.dumps(payload.runtime_config_json or {}, ensure_ascii=False),
                1 if payload.enabled else 0,
                payload.version,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                capability_key,
            ),
        )
        conn.commit()
        row = _row_to_dict(
            conn.execute(
                "SELECT * FROM ai_capability_configs WHERE capability_key = ?",
                (capability_key,),
            ).fetchone()
        )
        return success_response(data=row or {"capability_key": capability_key})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("")
async def list_agents(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    includeDisabled: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        _ensure_bootstrap_definitions(conn)
        where = ["1=1"]
        params: list[Any] = []
        normalized_status = _normalize_agent_status(status, "") if status else ""
        if normalized_status:
            where.append("d.status = ?")
            params.append(normalized_status)
        elif not includeDisabled:
            where.append("d.status != 'disabled'")
        where_sql = "WHERE " + " AND ".join(where)
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_definitions d {where_sql}", params
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"""
            SELECT
                d.id,
                d.agent_key,
                d.name,
                d.description,
                d.domain,
                d.status,
                d.owner_team,
                d.created_at,
                d.updated_at,
                v.version AS current_version,
                (SELECT COUNT(1) FROM agent_runs r WHERE r.agent_key = d.agent_key) AS run_count,
                (SELECT r.status FROM agent_runs r WHERE r.agent_key = d.agent_key ORDER BY r.started_at DESC, r.id DESC LIMIT 1) AS last_run_status,
                (SELECT r.started_at FROM agent_runs r WHERE r.agent_key = d.agent_key ORDER BY r.started_at DESC, r.id DESC LIMIT 1) AS last_run_at
            FROM agent_definitions d
            LEFT JOIN agent_versions v ON v.agent_id = d.id AND v.is_current = 1
            {where_sql}
            ORDER BY
                CASE d.status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END,
                d.updated_at DESC,
                d.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        items = [
            {
                "id": row["id"],
                "agentKey": row["agent_key"],
                "name": row["name"],
                "description": _safe_text(row["description"], 500),
                "domain": _safe_text(row["domain"], 40) or "shop",
                "status": _safe_text(row["status"], 20) or "draft",
                "ownerTeam": _safe_text(row["owner_team"], 80),
                "currentVersion": _safe_text(row["current_version"], 40) or "v1",
                "runCount": _safe_int(row["run_count"], 0),
                "lastRunStatus": _safe_text(row["last_run_status"], 20),
                "lastRunAt": row["last_run_at"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]
        return success_response(
            data={"items": items, "total": total, "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Control Config
# ---------------------------------------------------------------------------


@router.get("/{agent_key}/control-config")
async def get_agent_control_config(
    agent_key: str, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        _ensure_bootstrap_definitions(conn)
        entry = _ensure_agent_entry(conn, agent_key)
        if not entry:
            return error_response("AGENT_NOT_FOUND", "Agent 不存在", 404)
        row = conn.execute(
            """
            SELECT
                d.id AS agent_id,
                d.agent_key,
                d.name,
                d.description,
                d.domain,
                d.status,
                d.owner_team,
                d.created_at,
                d.updated_at,
                v.version,
                v.runtime_config_json,
                v.release_notes,
                v.prompt_template,
                v.is_current,
                v.is_candidate
            FROM agent_definitions d
            LEFT JOIN agent_versions v ON v.agent_id = d.id AND v.is_current = 1
            WHERE d.agent_key = ?
            LIMIT 1
            """,
            (entry["agentKey"],),
        ).fetchone()
        if row is None:
            return error_response("AGENT_NOT_FOUND", "Agent 不存在", 404)
        return success_response(
            data={
                "agent": {
                    "id": _safe_int(row["agent_id"], 0),
                    "agentKey": _safe_text(row["agent_key"], 80),
                    "name": _safe_text(row["name"], 100),
                    "description": _safe_text(row["description"], 500),
                    "domain": _safe_text(row["domain"], 40) or "shop",
                    "status": _normalize_agent_status(row["status"], "draft"),
                    "ownerTeam": _safe_text(row["owner_team"], 80),
                    "createdAt": _safe_int(row["created_at"], 0),
                    "updatedAt": _safe_int(row["updated_at"], 0),
                },
                "currentVersion": {
                    "version": _safe_text(row["version"], 40) or "v1",
                    "runtimeConfig": _parse_json_safe(row["runtime_config_json"], {})
                    or {},
                    "releaseNotes": _safe_text(row["release_notes"], 500),
                    "promptTemplate": _safe_text(row["prompt_template"], 12000),
                    "isCurrent": _safe_int(row["is_current"], 0) == 1,
                    "isCandidate": _safe_int(row["is_candidate"], 0) == 1,
                },
            }
        )
    except Exception as e:
        return error_response("READ_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/{agent_key}/control-config")
async def update_agent_control_config(
    agent_key: str,
    payload: AgentControlConfigUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        _ensure_bootstrap_definitions(conn)
        entry = _ensure_agent_entry(conn, agent_key)
        if not entry:
            return error_response("AGENT_NOT_FOUND", "Agent 不存在", 404)
        current = conn.execute(
            "SELECT id, version, runtime_config_json, release_notes, prompt_template FROM agent_versions WHERE agent_id = ? AND is_current = 1 ORDER BY id DESC LIMIT 1",
            (entry["id"],),
        ).fetchone()
        if current is None:
            return error_response("AGENT_NOT_FOUND", "当前版本不存在", 404)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        now = _now_ms()
        updates: list[str] = []
        params: list[Any] = []
        if data.get("name") is not None:
            updates.append("name = ?")
            params.append(
                _safe_text(data.get("name"), 100)
                or _default_agent_name(entry["agentKey"])
            )
        if data.get("description") is not None:
            updates.append("description = ?")
            params.append(_safe_text(data.get("description"), 500))
        if data.get("domain") is not None:
            updates.append("domain = ?")
            params.append(_safe_text(data.get("domain"), 40) or "shop")
        if data.get("status") is not None:
            updates.append("status = ?")
            params.append(_normalize_agent_status(data.get("status"), "draft"))
        owner_team = (
            data.get("ownerTeam")
            if data.get("ownerTeam") is not None
            else data.get("owner_team")
        )
        if owner_team is not None:
            updates.append("owner_team = ?")
            params.append(_safe_text(owner_team, 80))
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(entry["id"])
            conn.execute(
                f"UPDATE agent_definitions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        runtime_config = (
            data.get("runtimeConfig")
            if data.get("runtimeConfig") is not None
            else data.get("runtime_config")
        )
        release_notes = (
            data.get("releaseNotes")
            if data.get("releaseNotes") is not None
            else data.get("release_notes")
        )
        prompt_template = (
            data.get("promptTemplate")
            if data.get("promptTemplate") is not None
            else data.get("prompt_template")
        )
        if (
            runtime_config is not None
            or release_notes is not None
            or prompt_template is not None
        ):
            conn.execute(
                "UPDATE agent_versions SET runtime_config_json = ?, release_notes = ?, prompt_template = ?, updated_at = ? WHERE id = ?",
                (
                    _stringify_json(
                        runtime_config
                        if isinstance(runtime_config, dict)
                        else (
                            _parse_json_safe(current["runtime_config_json"], {}) or {}
                        )
                    ),
                    _safe_text(
                        release_notes
                        if release_notes is not None
                        else current["release_notes"],
                        500,
                    )
                    or None,
                    _safe_text(
                        prompt_template
                        if prompt_template is not None
                        else current["prompt_template"],
                        12000,
                    )
                    or None,
                    now,
                    current["id"],
                ),
            )
        conn.commit()
        return success_response(
            data={
                "success": True,
                "agentKey": entry["agentKey"],
                "updatedAt": now,
                "operatorId": _operator_from_user(user)["id"],
                "operatorName": _operator_from_user(user)["name"],
            }
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Releases
# ---------------------------------------------------------------------------


@router.get("/releases")
async def list_releases(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    agent_key: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where_parts: list[str] = []
        params: list[Any] = []
        normalized_status = _normalize_release_status(status, "") if status else ""
        normalized_agent_key = _normalize_agent_key(agent_key) if agent_key else ""
        if normalized_agent_key:
            where_parts.append("agent_key = ?")
            params.append(normalized_agent_key)
        if normalized_status:
            where_parts.append("status = ?")
            params.append(normalized_status)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_release_requests {where_sql}",
                params,
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"""
            SELECT release_id, agent_key, target_version, release_type, status, gate_required,
                   gate_passed, gate_snapshot_json, blocked_reasons_json, request_note,
                   request_meta_json, requested_by_id, requested_by_name, approved_by_id,
                   approved_by_name, approval_note, executed_at, created_at, updated_at
            FROM agent_release_requests
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return success_response(
            data={
                "items": [_map_release_request_row(row) for row in rows],
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": size,
                    "totalPages": max(1, (total + size - 1) // size),
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/releases/request")
async def request_release(
    payload: ReleaseRequest, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        request_agent_key = _normalize_agent_key(
            data.get("agentKey") or data.get("agent_key") or payload.agent_key
        )
        if not request_agent_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        _ensure_bootstrap_definitions(conn)
        entry = _ensure_agent_entry(conn, request_agent_key)
        if not entry:
            return error_response("NOT_FOUND", "Agent 不存在", 404)
        release_type = _normalize_release_type(data.get("releaseType"), "canary")
        target_version = _safe_text(
            data.get("targetVersion") or data.get("version") or payload.version, 40
        )
        version_row = None
        if target_version:
            version_row = conn.execute(
                "SELECT id, version FROM agent_versions WHERE agent_id = ? AND version = ? LIMIT 1",
                (entry["id"], target_version),
            ).fetchone()
        else:
            version_row = conn.execute(
                "SELECT id, version FROM agent_versions WHERE agent_id = ? AND is_current = 1 ORDER BY id DESC LIMIT 1",
                (entry["id"],),
            ).fetchone()
            if version_row is None:
                version_row = conn.execute(
                    "SELECT id, version FROM agent_versions WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
                    (entry["id"],),
                ).fetchone()
        if version_row is None:
            return error_response("NOT_FOUND", "目标版本不存在，请先创建版本", 404)
        gate_result = _evaluate_release_gate(
            conn, request_agent_key, release_type, data
        )
        now = _now_ms()
        release_id = _create_release_id()
        blocked_reasons = [
            {
                "agentKey": _safe_text(item.get("agentKey"), 80),
                "agentName": _safe_text(item.get("agentName"), 100),
                "reasons": item.get("reasons") or [],
                "actionHints": item.get("actionHints")
                or _build_release_action_hints(item.get("reasons") or []),
                "recommendation": _safe_text(item.get("recommendation"), 300),
            }
            for item in (gate_result.get("blockedItems") or [])
        ]
        status_value = (
            "blocked"
            if gate_result["gateRequired"] and not gate_result["gatePassed"]
            else "pending_approval"
        )
        conn.execute(
            """
            INSERT INTO agent_release_requests (
                release_id, agent_key, target_version, release_type, status,
                gate_required, gate_passed, gate_snapshot_json, blocked_reasons_json,
                request_note, request_meta_json, requested_by_id, requested_by_name,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                release_id,
                request_agent_key,
                _safe_text(version_row["version"], 40),
                release_type,
                status_value,
                1 if gate_result["gateRequired"] else 0,
                1 if gate_result["gatePassed"] else 0,
                _stringify_json(gate_result.get("snapshot") or {}, "{}"),
                _stringify_json(blocked_reasons, "[]"),
                _safe_text(
                    data.get("requestNote") or data.get("note") or payload.notes, 300
                ),
                _stringify_json(
                    data.get("requestMeta")
                    if isinstance(data.get("requestMeta"), dict)
                    else {},
                    "{}",
                ),
                operator["id"] or None,
                operator["name"] or None,
                now,
                now,
            ),
        )
        conn.commit()
        latest = _map_release_request_row(_load_release_request_row(conn, release_id))
        return success_response(
            data={
                "success": True,
                "message": "发布申请已提交，等待审批"
                if status_value != "blocked"
                else "发布申请已记录，但被 Shadow 门禁阻断",
                "request": latest,
                "gate": {
                    "gateRequired": gate_result["gateRequired"],
                    "gatePassed": gate_result["gatePassed"],
                    "blockedItems": gate_result.get("blockedItems") or [],
                    "reason": gate_result.get("reason") or "",
                },
            },
            status_code=201,
        )
    except Exception as e:
        return error_response("RELEASE_REQUEST_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/releases/{release_id}/approve")
async def approve_release(release_id: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        row = _load_release_request_row(conn, _safe_text(release_id, 80))
        if row is None:
            return error_response("RELEASE_NOT_FOUND", "发布申请不存在", 404)
        current_status = _normalize_release_status(row["status"], "pending_approval")
        if current_status not in {"pending_approval", "approved"}:
            return error_response("INVALID_PARAMS", "当前状态不可审批", 400)
        gate_result = _evaluate_release_gate(
            conn, row["agent_key"], row["release_type"], {}
        )
        blocked_reasons = [
            {
                "agentKey": _safe_text(item.get("agentKey"), 80),
                "agentName": _safe_text(item.get("agentName"), 100),
                "reasons": item.get("reasons") or [],
                "actionHints": item.get("actionHints")
                or _build_release_action_hints(item.get("reasons") or []),
                "recommendation": _safe_text(item.get("recommendation"), 300),
            }
            for item in (gate_result.get("blockedItems") or [])
        ]
        next_status = (
            "blocked"
            if gate_result["gateRequired"] and not gate_result["gatePassed"]
            else "approved"
        )
        now = _now_ms()
        conn.execute(
            "UPDATE agent_release_requests SET status = ?, gate_required = ?, gate_passed = ?, gate_snapshot_json = ?, blocked_reasons_json = ?, approved_by_id = ?, approved_by_name = ?, approval_note = ?, updated_at = ? WHERE release_id = ?",
            (
                next_status,
                1 if gate_result["gateRequired"] else 0,
                1 if gate_result["gatePassed"] else 0,
                _stringify_json(gate_result.get("snapshot") or {}, "{}"),
                _stringify_json(blocked_reasons, "[]"),
                operator["id"] or None,
                operator["name"] or None,
                "AgentCenter 审批通过",
                now,
                release_id,
            ),
        )
        conn.commit()
        if next_status == "approved":
            return await execute_release(release_id, user)
        latest = _map_release_request_row(_load_release_request_row(conn, release_id))
        return success_response(
            data={
                "success": True,
                "message": "审批已记录，但门禁阻断执行",
                "request": latest,
                "gate": {
                    "gateRequired": gate_result["gateRequired"],
                    "gatePassed": gate_result["gatePassed"],
                    "blockedItems": gate_result.get("blockedItems") or [],
                    "reason": gate_result.get("reason") or "",
                },
            }
        )
    except Exception as e:
        return error_response("APPROVE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/releases/{release_id}/reject")
async def reject_release(
    release_id: str,
    reason: str = "",
    payload: dict | None = Body(default=None),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        row = _load_release_request_row(conn, _safe_text(release_id, 80))
        if row is None:
            return error_response("RELEASE_NOT_FOUND", "发布申请不存在", 404)
        current_status = _normalize_release_status(row["status"], "pending_approval")
        if current_status not in {"pending_approval", "approved", "blocked"}:
            return error_response("INVALID_PARAMS", "当前状态不可驳回", 400)
        note = _safe_text(
            (payload or {}).get("rejectionNote")
            or (payload or {}).get("note")
            or reason,
            300,
        )
        conn.execute(
            "UPDATE agent_release_requests SET status = 'rejected', approved_by_id = ?, approved_by_name = ?, approval_note = ?, updated_at = ? WHERE release_id = ?",
            (
                operator["id"] or None,
                operator["name"] or None,
                note or None,
                _now_ms(),
                release_id,
            ),
        )
        conn.commit()
        latest = _map_release_request_row(_load_release_request_row(conn, release_id))
        return success_response(
            data={"success": True, "message": "发布申请已驳回", "request": latest}
        )
    except Exception as e:
        return error_response("REJECT_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/releases/{release_id}/execute")
async def execute_release(release_id: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        row = _load_release_request_row(conn, _safe_text(release_id, 80))
        if row is None:
            return error_response("RELEASE_NOT_FOUND", "发布申请不存在", 404)
        current_status = _normalize_release_status(row["status"], "pending_approval")
        if current_status not in {"approved", "pending_approval"}:
            return error_response("INVALID_PARAMS", "当前状态不可执行", 400)
        gate_result = _evaluate_release_gate(
            conn, row["agent_key"], row["release_type"], {}
        )
        blocked_reasons = [
            {
                "agentKey": _safe_text(item.get("agentKey"), 80),
                "agentName": _safe_text(item.get("agentName"), 100),
                "reasons": item.get("reasons") or [],
                "actionHints": item.get("actionHints")
                or _build_release_action_hints(item.get("reasons") or []),
                "recommendation": _safe_text(item.get("recommendation"), 300),
            }
            for item in (gate_result.get("blockedItems") or [])
        ]
        now = _now_ms()
        if gate_result["gateRequired"] and not gate_result["gatePassed"]:
            conn.execute(
                "UPDATE agent_release_requests SET status = 'blocked', gate_required = ?, gate_passed = 0, gate_snapshot_json = ?, blocked_reasons_json = ?, updated_at = ? WHERE release_id = ?",
                (
                    1 if gate_result["gateRequired"] else 0,
                    _stringify_json(gate_result.get("snapshot") or {}, "{}"),
                    _stringify_json(blocked_reasons, "[]"),
                    now,
                    release_id,
                ),
            )
            conn.commit()
            latest = _map_release_request_row(
                _load_release_request_row(conn, release_id)
            )
            return success_response(
                data={
                    "success": False,
                    "message": "执行已阻断：Shadow 门禁未通过",
                    "request": latest,
                    "gate": {
                        "gateRequired": gate_result["gateRequired"],
                        "gatePassed": False,
                        "blockedItems": gate_result.get("blockedItems") or [],
                        "reason": gate_result.get("reason") or "",
                    },
                }
            )
        execution = _apply_release_execution(conn, row, now)
        if not execution.get("ok"):
            return error_response(
                execution.get("code") or "UPDATE_FAILED",
                execution.get("message") or "执行发布失败",
                400,
            )
        conn.execute(
            "UPDATE agent_release_requests SET status = 'executed', gate_required = ?, gate_passed = ?, gate_snapshot_json = ?, blocked_reasons_json = ?, approved_by_id = CASE WHEN approved_by_id IS NULL OR trim(approved_by_id) = '' THEN ? ELSE approved_by_id END, approved_by_name = CASE WHEN approved_by_name IS NULL OR trim(approved_by_name) = '' THEN ? ELSE approved_by_name END, executed_at = ?, updated_at = ? WHERE release_id = ?",
            (
                1 if gate_result["gateRequired"] else 0,
                1 if gate_result["gatePassed"] else 0,
                _stringify_json(gate_result.get("snapshot") or {}, "{}"),
                _stringify_json(blocked_reasons, "[]"),
                operator["id"] or None,
                operator["name"] or None,
                now,
                now,
                release_id,
            ),
        )
        conn.commit()
        latest = _map_release_request_row(_load_release_request_row(conn, release_id))
        return success_response(
            data={
                "success": True,
                "message": "发布执行完成",
                "execution": execution,
                "request": latest,
            }
        )
    except Exception as e:
        return error_response("EXECUTE_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Versions
# ---------------------------------------------------------------------------


@router.get("/{agent_key}/versions")
async def list_agent_versions(
    agent_key: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        agent = conn.execute(
            "SELECT id, agent_key, name FROM agent_definitions WHERE agent_key = ? LIMIT 1",
            (normalized_key,),
        ).fetchone()
        if not agent:
            return success_response(
                data={
                    "agentKey": normalized_key,
                    "agentName": _default_agent_name(normalized_key),
                    "items": [],
                }
            )
        rows = conn.execute(
            "SELECT version, runtime_config_json, release_notes, is_current, is_candidate, created_at, updated_at FROM agent_versions WHERE agent_id = ? ORDER BY id DESC",
            (agent["id"],),
        ).fetchall()
        return success_response(
            data={
                "agentKey": _safe_text(agent["agent_key"], 80),
                "agentName": _safe_text(agent["name"], 100),
                "items": [
                    {
                        "version": _safe_text(row["version"], 40),
                        "runtimeConfig": _parse_json_safe(
                            row["runtime_config_json"], None
                        ),
                        "releaseNotes": _safe_text(row["release_notes"], 300),
                        "isCurrent": _safe_int(row["is_current"], 0) == 1,
                        "isCandidate": _safe_int(row["is_candidate"], 0) == 1,
                        "createdAt": _safe_int(row["created_at"], 0),
                        "updatedAt": _safe_int(row["updated_at"], 0),
                    }
                    for row in rows
                ],
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shadow Readiness
# ---------------------------------------------------------------------------


@router.get("/shadow-readiness")
async def get_shadow_readiness(
    days: int = Query(7, ge=1, le=90),
    agentKeys: str = Query(""),
    minShadowRuns: int | None = Query(None),
    maxFlaggedRate: float | None = Query(None),
    maxFallbackRate: float | None = Query(None),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        data = _build_shadow_readiness_data(
            conn,
            {
                "days": days,
                "agentKeys": agentKeys,
                "minShadowRuns": minShadowRuns,
                "maxFlaggedRate": maxFlaggedRate,
                "maxFallbackRate": maxFallbackRate,
            },
        )
        return success_response(data=data)
    except Exception:
        return success_response(
            data={
                "items": [],
                "summary": {"passCount": 0, "warnCount": 0, "failCount": 0},
            }
        )
    finally:
        conn.close()


@router.get("/shadow-readiness/gate")
async def get_shadow_readiness_gate(
    days: int = Query(0, ge=0, le=90),
    agentKeys: str = Query(""),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        data = _build_shadow_readiness_data(
            conn, {"days": days or 7, "agentKeys": agentKeys}
        )
        items = data.get("items") or []
        ready_items = [
            item
            for item in items
            if (item.get("readiness") or {}).get("canaryReady") is True
        ]
        blocked_items = [
            {
                "agentKey": item.get("agentKey") or "",
                "agentName": item.get("agentName") or "",
                "status": (item.get("readiness") or {}).get("status") or "fail",
                "reasons": (item.get("readiness") or {}).get("reasons") or [],
                "recommendation": (item.get("readiness") or {}).get("recommendation")
                or "",
            }
            for item in items
            if (item.get("readiness") or {}).get("canaryReady") is not True
        ]
        return success_response(
            data={
                "gatePassed": bool(items) and not blocked_items,
                "evaluatedAt": _now_ms(),
                "days": data.get("days", 7),
                "thresholds": data.get("thresholds") or {},
                "summary": {
                    "totalAgents": len(items),
                    "readyAgents": len(ready_items),
                    "blockedAgents": len(blocked_items),
                },
                "blockedItems": blocked_items,
            }
        )
    except Exception:
        return success_response(data={"gatePassed": False, "blockedItems": []})
    finally:
        conn.close()


@router.get("/shadow-readiness/config")
async def get_shadow_readiness_config(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        return success_response(data=_load_shadow_readiness_config_data(conn))
    except Exception:
        return success_response(data={})
    finally:
        conn.close()


@router.put("/shadow-readiness/config")
async def update_shadow_readiness_config(
    payload: ShadowReadinessConfigUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        current = _load_shadow_readiness_config_data(conn)
        raw = data.get("config") if isinstance(data.get("config"), dict) else data
        now = _now_ms()
        next_snapshot = _normalize_shadow_config_snapshot(
            {
                "configKey": DEFAULT_SHADOW_READINESS_CONFIG_KEY,
                "minShadowRuns": raw.get("minShadowRuns", current["minShadowRuns"]),
                "maxFlaggedRate": raw.get("maxFlaggedRate", current["maxFlaggedRate"]),
                "maxFallbackRate": raw.get(
                    "maxFallbackRate", current["maxFallbackRate"]
                ),
                "defaultDays": raw.get("defaultDays", current["defaultDays"]),
                "agentKeys": raw.get("agentKeys")
                if raw.get("agentKeys") is not None
                else raw.get("agentKeysText", current["agentKeys"]),
                "note": raw.get("note", current["note"]),
            }
        )
        if not next_snapshot["agentKeys"]:
            return error_response("INVALID_PARAMS", "agentKeys 不能为空", 400)
        diff = _build_shadow_config_diff(
            _normalize_shadow_config_snapshot(current), next_snapshot
        )
        conn.execute(
            """
            INSERT INTO agent_shadow_readiness_configs (
                config_key, min_shadow_runs, max_flagged_rate, max_fallback_rate,
                default_days, agent_keys_json, note, operator_id, operator_name,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(config_key) DO UPDATE SET
                min_shadow_runs = excluded.min_shadow_runs,
                max_flagged_rate = excluded.max_flagged_rate,
                max_fallback_rate = excluded.max_fallback_rate,
                default_days = excluded.default_days,
                agent_keys_json = excluded.agent_keys_json,
                note = excluded.note,
                operator_id = excluded.operator_id,
                operator_name = excluded.operator_name,
                updated_at = excluded.updated_at
            """,
            (
                DEFAULT_SHADOW_READINESS_CONFIG_KEY,
                next_snapshot["minShadowRuns"],
                next_snapshot["maxFlaggedRate"],
                next_snapshot["maxFallbackRate"],
                next_snapshot["defaultDays"],
                _stringify_json(next_snapshot["agentKeys"], "[]"),
                next_snapshot["note"],
                operator["id"] or None,
                operator["name"] or None,
                current["createdAt"] or now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO agent_shadow_readiness_config_logs (log_id, config_key, change_source, before_json, after_json, diff_json, note, operator_id, operator_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _create_shadow_config_log_id(),
                DEFAULT_SHADOW_READINESS_CONFIG_KEY,
                _safe_text(raw.get("changeSource"), 40).lower() or "manual",
                _stringify_json(_normalize_shadow_config_snapshot(current), "{}"),
                _stringify_json(next_snapshot, "{}"),
                _stringify_json(diff, "{}"),
                _safe_text(raw.get("changeNote"), 300) or next_snapshot["note"],
                operator["id"] or None,
                operator["name"] or None,
                now,
                now,
            ),
        )
        conn.commit()
        return success_response(
            data={
                "success": True,
                "changed": bool(diff),
                "config": {
                    **next_snapshot,
                    "operatorId": operator["id"],
                    "operatorName": operator["name"],
                    "updatedAt": now,
                },
                "diff": diff,
            }
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/shadow-readiness/config-logs")
async def get_shadow_readiness_config_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    configKey: str = Query(""),
    changeSource: str = Query(""),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = ["config_key = ?"]
        params: list[Any] = [
            _safe_text(configKey, 40) or DEFAULT_SHADOW_READINESS_CONFIG_KEY
        ]
        if _safe_text(changeSource, 40):
            where.append("change_source = ?")
            params.append(_safe_text(changeSource, 40).lower())
        where_sql = "WHERE " + " AND ".join(where)
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_shadow_readiness_config_logs {where_sql}",
                params,
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"SELECT log_id, config_key, change_source, before_json, after_json, diff_json, note, operator_id, operator_name, created_at, updated_at FROM agent_shadow_readiness_config_logs {where_sql} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return success_response(
            data={
                "items": [
                    {
                        "logId": row["log_id"],
                        "configKey": row["config_key"],
                        "changeSource": row["change_source"],
                        "before": _parse_json_safe(row["before_json"], {}) or {},
                        "after": _parse_json_safe(row["after_json"], {}) or {},
                        "diff": _parse_json_safe(row["diff_json"], {}) or {},
                        "note": _safe_text(row["note"], 300),
                        "operatorId": _safe_text(row["operator_id"], 80),
                        "operatorName": _safe_text(row["operator_name"], 80),
                        "createdAt": _safe_int(row["created_at"], 0),
                        "updatedAt": _safe_int(row["updated_at"], 0),
                    }
                    for row in rows
                ],
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": size,
                    "totalPages": max(1, (total + size - 1) // size),
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/shadow-readiness/config-suggest")
async def get_shadow_readiness_config_suggest(
    days: int = Query(0, ge=0, le=90),
    snapshotCount: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        current = _load_shadow_readiness_config_data(conn)
        rows = conn.execute(
            "SELECT snapshot_id, snapshot_at, items_json FROM agent_shadow_readiness_snapshots ORDER BY snapshot_at DESC, id DESC LIMIT ?",
            (snapshotCount,),
        ).fetchall()
        snapshot_items: list[dict[str, Any]] = []
        snapshot_ids: list[str] = []
        for row in rows:
            parsed = _parse_json_safe(row["items_json"], [])
            if isinstance(parsed, list) and parsed:
                snapshot_ids.append(_safe_text(row["snapshot_id"], 80))
                snapshot_items.extend(parsed)
        if not snapshot_items:
            live = _build_shadow_readiness_data(
                conn, {"days": days or current["defaultDays"]}
            )
            snapshot_items = live.get("items") or []
        per_agent: dict[str, dict[str, Any]] = {}
        for item in snapshot_items:
            key = _normalize_agent_key(item.get("agentKey"))
            if not key:
                continue
            stat = per_agent.setdefault(
                key,
                {
                    "shadowRuns": [],
                    "flaggedRates": [],
                    "fallbackRates": [],
                    "passCount": 0,
                },
            )
            stat["shadowRuns"].append(max(0, _safe_int(item.get("shadowRuns"), 0)))
            stat["flaggedRates"].append(_clamp_number(item.get("flaggedRate"), 0, 1, 0))
            stat["fallbackRates"].append(
                max(
                    _clamp_number(item.get("fallbackRate"), 0, 1, 0),
                    _clamp_number(item.get("failedRate"), 0, 1, 0),
                )
            )
            if (item.get("readiness") or {}).get("status") == "pass":
                stat["passCount"] += 1
        agent_stats = list(per_agent.values())
        all_shadow_runs = [
            sum(item["shadowRuns"]) / max(len(item["shadowRuns"]), 1)
            for item in agent_stats
            if item["shadowRuns"]
        ]
        all_flagged_rates = [
            sum(item["flaggedRates"]) / max(len(item["flaggedRates"]), 1)
            for item in agent_stats
            if item["flaggedRates"]
        ]
        all_fallback_rates = [
            sum(item["fallbackRates"]) / max(len(item["fallbackRates"]), 1)
            for item in agent_stats
            if item["fallbackRates"]
        ]
        suggested = _normalize_shadow_config_snapshot(
            {
                "configKey": current["configKey"],
                "minShadowRuns": max(
                    20,
                    round(
                        _pick_percentile(all_shadow_runs, 0.6)
                        or current["minShadowRuns"]
                    ),
                ),
                "maxFlaggedRate": round(
                    _clamp_number(
                        (
                            _pick_percentile(all_flagged_rates, 0.75)
                            or current["maxFlaggedRate"]
                        )
                        + 0.02,
                        0.05,
                        0.8,
                        current["maxFlaggedRate"],
                    ),
                    4,
                ),
                "maxFallbackRate": round(
                    _clamp_number(
                        (
                            _pick_percentile(all_fallback_rates, 0.75)
                            or current["maxFallbackRate"]
                        )
                        + 0.01,
                        0.01,
                        0.3,
                        current["maxFallbackRate"],
                    ),
                    4,
                ),
                "defaultDays": current["defaultDays"],
                "agentKeys": current["agentKeys"],
                "note": current["note"],
            }
        )
        baseline = _normalize_shadow_config_snapshot(current)
        diff = _build_shadow_config_diff(baseline, suggested)
        reasons = [
            f"基于最近 {len(snapshot_ids)} 份 Shadow 快照生成建议"
            if snapshot_ids
            else "暂无快照，已使用当前实时准入数据生成建议",
            f"建议最小样本：{suggested['minShadowRuns']}（当前 {baseline['minShadowRuns']}）",
            f"建议命中率阈值：{(suggested['maxFlaggedRate'] * 100):.2f}%（当前 {(baseline['maxFlaggedRate'] * 100):.2f}%）",
            f"建议 fallback 阈值：{(suggested['maxFallbackRate'] * 100):.2f}%（当前 {(baseline['maxFallbackRate'] * 100):.2f}%）",
        ]
        return success_response(
            data={
                "configKey": current["configKey"],
                "generatedAt": _now_ms(),
                "window": {
                    "days": days or current["defaultDays"],
                    "snapshotCount": snapshotCount,
                    "usedSnapshotCount": len(snapshot_ids),
                },
                "baseline": baseline,
                "suggested": suggested,
                "diff": diff,
                "reasons": reasons,
                "references": {"snapshotIds": snapshot_ids},
            }
        )
    except Exception:
        return success_response(data={"suggested": None, "reasons": []})
    finally:
        conn.close()


@router.get("/shadow-readiness/snapshots")
async def list_shadow_readiness_snapshots(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    days: int = Query(0, ge=0, le=180),
    includeItems: bool = Query(False),
    source: str = Query(""),
    agent_key: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where_parts: list[str] = []
        params: list[Any] = []
        if days > 0:
            where_parts.append("snapshot_at >= ?")
            params.append(_now_ms() - days * 24 * 60 * 60 * 1000)
        if _safe_text(source, 40):
            where_parts.append("source = ?")
            params.append(_safe_text(source, 40))
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_shadow_readiness_snapshots {where_sql}",
                params,
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"SELECT snapshot_id, snapshot_date, snapshot_at, days, agent_keys_json, thresholds_json, summary_json, items_json, source, operator_id, operator_name, created_at, updated_at FROM agent_shadow_readiness_snapshots {where_sql} ORDER BY snapshot_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        items = []
        for row in rows:
            parsed_items = (
                _parse_json_safe(row["items_json"], []) if includeItems else []
            )
            parsed_agent_keys = _parse_json_safe(row["agent_keys_json"], []) or []
            if agent_key and _normalize_agent_key(agent_key) not in parsed_agent_keys:
                continue
            items.append(
                {
                    "snapshotId": row["snapshot_id"],
                    "snapshotDate": row["snapshot_date"],
                    "snapshotAt": _safe_int(row["snapshot_at"], 0),
                    "days": _safe_int(row["days"], 0),
                    "agentKeys": parsed_agent_keys
                    if isinstance(parsed_agent_keys, list)
                    else [],
                    "thresholds": _parse_json_safe(row["thresholds_json"], {}) or {},
                    "summary": _parse_json_safe(row["summary_json"], {}) or {},
                    "items": parsed_items if isinstance(parsed_items, list) else [],
                    "source": _safe_text(row["source"], 40),
                    "operatorId": _safe_text(row["operator_id"], 80),
                    "operatorName": _safe_text(row["operator_name"], 80),
                    "createdAt": _safe_int(row["created_at"], 0),
                    "updatedAt": _safe_int(row["updated_at"], 0),
                }
            )
        return success_response(
            data={
                "items": items,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": size,
                    "totalPages": max(1, (total + size - 1) // size),
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/shadow-readiness/snapshots")
async def create_shadow_readiness_snapshot(
    payload: ShadowSnapshotCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        options = data.get("config") if isinstance(data.get("config"), dict) else data
        readiness = _build_shadow_readiness_data(conn, options)
        now = _now_ms()
        snapshot_id = _create_shadow_snapshot_id()
        snapshot_date = _to_date_key(now)
        agent_keys = _normalize_agent_keys(options.get("agentKeys")) or [
            item.get("agentKey")
            for item in readiness.get("items") or []
            if item.get("agentKey")
        ]
        conn.execute(
            "INSERT INTO agent_shadow_readiness_snapshots (snapshot_id, snapshot_date, snapshot_at, days, agent_keys_json, thresholds_json, summary_json, items_json, source, operator_id, operator_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                snapshot_date,
                now,
                _safe_int(readiness.get("days"), 7),
                _stringify_json(agent_keys, "[]"),
                _stringify_json(readiness.get("thresholds") or {}, "{}"),
                _stringify_json(readiness.get("summary") or {}, "{}"),
                _stringify_json(readiness.get("items") or [], "[]"),
                _safe_text(options.get("source"), 40) or "manual",
                operator["id"] or None,
                operator["name"] or None,
                now,
                now,
            ),
        )
        conn.commit()
        return success_response(
            data={
                "snapshotId": snapshot_id,
                "snapshotDate": snapshot_date,
                "snapshotAt": now,
                "source": _safe_text(options.get("source"), 40) or "manual",
                "operatorId": operator["id"],
                "operatorName": operator["name"],
                "data": readiness,
            },
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Runs
# ---------------------------------------------------------------------------


@router.get("/{agent_key}/runs")
async def list_agent_runs(
    agent_key: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    mode: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        where = ["agent_key = ?"]
        params: list[Any] = [normalized_key]
        normalized_status = _normalize_run_status(status, "") if status else ""
        normalized_mode = _normalize_run_mode(mode, "") if mode else ""
        if normalized_status:
            where.append("status = ?")
            params.append(normalized_status)
        if normalized_mode:
            where.append("mode = ?")
            params.append(normalized_mode)
        where_sql = "WHERE " + " AND ".join(where)
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_runs {where_sql}", params
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"SELECT run_id, agent_key, agent_version, trigger_source, mode, status, replay_source_run_id, replay_source_agent_key, replay_reason, decision, decision_source, error_type, error_message, latency_ms, token_used, cost_micros, risk_score, operator_id, operator_name, started_at, ended_at, created_at FROM agent_runs {where_sql} ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return success_response(
            data={
                "items": [_map_run_item(row) for row in rows],
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 0,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        detail = _get_run_detail(conn, _safe_text(run_id, 80))
        if detail is None:
            return error_response("RUN_NOT_FOUND", "Run 不存在", 404)
        return success_response(data=detail)
    except Exception as e:
        return error_response("READ_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/{agent_key}/runs/{run_id}")
async def get_agent_run(
    agent_key: str, run_id: str, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        detail = _get_run_detail(
            conn, _safe_text(run_id, 80), _normalize_agent_key(agent_key)
        )
        if detail is None:
            return error_response("RUN_NOT_FOUND", "Run 不存在", 404)
        return success_response(data=detail)
    except Exception as e:
        return error_response("READ_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Stats
# ---------------------------------------------------------------------------


@router.get("/{agent_key}/stats")
async def get_agent_stats(
    agent_key: str,
    days: int = Query(30, ge=1, le=90),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        since = _now_ms() - days * 24 * 60 * 60 * 1000
        summary = conn.execute(
            """
            SELECT
                COUNT(1) AS run_count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN status = 'fallback' THEN 1 ELSE 0 END) AS fallback_count,
                SUM(CASE WHEN decision = 'manual_review' THEN 1 ELSE 0 END) AS manual_review_count,
                SUM(CASE WHEN mode = 'shadow' THEN 1 ELSE 0 END) AS shadow_run_count,
                SUM(CASE WHEN mode = 'shadow' AND decision <> 'approve' THEN 1 ELSE 0 END) AS shadow_flagged_count,
                SUM(CASE WHEN mode = 'shadow' AND output_json LIKE '%\"blocked\":true%' THEN 1 ELSE 0 END) AS shadow_blocked_count,
                AVG(COALESCE(latency_ms, 0)) AS avg_latency_ms,
                SUM(COALESCE(token_used, 0)) AS token_used_total,
                SUM(COALESCE(cost_micros, 0)) AS cost_micros_total
            FROM agent_runs
            WHERE agent_key = ? AND started_at >= ?
            """,
            (normalized_key, since),
        ).fetchone()
        trend = conn.execute(
            """
            SELECT substr(datetime(started_at / 1000, 'unixepoch', 'localtime'), 1, 10) AS metric_date,
                   COUNT(1) AS run_count,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                   SUM(CASE WHEN status = 'fallback' THEN 1 ELSE 0 END) AS fallback_count,
                   AVG(COALESCE(latency_ms, 0)) AS avg_latency_ms,
                   SUM(COALESCE(token_used, 0)) AS token_used_total,
                   SUM(COALESCE(cost_micros, 0)) AS cost_micros_total
            FROM agent_runs
            WHERE agent_key = ? AND started_at >= ?
            GROUP BY metric_date
            ORDER BY metric_date DESC
            """,
            (normalized_key, since),
        ).fetchall()
        mode_breakdown = conn.execute(
            "SELECT mode, COUNT(1) AS run_count FROM agent_runs WHERE agent_key = ? AND started_at >= ? GROUP BY mode ORDER BY run_count DESC, mode ASC",
            (normalized_key, since),
        ).fetchall()
        decision_breakdown = conn.execute(
            "SELECT decision, COUNT(1) AS run_count FROM agent_runs WHERE agent_key = ? AND started_at >= ? GROUP BY decision ORDER BY run_count DESC, decision ASC",
            (normalized_key, since),
        ).fetchall()
        shadow_decisions = conn.execute(
            "SELECT decision, COUNT(1) AS run_count FROM agent_runs WHERE agent_key = ? AND started_at >= ? AND mode = 'shadow' GROUP BY decision ORDER BY run_count DESC, decision ASC",
            (normalized_key, since),
        ).fetchall()
        shadow_daily = conn.execute(
            "SELECT substr(datetime(started_at / 1000, 'unixepoch', 'localtime'), 1, 10) AS metric_date, COUNT(1) AS shadow_run_count, SUM(CASE WHEN decision <> 'approve' THEN 1 ELSE 0 END) AS risk_hit_count FROM agent_runs WHERE agent_key = ? AND started_at >= ? AND mode = 'shadow' GROUP BY metric_date ORDER BY metric_date DESC",
            (normalized_key, since),
        ).fetchall()
        shadow_rules = conn.execute(
            "SELECT output_json, trace_json FROM agent_runs WHERE agent_key = ? AND started_at >= ? AND mode = 'shadow' ORDER BY started_at DESC LIMIT 2000",
            (normalized_key, since),
        ).fetchall()
        metrics = conn.execute(
            "SELECT metric_date, mode, run_count, success_count, failed_count, fallback_count, manual_review_count, avg_latency_ms, p95_latency_ms, token_used_total, cost_micros_total, updated_at FROM agent_metrics_daily WHERE agent_key = ? ORDER BY metric_date DESC, mode ASC LIMIT ?",
            (normalized_key, days * 2),
        ).fetchall()
        shadow_rule_map: dict[str, int] = {}
        for row in shadow_rules:
            output = _parse_json_safe(row["output_json"], None)
            trace = _parse_json_safe(row["trace_json"], None)
            rule = (
                _safe_text((output or {}).get("rule") or (trace or {}).get("rule"), 100)
                or "unknown"
            )
            shadow_rule_map[rule] = shadow_rule_map.get(rule, 0) + 1
        run_count = _safe_int(summary["run_count"], 0) if summary else 0
        success_count = _safe_int(summary["success_count"], 0) if summary else 0
        total_shadow_runs = _safe_int(summary["shadow_run_count"], 0) if summary else 0
        flagged_shadow_runs = (
            _safe_int(summary["shadow_flagged_count"], 0) if summary else 0
        )
        blocked_shadow_runs = (
            _safe_int(summary["shadow_blocked_count"], 0) if summary else 0
        )
        return success_response(
            data={
                "days": days,
                "summary": {
                    "runCount": run_count,
                    "successCount": success_count,
                    "failedCount": _safe_int(summary["failed_count"], 0)
                    if summary
                    else 0,
                    "fallbackCount": _safe_int(summary["fallback_count"], 0)
                    if summary
                    else 0,
                    "manualReviewCount": _safe_int(summary["manual_review_count"], 0)
                    if summary
                    else 0,
                    "successRate": round(success_count / run_count, 4)
                    if run_count > 0
                    else 0,
                    "avgLatencyMs": round(_safe_number(summary["avg_latency_ms"], 0), 2)
                    if summary
                    else 0,
                    "tokenUsedTotal": _safe_int(summary["token_used_total"], 0)
                    if summary
                    else 0,
                    "costMicrosTotal": _safe_int(summary["cost_micros_total"], 0)
                    if summary
                    else 0,
                },
                "modeBreakdown": [
                    {
                        "mode": _safe_text(row["mode"], 20) or "unknown",
                        "runCount": _safe_int(row["run_count"], 0),
                    }
                    for row in mode_breakdown
                ],
                "decisionBreakdown": [
                    {
                        "decision": _safe_text(row["decision"], 40) or "unknown",
                        "runCount": _safe_int(row["run_count"], 0),
                    }
                    for row in decision_breakdown
                ],
                "shadowRisk": {
                    "totalShadowRuns": total_shadow_runs,
                    "flaggedShadowRuns": flagged_shadow_runs,
                    "blockedShadowRuns": blocked_shadow_runs,
                    "flaggedRate": round(flagged_shadow_runs / total_shadow_runs, 4)
                    if total_shadow_runs > 0
                    else 0,
                    "blockedRate": round(blocked_shadow_runs / total_shadow_runs, 4)
                    if total_shadow_runs > 0
                    else 0,
                    "byDecision": [
                        {
                            "decision": _safe_text(row["decision"], 40) or "unknown",
                            "runCount": _safe_int(row["run_count"], 0),
                        }
                        for row in shadow_decisions
                    ],
                    "byRule": [
                        {"rule": rule, "runCount": count}
                        for rule, count in sorted(
                            shadow_rule_map.items(),
                            key=lambda item: (-item[1], item[0]),
                        )[:20]
                    ],
                    "daily": [
                        {
                            "metricDate": row["metric_date"],
                            "shadowRunCount": _safe_int(row["shadow_run_count"], 0),
                            "riskHitCount": _safe_int(row["risk_hit_count"], 0),
                            "riskHitRate": round(
                                _safe_int(row["risk_hit_count"], 0)
                                / _safe_int(row["shadow_run_count"], 1),
                                4,
                            )
                            if _safe_int(row["shadow_run_count"], 0) > 0
                            else 0,
                        }
                        for row in shadow_daily
                    ],
                },
                "trend": [
                    {
                        "metricDate": row["metric_date"],
                        "runCount": _safe_int(row["run_count"], 0),
                        "successCount": _safe_int(row["success_count"], 0),
                        "failedCount": _safe_int(row["failed_count"], 0),
                        "fallbackCount": _safe_int(row["fallback_count"], 0),
                        "avgLatencyMs": round(
                            _safe_number(row["avg_latency_ms"], 0), 2
                        ),
                        "tokenUsedTotal": _safe_int(row["token_used_total"], 0),
                        "costMicrosTotal": _safe_int(row["cost_micros_total"], 0),
                    }
                    for row in trend
                ],
                "dailyMetrics": [
                    {
                        "metricDate": row["metric_date"],
                        "mode": _safe_text(row["mode"], 20) or "all",
                        "runCount": _safe_int(row["run_count"], 0),
                        "successCount": _safe_int(row["success_count"], 0),
                        "failedCount": _safe_int(row["failed_count"], 0),
                        "fallbackCount": _safe_int(row["fallback_count"], 0),
                        "manualReviewCount": _safe_int(row["manual_review_count"], 0),
                        "avgLatencyMs": round(
                            _safe_number(row["avg_latency_ms"], 0), 2
                        ),
                        "p95LatencyMs": round(
                            _safe_number(row["p95_latency_ms"], 0), 2
                        ),
                        "tokenUsedTotal": _safe_int(row["token_used_total"], 0),
                        "costMicrosTotal": _safe_int(row["cost_micros_total"], 0),
                        "updatedAt": row["updated_at"],
                    }
                    for row in metrics
                ],
            }
        )
    except Exception:
        return success_response(
            data={
                "summary": {
                    "runCount": 0,
                    "successCount": 0,
                    "failedCount": 0,
                    "fallbackCount": 0,
                    "manualReviewCount": 0,
                    "successRate": 0,
                    "avgLatencyMs": 0,
                    "tokenUsedTotal": 0,
                    "costMicrosTotal": 0,
                },
                "modeBreakdown": [],
                "decisionBreakdown": [],
                "shadowRisk": {
                    "totalShadowRuns": 0,
                    "flaggedShadowRuns": 0,
                    "blockedShadowRuns": 0,
                    "flaggedRate": 0,
                    "blockedRate": 0,
                    "byDecision": [],
                    "byRule": [],
                    "daily": [],
                },
                "trend": [],
                "dailyMetrics": [],
            }
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Evals
# ---------------------------------------------------------------------------


@router.get("/{agent_key}/evals")
async def list_agent_evals(
    agent_key: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    datasetName: str = Query(""),
    templateProfile: str = Query(""),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        where = ["agent_key = ?"]
        params: list[Any] = [normalized_key]
        normalized_status = _normalize_eval_status(status, "") if status else ""
        profile = (
            _normalize_eval_template_profile(templateProfile, "")
            if templateProfile
            else ""
        )
        if normalized_status:
            where.append("status = ?")
            params.append(normalized_status)
        if _safe_text(datasetName, 80):
            where.append("dataset_name = ?")
            params.append(_safe_text(datasetName, 80))
        if profile:
            where.append("template_profile = ?")
            params.append(profile)
        where_sql = "WHERE " + " AND ".join(where)
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_eval_runs {where_sql}", params
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"SELECT * FROM agent_eval_runs {where_sql} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return success_response(
            data={
                "items": [_map_eval_run_row(row) for row in rows],
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 0,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/{agent_key}/evals")
async def create_agent_eval(
    agent_key: str, payload: EvalRunCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        eval_data = data.get("config") if isinstance(data.get("config"), dict) else data
        result = _create_eval_run_record(conn, agent_key, eval_data, operator)
        return success_response(data=result, status_code=201)
    except Exception as e:
        return error_response("EVAL_CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/{agent_key}/evals/compare")
async def compare_agent_evals(
    agent_key: str,
    baseEvalRunId: str = Query(""),
    targetEvalRunId: str = Query(""),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        base_id = _safe_text(baseEvalRunId, 80)
        target_id = _safe_text(targetEvalRunId, 80)
        if not base_id or not target_id:
            return error_response(
                "INVALID_PARAMS", "baseEvalRunId 与 targetEvalRunId 不能为空", 400
            )
        if base_id == target_id:
            return error_response(
                "INVALID_PARAMS", "baseEvalRunId 与 targetEvalRunId 不能相同", 400
            )
        base_run = conn.execute(
            "SELECT * FROM agent_eval_runs WHERE eval_run_id = ? AND agent_key = ? LIMIT 1",
            (base_id, normalized_key),
        ).fetchone()
        target_run = conn.execute(
            "SELECT * FROM agent_eval_runs WHERE eval_run_id = ? AND agent_key = ? LIMIT 1",
            (target_id, normalized_key),
        ).fetchone()
        if base_run is None or target_run is None:
            return error_response(
                "NOT_FOUND", "对比任务不存在或与当前 Agent 不匹配", 404
            )
        base_cases = {
            row["case_key"]: row
            for row in conn.execute(
                "SELECT case_key, source_ref, expected_decision, actual_decision, passed, error_type, error_message FROM agent_eval_cases WHERE eval_run_id = ? ORDER BY id ASC",
                (base_id,),
            ).fetchall()
        }
        target_cases = {
            row["case_key"]: row
            for row in conn.execute(
                "SELECT case_key, source_ref, expected_decision, actual_decision, passed, error_type, error_message FROM agent_eval_cases WHERE eval_run_id = ? ORDER BY id ASC",
                (target_id,),
            ).fetchall()
        }
        regressions = []
        improvements = []
        stable_passed = 0
        stable_failed = 0
        missing_in_target = 0
        added_in_target = 0
        for case_key in sorted(set(base_cases) | set(target_cases)):
            base_case = base_cases.get(case_key)
            target_case = target_cases.get(case_key)
            if base_case is None and target_case is not None:
                added_in_target += 1
                continue
            if base_case is not None and target_case is None:
                missing_in_target += 1
                continue
            base_passed = _safe_int(base_case["passed"], 0) == 1
            target_passed = _safe_int(target_case["passed"], 0) == 1
            if base_passed and not target_passed:
                if len(regressions) < 50:
                    regressions.append(
                        {
                            "caseKey": case_key,
                            "sourceRef": _safe_text(
                                (target_case or base_case)["source_ref"], 160
                            ),
                            "expectedDecision": _safe_text(
                                (target_case or base_case)["expected_decision"], 40
                            ),
                            "baseActualDecision": _safe_text(
                                base_case["actual_decision"], 40
                            ),
                            "targetActualDecision": _safe_text(
                                target_case["actual_decision"], 40
                            ),
                            "basePassed": base_passed,
                            "targetPassed": target_passed,
                            "targetErrorType": _safe_text(
                                target_case["error_type"], 80
                            ),
                            "targetErrorMessage": _safe_text(
                                target_case["error_message"], 300
                            ),
                        }
                    )
            elif not base_passed and target_passed:
                if len(improvements) < 50:
                    improvements.append(
                        {
                            "caseKey": case_key,
                            "sourceRef": _safe_text(
                                (target_case or base_case)["source_ref"], 160
                            ),
                            "expectedDecision": _safe_text(
                                (target_case or base_case)["expected_decision"], 40
                            ),
                            "baseActualDecision": _safe_text(
                                base_case["actual_decision"], 40
                            ),
                            "targetActualDecision": _safe_text(
                                target_case["actual_decision"], 40
                            ),
                            "basePassed": base_passed,
                            "targetPassed": target_passed,
                        }
                    )
            elif base_passed and target_passed:
                stable_passed += 1
            else:
                stable_failed += 1
        ratio = lambda passed, total: round(passed / total, 4) if total > 0 else 0
        metric = lambda base_value, target_value: {
            "base": _safe_number(base_value, 0),
            "target": _safe_number(target_value, 0),
            "delta": round(
                _safe_number(target_value, 0) - _safe_number(base_value, 0), 6
            ),
        }
        total_compared_cases = (
            stable_passed + stable_failed + len(regressions) + len(improvements)
        )
        return success_response(
            data={
                "baseEvalRun": {
                    "evalRunId": base_run["eval_run_id"],
                    "datasetName": _safe_text(base_run["dataset_name"], 80),
                    "datasetVersion": _safe_text(base_run["dataset_version"], 40),
                    "templateProfile": _safe_text(base_run["template_profile"], 20)
                    or "standard",
                    "mode": _safe_text(base_run["mode"], 20) or "offline",
                    "status": _safe_text(base_run["status"], 20),
                    "createdAt": base_run["created_at"],
                },
                "targetEvalRun": {
                    "evalRunId": target_run["eval_run_id"],
                    "datasetName": _safe_text(target_run["dataset_name"], 80),
                    "datasetVersion": _safe_text(target_run["dataset_version"], 40),
                    "templateProfile": _safe_text(target_run["template_profile"], 20)
                    or "standard",
                    "mode": _safe_text(target_run["mode"], 20) or "offline",
                    "status": _safe_text(target_run["status"], 20),
                    "createdAt": target_run["created_at"],
                },
                "metrics": {
                    "passRate": metric(
                        ratio(
                            _safe_int(base_run["passed_cases"], 0),
                            _safe_int(base_run["total_cases"], 0),
                        ),
                        ratio(
                            _safe_int(target_run["passed_cases"], 0),
                            _safe_int(target_run["total_cases"], 0),
                        ),
                    ),
                    "precisionScore": metric(
                        base_run["precision_score"], target_run["precision_score"]
                    ),
                    "recallScore": metric(
                        base_run["recall_score"], target_run["recall_score"]
                    ),
                    "f1Score": metric(base_run["f1_score"], target_run["f1_score"]),
                    "falsePositiveRate": metric(
                        base_run["false_positive_rate"],
                        target_run["false_positive_rate"],
                    ),
                    "avgLatencyMs": metric(
                        base_run["avg_latency_ms"], target_run["avg_latency_ms"]
                    ),
                    "tokenUsedTotal": metric(
                        base_run["token_used_total"], target_run["token_used_total"]
                    ),
                    "costMicrosTotal": metric(
                        base_run["cost_micros_total"], target_run["cost_micros_total"]
                    ),
                },
                "caseSummary": {
                    "totalComparedCases": total_compared_cases,
                    "regressions": len(regressions),
                    "improvements": len(improvements),
                    "stablePassed": stable_passed,
                    "stableFailed": stable_failed,
                    "missingInTarget": missing_in_target,
                    "addedInTarget": added_in_target,
                },
                "regressions": regressions,
                "improvements": improvements,
            }
        )
    except Exception as e:
        return error_response("COMPARE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/{agent_key}/evals/{eval_run_id}")
async def get_agent_eval(
    agent_key: str, eval_run_id: str, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        detail = _get_eval_run_detail(
            conn, _safe_text(eval_run_id, 80), _normalize_agent_key(agent_key), 1, 200
        )
        if detail is None:
            return error_response("EVAL_NOT_FOUND", "Eval run 不存在", 404)
        return success_response(data=detail)
    except Exception as e:
        return error_response("READ_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/{agent_key}/evals/{eval_run_id}/cases/{case_key}/replay")
async def replay_eval_case(
    agent_key: str,
    eval_run_id: str,
    case_key: str,
    payload: ReplayRequest | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        eval_row = conn.execute(
            "SELECT dataset_name, dataset_version, template_profile FROM agent_eval_runs WHERE eval_run_id = ? AND agent_key = ? LIMIT 1",
            (_safe_text(eval_run_id, 80), _normalize_agent_key(agent_key)),
        ).fetchone()
        if eval_row is None:
            return error_response(
                "EVAL_NOT_FOUND", "评测任务不存在或与当前 Agent 不匹配", 404
            )
        case_row = conn.execute(
            "SELECT case_key, source_ref, expected_decision, actual_decision, passed, score, input_json, expected_json, actual_json, trace_json, error_type, error_message, latency_ms, token_used, cost_micros FROM agent_eval_cases WHERE eval_run_id = ? AND case_key = ? LIMIT 1",
            (_safe_text(eval_run_id, 80), _safe_text(case_key, 120)),
        ).fetchone()
        if case_row is None:
            return error_response("NOT_FOUND", "评测用例不存在", 404)
        replay_payload = {
            "mode": "replay",
            "status": "success" if _safe_int(case_row["passed"], 0) == 1 else "failed",
            "triggerSource": "admin_eval_case_replay",
            "decision": _safe_text(case_row["actual_decision"], 40)
            or _safe_text(case_row["expected_decision"], 40)
            or "manual_review",
            "decisionSource": "eval_case_replay",
            "reason": _safe_text(
                (payload.model_dump() if payload else {}).get("replayReason"), 300
            )
            or f"评测回放 {eval_run_id}/{case_key}",
            "riskScore": 0.2 if _safe_int(case_row["passed"], 0) == 1 else 0.85,
            "latencyMs": _safe_int(case_row["latency_ms"], 180),
            "tokenUsed": _safe_int(case_row["token_used"], 0),
            "costMicros": _safe_int(case_row["cost_micros"], 0),
            "errorType": ""
            if _safe_int(case_row["passed"], 0) == 1
            else (_safe_text(case_row["error_type"], 80) or "eval_regression"),
            "errorMessage": ""
            if _safe_int(case_row["passed"], 0) == 1
            else (_safe_text(case_row["error_message"], 300) or "评测回归用例"),
            "input": _parse_json_safe(case_row["input_json"], None)
            or {"case_key": case_key},
            "output": {
                "decision": _safe_text(case_row["actual_decision"], 40),
                "expected_decision": _safe_text(case_row["expected_decision"], 40),
                "passed": _safe_int(case_row["passed"], 0) == 1,
                "score": _safe_number(case_row["score"], 0),
                "eval_run_id": eval_run_id,
                "case_key": case_key,
                "source_ref": _safe_text(case_row["source_ref"], 160),
                "expected": _parse_json_safe(case_row["expected_json"], None),
                "actual": _parse_json_safe(case_row["actual_json"], None),
            },
            "trace": {
                "replay_context": {
                    "source": "eval_case",
                    "eval_run_id": eval_run_id,
                    "case_key": case_key,
                    "dataset_name": _safe_text(eval_row["dataset_name"], 80),
                    "dataset_version": _safe_text(eval_row["dataset_version"], 40),
                    "template_profile": _safe_text(eval_row["template_profile"], 20),
                    "source_ref": _safe_text(case_row["source_ref"], 160),
                    "passed": _safe_int(case_row["passed"], 0) == 1,
                },
                "case_trace": _parse_json_safe(case_row["trace_json"], None),
            },
            "replaySourceRunId": "",
            "replaySourceAgentKey": _normalize_agent_key(agent_key),
            "replayReason": _safe_text(
                (payload.model_dump() if payload else {}).get("replayReason"), 300
            )
            or "评测回归用例回放",
        }
        return success_response(
            data=_create_run_record(
                conn,
                agent_key,
                replay_payload,
                operator,
                {
                    "defaultMode": "replay",
                    "defaultTriggerSource": "admin_eval_case_replay",
                    "defaultDecisionSource": "eval_case_replay",
                    "defaultInputText": "评测回放输入样例",
                    "defaultSuccessReason": "评测回放通过",
                    "defaultFailedReason": "评测回放失败",
                    "successMessage": "评测回放运行记录已创建",
                },
            ),
            status_code=201,
        )
    except Exception as e:
        return error_response("REPLAY_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Eval Datasets
# ---------------------------------------------------------------------------


@router.get("/{agent_key}/eval-datasets")
async def list_eval_datasets(
    agent_key: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    status: str = Query(""),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        where = ["agent_key = ?"]
        params: list[Any] = [normalized_key]
        if _safe_text(search, 80):
            where.append("(name LIKE ? OR version LIKE ?)")
            params.extend(
                [f"%{_safe_text(search, 80)}%", f"%{_safe_text(search, 80)}%"]
            )
        if _safe_text(status, 20) and _safe_text(status, 20).lower() != "all":
            where.append("status = ?")
            params.append(_safe_text(status, 20).lower())
        where_sql = "WHERE " + " AND ".join(where)
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_eval_datasets {where_sql}", params
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"SELECT dataset_id, agent_key, name, version, source_type, description, tags_json, case_count, active_case_count, status, operator_id, operator_name, created_at, updated_at FROM agent_eval_datasets {where_sql} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return success_response(
            data={
                "items": [
                    {
                        "datasetId": row["dataset_id"],
                        "agentKey": row["agent_key"],
                        "name": _safe_text(row["name"], 80),
                        "version": _safe_text(row["version"], 40),
                        "sourceType": _safe_text(row["source_type"], 40),
                        "description": _safe_text(row["description"], 500),
                        "tags": _parse_json_safe(row["tags_json"], []),
                        "caseCount": _safe_int(row["case_count"], 0),
                        "activeCaseCount": _safe_int(row["active_case_count"], 0),
                        "status": _safe_text(row["status"], 20) or "active",
                        "operatorId": _safe_text(row["operator_id"], 80),
                        "operatorName": _safe_text(row["operator_name"], 80),
                        "createdAt": row["created_at"],
                        "updatedAt": row["updated_at"],
                    }
                    for row in rows
                ],
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 0,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/{agent_key}/eval-datasets/{dataset_id}/cases")
async def list_eval_dataset_cases(
    agent_key: str,
    dataset_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    activeOnly: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        dataset_key = _safe_text(dataset_id, 80)
        dataset = conn.execute(
            "SELECT dataset_id, agent_key, name, version, source_type, description, case_count, active_case_count, status, created_at, updated_at FROM agent_eval_datasets WHERE dataset_id = ? AND agent_key = ? LIMIT 1",
            (dataset_key, normalized_key),
        ).fetchone()
        if dataset is None:
            return error_response("NOT_FOUND", "样本集不存在", 404)
        where = ["dataset_id = ?"]
        params: list[Any] = [dataset_key]
        if activeOnly:
            where.append("is_active = 1")
        if _safe_text(search, 80):
            where.append("(case_key LIKE ? OR source_ref LIKE ?)")
            params.extend(
                [f"%{_safe_text(search, 80)}%", f"%{_safe_text(search, 80)}%"]
            )
        where_sql = "WHERE " + " AND ".join(where)
        total = _safe_int(
            conn.execute(
                f"SELECT COUNT(1) AS total FROM agent_eval_dataset_cases {where_sql}",
                params,
            ).fetchone()["total"],
            0,
        )
        rows = conn.execute(
            f"SELECT case_key, source_ref, risk_level, tags_json, input_json, expected_decision, expected_json, note, is_active, created_at, updated_at FROM agent_eval_dataset_cases {where_sql} ORDER BY id ASC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return success_response(
            data={
                "dataset": {
                    "datasetId": dataset["dataset_id"],
                    "agentKey": dataset["agent_key"],
                    "name": _safe_text(dataset["name"], 80),
                    "version": _safe_text(dataset["version"], 40),
                    "sourceType": _safe_text(dataset["source_type"], 40),
                    "description": _safe_text(dataset["description"], 500),
                    "caseCount": _safe_int(dataset["case_count"], 0),
                    "activeCaseCount": _safe_int(dataset["active_case_count"], 0),
                    "status": _safe_text(dataset["status"], 20) or "active",
                    "createdAt": dataset["created_at"],
                    "updatedAt": dataset["updated_at"],
                },
                "cases": [
                    {
                        "caseKey": row["case_key"],
                        "sourceRef": _safe_text(row["source_ref"], 160),
                        "riskLevel": _safe_text(row["risk_level"], 40),
                        "tags": _parse_json_safe(row["tags_json"], []),
                        "input": _parse_json_safe(row["input_json"], None),
                        "expectedDecision": _safe_text(row["expected_decision"], 40),
                        "expected": _parse_json_safe(row["expected_json"], None),
                        "note": _safe_text(row["note"], 300),
                        "isActive": _safe_int(row["is_active"], 0) == 1,
                        "createdAt": row["created_at"],
                        "updatedAt": row["updated_at"],
                    }
                    for row in rows
                ],
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 0,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.patch("/{agent_key}/eval-datasets/{dataset_id}/cases/{case_key}")
async def update_eval_case(
    agent_key: str,
    dataset_id: str,
    case_key: str,
    payload: EvalCaseUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        data = (
            payload.model_dump(exclude_none=True)
            if hasattr(payload, "model_dump")
            else dict(payload)
        )
        if not data:
            return error_response("NO_CHANGES", "没有需要更新的字段")
        operator = _operator_from_user(user)
        normalized_key = _normalize_agent_key(agent_key)
        dataset_key = _safe_text(dataset_id, 80)
        case_id = _safe_text(case_key, 120)
        dataset = conn.execute(
            "SELECT dataset_id FROM agent_eval_datasets WHERE dataset_id = ? AND agent_key = ? LIMIT 1",
            (dataset_key, normalized_key),
        ).fetchone()
        if dataset is None:
            return error_response("NOT_FOUND", "样本集不存在", 404)
        current = conn.execute(
            "SELECT * FROM agent_eval_dataset_cases WHERE dataset_id = ? AND case_key = ? LIMIT 1",
            (dataset_key, case_id),
        ).fetchone()
        if current is None:
            return error_response("NOT_FOUND", "样本用例不存在", 404)
        expected_decision = _safe_text(
            data.get("expectedDecision")
            or data.get("expected_decision")
            or current["expected_decision"],
            40,
        )
        if (
            data.get("expectedDecision") is not None
            and expected_decision not in EVAL_DECISION_SET
        ):
            return error_response(
                "INVALID_PARAMS",
                "expectedDecision 仅支持 approve/reject/manual_review",
                400,
            )
        next_input = (
            data.get("input")
            if isinstance(data.get("input"), dict)
            else _parse_json_safe(current["input_json"], None)
        )
        next_expected = (
            data.get("expected")
            if isinstance(data.get("expected"), dict)
            else (
                _parse_json_safe(current["expected_json"], None)
                or {"decision": expected_decision or "manual_review"}
            )
        )
        if data.get("expectedDecision") is not None:
            next_expected["decision"] = expected_decision
        next_tags = (
            data.get("tags")
            if isinstance(data.get("tags"), list)
            else (_parse_json_safe(current["tags_json"], []) or [])
        )
        action_note = _safe_text(data.get("actionNote"), 120)
        note = _safe_text(data.get("note") or current["note"], 300)
        merged_note = _safe_text(
            f"{note + ' | ' if note and action_note else note}{datetime.fromtimestamp(_now_ms() / 1000, tz=timezone.utc).isoformat()} {operator['name']}: {action_note}"
            if action_note
            else note,
            300,
        )
        conn.execute(
            "UPDATE agent_eval_dataset_cases SET source_ref = ?, risk_level = ?, tags_json = ?, input_json = ?, expected_decision = ?, expected_json = ?, note = ?, is_active = ?, updated_at = ? WHERE dataset_id = ? AND case_key = ?",
            (
                _safe_text(
                    data.get("sourceRef")
                    or data.get("source_ref")
                    or current["source_ref"],
                    160,
                )
                or None,
                _safe_text(
                    data.get("riskLevel")
                    or data.get("risk_level")
                    or current["risk_level"],
                    40,
                )
                or None,
                _stringify_json(next_tags, "[]") if next_tags else None,
                _stringify_json(next_input or {}, "{}"),
                expected_decision or None,
                _stringify_json(
                    next_expected or {"decision": expected_decision or "manual_review"},
                    "{}",
                ),
                merged_note or None,
                1
                if _normalize_boolean(
                    data.get("isActive")
                    if data.get("isActive") is not None
                    else data.get("is_active"),
                    _safe_int(current["is_active"], 1) == 1,
                )
                else 0,
                _now_ms(),
                dataset_key,
                case_id,
            ),
        )
        count_row = conn.execute(
            "SELECT COUNT(1) AS total_count, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_count FROM agent_eval_dataset_cases WHERE dataset_id = ?",
            (dataset_key,),
        ).fetchone()
        conn.execute(
            "UPDATE agent_eval_datasets SET case_count = ?, active_case_count = ?, updated_at = ? WHERE dataset_id = ?",
            (
                _safe_int(count_row["total_count"], 0),
                _safe_int(count_row["active_count"], 0),
                _now_ms(),
                dataset_key,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM agent_eval_dataset_cases WHERE case_key = ? AND dataset_id = ?",
            (case_id, dataset_key),
        ).fetchone()
        return success_response(
            data={
                "datasetId": dataset_key,
                "case": {
                    "caseKey": row["case_key"],
                    "sourceRef": _safe_text(row["source_ref"], 160),
                    "riskLevel": _safe_text(row["risk_level"], 40),
                    "tags": _parse_json_safe(row["tags_json"], []),
                    "input": _parse_json_safe(row["input_json"], None),
                    "expectedDecision": _safe_text(row["expected_decision"], 40),
                    "expected": _parse_json_safe(row["expected_json"], None),
                    "note": _safe_text(row["note"], 300),
                    "isActive": _safe_int(row["is_active"], 0) == 1,
                    "updatedAt": _safe_int(row["updated_at"], 0),
                },
                "datasetStats": {
                    "caseCount": _safe_int(count_row["total_count"], 0),
                    "activeCaseCount": _safe_int(count_row["active_count"], 0),
                    "updatedAt": _now_ms(),
                },
            }
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/{agent_key}/eval-datasets/import")
async def import_eval_dataset(
    agent_key: str,
    payload: EvalDatasetImport,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        raw = (
            data
            if data.get("cases") is not None or data.get("datasetName") is not None
            else {"cases": data.get("dataset", []), "datasetName": data.get("name")}
        )
        normalized_key = _normalize_agent_key(agent_key)
        if not normalized_key:
            return error_response("INVALID_PARAMS", "agentKey 格式无效", 400)
        now = _now_ms()
        dataset_name = _safe_text(raw.get("datasetName") or raw.get("name"), 80)
        if not dataset_name:
            return error_response("INVALID_PARAMS", "datasetName 不能为空", 400)
        dataset_version = _safe_text(
            raw.get("datasetVersion") or raw.get("version"), 40
        ) or datetime.fromtimestamp(now / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        import_mode = _safe_text(raw.get("importMode"), 20).lower() or "replace"
        if import_mode not in {"replace", "append", "upsert"}:
            import_mode = "replace"
        existing = conn.execute(
            "SELECT dataset_id FROM agent_eval_datasets WHERE agent_key = ? AND name = ? AND version = ? LIMIT 1",
            (normalized_key, dataset_name, dataset_version),
        ).fetchone()
        dataset_key = (
            _safe_text(existing["dataset_id"], 80) if existing else _create_dataset_id()
        )
        if existing:
            conn.execute(
                "UPDATE agent_eval_datasets SET source_type = ?, description = ?, tags_json = ?, operator_id = ?, operator_name = ?, updated_at = ? WHERE dataset_id = ?",
                (
                    _safe_text(raw.get("sourceType"), 40) or "manual_import",
                    _safe_text(raw.get("description"), 500) or None,
                    _stringify_json(
                        raw.get("tags") if isinstance(raw.get("tags"), list) else [],
                        "[]",
                    ),
                    operator["id"] or None,
                    operator["name"] or None,
                    now,
                    dataset_key,
                ),
            )
        else:
            conn.execute(
                "INSERT INTO agent_eval_datasets (dataset_id, agent_key, name, version, source_type, description, tags_json, case_count, active_case_count, status, operator_id, operator_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'active', ?, ?, ?, ?)",
                (
                    dataset_key,
                    normalized_key,
                    dataset_name,
                    dataset_version,
                    _safe_text(raw.get("sourceType"), 40) or "manual_import",
                    _safe_text(raw.get("description"), 500) or None,
                    _stringify_json(
                        raw.get("tags") if isinstance(raw.get("tags"), list) else [],
                        "[]",
                    ),
                    operator["id"] or None,
                    operator["name"] or None,
                    now,
                    now,
                ),
            )
        if import_mode == "replace":
            conn.execute(
                "DELETE FROM agent_eval_dataset_cases WHERE dataset_id = ?",
                (dataset_key,),
            )
        insert_sql = "INSERT INTO agent_eval_dataset_cases (dataset_id, case_key, source_ref, risk_level, tags_json, input_json, expected_decision, expected_json, note, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        cases = raw.get("cases") if isinstance(raw.get("cases"), list) else []
        for idx, item in enumerate(cases[:5000], start=1):
            case = item if isinstance(item, dict) else {}
            case_key_value = (
                _safe_text(case.get("caseKey") or case.get("case_key"), 120)
                or f"{normalized_key}_case_{idx}"
            )
            expected_decision = (
                _safe_text(
                    case.get("expectedDecision")
                    or case.get("expected_decision")
                    or ((case.get("expected") or {}).get("decision")),
                    40,
                )
                or "manual_review"
            )
            values = (
                dataset_key,
                case_key_value,
                _safe_text(case.get("sourceRef") or case.get("source_ref"), 160)
                or None,
                _safe_text(case.get("riskLevel") or case.get("risk_level"), 40) or None,
                _stringify_json(
                    case.get("tags") if isinstance(case.get("tags"), list) else [], "[]"
                )
                if isinstance(case.get("tags"), list) and case.get("tags")
                else None,
                _stringify_json(
                    case.get("input")
                    if isinstance(case.get("input"), dict)
                    else {"text": _safe_text(case.get("input"), 600)},
                    "{}",
                ),
                expected_decision or None,
                _stringify_json(
                    case.get("expected")
                    if isinstance(case.get("expected"), dict)
                    else {"decision": expected_decision},
                    "{}",
                ),
                _safe_text(case.get("note"), 300) or None,
                1
                if _normalize_boolean(
                    case.get("isActive")
                    if case.get("isActive") is not None
                    else case.get("is_active"),
                    True,
                )
                else 0,
                now,
                now,
            )
            if import_mode == "append":
                conn.execute(
                    insert_sql + " ON CONFLICT(dataset_id, case_key) DO NOTHING", values
                )
            else:
                conn.execute(
                    insert_sql
                    + " ON CONFLICT(dataset_id, case_key) DO UPDATE SET source_ref = excluded.source_ref, risk_level = excluded.risk_level, tags_json = excluded.tags_json, input_json = excluded.input_json, expected_decision = excluded.expected_decision, expected_json = excluded.expected_json, note = excluded.note, is_active = excluded.is_active, updated_at = excluded.updated_at",
                    values,
                )
        count_row = conn.execute(
            "SELECT COUNT(1) AS total_count, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_count FROM agent_eval_dataset_cases WHERE dataset_id = ?",
            (dataset_key,),
        ).fetchone()
        conn.execute(
            "UPDATE agent_eval_datasets SET case_count = ?, active_case_count = ?, updated_at = ? WHERE dataset_id = ?",
            (
                _safe_int(count_row["total_count"], 0),
                _safe_int(count_row["active_count"], 0),
                now,
                dataset_key,
            ),
        )
        conn.commit()
        dataset_result = {
            "datasetId": dataset_key,
            "agentKey": normalized_key,
            "name": dataset_name,
            "version": dataset_version,
            "sourceType": _safe_text(raw.get("sourceType"), 40) or "manual_import",
            "description": _safe_text(raw.get("description"), 500),
            "tags": raw.get("tags") if isinstance(raw.get("tags"), list) else [],
            "importMode": import_mode,
            "importedCases": len(cases[:5000]),
            "caseCount": _safe_int(count_row["total_count"], 0),
            "activeCaseCount": _safe_int(count_row["active_count"], 0),
            "updatedAt": now,
        }
        if _normalize_boolean(raw.get("autoRun"), True):
            eval_result = _create_eval_run_record(
                conn,
                normalized_key,
                {
                    "datasetName": dataset_name,
                    "datasetVersion": dataset_version,
                    "mode": _safe_text(raw.get("mode"), 20) or "offline",
                    "templateProfile": _safe_text(raw.get("templateProfile"), 20)
                    or "standard",
                    "targetPassRate": raw.get("targetPassRate"),
                    "notes": _safe_text(raw.get("autoRunNote"), 500)
                    or f"导入后自动评测: {dataset_name}@{dataset_version}",
                    "cases": [
                        {
                            "caseKey": row["case_key"],
                            "sourceType": "dataset_import",
                            "sourceRef": _safe_text(row["source_ref"], 160),
                            "expectedDecision": _safe_text(row["expected_decision"], 40)
                            or "manual_review",
                            "input": _parse_json_safe(row["input_json"], None)
                            or {"text": ""},
                            "expected": _parse_json_safe(row["expected_json"], None)
                            or {
                                "decision": _safe_text(row["expected_decision"], 40)
                                or "manual_review"
                            },
                        }
                        for row in conn.execute(
                            "SELECT case_key, source_ref, expected_decision, input_json, expected_json FROM agent_eval_dataset_cases WHERE dataset_id = ? AND is_active = 1 ORDER BY id ASC LIMIT ?",
                            (
                                dataset_key,
                                min(max(_safe_int(raw.get("caseLimit"), 500), 1), 2000),
                            ),
                        ).fetchall()
                    ],
                },
                operator,
            )
            return success_response(
                data={
                    "dataset": dataset_result,
                    "evalRun": eval_result,
                    "message": "样本集导入完成并已触发评测",
                }
            )
        return success_response(
            data={"dataset": dataset_result, "message": "样本集导入完成"}
        )
    except Exception as e:
        return error_response("IMPORT_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/{agent_key}/eval-datasets/{dataset_id}/run")
async def run_eval_dataset(
    agent_key: str,
    dataset_id: str,
    payload: dict | None = Body(default=None),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        normalized_key = _normalize_agent_key(agent_key)
        dataset_key = _safe_text(dataset_id, 80)
        operator = _operator_from_user(user)
        dataset = conn.execute(
            "SELECT dataset_id, name, version FROM agent_eval_datasets WHERE dataset_id = ? AND agent_key = ? LIMIT 1",
            (dataset_key, normalized_key),
        ).fetchone()
        if dataset is None:
            return error_response("NOT_FOUND", "样本集不存在", 404)
        case_limit = min(max(_safe_int((payload or {}).get("caseLimit"), 500), 1), 2000)
        cases = [
            {
                "caseKey": row["case_key"],
                "sourceType": "dataset_import",
                "sourceRef": _safe_text(row["source_ref"], 160),
                "expectedDecision": _safe_text(row["expected_decision"], 40)
                or "manual_review",
                "input": _parse_json_safe(row["input_json"], None) or {"text": ""},
                "expected": _parse_json_safe(row["expected_json"], None)
                or {
                    "decision": _safe_text(row["expected_decision"], 40)
                    or "manual_review"
                },
            }
            for row in conn.execute(
                "SELECT case_key, source_ref, expected_decision, input_json, expected_json FROM agent_eval_dataset_cases WHERE dataset_id = ? AND is_active = 1 ORDER BY id ASC LIMIT ?",
                (dataset_key, case_limit),
            ).fetchall()
        ]
        if not cases:
            return error_response("INVALID_PARAMS", "样本集中没有可用用例", 400)
        result = _create_eval_run_record(
            conn,
            normalized_key,
            {
                "datasetName": _safe_text(dataset["name"], 80),
                "datasetVersion": _safe_text(dataset["version"], 40),
                "mode": _safe_text((payload or {}).get("mode"), 20) or "offline",
                "templateProfile": _safe_text(
                    (payload or {}).get("templateProfile"), 20
                )
                or "standard",
                "targetPassRate": (payload or {}).get("targetPassRate"),
                "notes": _safe_text((payload or {}).get("notes"), 500)
                or f"从样本集触发评测: {dataset['name']}@{dataset['version']}",
                "cases": cases,
            },
            operator,
        )
        return success_response(data=result, status_code=201)
    except Exception as e:
        return error_response("EVAL_RUN_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Test
# ---------------------------------------------------------------------------


@router.post("/{agent_key}/test")
async def test_agent(
    agent_key: str,
    payload: AgentTestRequest,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        result = _create_run_record(
            conn,
            agent_key,
            data,
            operator,
            {
                "defaultMode": "test",
                "defaultTriggerSource": "admin_test",
                "defaultDecisionSource": "manual_test",
                "defaultInputText": "Agent 测试输入样例",
                "defaultSuccessReason": "测试运行通过",
                "defaultFailedReason": "测试运行失败",
                "successMessage": "测试运行记录已创建",
            },
        )
        return success_response(data=result, status_code=201)
    except Exception as e:
        return error_response("TEST_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Replay
# ---------------------------------------------------------------------------


@router.post("/{agent_key}/replay")
async def replay_agent(
    agent_key: str,
    payload: ReplayRequest,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        source_run_id = _safe_text(data.get("sourceRunId") or data.get("runId"), 80)
        if not source_run_id:
            return error_response("INVALID_PARAMS", "sourceRunId 不能为空", 400)
        source_run = conn.execute(
            "SELECT run_id, agent_key, status, input_json, output_json, trace_json, error_type, error_message, decision, risk_score, latency_ms, token_used, cost_micros FROM agent_runs WHERE run_id = ? LIMIT 1",
            (source_run_id,),
        ).fetchone()
        if source_run is None:
            return error_response("NOT_FOUND", "sourceRunId 对应运行不存在", 404)
        if _normalize_agent_key(source_run["agent_key"]) != _normalize_agent_key(
            agent_key
        ):
            return error_response(
                "INVALID_PARAMS", "sourceRunId 与 agentKey 不匹配", 400
            )
        steps = [
            {
                "stepType": row["step_type"],
                "stepName": row["step_name"],
                "status": row["status"],
                "input": _parse_json_safe(row["input_json"], None),
                "output": _parse_json_safe(row["output_json"], None),
                "errorType": _safe_text(row["error_type"], 80),
                "errorMessage": _safe_text(row["error_message"], 300),
                "latencyMs": _safe_int(row["latency_ms"], 0),
                "toolName": _safe_text(row["tool_name"], 80),
            }
            for row in conn.execute(
                "SELECT step_type, step_name, status, input_json, output_json, error_type, error_message, latency_ms, tool_name FROM agent_run_steps WHERE run_id = ? ORDER BY step_index ASC",
                (source_run_id,),
            ).fetchall()
        ]
        replay_payload = {
            "mode": "replay",
            "status": _safe_text(data.get("status"), 20)
            or _safe_text(source_run["status"], 20)
            or "success",
            "triggerSource": _safe_text(data.get("triggerSource"), 40)
            or "admin_replay",
            "decision": _safe_text(data.get("decision"), 40)
            or _safe_text(source_run["decision"], 40)
            or "manual_review",
            "decisionSource": _safe_text(data.get("decisionSource"), 40) or "replay",
            "reason": _safe_text(data.get("reason"), 300)
            or f"回放来源 run: {source_run_id}",
            "riskScore": data.get("riskScore")
            if data.get("riskScore") is not None
            else _safe_number(source_run["risk_score"], 0),
            "latencyMs": data.get("latencyMs")
            if data.get("latencyMs") is not None
            else _safe_int(source_run["latency_ms"], 180),
            "tokenUsed": data.get("tokenUsed")
            if data.get("tokenUsed") is not None
            else _safe_int(source_run["token_used"], 0),
            "costMicros": data.get("costMicros")
            if data.get("costMicros") is not None
            else _safe_int(source_run["cost_micros"], 0),
            "errorType": _safe_text(data.get("errorType"), 80)
            or _safe_text(source_run["error_type"], 80),
            "errorMessage": _safe_text(data.get("errorMessage"), 300)
            or _safe_text(source_run["error_message"], 300),
            "input": data.get("input")
            if isinstance(data.get("input"), dict)
            else _parse_json_safe(source_run["input_json"], None),
            "output": data.get("output")
            if isinstance(data.get("output"), dict)
            else _parse_json_safe(source_run["output_json"], None),
            "trace": data.get("trace")
            if isinstance(data.get("trace"), dict)
            else _parse_json_safe(source_run["trace_json"], None),
            "steps": data.get("steps")
            if isinstance(data.get("steps"), list) and data.get("steps")
            else steps,
            "replaySourceRunId": source_run_id,
            "replaySourceAgentKey": _normalize_agent_key(agent_key),
            "replayReason": _safe_text(data.get("replayReason"), 300) or "管理面板回放",
        }
        return success_response(
            data=_create_run_record(
                conn,
                agent_key,
                replay_payload,
                operator,
                {
                    "defaultMode": "replay",
                    "defaultTriggerSource": "admin_replay",
                    "defaultDecisionSource": "replay",
                    "defaultInputText": "Agent 回放输入样例",
                    "defaultSuccessReason": "回放运行通过",
                    "defaultFailedReason": "回放运行失败",
                    "successMessage": "回放运行记录已创建",
                },
            ),
            status_code=201,
        )
    except Exception as e:
        return error_response("REPLAY_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Run
# ---------------------------------------------------------------------------


@router.post("/{agent_key}/run")
async def run_agent(
    agent_key: str,
    payload: AgentRunRequest,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        operator = _operator_from_user(user)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        result = _create_run_record(
            conn,
            agent_key,
            data,
            operator,
            {
                "defaultMode": "prod",
                "defaultTriggerSource": "external_event",
                "defaultDecisionSource": "agent_runtime",
                "defaultInputText": "Agent 生产输入样例",
                "defaultSuccessReason": "生产运行通过",
                "defaultFailedReason": "生产运行失败",
                "successMessage": "运行记录已创建",
            },
        )
        return success_response(data=result, status_code=201)
    except Exception as e:
        return error_response("RUN_FAILED", str(e), 500)
    finally:
        conn.close()
