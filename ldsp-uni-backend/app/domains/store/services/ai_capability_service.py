"""Unified AI capability configuration service for LD Store.

Phase 1 goals:
- create/ensure unified provider/capability/prompt tables
- expose unified read APIs
- keep backward compatibility with legacy tables
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import settings


CAPABILITY_PRODUCT_REVIEW = "shop_product_review"
CAPABILITY_COMMENT_REVIEW = "shop_comment_review"
CAPABILITY_IMAGE_REVIEW = "shop_image_review"
CAPABILITY_DAILY_REPORT = "shop_ops_daily_report"
CAPABILITY_WEEKLY_REPORT = "shop_ops_weekly_report"
CAPABILITY_MONTHLY_REPORT = "shop_ops_monthly_report"


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


def ensure_unified_ai_schema() -> None:
    conn = _db()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ai_provider_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_key TEXT UNIQUE,
                name TEXT NOT NULL,
                provider_type TEXT NOT NULL DEFAULT 'openai_compatible',
                base_url TEXT,
                api_key_encrypted TEXT,
                model TEXT,
                timeout_ms INTEGER DEFAULT 30000,
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 0,
                gateway_route TEXT,
                gateway_workspace TEXT,
                extra_config_json TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ai_capability_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability_key TEXT UNIQUE,
                name TEXT NOT NULL,
                provider_config_id INTEGER,
                backup_provider_config_id INTEGER,
                prompt_template TEXT,
                review_criteria_json TEXT,
                runtime_config_json TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                version TEXT DEFAULT 'v1',
                legacy_source_type TEXT,
                legacy_source_id INTEGER,
                created_at INTEGER,
                updated_at INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ai_prompt_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_key TEXT UNIQUE,
                scene TEXT NOT NULL,
                name TEXT NOT NULL,
                prompt_template TEXT NOT NULL,
                variables_json TEXT,
                source_type TEXT DEFAULT 'manual',
                is_builtin INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER,
                updated_at INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ai_capability_prompt_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability_key TEXT NOT NULL,
                template_id INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER,
                updated_at INTEGER,
                UNIQUE(capability_key, template_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT UNIQUE,
                job_type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                schedule_type TEXT NOT NULL DEFAULT 'interval',
                interval_seconds INTEGER,
                cron_expr TEXT,
                runtime_config_json TEXT,
                last_run_at INTEGER,
                last_status TEXT,
                last_error TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS scheduled_job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT NOT NULL,
                trigger_source TEXT,
                status TEXT,
                started_at INTEGER,
                ended_at INTEGER,
                duration_ms INTEGER,
                result_json TEXT,
                error_message TEXT
            )"""
        )

        # Extend agent_runs in-place to store unified runtime metadata.
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "agent_runs" in table_names:
            run_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(agent_runs)").fetchall()
            }
            desired_columns = {
                "capability_key": "TEXT",
                "provider_config_id": "INTEGER",
                "provider_name": "TEXT",
                "provider_type": "TEXT",
                "gateway_route": "TEXT",
                "target_type": "TEXT",
                "target_id": "TEXT",
                "prompt_template_snapshot": "TEXT",
                "input_payload_json": "TEXT",
                "output_payload_json": "TEXT",
                "structured_result_json": "TEXT",
                "cost_tokens_prompt": "INTEGER",
                "cost_tokens_completion": "INTEGER",
                "cost_amount_micros": "INTEGER",
                "scheduled_job_key": "TEXT",
            }
            for column, ddl in desired_columns.items():
                if column not in run_columns:
                    conn.execute(f"ALTER TABLE agent_runs ADD COLUMN {column} {ddl}")

        conn.commit()
    finally:
        conn.close()


def migrate_legacy_ai_configs() -> None:
    """Populate unified capability/provider tables from legacy config tables.

    This migration is intentionally idempotent and read-only with respect to old
    tables: legacy rows remain the source of truth until capabilities are fully
    switched over.
    """

    conn = _db()
    try:
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        now = __import__("time").time_ns() // 1_000_000

        legacy_api_rows = []
        if "ai_api_config" in table_names:
            api_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(ai_api_config)").fetchall()
            }
            order_column = "sort_order" if "sort_order" in api_columns else "id"
            legacy_api_rows = [
                dict(row)
                for row in conn.execute(
                    f"SELECT * FROM ai_api_config ORDER BY {order_column} ASC, created_at ASC"
                ).fetchall()
            ]
        provider_id_map: dict[int, int] = {}
        for row in legacy_api_rows:
            provider_key = f"legacy_api_config_{row['id']}"
            conn.execute(
                """INSERT INTO ai_provider_configs (
                    provider_key, name, provider_type, base_url, api_key_encrypted, model,
                    timeout_ms, enabled, priority, created_at, updated_at
                ) VALUES (?, ?, 'openai_compatible', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_key) DO UPDATE SET
                    name = excluded.name,
                    base_url = excluded.base_url,
                    api_key_encrypted = excluded.api_key_encrypted,
                    model = excluded.model,
                    timeout_ms = excluded.timeout_ms,
                    enabled = excluded.enabled,
                    priority = excluded.priority,
                    updated_at = excluded.updated_at""",
                (
                    provider_key,
                    row.get("name") or f"Legacy API #{row['id']}",
                    row.get("base_url") or row.get("llm_url") or "",
                    row.get("api_key")
                    or row.get("api_key_encrypted")
                    or row.get("llm_api_key_encrypted")
                    or "",
                    row.get("model") or row.get("llm_model") or "",
                    int(row.get("timeout") or row.get("timeout_ms") or 30000),
                    1 if (row.get("enabled") or row.get("is_enabled")) else 0,
                    int(row.get("sort_order") or row.get("id") or 0),
                    now,
                    now,
                ),
            )
            provider = conn.execute(
                "SELECT id FROM ai_provider_configs WHERE provider_key = ?",
                (provider_key,),
            ).fetchone()
            if provider:
                provider_id_map[int(row["id"])] = int(provider["id"])

        def upsert_capability(
            capability_key: str,
            name: str,
            provider_config_id: int | None,
            backup_provider_config_id: int | None,
            prompt_template: str,
            review_criteria_json: Any,
            runtime_config_json: Any,
            legacy_source_type: str,
            legacy_source_id: int | None,
        ) -> None:
            conn.execute(
                """INSERT INTO ai_capability_configs (
                    capability_key, name, provider_config_id, backup_provider_config_id,
                    prompt_template, review_criteria_json, runtime_config_json, enabled,
                    version, legacy_source_type, legacy_source_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'v1', ?, ?, ?, ?)
                ON CONFLICT(capability_key) DO UPDATE SET
                    name = excluded.name,
                    provider_config_id = COALESCE(excluded.provider_config_id, ai_capability_configs.provider_config_id),
                    backup_provider_config_id = COALESCE(excluded.backup_provider_config_id, ai_capability_configs.backup_provider_config_id),
                    prompt_template = CASE WHEN excluded.prompt_template != '' THEN excluded.prompt_template ELSE ai_capability_configs.prompt_template END,
                    review_criteria_json = CASE WHEN excluded.review_criteria_json IS NOT NULL THEN excluded.review_criteria_json ELSE ai_capability_configs.review_criteria_json END,
                    runtime_config_json = CASE WHEN excluded.runtime_config_json IS NOT NULL THEN excluded.runtime_config_json ELSE ai_capability_configs.runtime_config_json END,
                    legacy_source_type = excluded.legacy_source_type,
                    legacy_source_id = excluded.legacy_source_id,
                    updated_at = excluded.updated_at""",
                (
                    capability_key,
                    name,
                    provider_config_id,
                    backup_provider_config_id,
                    prompt_template or "",
                    json.dumps(review_criteria_json, ensure_ascii=False)
                    if review_criteria_json is not None
                    else None,
                    json.dumps(runtime_config_json, ensure_ascii=False)
                    if runtime_config_json is not None
                    else None,
                    legacy_source_type,
                    legacy_source_id,
                    now,
                    now,
                ),
            )

        product_review = None
        if "ai_review_config" in table_names:
            review_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(ai_review_config)"
                ).fetchall()
            }
            enabled_column = "enabled" if "enabled" in review_columns else "is_enabled"
            order_column = "sort_order" if "sort_order" in review_columns else "id"
            product_review = conn.execute(
                f"SELECT * FROM ai_review_config WHERE {enabled_column} = 1 ORDER BY {order_column} ASC, created_at DESC LIMIT 1"
            ).fetchone()
        if product_review:
            review_config = _safe_json_loads(product_review["config"], {}) or {}
            if not review_config and product_review["review_criteria"]:
                review_config = {
                    "review_criteria": _safe_json_loads(
                        product_review["review_criteria"], {}
                    )
                    or {}
                }
            upsert_capability(
                CAPABILITY_PRODUCT_REVIEW,
                "商品审核",
                provider_id_map.get(
                    int(product_review["api_config_id"])
                    if product_review["api_config_id"]
                    else 0
                ),
                provider_id_map.get(
                    int(product_review["backup_api_config_id"])
                    if "backup_api_config_id" in product_review.keys()
                    and product_review["backup_api_config_id"]
                    else 0
                ),
                str(product_review["prompt_template"] or ""),
                review_config.get("review_criteria")
                if isinstance(review_config, dict)
                else None,
                review_config,
                "ai_review_config",
                int(product_review["id"]),
            )

        comment_review = None
        if "shop_comment_ai_config" in table_names:
            comment_review = conn.execute(
                "SELECT * FROM shop_comment_ai_config ORDER BY is_enabled DESC, updated_at DESC, id DESC LIMIT 1"
            ).fetchone()
        if comment_review:
            upsert_capability(
                CAPABILITY_COMMENT_REVIEW,
                "评论审核",
                provider_id_map.get(
                    int(comment_review["api_config_id"])
                    if comment_review["api_config_id"]
                    else 0
                ),
                provider_id_map.get(
                    int(comment_review["backup_api_config_id"])
                    if "backup_api_config_id" in comment_review.keys()
                    and comment_review["backup_api_config_id"]
                    else 0
                ),
                str(comment_review["prompt_template"] or ""),
                _safe_json_loads(comment_review["review_criteria"], {}),
                {
                    "approve_threshold": float(
                        comment_review["approve_threshold"] or 0.85
                    ),
                    "reject_threshold": float(
                        comment_review["reject_threshold"] or 0.85
                    ),
                },
                "shop_comment_ai_config",
                int(comment_review["id"]),
            )

        # Image review starts with a synthetic capability entry so the admin panel
        # can be unified even before the legacy table is fully mapped.
        upsert_capability(
            CAPABILITY_IMAGE_REVIEW,
            "图片审核",
            next(iter(provider_id_map.values()), None),
            None,
            "",
            {"rejectThreshold": 0.75},
            {"legacy_source": "image_manage"},
            "image_manage",
            None,
        )

        upsert_capability(
            CAPABILITY_DAILY_REPORT,
            "日报生成",
            next(iter(provider_id_map.values()), None),
            None,
            "请根据运营数据生成日报，输出摘要、亮点、风险与行动建议。",
            None,
            {"reportType": "daily"},
            "ops_report",
            None,
        )
        upsert_capability(
            CAPABILITY_WEEKLY_REPORT,
            "周报生成",
            next(iter(provider_id_map.values()), None),
            None,
            "请根据运营数据生成周报，输出趋势、亮点、风险与行动建议。",
            None,
            {"reportType": "weekly"},
            "ops_report",
            None,
        )
        upsert_capability(
            CAPABILITY_MONTHLY_REPORT,
            "月报生成",
            next(iter(provider_id_map.values()), None),
            None,
            "请根据运营数据生成月报，输出核心指标、风险和下月建议。",
            None,
            {"reportType": "monthly"},
            "ops_report",
            None,
        )

        conn.commit()
    finally:
        conn.close()


class AICapabilityService:
    def ensure_ready(self) -> None:
        ensure_unified_ai_schema()
        migrate_legacy_ai_configs()

    def get_provider_config(self, provider_id: int | None) -> dict | None:
        if not provider_id:
            return None
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM ai_provider_configs WHERE id = ?",
                (provider_id,),
            ).fetchone()
            return _row_to_dict(row)
        finally:
            conn.close()

    def get_capability_config(self, capability_key: str) -> dict | None:
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM ai_capability_configs WHERE capability_key = ? LIMIT 1",
                (capability_key,),
            ).fetchone()
            data = _row_to_dict(row)
            if not data:
                return None
            data["review_criteria_json"] = _safe_json_loads(
                data.get("review_criteria_json"), {}
            )
            data["runtime_config_json"] = _safe_json_loads(
                data.get("runtime_config_json"), {}
            )
            return data
        finally:
            conn.close()

    def resolve_capability(self, capability_key: str) -> dict | None:
        self.ensure_ready()
        capability = self.get_capability_config(capability_key)
        if not capability:
            return None
        primary = self.get_provider_config(capability.get("provider_config_id"))
        fallback = self.get_provider_config(capability.get("backup_provider_config_id"))
        return {
            "capability": capability,
            "primary": primary,
            "fallback": fallback,
        }

    def sync_legacy_product_review_config(self, legacy_config_id: int) -> None:
        """Force sync one legacy ai_review_config row into unified capability.

        Used when old admin pages still edit legacy config tables but new runtime
        should read unified capability first.
        """

        self.ensure_ready()
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM ai_review_config WHERE id = ? LIMIT 1",
                (legacy_config_id,),
            ).fetchone()
            if not row:
                return
            row = dict(row)
            provider = None
            if row.get("api_config_id"):
                provider = conn.execute(
                    "SELECT id FROM ai_provider_configs WHERE provider_key = ? LIMIT 1",
                    (f"legacy_api_config_{int(row['api_config_id'])}",),
                ).fetchone()
            backup = None
            if row.get("backup_api_config_id"):
                backup = conn.execute(
                    "SELECT id FROM ai_provider_configs WHERE provider_key = ? LIMIT 1",
                    (f"legacy_api_config_{int(row['backup_api_config_id'])}",),
                ).fetchone()
            review_config = _safe_json_loads(row.get("config"), {}) or {}
            if not review_config:
                review_config = {
                    "review_criteria": _safe_json_loads(row.get("review_criteria"), {})
                    or {},
                    "temperature": row.get("temperature"),
                    "max_tokens": row.get("max_tokens"),
                    "timeout_ms": row.get("timeout_ms"),
                }
            now = __import__("time").time_ns() // 1_000_000
            conn.execute(
                """UPDATE ai_capability_configs SET
                    name = ?,
                    provider_config_id = ?,
                    backup_provider_config_id = ?,
                    prompt_template = ?,
                    review_criteria_json = ?,
                    runtime_config_json = ?,
                    enabled = ?,
                    version = ?,
                    legacy_source_type = 'ai_review_config',
                    legacy_source_id = ?,
                    updated_at = ?
                   WHERE capability_key = ?""",
                (
                    row.get("name") or "商品审核",
                    int(provider["id"]) if provider else None,
                    int(backup["id"]) if backup else None,
                    row.get("prompt_template") or "",
                    json.dumps(
                        review_config.get("review_criteria") or {}, ensure_ascii=False
                    ),
                    json.dumps(review_config, ensure_ascii=False),
                    1 if (row.get("enabled") or row.get("is_enabled")) else 0,
                    "v1",
                    int(row.get("id") or 0),
                    now,
                    CAPABILITY_PRODUCT_REVIEW,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def sync_legacy_comment_review_config(self, legacy_config_id: int) -> None:
        self.ensure_ready()
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM shop_comment_ai_config WHERE id = ? LIMIT 1",
                (legacy_config_id,),
            ).fetchone()
            if not row:
                return
            row = dict(row)
            provider = None
            if row.get("api_config_id"):
                provider = conn.execute(
                    "SELECT id FROM ai_provider_configs WHERE provider_key = ? LIMIT 1",
                    (f"legacy_api_config_{int(row['api_config_id'])}",),
                ).fetchone()
            backup = None
            if row.get("backup_api_config_id"):
                backup = conn.execute(
                    "SELECT id FROM ai_provider_configs WHERE provider_key = ? LIMIT 1",
                    (f"legacy_api_config_{int(row['backup_api_config_id'])}",),
                ).fetchone()
            now = __import__("time").time_ns() // 1_000_000
            runtime_config = {
                "approve_threshold": float(row.get("approve_threshold") or 0.85),
                "reject_threshold": float(row.get("reject_threshold") or 0.85),
            }
            conn.execute(
                """UPDATE ai_capability_configs SET
                    name = ?,
                    provider_config_id = ?,
                    backup_provider_config_id = ?,
                    prompt_template = ?,
                    review_criteria_json = ?,
                    runtime_config_json = ?,
                    enabled = ?,
                    version = ?,
                    legacy_source_type = 'shop_comment_ai_config',
                    legacy_source_id = ?,
                    updated_at = ?
                   WHERE capability_key = ?""",
                (
                    row.get("name") or "评论审核",
                    int(provider["id"]) if provider else None,
                    int(backup["id"]) if backup else None,
                    row.get("prompt_template") or "",
                    json.dumps(
                        _safe_json_loads(row.get("review_criteria"), {}) or {},
                        ensure_ascii=False,
                    ),
                    json.dumps(runtime_config, ensure_ascii=False),
                    1 if row.get("is_enabled") else 0,
                    "v1",
                    int(row.get("id") or 0),
                    now,
                    CAPABILITY_COMMENT_REVIEW,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def sync_report_capability(self, report_type: str) -> None:
        self.ensure_ready()
        safe_type = str(report_type or "").strip().lower()
        capability_key_map = {
            "daily": CAPABILITY_DAILY_REPORT,
            "weekly": CAPABILITY_WEEKLY_REPORT,
            "monthly": CAPABILITY_MONTHLY_REPORT,
        }
        capability_key = capability_key_map.get(safe_type)
        if not capability_key:
            return
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM shop_ops_report_configs WHERE report_type = ? LIMIT 1",
                (safe_type,),
            ).fetchone()
            if not row:
                return
            row = dict(row)
            provider = None
            api_config_id = _safe_json_loads(row.get("schedule_json"), {}).get(
                "apiConfigId"
            )
            if api_config_id:
                provider = conn.execute(
                    "SELECT id FROM ai_provider_configs WHERE provider_key = ? LIMIT 1",
                    (f"legacy_api_config_{int(api_config_id)}",),
                ).fetchone()
            now = __import__("time").time_ns() // 1_000_000
            runtime_config = _safe_json_loads(row.get("schedule_json"), {}) or {}
            prompt_template = runtime_config.get("promptTemplate") or {
                "daily": "请根据运营数据生成日报，输出摘要、亮点、风险与行动建议。",
                "weekly": "请根据运营数据生成周报，输出趋势、亮点、风险与行动建议。",
                "monthly": "请根据运营数据生成月报，输出核心指标、风险和下月建议。",
            }.get(safe_type, "")
            conn.execute(
                """UPDATE ai_capability_configs SET
                    name = ?,
                    provider_config_id = ?,
                    prompt_template = ?,
                    runtime_config_json = ?,
                    enabled = ?,
                    version = ?,
                    legacy_source_type = 'shop_ops_report_configs',
                    legacy_source_id = ?,
                    updated_at = ?
                   WHERE capability_key = ?""",
                (
                    {
                        "daily": "日报生成",
                        "weekly": "周报生成",
                        "monthly": "月报生成",
                    }.get(safe_type, safe_type),
                    int(provider["id"]) if provider else None,
                    prompt_template,
                    json.dumps(runtime_config, ensure_ascii=False),
                    1 if row.get("enabled") else 0,
                    "v1",
                    int(row.get("id") or 0),
                    now,
                    capability_key,
                ),
            )
            conn.commit()
        finally:
            conn.close()
