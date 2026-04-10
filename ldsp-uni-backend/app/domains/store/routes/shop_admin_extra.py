"""Missing shop admin routes."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user
from app.gateway.agents.registry import registry
from app.domains.store.services.ai_capability_service import AICapabilityService
from app.domains.store.services.agent_runtime_service import AgentRuntimeService

router = APIRouter(tags=["store"])


def _db() -> sqlite3.Connection:
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


class ShopCreateAdmin(BaseModel):
    name: str = ""
    description: str = ""
    owner_id: int = 0
    tags: list[str] = []
    contact: str = ""


class CategoryUpdatePayload(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class StoreUpdatePayload(BaseModel):
    name: str | None = None
    address: str | None = None
    contact: str | None = None


class ForbiddenWordUpdate(BaseModel):
    word: str | None = None
    replacement: str | None = None


class BuyRequestDeletePayload(BaseModel):
    reason: str = ""


class ReportStatusUpdate(BaseModel):
    status: str
    admin_note: str = ""


class CampaignMessageDetail(BaseModel):
    title: str = ""
    content: str = ""
    recipients: list[int] = []


class CommentAIConfigTest(BaseModel):
    config: dict = {}
    sample_comment: str = ""


class CommentReviewPayload(BaseModel):
    action: str = "approve"
    reason: str = ""


class CommentReportStatusUpdate(BaseModel):
    status: str
    admin_note: str = ""


class AnalyticsReportGeneratePayload(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    filters: dict = {}


class ReportConfigUpdate(BaseModel):
    name: str | None = None
    config: dict = {}


class OpsCopilotTestPayload(BaseModel):
    query: str = ""
    params: dict = {}


# ---------------------------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------------------------


@router.get("/api/admin/shops")
async def admin_list_shops_extra(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    keyword: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        if keyword:
            where += " AND (name LIKE ? OR description LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        cur = conn.execute(f"SELECT COUNT(*) as total FROM shops {where}", params)
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shops {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/admin/shops")
async def admin_create_shop_extra(
    payload: ShopCreateAdmin, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        tags_str = ",".join(payload.tags) if payload.tags else ""
        cur = conn.execute(
            "INSERT INTO shops (name, description, tags, contact, owner_id, status, created_at) VALUES (?, ?, ?, ?, ?, 'approved', ?)",
            (
                payload.name,
                payload.description,
                tags_str,
                payload.contact,
                payload.owner_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM shops WHERE id = ?", (cur.lastrowid,))
        return success_response(data=_row_to_dict(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/categories/{category_id}")
async def admin_update_category_path(
    category_id: int,
    payload: CategoryUpdatePayload,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的字段")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), category_id]
        conn.execute(f"UPDATE shop_categories SET {set_clause} WHERE id = ?", params)
        conn.commit()
        cur = conn.execute("SELECT * FROM shop_categories WHERE id = ?", (category_id,))
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/categories/{category_id}")
async def admin_delete_category_path(
    category_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute("DELETE FROM shop_categories WHERE id = ?", (category_id,))
        conn.commit()
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/stores/{store_id}")
async def admin_delete_store_path(
    store_id: int, user: dict = Depends(get_current_user)
):
    """Legacy-compatible delete path for old admin-panel store CRUD."""
    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        store = conn.execute(
            "SELECT id, product_type, category_id FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (store_id,),
        ).fetchone()
        if not store:
            return error_response("NOT_FOUND", "小店不存在", 404)
        if str(store["product_type"] or "") != "store":
            return error_response("INVALID_TYPE", "该商品不是小店类型", 400)

        admin_name = str(user.get("username") or "Admin")
        conn.execute(
            "UPDATE shop_products SET is_deleted = 1, deleted_at = ?, deleted_by = ?, updated_at = ? WHERE id = ?",
            (now_ms, f"admin:{admin_name}", now_ms, store_id),
        )
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, 'admin_delete_store', ?, '管理员删除小店', ?)",
            (store_id, admin_name, now_ms),
        )
        conn.execute(
            "UPDATE shop_categories SET product_count = (SELECT COUNT(*) FROM shop_products WHERE category_id = ? AND (is_deleted = 0 OR is_deleted IS NULL)) WHERE id = ?",
            (int(store["category_id"] or 0), int(store["category_id"] or 0)),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "小店已删除"})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/buy-chat/forbidden-words/{word_id}")
async def admin_delete_forbidden_word_path(
    word_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute(
            "DELETE FROM shop_buy_chat_forbidden_words WHERE id = ?", (word_id,)
        )
        conn.commit()
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/buy-chat/forbidden-words/{word_id}")
async def admin_update_forbidden_word_path(
    word_id: int,
    payload: ForbiddenWordUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的字段")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), word_id]
        conn.execute(
            f"UPDATE shop_buy_chat_forbidden_words SET {set_clause} WHERE id = ?",
            params,
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_chat_forbidden_words WHERE id = ?", (word_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/buy-requests/{request_id}")
async def admin_delete_buy_request(
    request_id: int,
    reason: str = "",
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        conn.execute("DELETE FROM shop_buy_requests WHERE id = ?", (request_id,))
        conn.commit()
        return success_response(data={"deleted": True, "reason": reason})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/reports/overview")
async def admin_reports_overview(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_product_reports WHERE status = 'pending'"
        )
        pending = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_product_reports WHERE status = 'resolved'"
        )
        resolved = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT report_source as type, COUNT(*) as c FROM shop_product_reports GROUP BY report_source ORDER BY c DESC"
        )
        by_type = {row["type"]: row["c"] for row in cur.fetchall()}
        return success_response(
            data={
                "pending": pending,
                "resolved": resolved,
                "by_type": by_type,
            }
        )
    except Exception:
        return success_response(data={"pending": 0, "resolved": 0, "by_type": {}})
    finally:
        conn.close()


@router.post("/api/admin/shop/reports/{report_id}/status")
async def admin_update_report_status(
    report_id: int,
    payload: ReportStatusUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_product_reports SET status = ?, admin_note = ?, handled_by = ?, handled_at = ?, updated_at = ? WHERE id = ?",
            (
                payload.status,
                payload.admin_note,
                user.get("username") or "admin",
                now_ms,
                now_ms,
                report_id,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_product_reports WHERE id = ?", (report_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/messages/{message_id}")
async def admin_get_message_detail(
    message_id: int, user: dict = Depends(get_current_user)
):
    recipientStatus: str = Query("", alias="recipientStatus")
    search: str = Query("")
    page: int = Query(1, ge=1)
    pageSize: int = Query(20, ge=1, le=100)
    conn = _db()
    try:
        campaign = conn.execute(
            """SELECT c.*, 
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id), 0) AS total_recipients,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'pending'), 0) AS pending_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'sent'), 0) AS sent_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'failed'), 0) AS failed_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'cancelled'), 0) AS cancelled_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t JOIN shop_user_messages m ON m.id = t.message_id WHERE t.campaign_id = c.id AND t.status = 'sent' AND COALESCE(m.is_read, 0) = 1), 0) AS read_count
               FROM shop_admin_message_campaigns c
               WHERE c.id = ? LIMIT 1""",
            (message_id,),
        ).fetchone()
        campaign_row = _row_to_dict(campaign)
        if campaign_row is None:
            return error_response("MESSAGE_NOT_FOUND", "消息不存在", 404)

        offset = (page - 1) * pageSize
        where = ["campaign_id = ?"]
        params: list = [message_id]
        if recipientStatus:
            where.append("status = ?")
            params.append(recipientStatus)
        if search.strip():
            like = f"%{search.strip()}%"
            where.append("(username LIKE ? OR name LIKE ? OR user_id LIKE ?)")
            params.extend([like, like, like])
        where_sql = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_admin_message_targets WHERE {where_sql}",
            params,
        ).fetchone()["total"]
        targets = _rows_to_dicts(
            conn.execute(
                f"SELECT * FROM shop_admin_message_targets WHERE {where_sql} ORDER BY id ASC LIMIT ? OFFSET ?",
                (*params, pageSize, offset),
            ).fetchall()
        )
        return success_response(
            data={
                "campaign": campaign_row,
                "targets": targets,
                "recipients": targets,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": pageSize,
                    "totalPages": (total + pageSize - 1) // pageSize
                    if total > 0
                    else 1,
                },
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/comment-ai/config/test")
async def admin_test_comment_ai(
    payload: CommentAIConfigTest, user: dict = Depends(get_current_user)
):
    try:
        sample = (payload.sample_comment or "").strip()
        if not sample:
            return error_response("INVALID_PARAMS", "sample_comment 不能为空", 400)
        capability = AICapabilityService().resolve_capability("shop_comment_review")
        result = await AgentRuntimeService().run_comment_review(
            content=sample,
            target_id="comment-config-test",
            context={
                "review_config_id": (payload.config or {}).get("config_id"),
                "category_id": (payload.config or {}).get("category_id"),
                "product_name": (payload.config or {}).get("product_name")
                or "测试商品",
                "username": user.get("username") or "admin",
            },
            trigger_source="manual_test",
            operator={
                "user_id": str(user.get("user_id") or "admin"),
                "username": user.get("username") or "admin",
            },
        )
        result = {
            "tested": True,
            "sample_comment": payload.sample_comment,
            "config": payload.config,
            "result": result,
            "verdict": result.get("decision"),
            "score": result.get("confidence"),
            "reason": result.get("reason"),
            "capability_key": "shop_comment_review",
            "provider_type": result.get("provider_type")
            or ((capability or {}).get("primary") or {}).get("provider_type")
            or "openai_compatible",
            "gateway_route": result.get("gateway_route")
            or ((capability or {}).get("primary") or {}).get("gateway_route")
            or "",
        }
        return success_response(data=result)
    except Exception as e:
        return error_response("TEST_FAILED", str(e), 500)


@router.post("/api/admin/shop/comments/{comment_id}/review")
async def admin_review_comment(
    comment_id: int,
    payload: CommentReviewPayload,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        status_map = {
            "approve": "manual_approved",
            "reject": "manual_rejected",
            "hide": "hidden",
        }
        new_status = status_map.get(payload.action, payload.action)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_product_comments SET status = ?, manual_reason = ?, manual_reviewer = ?, manual_reviewed_at = ?, updated_at = ? WHERE id = ?",
            (
                new_status,
                payload.reason,
                user.get("username") or "admin",
                now_ms,
                now_ms,
                comment_id,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_product_comments WHERE id = ?", (comment_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("REVIEW_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/comments/{comment_id}/ai-review")
async def admin_ai_review_comment(
    comment_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        comment = _row_to_dict(
            conn.execute(
                "SELECT * FROM shop_product_comments WHERE id = ? LIMIT 1",
                (comment_id,),
            ).fetchone()
        )
        if not comment:
            return error_response("NOT_FOUND", "评论不存在", 404)
        result = await AgentRuntimeService().run_comment_review(
            content=comment.get("content") or "",
            target_id=f"comment:{comment_id}",
            context={
                "comment_id": comment_id,
                "product_id": comment.get("product_id") or 0,
                "username": comment.get("username") or "",
            },
            trigger_source="admin_manual_review",
            operator={
                "user_id": str(user.get("user_id") or "admin"),
                "username": user.get("username") or "admin",
            },
        )
        return success_response(data=result)
    except Exception as e:
        return error_response("REVIEW_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/comment-reports/{report_id}/status")
async def admin_update_comment_report_status(
    report_id: int,
    payload: CommentReportStatusUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_product_comment_reports SET status = ?, admin_note = ?, handled_by = ?, handled_at = ?, updated_at = ? WHERE id = ?",
            (
                payload.status,
                payload.admin_note,
                user.get("username") or "admin",
                now_ms,
                now_ms,
                report_id,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_product_comment_reports WHERE id = ?", (report_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/analytics/reports/{run_id}")
async def admin_analytics_report_detail(
    run_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM generated_reports WHERE id = ?", (run_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("REPORT_NOT_FOUND", "报告不存在", 404)
        return success_response(data=row)
    except Exception:
        return success_response(data={"id": run_id})
    finally:
        conn.close()


@router.post("/api/admin/shop/analytics/reports/{report_type}/generate")
async def admin_generate_report_type(
    report_type: str,
    payload: AnalyticsReportGeneratePayload,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        import json as _json

        filters_str = _json.dumps(payload.filters)
        cur = conn.execute(
            "INSERT INTO generated_reports (report_type, start_date, end_date, filters, status, created_at) VALUES (?, ?, ?, ?, 'generating', ?)",
            (
                report_type,
                payload.start_date,
                payload.end_date,
                filters_str,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM generated_reports WHERE id = ?", (cur.lastrowid,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("GENERATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/analytics/report-configs/{report_type}")
async def admin_update_report_config(
    report_type: str,
    payload: ReportConfigUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        import json as _json

        config_str = _json.dumps(payload.config)
        updates = {"config": config_str}
        if payload.name:
            updates["name"] = payload.name
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), report_type]
        conn.execute(
            f"UPDATE report_configs SET {set_clause} WHERE report_type = ?", params
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM report_configs WHERE report_type = ?", (report_type,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/analytics/ops-copilot/blueprint")
async def admin_ops_copilot_blueprint(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT COUNT(*) as c FROM shops")
        shops = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM products")
        products = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM orders")
        orders = cur.fetchone()["c"]
        return success_response(
            data={
                "blueprint": {
                    "shops": shops,
                    "products": products,
                    "orders": orders,
                },
                "modules": ["reports", "analytics", "copilot"],
            }
        )
    except Exception:
        return success_response(
            data={"blueprint": {}, "modules": ["reports", "analytics", "copilot"]}
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/analytics/ops-copilot/test")
async def admin_ops_copilot_test(
    payload: OpsCopilotTestPayload, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        result = {
            "query": payload.query,
            "params": payload.params,
            "answer": "Ops copilot test response",
            "data": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return success_response(data=result)
    except Exception as e:
        return error_response("TEST_FAILED", str(e), 500)
    finally:
        conn.close()
