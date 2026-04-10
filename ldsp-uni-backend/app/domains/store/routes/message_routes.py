"""Message routes."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user

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


# ---------------------------------------------------------------------------
# User Auth Routes
# ---------------------------------------------------------------------------


@router.get("/api/shop/messages/unread-summary")
async def messages_unread_summary(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_user_messages WHERE user_id = ? AND user_site = ? AND is_read = 0",
            (user_id, site),
        )
        unread = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT message_type as type, COUNT(*) as c FROM shop_user_messages WHERE user_id = ? AND user_site = ? AND is_read = 0 GROUP BY message_type",
            (user_id, site),
        )
        by_type = {row["type"]: row["c"] for row in cur.fetchall()}
        return success_response(data={"unread_count": unread, "by_type": by_type})
    except Exception:
        return success_response(data={"unread_count": 0, "by_type": {}})
    finally:
        conn.close()


@router.post("/api/shop/messages/system/read-all")
async def mark_all_system_messages_read(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            "UPDATE shop_user_messages SET is_read = 1, read_at = ?, updated_at = ? WHERE user_id = ? AND user_site = ? AND message_type = 'system' AND is_read = 0",
            (now_ms, now_ms, user_id, site),
        )
        count = cur.rowcount
        conn.commit()
        return success_response(data={"marked_read": count})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/messages/system/{message_id}/read")
async def mark_single_system_message_read(
    message_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            "UPDATE shop_user_messages SET is_read = 1, read_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND user_site = ? AND message_type = 'system'",
            (now_ms, now_ms, message_id, user_id, site),
        )
        if cur.rowcount == 0:
            return error_response("MESSAGE_NOT_FOUND", "消息不存在", 404)
        conn.commit()
        return success_response(data={"marked_read": True})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/comments/{comment_id}/replies")
async def get_comment_replies(
    comment_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as total FROM shop_product_comment_replies WHERE comment_id = ?",
            (comment_id,),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            "SELECT * FROM shop_product_comment_replies WHERE comment_id = ? ORDER BY created_at LIMIT ? OFFSET ?",
            [comment_id, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "replies": rows,
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
