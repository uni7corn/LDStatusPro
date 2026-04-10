"""Order detail and management routes."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user
from app.domains.store.services.ldc import decrypt_ldc_key, query_ldc_order

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


def _safe_json_loads(value, fallback=None):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return __import__("json").loads(value)
    except Exception:
        return fallback


def _enrich_order(order: dict | None) -> dict | None:
    if not order:
        return order
    enriched = dict(order)
    snapshot = _safe_json_loads(enriched.get("product_snapshot"), {}) or {}
    if snapshot:
        enriched["product"] = snapshot
    product_type = str(snapshot.get("product_type") or "")
    enriched["order_type"] = (
        "normal"
        if product_type == "normal"
        else ("cdk" if product_type == "cdk" else enriched.get("order_type") or "cdk")
    )
    enriched["requires_buyer_contact"] = product_type == "normal"
    enriched["comment_enabled"] = product_type in {"normal", "cdk"}
    return enriched


def _enrich_buy_order(order: dict | None) -> dict | None:
    if not order:
        return order
    enriched = dict(order)
    enriched["orderNo"] = enriched.get("order_no") or ""
    enriched["requestId"] = int(enriched.get("request_id") or 0)
    enriched["sessionId"] = int(enriched.get("session_id") or 0)
    enriched["requestTitle"] = enriched.get("request_title") or ""
    enriched["requestBudgetPrice"] = float(enriched.get("request_budget_price") or 0)
    enriched["sessionStatus"] = enriched.get("session_status") or ""
    enriched["chatPath"] = (
        f"/buy-request/{enriched.get('requestId') or 0}?session={enriched.get('sessionId') or 0}"
    )
    return enriched


def _page_params(page: int = 1, size: int = 20) -> tuple[int, int]:
    page = max(1, page)
    size = max(1, min(size, 100))
    return (page - 1) * size, size


# ---------------------------------------------------------------------------
# User Auth Routes
# ---------------------------------------------------------------------------


@router.get("/api/shop/orders/{order_no}")
async def get_order_detail(
    order_no: str,
    role: str = Query("buyer"),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        safe_role = "seller" if str(role or "").strip() == "seller" else "buyer"
        user_column = "seller_user_id" if safe_role == "seller" else "buyer_user_id"
        site_column = "seller_site" if safe_role == "seller" else "buyer_site"
        cur = conn.execute(
            f"SELECT * FROM shop_orders WHERE order_no = ? AND {user_column} = ? AND {site_column} = ?",
            (order_no, str(user_id), site),
        )
        row = _enrich_order(_row_to_dict(cur.fetchone()))
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        logs = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_order_logs WHERE order_id = ? ORDER BY created_at DESC LIMIT 50",
                (row.get("id"),),
            ).fetchall()
        )
        return success_response(data={"order": row, "logs": logs})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/orders/{order_no}/cancel")
async def cancel_order(
    order_no: str,
    reason: str = "",
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT status FROM shop_orders WHERE order_no = ? AND buyer_user_id = ?",
            (order_no, str(user_id)),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        if row["status"] not in ("pending",):
            return error_response("ORDER_NOT_CANCELLABLE", "订单当前状态不可取消", 400)
        conn.execute(
            "UPDATE shop_orders SET status = 'cancelled', buyer_cancel_reason = ?, updated_at = ? WHERE order_no = ? AND buyer_user_id = ?",
            (
                reason,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                order_no,
                str(user_id),
            ),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "订单已取消"})
    except Exception as e:
        return error_response("CANCEL_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/orders/{order_no}/payment-url")
async def get_order_payment_url(order_no: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT * FROM shop_orders WHERE order_no = ? AND buyer_user_id = ?",
            (order_no, str(user_id)),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        payment_url = (row.get("payment_url") or "").strip()
        if not payment_url:
            return error_response("PAYMENT_URL_NOT_READY", "订单尚未生成支付链接", 409)
        return success_response(data={"paymentUrl": payment_url, "orderNo": order_no})
    except Exception as e:
        return error_response("PAYMENT_URL_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/orders/{order_no}/refresh")
async def refresh_order_payment(order_no: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT * FROM shop_orders WHERE order_no = ? AND buyer_user_id = ?",
            (order_no, str(user_id)),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        if row.get("status") in ("delivered", "paid"):
            return success_response(
                data={
                    "order": _enrich_order(row),
                    "status": row.get("status"),
                    "message": "订单状态已刷新",
                }
            )
        merchant_pid = str(row.get("merchant_pid_snapshot") or "").strip()
        encrypted_key = str(row.get("merchant_key_encrypted_snapshot") or "").strip()
        if merchant_pid and encrypted_key:
            try:
                key_plain = decrypt_ldc_key(encrypted_key, settings.jwt_secret_key)
                query = await query_ldc_order(
                    pid=merchant_pid,
                    key=key_plain,
                    trade_no=str(row.get("ldc_trade_no") or ""),
                    order_no=order_no,
                )
                if (
                    query.get("success")
                    and str(query.get("data", {}).get("status") or "") == "1"
                ):
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    conn.execute(
                        "UPDATE shop_orders SET status = 'paid', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE order_no = ? AND buyer_user_id = ?",
                        (
                            query.get("data", {}).get("tradeNo"),
                            now_ms,
                            now_ms,
                            order_no,
                            str(user_id),
                        ),
                    )
                    if str(row.get("delivery_type") or "") == "auto":
                        locked = conn.execute(
                            "SELECT id, code FROM shop_cdk WHERE lock_order_id = (SELECT id FROM shop_orders WHERE order_no = ?) AND status = 'locked' ORDER BY created_at ASC",
                            (order_no,),
                        ).fetchall()
                        if locked:
                            delivery_content = "\n".join(str(r["code"]) for r in locked)
                            conn.execute(
                                "UPDATE shop_orders SET status = 'delivered', delivery_content = ?, delivered_at = ?, updated_at = ? WHERE order_no = ? AND buyer_user_id = ?",
                                (
                                    delivery_content,
                                    now_ms,
                                    now_ms,
                                    order_no,
                                    str(user_id),
                                ),
                            )
                            for item in locked:
                                conn.execute(
                                    "UPDATE shop_cdk SET status = 'sold', sold_at = ?, lock_token = NULL WHERE id = ?",
                                    (now_ms, item["id"]),
                                )
                    conn.commit()
                    cur = conn.execute(
                        "SELECT * FROM shop_orders WHERE order_no = ? AND buyer_user_id = ?",
                        (order_no, str(user_id)),
                    )
                    row = _row_to_dict(cur.fetchone())
            except Exception:
                pass
        return success_response(
            data={
                "order": _enrich_order(row),
                "status": row.get("status"),
                "message": "订单状态已刷新",
            }
        )
    except Exception as e:
        return error_response("REFRESH_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/orders/{order_no}/deliver")
async def deliver_order(
    order_no: str,
    deliver_note: str = "",
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT * FROM shop_orders WHERE order_no = ? AND seller_user_id = ?",
            (order_no, str(user_id)),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在或无权限", 404)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_orders SET status = 'delivered', seller_deliver_note = ?, delivered_at = ?, updated_at = ? WHERE order_no = ? AND seller_user_id = ?",
            (deliver_note, now_ms, now_ms, order_no, str(user_id)),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "发货成功"})
    except Exception as e:
        return error_response("DELIVER_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-orders/{order_no}")
async def get_buy_order_detail(order_no: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT bo.*, r.title AS request_title, r.budget_price AS request_budget_price,
                      s.status AS session_status
               FROM shop_buy_orders bo
               LEFT JOIN shop_buy_requests r ON r.id = bo.request_id
               LEFT JOIN shop_buy_sessions s ON s.id = bo.session_id
               WHERE bo.order_no = ?
               AND ((requester_user_id = ? AND requester_site = ?)
                  OR (provider_user_id = ? AND provider_site = ?))""",
            (order_no, str(user_id), site, str(user_id), site),
        )
        row = _enrich_buy_order(_row_to_dict(cur.fetchone()))
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        return success_response(data={"order": row})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-orders/{order_no}/payment-url")
async def get_buy_order_payment_url(
    order_no: str, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT * FROM shop_buy_orders WHERE order_no = ?
               AND requester_user_id = ? AND requester_site = ? LIMIT 1""",
            (order_no, str(user_id), site),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        if row.get("status") != "pending":
            return error_response("INVALID_ORDER_STATUS", "订单状态不支持继续支付", 400)
        if int(row.get("pay_expired_at") or 0) <= int(
            datetime.now(timezone.utc).timestamp() * 1000
        ):
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            conn.execute(
                "UPDATE shop_buy_orders SET status = 'expired', updated_at = ? WHERE order_no = ? AND status = 'pending'",
                (now_ms, order_no),
            )
            conn.commit()
            return error_response("ORDER_EXPIRED", "订单已过期", 400)
        payment_url = str(row.get("payment_url") or "").strip()
        if not payment_url or not payment_url.startswith("https://credit.linux.do/"):
            return error_response("PAYMENT_LINK_UNAVAILABLE", "支付链接不可用", 400)
        return success_response(
            data={
                "orderNo": row.get("order_no"),
                "amount": row.get("amount"),
                "paymentUrl": payment_url,
                "expireAt": row.get("pay_expired_at"),
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-orders/{order_no}/refresh")
async def refresh_buy_order(order_no: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT * FROM shop_buy_orders WHERE order_no = ?
               AND ((requester_user_id = ? AND requester_site = ?)
                 OR (provider_user_id = ? AND provider_site = ?))""",
            (order_no, str(user_id), site, str(user_id), site),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        if row.get("status") == "completed":
            return success_response(
                data={
                    "order": _enrich_buy_order(row),
                    "status": row.get("status"),
                    "message": "订单已完成",
                }
            )
        merchant_pid = str(row.get("merchant_pid_snapshot") or "").strip()
        encrypted_key = str(row.get("merchant_key_encrypted_snapshot") or "").strip()
        if merchant_pid and encrypted_key:
            try:
                key_plain = decrypt_ldc_key(encrypted_key, settings.jwt_secret_key)
                query = await query_ldc_order(
                    pid=merchant_pid,
                    key=key_plain,
                    trade_no=str(row.get("ldc_trade_no") or ""),
                    order_no=order_no,
                )
                if (
                    query.get("success")
                    and str(query.get("data", {}).get("status") or "") == "1"
                ):
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    conn.execute(
                        "UPDATE shop_buy_orders SET status = 'completed', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE order_no = ?",
                        (
                            query.get("data", {}).get("tradeNo"),
                            now_ms,
                            now_ms,
                            order_no,
                        ),
                    )
                    conn.execute(
                        "UPDATE shop_buy_sessions SET contact_unlocked_at = COALESCE(contact_unlocked_at, ?), requester_confirm_paid_at = COALESCE(requester_confirm_paid_at, ?), updated_at = ? WHERE id = ?",
                        (now_ms, now_ms, now_ms, row.get("session_id")),
                    )
                    conn.commit()
                    cur = conn.execute(
                        """SELECT bo.*, r.title AS request_title, r.budget_price AS request_budget_price,
                                  s.status AS session_status
                           FROM shop_buy_orders bo
                           LEFT JOIN shop_buy_requests r ON r.id = bo.request_id
                           LEFT JOIN shop_buy_sessions s ON s.id = bo.session_id
                           WHERE bo.order_no = ? LIMIT 1""",
                        (order_no,),
                    )
                    row = _enrich_buy_order(_row_to_dict(cur.fetchone()))
                    return success_response(
                        data={
                            "order": row,
                            "status": row.get("status"),
                            "message": "支付已确认，订单已完成",
                        }
                    )
            except Exception:
                pass
        if row.get("status") == "pending" and int(
            row.get("pay_expired_at") or 0
        ) <= int(datetime.now(timezone.utc).timestamp() * 1000):
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            conn.execute(
                "UPDATE shop_buy_orders SET status = 'expired', updated_at = ? WHERE order_no = ? AND status = 'pending'",
                (now_ms, order_no),
            )
            conn.commit()
            return success_response(
                data={
                    "order": _enrich_buy_order({**row, "status": "expired"}),
                    "status": "expired",
                    "message": "订单已过期",
                }
            )
        return success_response(
            data={
                "order": _enrich_buy_order(row),
                "status": row.get("status"),
                "message": "订单尚未支付，请完成支付后再刷新",
            }
        )
    except Exception as e:
        return error_response("REFRESH_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/top-service/board")
async def top_service_quota_board(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT * FROM shop_top_orders WHERE user_id = ? ORDER BY created_at DESC",
            (str(user_id),),
        )
        orders = _rows_to_dicts(cur.fetchall())
        active = [o for o in orders if o.get("status") == "active"]
        return success_response(
            data={"active_services": active, "total_count": len(orders)}
        )
    except Exception:
        return success_response(data={"active_services": [], "total_count": 0})
    finally:
        conn.close()


@router.get("/api/shop/top-service/orders")
async def top_service_orders_list(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT COUNT(*) as total FROM shop_top_orders WHERE user_id = ?",
            (str(user_id),),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            "SELECT * FROM shop_top_orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [str(user_id), limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "orders": rows,
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


@router.get("/api/shop/top-service/orders/{order_no}/payment-url")
async def top_service_order_payment_url(
    order_no: str, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT * FROM shop_top_orders WHERE order_no = ? AND user_id = ?",
            (order_no, str(user_id)),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        payment_url = (row.get("payment_url") or "").strip()
        if not payment_url:
            return error_response("PAYMENT_URL_NOT_READY", "订单尚未生成支付链接", 409)
        return success_response(data={"payment_url": payment_url, "order_no": order_no})
    except Exception as e:
        return error_response("PAYMENT_URL_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/top-service/orders/{order_no}/refresh")
async def refresh_top_service_order(
    order_no: str, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT * FROM shop_top_orders WHERE order_no = ? AND user_id = ?",
            (order_no, str(user_id)),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        if row.get("status") in ("active", "paid"):
            return success_response(
                data={"order_no": order_no, "status": row.get("status")}
            )
        merchant_pid = str(row.get("merchant_pid_snapshot") or "").strip()
        encrypted_key = str(row.get("merchant_key_encrypted_snapshot") or "").strip()
        if merchant_pid and encrypted_key:
            try:
                key_plain = decrypt_ldc_key(encrypted_key, settings.jwt_secret_key)
                query = await query_ldc_order(
                    pid=merchant_pid,
                    key=key_plain,
                    trade_no=str(row.get("ldc_trade_no") or ""),
                    order_no=order_no,
                )
                if (
                    query.get("success")
                    and str(query.get("data", {}).get("status") or "") == "1"
                ):
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    conn.execute(
                        "UPDATE shop_top_orders SET status = 'active', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE order_no = ? AND user_id = ?",
                        (
                            query.get("data", {}).get("tradeNo"),
                            now_ms,
                            now_ms,
                            order_no,
                            str(user_id),
                        ),
                    )
                    conn.commit()
                    cur = conn.execute(
                        "SELECT * FROM shop_top_orders WHERE order_no = ? AND user_id = ?",
                        (order_no, str(user_id)),
                    )
                    row = _row_to_dict(cur.fetchone())
            except Exception:
                pass
        return success_response(
            data={"order_no": order_no, "status": row.get("status")}
        )
    except Exception as e:
        return error_response("REFRESH_FAILED", str(e), 500)
    finally:
        conn.close()
