"""Database-backed AI gateway config loader.

The unified backend should use database configuration as the single source of
truth for AI gateway routing. Environment variables are not used as the
runtime source for model/API selection.
"""

from __future__ import annotations

import base64
import os
import sqlite3
from pathlib import Path

from app.config import settings
from app.domains.store.services.ai_capability_service import AICapabilityService


def _store_conn() -> sqlite3.Connection:
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


class AIGatewayConfigError(RuntimeError):
    pass


def _decrypt_legacy_api_key(raw_value: str) -> str:
    value = str(raw_value or "")
    if not value:
        return ""
    if not value.startswith("ENC:"):
        return value
    encryption_key = str(settings.encryption_key or "").strip()
    if not encryption_key:
        return ""
    try:
        decoded = base64.b64decode(value[4:]).decode("latin1")
        chars = []
        for index, char in enumerate(decoded):
            chars.append(
                chr(ord(char) ^ ord(encryption_key[index % len(encryption_key)]))
            )
        return "".join(chars)
    except Exception:
        return ""


def _normalize_api_config_row(data: dict) -> dict:
    normalized = dict(data or {})
    normalized.setdefault("base_url", normalized.get("llm_url") or "")
    normalized.setdefault("model", normalized.get("llm_model") or "")
    encrypted = (
        normalized.get("api_key")
        or normalized.get("api_key_encrypted")
        or normalized.get("llm_api_key_encrypted")
        or ""
    )
    normalized["api_key"] = _decrypt_legacy_api_key(str(encrypted or ""))
    return normalized


def load_primary_api_config() -> dict:
    conn = _store_conn()
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(ai_api_config)").fetchall()
        }
        enabled_column = "enabled" if "enabled" in columns else "is_enabled"
        order_column = "sort_order" if "sort_order" in columns else "id"
        row = conn.execute(
            f"""SELECT * FROM ai_api_config
               WHERE {enabled_column} = 1
               ORDER BY {order_column} ASC, created_at DESC
               LIMIT 1"""
        ).fetchone()
        if not row:
            raise AIGatewayConfigError(
                "未配置可用的主 API，请先在管理面板中配置 ai_api_config"
            )
        data = _normalize_api_config_row(dict(row))
        if not data.get("base_url") or not data.get("api_key") or not data.get("model"):
            raise AIGatewayConfigError("主 API 配置不完整，缺少 base_url/api_key/model")
        return data
    finally:
        conn.close()


def load_api_config_by_id(config_id: int | None) -> dict | None:
    if not config_id:
        return None
    conn = _store_conn()
    try:
        row = conn.execute(
            "SELECT * FROM ai_api_config WHERE id = ?", (config_id,)
        ).fetchone()
        return _normalize_api_config_row(dict(row)) if row else None
    finally:
        conn.close()


def load_review_config(
    config_id: int | None = None, category_id: int | None = None
) -> dict | None:
    conn = _store_conn()
    try:
        row = None
        if config_id:
            row = conn.execute(
                "SELECT * FROM ai_review_config WHERE id = ?", (config_id,)
            ).fetchone()
        elif category_id is not None:
            config_binding = conn.execute(
                """SELECT cc.config_id
                   FROM ai_review_category_config cc
                   WHERE cc.category_id = ? AND cc.is_enabled = 1
                   ORDER BY cc.updated_at DESC, cc.id DESC
                   LIMIT 1""",
                (category_id,),
            ).fetchone()
            if config_binding and config_binding[0]:
                row = conn.execute(
                    "SELECT * FROM ai_review_config WHERE id = ? LIMIT 1",
                    (config_binding[0],),
                ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def build_llm_runtime_config(
    review_config_id: int | None = None,
    category_id: int | None = None,
    capability_key: str | None = None,
) -> dict:
    capability_service = AICapabilityService()
    capability_service.ensure_ready()

    effective_capability_key = capability_key or (
        "shop_product_review" if review_config_id else None
    )

    if effective_capability_key:
        capability = capability_service.resolve_capability(effective_capability_key)
        if capability and capability.get("primary"):
            primary = _normalize_api_config_row(capability["primary"])
            fallback = (
                _normalize_api_config_row(capability["fallback"])
                if capability.get("fallback")
                else None
            )
            return {
                "primary": primary,
                "fallback": fallback,
                "review_config": capability["capability"],
                "capability_key": effective_capability_key,
            }

    review_config = load_review_config(review_config_id, category_id)
    api_config = None
    backup_config = None

    if review_config:
        api_config = load_api_config_by_id(review_config.get("api_config_id"))
        backup_config = load_api_config_by_id(review_config.get("backup_api_config_id"))

    if api_config is None:
        api_config = load_primary_api_config()

    return {
        "primary": api_config,
        "fallback": backup_config,
        "review_config": review_config,
        "capability_key": effective_capability_key,
    }
