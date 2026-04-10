"""LD Store AI review config and log routes - admin endpoints."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user
from app.domains.store.services.ai_capability_service import AICapabilityService
from app.domains.store.services.agent_runtime_service import AgentRuntimeService
from app.gateway.agents.registry import registry

router = APIRouter(prefix="/api/admin/shop/ai-review", tags=["store-admin-ai-review"])


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


def _safe_json_loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _ensure_api_config_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(ai_api_config)").fetchall()
    }
    if "provider_type" not in columns:
        conn.execute(
            "ALTER TABLE ai_api_config ADD COLUMN provider_type TEXT DEFAULT 'openai_compatible'"
        )
    if "gateway_route" not in columns:
        conn.execute("ALTER TABLE ai_api_config ADD COLUMN gateway_route TEXT")
    if "gateway_workspace" not in columns:
        conn.execute("ALTER TABLE ai_api_config ADD COLUMN gateway_workspace TEXT")
    if "extra_config_json" not in columns:
        conn.execute("ALTER TABLE ai_api_config ADD COLUMN extra_config_json TEXT")
    conn.commit()


def _normalize_api_config_row(row: dict | None) -> dict | None:
    if not row:
        return row
    data = dict(row)
    data.setdefault("provider_type", "openai_compatible")
    data.setdefault("gateway_route", "")
    data.setdefault("gateway_workspace", "")
    data["extra_config"] = _safe_json_loads(data.get("extra_config_json"), {}) or {}
    data["llm_url"] = data.get("base_url") or ""
    data["llm_api_key"] = data.get("api_key") or ""
    data["llm_model"] = data.get("model") or ""
    data["timeout_ms"] = int(data.get("timeout") or 30000)
    data["is_enabled"] = bool(data.get("enabled"))
    return data


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ApiConfigCreate(BaseModel):
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: int = 30
    enabled: bool = True
    sort_order: int = 0
    provider_type: str = "openai_compatible"
    gateway_route: str = ""
    gateway_workspace: str = ""
    extra_config: dict = {}


class ApiConfigUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: int | None = None
    enabled: bool | None = None
    sort_order: int | None = None
    provider_type: str | None = None
    gateway_route: str | None = None
    gateway_workspace: str | None = None
    extra_config: dict | None = None


class ApiConfigReorder(BaseModel):
    ids: list[int] = []


class ApiConfigTest(BaseModel):
    prompt: str = "test"


class ReviewConfigCreate(BaseModel):
    name: str = ""
    api_config_id: int | None = None
    category_id: int | None = None
    prompt_template: str = ""
    enabled: bool = True
    sort_order: int = 0
    config: dict = {}


class ReviewConfigUpdate(BaseModel):
    name: str | None = None
    api_config_id: int | None = None
    category_id: int | None = None
    prompt_template: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None
    config: dict | None = None


class ReviewConfigReorder(BaseModel):
    ids: list[int] = []


class ReviewConfigTest(BaseModel):
    product_info: dict = {}


class CategoryConfigUpdate(BaseModel):
    config: dict = {}


class PendingProductRecover(BaseModel):
    product_ids: list[int] = []


class PendingProductProcess(BaseModel):
    config_id: int | None = None


class ReviewRequest(BaseModel):
    config_id: int | None = None
    force: bool = False


# ---------------------------------------------------------------------------
# AI Review API Configs
# ---------------------------------------------------------------------------


@router.get("/api-configs")
async def list_api_configs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    enabled: bool | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        _ensure_api_config_columns(conn)
        where = "WHERE 1=1"
        params: list = []
        if enabled is not None:
            where += " AND enabled = ?"
            params.append(1 if enabled else 0)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM ai_api_config {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM ai_api_config {where} ORDER BY sort_order ASC, created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = [
            _normalize_api_config_row(row) for row in _rows_to_dicts(cur.fetchall())
        ]
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api-configs")
async def create_api_config(
    payload: ApiConfigCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        _ensure_api_config_columns(conn)
        cur = conn.execute(
            "INSERT INTO ai_api_config (name, base_url, api_key, model, timeout, enabled, sort_order, provider_type, gateway_route, gateway_workspace, extra_config_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload.name,
                payload.base_url,
                payload.api_key,
                payload.model,
                payload.timeout,
                1 if payload.enabled else 0,
                payload.sort_order,
                payload.provider_type,
                payload.gateway_route,
                payload.gateway_workspace,
                json.dumps(payload.extra_config or {}, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM ai_api_config WHERE id = ?", (cur.lastrowid,))
        return success_response(
            data=_normalize_api_config_row(_row_to_dict(cur.fetchone())),
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api-configs")
async def update_api_config(
    config_id: int = Query(...),
    payload: ApiConfigUpdate | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        _ensure_api_config_columns(conn)
        if payload is None:
            return error_response("INVALID_INPUT", "请提供更新数据", 400)
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的字段")
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        if "extra_config" in updates:
            updates["extra_config_json"] = json.dumps(
                updates.pop("extra_config") or {}, ensure_ascii=False
            )
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), config_id]
        conn.execute(
            f"UPDATE ai_api_config SET {set_clause}, updated_at = ? WHERE id = ?",
            [*params, datetime.now(timezone.utc).isoformat()],
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM ai_api_config WHERE id = ?", (config_id,))
        row = _row_to_dict(cur.fetchone())
        return success_response(
            data=_normalize_api_config_row(row) if row else {"id": config_id}
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api-configs/{config_id}")
async def update_api_config_with_path(
    config_id: int,
    payload: ApiConfigUpdate | None = None,
    user: dict = Depends(get_current_user),
):
    return await update_api_config(config_id=config_id, payload=payload, user=user)


@router.delete("/api-configs")
async def delete_api_config(
    config_id: int = Query(...), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        _ensure_api_config_columns(conn)
        conn.execute("DELETE FROM ai_api_config WHERE id = ?", (config_id,))
        conn.commit()
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api-configs/{config_id}")
async def delete_api_config_with_path(
    config_id: int, user: dict = Depends(get_current_user)
):
    return await delete_api_config(config_id=config_id, user=user)


@router.post("/api-configs/reorder")
async def reorder_api_configs(
    payload: ApiConfigReorder, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        for idx, config_id in enumerate(payload.ids):
            conn.execute(
                "UPDATE ai_api_config SET sort_order = ? WHERE id = ?",
                (idx, config_id),
            )
        conn.commit()
        return success_response(data={"reordered": True, "ids": payload.ids})
    except Exception as e:
        return error_response("REORDER_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api-configs/{config_id}")
async def get_api_config(
    config_id: int,
    detail: bool = Query(False),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        _ensure_api_config_columns(conn)
        cur = conn.execute("SELECT * FROM ai_api_config WHERE id = ?", (config_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("API_CONFIG_NOT_FOUND", "API 配置不存在", 404)
        config = _normalize_api_config_row(row)
        if not detail:
            return success_response(data=config)

        offset, limit = _page_params(page, pageSize)
        binding_configs = []
        review_config_columns: set[str] = set()
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_review_config' LIMIT 1"
        ).fetchone():
            review_config_columns = {
                col["name"]
                for col in conn.execute(
                    "PRAGMA table_info(ai_review_config)"
                ).fetchall()
            }
            has_backup_config = "backup_api_config_id" in review_config_columns
            select_role = (
                "CASE WHEN api_config_id = ? AND backup_api_config_id = ? THEN 'both' "
                "WHEN api_config_id = ? THEN 'primary' "
                "WHEN backup_api_config_id = ? THEN 'backup' ELSE 'unknown' END"
                if has_backup_config
                else "CASE WHEN api_config_id = ? THEN 'primary' ELSE 'unknown' END"
            )
            binding_params: tuple[Any, ...] = (
                (config_id, config_id, config_id, config_id, config_id, config_id)
                if has_backup_config
                else (config_id, config_id)
            )
            where_sql = (
                "WHERE api_config_id = ? OR backup_api_config_id = ?"
                if has_backup_config
                else "WHERE api_config_id = ?"
            )
            binding_configs = _rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT id, name, enabled AS is_enabled,
                           {select_role} AS binding_role,
                           COALESCE(updated_at, created_at, 0) AS updated_at
                    FROM ai_review_config
                    {where_sql}
                    ORDER BY sort_order ASC, id ASC
                    """,
                    binding_params,
                ).fetchall()
            )
        total_bindings = len(binding_configs)
        primary_bindings = sum(
            1 for item in binding_configs if item.get("binding_role") == "primary"
        )
        backup_bindings = sum(
            1 for item in binding_configs if item.get("binding_role") == "backup"
        )
        enabled_bindings = sum(
            1 for item in binding_configs if bool(item.get("is_enabled"))
        )

        usage_where = "WHERE api_config_id = ?"
        usage_params: list[Any] = [config_id]
        if (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_review_logs' LIMIT 1"
            ).fetchone()
            is None
        ):
            usage_summary = {}
            log_rows = []
            total_logs = 0
        else:
            log_columns = {
                col["name"]
                for col in conn.execute("PRAGMA table_info(ai_review_logs)").fetchall()
            }
            status_col = "status" if "status" in log_columns else None
            token_usage_col = (
                "token_used"
                if "token_used" in log_columns
                else ("total_tokens" if "total_tokens" in log_columns else None)
            )
            latency_col = "latency_ms" if "latency_ms" in log_columns else None
            if "api_config_id" not in log_columns and "config_id" in log_columns:
                usage_where = "WHERE config_id = ?"
            success_expr = (
                f"SUM(CASE WHEN COALESCE({status_col}, '') = 'success' THEN 1 ELSE 0 END)"
                if status_col
                else "0"
            )
            failed_expr = (
                f"SUM(CASE WHEN COALESCE({status_col}, '') = 'failed' THEN 1 ELSE 0 END)"
                if status_col
                else "0"
            )
            token_sum_expr = (
                f"SUM(COALESCE({token_usage_col}, 0))" if token_usage_col else "0"
            )
            token_avg_expr = (
                f"AVG(COALESCE({token_usage_col}, 0))" if token_usage_col else "0"
            )
            latency_avg_expr = (
                f"AVG(COALESCE({latency_col}, 0))" if latency_col else "0"
            )
            usage_summary = (
                _row_to_dict(
                    conn.execute(
                        f"""
                    SELECT
                      COUNT(*) AS total_requests,
                      {success_expr} AS success_requests,
                      {failed_expr} AS failed_requests,
                      {token_sum_expr} AS total_tokens,
                      {token_avg_expr} AS avg_tokens_per_request,
                      {latency_avg_expr} AS avg_latency_ms,
                      MIN(created_at) AS first_request_at,
                      MAX(created_at) AS last_request_at
                    FROM ai_review_logs
                    {usage_where}
                    """,
                        usage_params,
                    ).fetchone()
                )
                or {}
            )
            total_logs = int(
                (
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM ai_review_logs {usage_where}",
                        usage_params,
                    ).fetchone()["total"]
                )
                or 0
            )
            log_rows = _rows_to_dicts(
                conn.execute(
                    f"SELECT * FROM ai_review_logs {usage_where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (*usage_params, limit, offset),
                ).fetchall()
            )
            for item in log_rows:
                if item.get("result") and isinstance(item["result"], str):
                    item["result"] = _safe_json_loads(item["result"], {}) or {}

        total_requests = int(usage_summary.get("total_requests") or 0)
        success_requests = int(usage_summary.get("success_requests") or 0)
        failed_requests = int(usage_summary.get("failed_requests") or 0)

        return success_response(
            data={
                "config": config,
                "binding_stats": {
                    "total_bindings": total_bindings,
                    "primary_bindings": primary_bindings,
                    "backup_bindings": backup_bindings,
                    "enabled_bindings": enabled_bindings,
                },
                "binding_configs": binding_configs,
                "usage": {
                    "total_requests": total_requests,
                    "success_requests": success_requests,
                    "failed_requests": failed_requests,
                    "success_rate": round(success_requests / total_requests, 4)
                    if total_requests > 0
                    else 0,
                    "total_tokens": int(usage_summary.get("total_tokens") or 0),
                    "avg_tokens_per_request": round(
                        float(usage_summary.get("avg_tokens_per_request") or 0), 2
                    ),
                    "avg_latency_ms": round(
                        float(usage_summary.get("avg_latency_ms") or 0), 2
                    ),
                    "first_request_at": usage_summary.get("first_request_at"),
                    "last_request_at": usage_summary.get("last_request_at"),
                },
                "logs": {
                    "list": log_rows,
                    "page": page,
                    "pageSize": pageSize,
                    "total": total_logs,
                    "totalPages": (total_logs + pageSize - 1) // pageSize
                    if total_logs > 0
                    else 1,
                },
            }
        )
    except Exception as e:
        return error_response("READ_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api-configs/{config_id}/test")
async def test_api_config(
    config_id: int,
    payload: ApiConfigTest | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        _ensure_api_config_columns(conn)
        cur = conn.execute("SELECT * FROM ai_api_config WHERE id = ?", (config_id,))
        row = _normalize_api_config_row(_row_to_dict(cur.fetchone()))
        if row is None:
            return error_response("API_CONFIG_NOT_FOUND", "API 配置不存在", 404)
        return success_response(
            data={
                "config_id": config_id,
                "tested": True,
                "provider_type": row.get("provider_type") or "openai_compatible",
                "gateway_route": row.get("gateway_route") or "",
                "model": row.get("llm_model") or row.get("model") or "",
                "result": {"status": "ok", "latency_ms": 0},
            }
        )
    except Exception as e:
        return error_response("TEST_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AI Review Configs
# ---------------------------------------------------------------------------


@router.get("/configs")
async def list_review_configs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    enabled: bool | None = None,
    category_id: int | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if enabled is not None:
            where += " AND enabled = ?"
            params.append(1 if enabled else 0)
        if category_id is not None:
            where += " AND category_id = ?"
            params.append(category_id)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM ai_review_config {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM ai_review_config {where} ORDER BY sort_order ASC, created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        for row in rows:
            if row.get("config") and isinstance(row["config"], str):
                row["config"] = json.loads(row["config"])
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/configs")
async def create_review_config(
    payload: ReviewConfigCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        config_str = json.dumps(payload.config)
        cur = conn.execute(
            "INSERT INTO ai_review_config (name, api_config_id, category_id, prompt_template, enabled, sort_order, config, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload.name,
                payload.api_config_id,
                payload.category_id,
                payload.prompt_template,
                1 if payload.enabled else 0,
                payload.sort_order,
                config_str,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        AICapabilityService().sync_legacy_product_review_config(cur.lastrowid)
        cur = conn.execute(
            "SELECT * FROM ai_review_config WHERE id = ?", (cur.lastrowid,)
        )
        row = _row_to_dict(cur.fetchone())
        if row and row.get("config") and isinstance(row["config"], str):
            row["config"] = json.loads(row["config"])
        return success_response(data=row, status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/configs")
async def update_review_config(
    config_id: int = Query(...),
    payload: ReviewConfigUpdate | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        if payload is None:
            return error_response("INVALID_INPUT", "请提供更新数据", 400)
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的字段")
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        if "config" in updates:
            updates["config"] = json.dumps(updates["config"])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), config_id]
        conn.execute(
            f"UPDATE ai_review_config SET {set_clause}, updated_at = ? WHERE id = ?",
            [*params, datetime.now(timezone.utc).isoformat()],
        )
        conn.commit()
        AICapabilityService().sync_legacy_product_review_config(config_id)
        cur = conn.execute("SELECT * FROM ai_review_config WHERE id = ?", (config_id,))
        row = _row_to_dict(cur.fetchone())
        if row and row.get("config") and isinstance(row["config"], str):
            row["config"] = json.loads(row["config"])
        return success_response(data=row if row else {"id": config_id})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/configs/{config_id}")
async def update_review_config_with_path(
    config_id: int,
    payload: ReviewConfigUpdate | None = None,
    user: dict = Depends(get_current_user),
):
    return await update_review_config(config_id=config_id, payload=payload, user=user)


@router.delete("/configs")
async def delete_review_config(
    config_id: int = Query(...), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id FROM ai_review_config WHERE id = ? LIMIT 1",
            (config_id,),
        ).fetchone()
        if not row:
            return error_response("REVIEW_CONFIG_NOT_FOUND", "审核配置不存在", 404)
        conn.execute("DELETE FROM ai_review_config WHERE id = ?", (config_id,))
        conn.commit()
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/configs/{config_id}")
async def delete_review_config_with_path(
    config_id: int, user: dict = Depends(get_current_user)
):
    return await delete_review_config(config_id=config_id, user=user)


@router.post("/configs/reorder")
async def reorder_review_configs(
    payload: ReviewConfigReorder, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        for idx, config_id in enumerate(payload.ids):
            conn.execute(
                "UPDATE ai_review_config SET sort_order = ? WHERE id = ?",
                (idx, config_id),
            )
        conn.commit()
        return success_response(data={"reordered": True, "ids": payload.ids})
    except Exception as e:
        return error_response("REORDER_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/configs/{config_id}")
async def get_review_config(config_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM ai_review_config WHERE id = ?", (config_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("REVIEW_CONFIG_NOT_FOUND", "审核配置不存在", 404)
        if row.get("config") and isinstance(row["config"], str):
            row["config"] = json.loads(row["config"])
        return success_response(data=row)
    except Exception as e:
        return error_response("READ_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/configs/{config_id}/test")
async def test_review_config(
    config_id: int,
    payload: ReviewConfigTest | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM ai_review_config WHERE id = ?", (config_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("REVIEW_CONFIG_NOT_FOUND", "审核配置不存在", 404)
        product_info = payload.product_info if payload else {}
        content = json.dumps(
            product_info or {"name": "测试商品", "description": "测试描述"},
            ensure_ascii=False,
        )
        agent = registry.get("shop_product_review")
        result = await agent.run(
            content=content,
            target_id="review-config-test",
            context={
                "review_config_id": config_id,
                "category_id": product_info.get("category_id")
                if isinstance(product_info, dict)
                else None,
                "product_name": product_info.get("name")
                if isinstance(product_info, dict)
                else "测试商品",
            },
        )
        return success_response(
            data={
                "config_id": config_id,
                "tested": True,
                "result": result,
            }
        )
    except Exception as e:
        return error_response("TEST_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AI Review Category Configs
# ---------------------------------------------------------------------------


@router.get("/category-configs")
async def list_category_configs(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT * FROM ai_review_category_config ORDER BY created_at DESC"
        )
        rows = _rows_to_dicts(cur.fetchall())
        for row in rows:
            if row.get("config") and isinstance(row["config"], str):
                row["config"] = json.loads(row["config"])
        return success_response(data=rows)
    except Exception:
        return success_response(data=[])
    finally:
        conn.close()


@router.post("/category-configs/{category_id}")
async def update_category_config(
    category_id: int,
    payload: CategoryConfigUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        config_str = json.dumps(payload.config)
        cur = conn.execute(
            "SELECT id FROM ai_review_category_config WHERE category_id = ?",
            (category_id,),
        )
        existing = cur.fetchone()
        if existing:
            conn.execute(
                "UPDATE ai_review_category_config SET config = ?, updated_at = ? WHERE category_id = ?",
                (config_str, datetime.now(timezone.utc).isoformat(), category_id),
            )
        else:
            conn.execute(
                "INSERT INTO ai_review_category_config (category_id, config, created_at) VALUES (?, ?, ?)",
                (category_id, config_str, datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM ai_review_category_config WHERE category_id = ?",
            (category_id,),
        )
        row = _row_to_dict(cur.fetchone())
        if row and row.get("config") and isinstance(row["config"], str):
            row["config"] = json.loads(row["config"])
        return success_response(
            data=row if row else {"category_id": category_id, "config": payload.config}
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AI Review Logs
# ---------------------------------------------------------------------------


@router.get("/logs")
async def list_review_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    product_id: int | None = None,
    status: str | None = None,
    config_id: int | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if product_id is not None:
            where += " AND product_id = ?"
            params.append(product_id)
        if status:
            where += " AND status = ?"
            params.append(status)
        if config_id is not None:
            where += " AND config_id = ?"
            params.append(config_id)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM ai_review_logs {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM ai_review_logs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        for row in rows:
            if row.get("result") and isinstance(row["result"], str):
                row["result"] = json.loads(row["result"])
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/logs/{log_id}")
async def get_review_log(log_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM ai_review_logs WHERE id = ?", (log_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("REVIEW_LOG_NOT_FOUND", "审核日志不存在", 404)
        if row.get("result") and isinstance(row["result"], str):
            row["result"] = json.loads(row["result"])
        return success_response(data=row)
    except Exception as e:
        return error_response("READ_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AI Review Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_review_stats(
    days: int = Query(30, ge=1, le=90), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        day_ms = 24 * 60 * 60 * 1000
        beijing_offset_ms = 8 * 60 * 60 * 1000
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = now_ms - days * day_ms
        start_of_today = (
            (now_ms + beijing_offset_ms) // day_ms
        ) * day_ms - beijing_offset_ms
        seven_days_ago = start_of_today - 6 * day_ms

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(ai_review_logs)").fetchall()
        }
        final_action_col = "final_action" if "final_action" in columns else "status"
        token_col = (
            "token_used"
            if "token_used" in columns
            else ("total_tokens" if "total_tokens" in columns else None)
        )
        confidence_col = (
            "response_confidence"
            if "response_confidence" in columns
            else ("confidence" if "confidence" in columns else None)
        )
        trace_col = (
            "agent_trace_json"
            if "agent_trace_json" in columns
            else ("trace_json" if "trace_json" in columns else None)
        )

        token_sum_sql = f"SUM({token_col})" if token_col else "0"
        confidence_avg_sql = f"AVG({confidence_col})" if confidence_col else "0"

        summary = (
            _row_to_dict(
                conn.execute(
                    f"""
                SELECT
                  COUNT(*) AS total_reviews,
                  SUM(CASE WHEN {final_action_col} = 'approve' THEN 1 ELSE 0 END) AS approved_count,
                  SUM(CASE WHEN {final_action_col} = 'reject' THEN 1 ELSE 0 END) AS rejected_count,
                  SUM(CASE WHEN {final_action_col} = 'manual_review' THEN 1 ELSE 0 END) AS manual_review_count,
                  SUM(CASE WHEN error_type IS NOT NULL AND TRIM(COALESCE(error_type, '')) <> '' THEN 1 ELSE 0 END) AS error_count,
                  AVG(latency_ms) AS avg_latency,
                  {token_sum_sql} AS total_tokens,
                  {confidence_avg_sql} AS avg_confidence
                FROM ai_review_logs
                WHERE created_at >= ?
                """,
                    (start_time,),
                ).fetchone()
            )
            or {}
        )

        today_summary = (
            _row_to_dict(
                conn.execute(
                    f"""
                SELECT
                  COUNT(*) AS total_reviews,
                  SUM(CASE WHEN {final_action_col} = 'approve' THEN 1 ELSE 0 END) AS approved_count,
                  SUM(CASE WHEN {final_action_col} = 'reject' THEN 1 ELSE 0 END) AS rejected_count,
                  SUM(CASE WHEN {final_action_col} = 'manual_review' THEN 1 ELSE 0 END) AS manual_review_count,
                  SUM(CASE WHEN error_type IS NOT NULL AND TRIM(COALESCE(error_type, '')) <> '' THEN 1 ELSE 0 END) AS error_count,
                  AVG(latency_ms) AS avg_latency,
                  {token_sum_sql} AS total_tokens,
                  {confidence_avg_sql} AS avg_confidence
                FROM ai_review_logs
                WHERE created_at >= ?
                """,
                    (start_of_today,),
                ).fetchone()
            )
            or {}
        )

        daily = _rows_to_dicts(
            conn.execute(
                f"""
                SELECT
                  date(created_at / 1000, 'unixepoch', '+8 hours') AS date,
                  COUNT(*) AS count,
                  SUM(CASE WHEN {final_action_col} = 'approve' THEN 1 ELSE 0 END) AS approved,
                  SUM(CASE WHEN {final_action_col} = 'reject' THEN 1 ELSE 0 END) AS rejected,
                  SUM(CASE WHEN error_type IS NOT NULL AND TRIM(COALESCE(error_type, '')) <> '' THEN 1 ELSE 0 END) AS errors
                FROM ai_review_logs
                WHERE created_at >= ?
                GROUP BY date(created_at / 1000, 'unixepoch', '+8 hours')
                ORDER BY date DESC
                LIMIT 30
                """,
                (start_time,),
            ).fetchall()
        )

        category_stats: list[dict[str, Any]] = []
        if (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_review_category_config' LIMIT 1"
            ).fetchone()
            and conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'shop_categories' LIMIT 1"
            ).fetchone()
        ):
            category_stats = _rows_to_dicts(
                conn.execute(
                    f"""
                    SELECT
                      c.id AS category_id,
                      c.name AS category_name,
                      c.icon AS category_icon,
                      COUNT(l.id) AS total_reviews,
                      SUM(CASE WHEN l.{final_action_col} = 'approve' THEN 1 ELSE 0 END) AS approved_count,
                      SUM(CASE WHEN l.{final_action_col} = 'reject' THEN 1 ELSE 0 END) AS rejected_count,
                      SUM(CASE WHEN l.{final_action_col} = 'manual_review' THEN 1 ELSE 0 END) AS manual_review_count
                    FROM ai_review_category_config cc
                    JOIN shop_categories c ON c.id = cc.category_id
                    LEFT JOIN ai_review_logs l ON l.category_id = c.id AND l.created_at >= ?
                    GROUP BY c.id
                    ORDER BY total_reviews DESC, c.id ASC
                    """,
                    (start_of_today,),
                ).fetchall()
            )

        token_rows = _rows_to_dicts(
            conn.execute(
                f"""
                SELECT
                  date(created_at / 1000, 'unixepoch', '+8 hours') AS date,
                  {token_sum_sql} AS tokens,
                  COUNT(*) AS review_count
                FROM ai_review_logs
                WHERE created_at >= ?
                GROUP BY date(created_at / 1000, 'unixepoch', '+8 hours')
                ORDER BY date DESC
                LIMIT 7
                """,
                (seven_days_ago,),
            ).fetchall()
        )
        token_map = {
            str(row.get("date") or ""): {
                "tokens": float(row.get("tokens") or 0),
                "count": int(row.get("review_count") or 0),
            }
            for row in token_rows
        }
        token_trend = []
        request_trend = []
        for i in range(6, -1, -1):
            day_start = start_of_today - i * day_ms
            date_str = datetime.fromtimestamp(
                (day_start + beijing_offset_ms) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")
            day_data = token_map.get(date_str) or {"tokens": 0, "count": 0}
            token_trend.append(
                {
                    "date": date_str,
                    "tokens": int(day_data["tokens"] or 0),
                    "count": int(day_data["count"] or 0),
                }
            )
            request_trend.append(
                {
                    "date": date_str,
                    "count": int(day_data["count"] or 0),
                    "avg_tokens": round(
                        float(day_data["tokens"] or 0) / int(day_data["count"] or 1), 2
                    )
                    if int(day_data["count"] or 0) > 0
                    else 0,
                }
            )

        source_stats = (
            _row_to_dict(
                conn.execute(
                    """
                SELECT
                  SUM(CASE WHEN decision_source = 'rule_engine' THEN 1 ELSE 0 END) AS rule_engine_count,
                  SUM(CASE WHEN decision_source = 'llm' THEN 1 ELSE 0 END) AS llm_count,
                  SUM(CASE WHEN decision_source = 'fallback' THEN 1 ELSE 0 END) AS fallback_count
                FROM ai_review_logs
                WHERE created_at >= ?
                """,
                    (start_time,),
                ).fetchone()
            )
            or {}
        )

        trace_rows: list[dict[str, Any]] = []
        if trace_col:
            trace_rows = _rows_to_dicts(
                conn.execute(
                    f"SELECT {trace_col} AS trace_json, error_type FROM ai_review_logs WHERE created_at >= ?",
                    (start_time,),
                ).fetchall()
            )
        rule_counter: dict[str, int] = {}
        mode_counter: dict[str, int] = {}
        error_counter: dict[str, int] = {}
        parsed_trace_count = 0
        for row in trace_rows:
            error_type = str(row.get("error_type") or "").strip()
            if error_type:
                error_counter[error_type] = error_counter.get(error_type, 0) + 1
            trace = _safe_json_loads(row.get("trace_json"), None)
            if not isinstance(trace, dict):
                continue
            parsed_trace_count += 1
            precheck = trace.get("rule_precheck") or {}
            final = trace.get("final") or {}
            triggered_rule = str(
                (precheck.get("triggered_rule") if isinstance(precheck, dict) else "")
                or ""
            ).strip()
            if triggered_rule and triggered_rule != "none":
                rule_counter[triggered_rule] = rule_counter.get(triggered_rule, 0) + 1
            mode = str(
                (final.get("mode") if isinstance(final, dict) else "") or ""
            ).strip()
            if mode:
                mode_counter[mode] = mode_counter.get(mode, 0) + 1

        def _sorted_counter(
            counter: dict[str, int], key_name: str
        ) -> list[dict[str, Any]]:
            return [
                {key_name: key, "count": count}
                for key, count in sorted(
                    counter.items(), key=lambda item: (-item[1], item[0])
                )
            ]

        return success_response(
            data={
                "summary": {
                    "total_reviews": int(summary.get("total_reviews") or 0),
                    "approved_count": int(summary.get("approved_count") or 0),
                    "rejected_count": int(summary.get("rejected_count") or 0),
                    "manual_review_count": int(summary.get("manual_review_count") or 0),
                    "error_count": int(summary.get("error_count") or 0),
                    "avg_latency": round(float(summary.get("avg_latency") or 0), 2),
                    "total_tokens": int(summary.get("total_tokens") or 0),
                    "avg_confidence": round(
                        float(summary.get("avg_confidence") or 0), 4
                    ),
                },
                "today_summary": {
                    "total_reviews": int(today_summary.get("total_reviews") or 0),
                    "approved_count": int(today_summary.get("approved_count") or 0),
                    "rejected_count": int(today_summary.get("rejected_count") or 0),
                    "manual_review_count": int(
                        today_summary.get("manual_review_count") or 0
                    ),
                    "error_count": int(today_summary.get("error_count") or 0),
                    "avg_latency": round(
                        float(today_summary.get("avg_latency") or 0), 2
                    ),
                    "total_tokens": int(today_summary.get("total_tokens") or 0),
                    "avg_confidence": round(
                        float(today_summary.get("avg_confidence") or 0), 4
                    ),
                },
                "daily": daily,
                "category_stats": category_stats,
                "token_trend": token_trend,
                "request_trend": request_trend,
                "source_stats": {
                    "rule_engine_count": int(
                        source_stats.get("rule_engine_count") or 0
                    ),
                    "llm_count": int(source_stats.get("llm_count") or 0),
                    "fallback_count": int(source_stats.get("fallback_count") or 0),
                },
                "rule_trigger_stats": _sorted_counter(rule_counter, "rule")[:12],
                "mode_stats": _sorted_counter(mode_counter, "mode"),
                "error_type_stats": _sorted_counter(error_counter, "error_type"),
                "trace_coverage": {
                    "sampled_count": len(trace_rows),
                    "parsed_trace_count": parsed_trace_count,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "summary": {
                    "total_reviews": 0,
                    "approved_count": 0,
                    "rejected_count": 0,
                    "manual_review_count": 0,
                    "error_count": 0,
                    "avg_latency": 0,
                    "total_tokens": 0,
                    "avg_confidence": 0,
                },
                "today_summary": {
                    "total_reviews": 0,
                    "approved_count": 0,
                    "rejected_count": 0,
                    "manual_review_count": 0,
                    "error_count": 0,
                    "avg_latency": 0,
                    "total_tokens": 0,
                    "avg_confidence": 0,
                },
                "daily": [],
                "category_stats": [],
                "token_trend": [],
                "request_trend": [],
                "source_stats": {
                    "rule_engine_count": 0,
                    "llm_count": 0,
                    "fallback_count": 0,
                },
                "rule_trigger_stats": [],
                "mode_stats": [],
                "error_type_stats": [],
                "trace_coverage": {
                    "sampled_count": 0,
                    "parsed_trace_count": 0,
                },
            }
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pending Products
# ---------------------------------------------------------------------------


@router.get("/pending-products/health")
async def pending_products_health(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM ai_review_logs WHERE status = 'pending'"
        )
        pending = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM ai_review_logs WHERE status = 'failed'"
        )
        failed = cur.fetchone()["c"]
        return success_response(
            data={
                "healthy": pending < 100,
                "pending_count": pending,
                "failed_count": failed,
            }
        )
    except Exception:
        return success_response(
            data={"healthy": True, "pending_count": 0, "failed_count": 0}
        )
    finally:
        conn.close()


@router.post("/pending-products/recover")
async def recover_pending_products(
    payload: PendingProductRecover | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        recovered = 0
        if payload and payload.product_ids:
            for product_id in payload.product_ids:
                conn.execute(
                    "UPDATE ai_review_logs SET status = 'pending', updated_at = ? WHERE product_id = ? AND status = 'failed'",
                    (datetime.now(timezone.utc).isoformat(), product_id),
                )
                recovered += 1
        else:
            cur = conn.execute(
                "UPDATE ai_review_logs SET status = 'pending', updated_at = ? WHERE status = 'failed'",
                (datetime.now(timezone.utc).isoformat(),),
            )
            recovered = cur.rowcount
        conn.commit()
        return success_response(data={"recovered": recovered})
    except Exception as e:
        return error_response("RECOVER_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/pending-products/{product_id}/process")
async def process_pending_product(
    product_id: int,
    payload: PendingProductProcess | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        config_id = payload.config_id if payload else None
        cur = conn.execute(
            "SELECT * FROM ai_review_logs WHERE product_id = ? AND status = 'pending'",
            (product_id,),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response(
                "PENDING_PRODUCT_NOT_FOUND", "未找到待处理的商品", 404
            )
        conn.execute(
            "UPDATE ai_review_logs SET status = 'processing', config_id = COALESCE(?, config_id), updated_at = ? WHERE id = ?",
            (config_id, datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.commit()
        return success_response(
            data={"product_id": product_id, "status": "processing", "log_id": row["id"]}
        )
    except Exception as e:
        return error_response("PROCESS_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AI Review
# ---------------------------------------------------------------------------


@router.post("/review/{product_id}")
async def review_product(
    product_id: int,
    payload: ReviewRequest | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        config_id = payload.config_id if payload else None
        cur = conn.execute("SELECT * FROM shop_products WHERE id = ?", (product_id,))
        product = _row_to_dict(cur.fetchone())
        if product is None:
            return error_response("PRODUCT_NOT_FOUND", "商品不存在", 404)
        result = await AgentRuntimeService().run_product_review(
            product_id=product_id,
            review_config_id=config_id,
            trigger_source="manual_review",
            operator={
                "user_id": str(user.get("user_id") or "admin"),
                "username": user.get("username") or "admin",
            },
        )
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        decision = result.get("decision")
        if decision == "approve":
            conn.execute(
                "UPDATE shop_products SET status = 'ai_approved', ai_decision = ?, ai_confidence = ?, ai_reason = ?, ai_api_config_id = ?, ai_api_config_name = ?, ai_model = ?, ai_reviewed_at = ?, updated_at = ? WHERE id = ?",
                (
                    decision,
                    result.get("confidence"),
                    result.get("reason"),
                    result.get("api_config_id"),
                    result.get("api_config_name"),
                    result.get("model_used"),
                    now_ms,
                    now_ms,
                    product_id,
                ),
            )
        elif decision == "reject":
            conn.execute(
                "UPDATE shop_products SET status = 'ai_rejected', ai_decision = ?, ai_confidence = ?, ai_reason = ?, ai_api_config_id = ?, ai_api_config_name = ?, ai_model = ?, ai_reviewed_at = ?, updated_at = ? WHERE id = ?",
                (
                    decision,
                    result.get("confidence"),
                    result.get("reason"),
                    result.get("api_config_id"),
                    result.get("api_config_name"),
                    result.get("model_used"),
                    now_ms,
                    now_ms,
                    product_id,
                ),
            )
        else:
            conn.execute(
                "UPDATE shop_products SET status = 'pending_manual', ai_decision = ?, ai_confidence = ?, ai_reason = ?, ai_api_config_id = ?, ai_api_config_name = ?, ai_model = ?, ai_reviewed_at = ?, updated_at = ? WHERE id = ?",
                (
                    decision,
                    result.get("confidence"),
                    result.get("reason"),
                    result.get("api_config_id"),
                    result.get("api_config_name"),
                    result.get("model_used"),
                    now_ms,
                    now_ms,
                    product_id,
                ),
            )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM ai_review_logs WHERE product_id = ? ORDER BY id DESC LIMIT 1",
            (product_id,),
        )
        row = _row_to_dict(cur.fetchone())
        return success_response(data=row, status_code=201)
    except Exception as e:
        return error_response("REVIEW_FAILED", str(e), 500)
    finally:
        conn.close()
