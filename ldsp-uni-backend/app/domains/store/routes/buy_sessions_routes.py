"""Buy session trading and communication routes."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user
from app.domains.store.services.ldc import (
    create_ldc_order,
    decrypt_ldc_key,
    query_ldc_order,
)

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


def _public_buy_order_status(status: str | None) -> str:
    raw = str(status or "").strip().lower()
    if raw in {"paid", "completed"}:
        return "completed"
    if raw in {"cancelled", "closed"}:
        return "cancelled"
    return raw or "pending"


class SessionStart(BaseModel):
    seller_id: int | None = None
    message: str = ""


class PriceUpdate(BaseModel):
    price: float


class StatusUpdate(BaseModel):
    status: str


class MessageSend(BaseModel):
    content: str = ""
    type: str = "text"


class PaymentCreate(BaseModel):
    amount: float
    method: str = "default"


class MarkPaidPayload(BaseModel):
    note: str = ""


class CloseSessionPayload(BaseModel):
    reason: str = ""


class ReopenSessionPayload(BaseModel):
    reason: str = ""


# ---------------------------------------------------------------------------
# User Auth Routes
# ---------------------------------------------------------------------------


@router.get("/api/shop/buy-requests/{request_id}/sessions")
async def get_buy_request_sessions(
    request_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT COUNT(*) as total FROM shop_buy_sessions
               WHERE request_id = ?
                 AND ((requester_user_id = ? AND requester_site = ?)
                   OR (provider_user_id = ? AND provider_site = ?))""",
            (request_id, user_id, site, user_id, site),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            """SELECT * FROM shop_buy_sessions
               WHERE request_id = ?
                 AND ((requester_user_id = ? AND requester_site = ?)
                   OR (provider_user_id = ? AND provider_site = ?))
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            [request_id, user_id, site, user_id, site, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "sessions": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/shop/buy-requests/{request_id}/sessions")
async def start_buy_session(
    request_id: int,
    payload: SessionStart,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        request_row = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ? LIMIT 1",
            (request_id,),
        ).fetchone()
        if not request_row:
            return error_response("NOT_FOUND", "求购不存在", 404)
        request_row = dict(request_row)
        if (
            str(request_row.get("requester_user_id") or "") == user_id
            and str(request_row.get("requester_site") or "linux.do") == site
        ):
            return error_response("FORBIDDEN", "求购方不能主动发起洽谈", 403)
        existing = conn.execute(
            "SELECT * FROM shop_buy_sessions WHERE request_id = ? AND provider_user_id = ? AND provider_site = ? ORDER BY id DESC LIMIT 1",
            (request_id, user_id, site),
        ).fetchone()
        if existing:
            return success_response(data={"created": False, "session": dict(existing)})
        cur = conn.execute(
            """INSERT INTO shop_buy_sessions (
                request_id, requester_user_id, requester_site, requester_username,
                provider_user_id, provider_site, provider_username,
                status, created_at, updated_at, last_message_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'negotiating', ?, ?, ?)""",
            (
                request_id,
                str(request_row.get("requester_user_id") or ""),
                str(request_row.get("requester_site") or "linux.do"),
                str(request_row.get("requester_username") or ""),
                user_id,
                site,
                user.get("username") or "",
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.execute(
            "UPDATE shop_buy_requests SET status = CASE WHEN status = 'open' THEN 'negotiating' ELSE status END, updated_at = ? WHERE id = ?",
            (int(datetime.now(timezone.utc).timestamp() * 1000), request_id),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_sessions WHERE id = ?", (cur.lastrowid,)
        )
        return success_response(
            data={"created": True, "session": _row_to_dict(cur.fetchone())},
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-requests/{request_id}/price")
async def update_buy_request_price(
    request_id: int,
    payload: PriceUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        conn.execute(
            "UPDATE shop_buy_requests SET budget_price = ?, updated_at = ? WHERE id = ? AND requester_user_id = ? AND requester_site = ?",
            (
                payload.price,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                request_id,
                user_id,
                site,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ?", (request_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-requests/{request_id}/status")
async def update_buy_request_status(
    request_id: int,
    payload: StatusUpdate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        conn.execute(
            "UPDATE shop_buy_requests SET status = ?, updated_at = ? WHERE id = ? AND requester_user_id = ? AND requester_site = ?",
            (
                payload.status,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                request_id,
                user_id,
                site,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ?", (request_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-sessions/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    limit: int | None = Query(None),
    sinceId: int = Query(0, ge=0),
    beforeId: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    effective_size = limit if limit is not None else size
    offset, effective_limit = _page_params(page, effective_size)
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT s.*, r.status AS request_status,
                      COALESCE((SELECT bo.order_no FROM shop_buy_orders bo WHERE bo.session_id = s.id ORDER BY bo.id DESC LIMIT 1), '') AS latest_order_no,
                      COALESCE((SELECT bo.status FROM shop_buy_orders bo WHERE bo.session_id = s.id ORDER BY bo.id DESC LIMIT 1), '') AS latest_order_status,
                      COALESCE((SELECT bo.pay_expired_at FROM shop_buy_orders bo WHERE bo.session_id = s.id ORDER BY bo.id DESC LIMIT 1), 0) AS latest_order_pay_expired_at,
                      COALESCE((SELECT bo.paid_at FROM shop_buy_orders bo WHERE bo.session_id = s.id ORDER BY bo.id DESC LIMIT 1), 0) AS latest_order_paid_at,
                      COALESCE((SELECT bo.completed_at FROM shop_buy_orders bo WHERE bo.session_id = s.id ORDER BY bo.id DESC LIMIT 1), 0) AS latest_order_completed_at
               FROM shop_buy_sessions s
               JOIN shop_buy_requests r ON r.id = s.request_id
               WHERE s.id = ?
               AND ((requester_user_id = ? AND requester_site = ?)
                  OR (provider_user_id = ? AND provider_site = ?))""",
            (session_id, user_id, site, user_id, site),
        )
        session = cur.fetchone()
        if not session:
            return error_response("SESSION_NOT_FOUND", "会话不存在", 404)
        session_row = dict(session)
        where = ["session_id = ?"]
        params: list[Any] = [session_id]
        order_by = "id ASC"
        if sinceId > 0:
            where.append("id > ?")
            params.append(sinceId)
        if beforeId > 0:
            where.append("id < ?")
            params.append(beforeId)
            order_by = "id DESC"
        where_sql = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_buy_messages WHERE {where_sql}",
            params,
        ).fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_buy_messages WHERE {where_sql} ORDER BY {order_by} LIMIT ? OFFSET ?",
            [*params, effective_limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        if beforeId > 0:
            rows.reverse()
        latest_message_id = int(rows[-1]["id"] or 0) if rows else 0
        has_more_before = False
        has_more_after = False
        if rows:
            if beforeId > 0 or sinceId <= 0:
                oldest_id = int(rows[0]["id"] or 0)
                has_more_before = (
                    conn.execute(
                        "SELECT 1 FROM shop_buy_messages WHERE session_id = ? AND id < ? LIMIT 1",
                        (session_id, oldest_id),
                    ).fetchone()
                    is not None
                )
            if sinceId > 0:
                has_more_after = (
                    conn.execute(
                        "SELECT 1 FROM shop_buy_messages WHERE session_id = ? AND id > ? LIMIT 1",
                        (session_id, latest_message_id),
                    ).fetchone()
                    is not None
                )
        return success_response(
            data={
                "items": rows,
                "messages": rows,
                "session": {
                    "id": session_row.get("id"),
                    "status": session_row.get("status") or "negotiating",
                    "requestStatus": session_row.get("request_status") or "open",
                    "providerMarkPaidAt": int(
                        session_row.get("provider_mark_paid_at") or 0
                    ),
                    "requesterConfirmPaidAt": int(
                        session_row.get("requester_confirm_paid_at") or 0
                    ),
                    "contactUnlockedAt": int(
                        session_row.get("contact_unlocked_at") or 0
                    ),
                    "paymentOrderNo": session_row.get("latest_order_no") or "",
                    "paymentOrderStatus": _public_buy_order_status(
                        session_row.get("latest_order_status")
                    )
                    if session_row.get("latest_order_no")
                    else "",
                    "paymentPayExpiredAt": int(
                        session_row.get("latest_order_pay_expired_at") or 0
                    ),
                    "paymentPaidAt": int(session_row.get("latest_order_paid_at") or 0),
                    "paymentCompletedAt": int(
                        session_row.get("latest_order_completed_at") or 0
                    ),
                },
                "total": total,
                "page": page,
                "size": effective_size,
                "limit": effective_size,
                "sinceId": sinceId,
                "beforeId": beforeId,
                "pagination": {
                    "page": page,
                    "pageSize": effective_size,
                    "total": total,
                    "totalPages": (total + effective_size - 1) // effective_size,
                    "hasMoreBefore": has_more_before,
                    "hasMoreAfter": has_more_after,
                    "latestMessageId": latest_message_id,
                    "oldestMessageId": int(rows[0]["id"] or 0) if rows else 0,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "messages": [],
                "session": None,
                "total": 0,
                "page": page,
                "size": effective_size,
                "limit": effective_size,
                "sinceId": sinceId,
                "beforeId": beforeId,
                "pagination": {
                    "page": page,
                    "pageSize": effective_size,
                    "total": 0,
                    "totalPages": 0,
                    "hasMoreBefore": False,
                    "hasMoreAfter": False,
                    "latestMessageId": 0,
                    "oldestMessageId": 0,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/shop/buy-sessions/{session_id}/messages")
async def send_session_message(
    session_id: int,
    payload: MessageSend,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        session_row = conn.execute(
            """SELECT * FROM shop_buy_sessions WHERE id = ?
               AND ((requester_user_id = ? AND requester_site = ?)
                 OR (provider_user_id = ? AND provider_site = ?))""",
            (session_id, user_id, site, user_id, site),
        ).fetchone()
        if not session_row:
            return error_response("SESSION_NOT_FOUND", "会话不存在", 404)
        session_row = dict(session_row)
        sender_role = (
            "requester"
            if (
                str(session_row.get("requester_user_id") or "") == user_id
                and str(session_row.get("requester_site") or "linux.do") == site
            )
            else "provider"
        )
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            "INSERT INTO shop_buy_messages (request_id, session_id, sender_role, sender_user_id, sender_site, sender_username, content, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(session_row.get("request_id") or 0),
                session_id,
                sender_role,
                user_id,
                site,
                user.get("username") or "",
                payload.content,
                now_ms,
            ),
        )
        conn.execute(
            "UPDATE shop_buy_sessions SET last_message_at = ?, updated_at = ? WHERE id = ?",
            (now_ms, now_ms, session_id),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_messages WHERE id = ?", (cur.lastrowid,)
        )
        return success_response(
            data={"message": _row_to_dict(cur.fetchone())}, status_code=201
        )
    except Exception as e:
        return error_response("SEND_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-sessions/{session_id}/payment")
async def create_session_payment(
    session_id: int,
    payload: PaymentCreate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        session_row = conn.execute(
            """SELECT s.*, r.title as request_title, r.budget_price as request_budget_price,
                      r.requester_user_id, r.requester_site, r.requester_username,
                      s.provider_user_id, s.provider_site, s.provider_username,
                      s.contact_unlocked_at
               FROM shop_buy_sessions s
               JOIN shop_buy_requests r ON r.id = s.request_id
               WHERE s.id = ? LIMIT 1""",
            (session_id,),
        ).fetchone()
        if not session_row:
            return error_response("NOT_FOUND", "会话不存在", 404)
        session_row = dict(session_row)
        is_requester = (
            str(session_row.get("requester_user_id") or "") == user_id
            and str(session_row.get("requester_site") or "linux.do") == site
        )
        if not is_requester:
            return error_response("FORBIDDEN", "仅求购方可创建支付订单", 403)
        if session_row.get("contact_unlocked_at"):
            return error_response("ORDER_COMPLETED", "订单已完成，联系方式已开放", 400)

        latest_order = conn.execute(
            "SELECT * FROM shop_buy_orders WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if (
            latest_order
            and str(latest_order["status"] or "") == "pending"
            and int(latest_order["pay_expired_at"] or 0) > now_ms
        ):
            return success_response(
                data={
                    "created": False,
                    "order": {
                        **dict(latest_order),
                        "paymentUrl": latest_order["payment_url"] or "",
                    },
                }
            )
        if (
            latest_order
            and str(latest_order["status"] or "") == "pending"
            and int(latest_order["pay_expired_at"] or 0) <= now_ms
        ):
            conn.execute(
                "UPDATE shop_buy_orders SET status = 'expired', updated_at = ? WHERE id = ? AND status = 'pending'",
                (now_ms, latest_order["id"]),
            )

        merchant = conn.execute(
            "SELECT ldc_pid, ldc_key_encrypted, is_active, is_verified FROM shop_merchant_config WHERE user_id = ? AND site = ? LIMIT 1",
            (
                str(session_row.get("provider_user_id") or ""),
                str(session_row.get("provider_site") or "linux.do"),
            ),
        ).fetchone()
        if not merchant or not merchant["ldc_pid"] or not merchant["ldc_key_encrypted"]:
            return error_response(
                "PROVIDER_NOT_CONFIGURED",
                "服务方未配置可用的收款信息，暂时无法支付",
                400,
            )
        if not merchant["is_active"] or not merchant["is_verified"]:
            return error_response(
                "PROVIDER_MERCHANT_DISABLED",
                "服务方收款配置未启用或未通过审核，暂时无法支付",
                400,
            )

        amount = float(session_row.get("request_budget_price") or payload.amount or 0)
        if amount <= 0:
            return error_response("INVALID_AMOUNT", "金额无效", 400)
        order_no = f"LB{now_ms}"
        expire_at = now_ms + 5 * 60 * 1000
        worker_url = (
            settings.worker_url or settings.api_base_url or "https://api.ldspro.qzz.io"
        ).rstrip("/")
        notify_url = f"{worker_url}/api/shop/ldc/notify"
        return_url = f"{worker_url}/api/shop/ldc/return"
        ldc_key_plain = decrypt_ldc_key(
            str(merchant["ldc_key_encrypted"]), settings.jwt_secret_key
        )
        request_title = str(
            session_row.get("request_title") or f"求购#{session_row.get('request_id')}"
        )[:40]
        ldc_result = await create_ldc_order(
            pid=str(merchant["ldc_pid"]),
            key=ldc_key_plain,
            order_no=order_no,
            product_name=f"LD士多求购 - {request_title}",
            amount=amount,
            notify_url=notify_url,
            return_url=return_url,
        )
        if not ldc_result.get("success"):
            return error_response(
                "LDC_ERROR", ldc_result.get("error") or "创建支付订单失败", 500
            )

        cur = conn.execute(
            """INSERT INTO shop_buy_orders (
                order_no, session_id, request_id,
                requester_user_id, requester_site, requester_username,
                provider_user_id, provider_site, provider_username,
                amount, status, payment_url, pay_expired_at,
                merchant_pid_snapshot, merchant_key_encrypted_snapshot, merchant_config_snapshot_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (
                order_no,
                session_id,
                int(session_row.get("request_id") or 0),
                str(session_row.get("requester_user_id") or ""),
                str(session_row.get("requester_site") or "linux.do"),
                str(session_row.get("requester_username") or ""),
                str(session_row.get("provider_user_id") or ""),
                str(session_row.get("provider_site") or "linux.do"),
                str(session_row.get("provider_username") or ""),
                amount,
                ldc_result.get("paymentUrl"),
                expire_at,
                merchant["ldc_pid"],
                merchant["ldc_key_encrypted"],
                now_ms,
                now_ms,
                now_ms,
            ),
        )
        conn.execute(
            "INSERT INTO shop_buy_messages (request_id, session_id, sender_role, content, created_at) VALUES (?, ?, 'system', ?, ?)",
            (
                int(session_row.get("request_id") or 0),
                session_id,
                f"Requester created payment order ({order_no}). Complete payment on platform, contact unlocks after callback confirmation.",
                now_ms,
            ),
        )
        conn.execute(
            "UPDATE shop_buy_sessions SET last_message_at = ?, updated_at = ? WHERE id = ?",
            (now_ms, now_ms, session_id),
        )
        conn.execute(
            "UPDATE shop_buy_requests SET updated_at = ? WHERE id = ?",
            (now_ms, int(session_row.get("request_id") or 0)),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_orders WHERE id = ?", (cur.lastrowid,)
        )
        order_row = _row_to_dict(cur.fetchone()) or {}
        order_row["paymentUrl"] = order_row.get("payment_url") or ""
        return success_response(
            data={"created": True, "order": order_row}, status_code=201
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-sessions/{session_id}/mark-paid")
async def mark_session_paid(
    session_id: int,
    payload: MarkPaidPayload,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        conn.execute(
            "UPDATE shop_buy_sessions SET status = 'paid', provider_mark_paid_at = ?, updated_at = ? WHERE id = ? AND provider_user_id = ?",
            (
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                session_id,
                user_id,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_sessions WHERE id = ?", (session_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-sessions/{session_id}/confirm-paid")
async def confirm_session_paid(
    session_id: int,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        conn.execute(
            "UPDATE shop_buy_sessions SET status = 'paid', requester_confirm_paid_at = ?, contact_unlocked_at = COALESCE(contact_unlocked_at, ?), updated_at = ? WHERE id = ? AND requester_user_id = ?",
            (
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                session_id,
                user_id,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_sessions WHERE id = ?", (session_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("CONFIRM_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-sessions/{session_id}/close")
async def close_session(
    session_id: int,
    payload: CloseSessionPayload,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        conn.execute(
            "UPDATE shop_buy_sessions SET status = 'closed', closed_at = ?, close_reason = ?, updated_at = ? WHERE id = ? AND (requester_user_id = ? OR provider_user_id = ?)",
            (
                int(datetime.now(timezone.utc).timestamp() * 1000),
                payload.reason,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                session_id,
                user_id,
                user_id,
            ),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "会话已关闭"})
    except Exception as e:
        return error_response("CLOSE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-sessions/{session_id}/reopen")
async def reopen_session(
    session_id: int,
    payload: ReopenSessionPayload,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        conn.execute(
            "UPDATE shop_buy_sessions SET status = 'negotiating', closed_at = NULL, close_reason = ?, updated_at = ? WHERE id = ? AND (requester_user_id = ? OR provider_user_id = ?)",
            (
                payload.reason,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                session_id,
                user_id,
                user_id,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_sessions WHERE id = ?", (session_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("REOPEN_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------------------------


@router.get("/api/admin/shop/buy-sessions")
async def admin_list_buy_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
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
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM buy_sessions {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM buy_sessions {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
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


@router.get("/api/admin/shop/buy-sessions/{session_id}")
async def admin_get_buy_session(
    session_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM buy_sessions WHERE id = ?", (session_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("SESSION_NOT_FOUND", "会话不存在", 404)
        return success_response(data=row)
    except Exception:
        return success_response(data={"id": session_id})
    finally:
        conn.close()


@router.get("/api/admin/shop/buy-sessions/{session_id}/messages")
async def admin_get_session_messages(
    session_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as total FROM buy_messages WHERE session_id = ?",
            (session_id,),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            "SELECT * FROM buy_messages WHERE session_id = ? ORDER BY created_at LIMIT ? OFFSET ?",
            [session_id, limit, offset],
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
