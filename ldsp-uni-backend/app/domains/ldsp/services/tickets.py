"""Ticket service for managing support tickets."""

from __future__ import annotations

import sqlite3
import structlog
from app.config import settings

logger = structlog.get_logger(__name__)

DEFAULT_TICKET_TYPES = [
    {
        "id": "feature_request",
        "label": "功能建议",
        "icon": "feature",
        "description": "建议新功能或改进方案。",
    },
    {
        "id": "bug_report",
        "label": "问题反馈",
        "icon": "bug",
        "description": "反馈 Bug 或异常行为。",
    },
]


class TicketService:
    """Service for ticket database operations."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.ldsp_database_path

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _sanitize_string(self, value, max_len: int) -> str:
        text = str(value or "").strip()
        return text[:max_len]

    def get_user_tickets(self, site: str, user_id: str, options: dict | None = None):
        options = options or {}
        status = options.get("status")
        page = max(1, int(options.get("page") or 1))
        page_size = min(50, max(1, int(options.get("pageSize") or 20)))
        offset = (page - 1) * page_size
        conn = self._get_conn()
        try:
            where_clause = "WHERE site = ? AND user_id = ?"
            params: list = [site, user_id]

            if status in ("open", "closed"):
                where_clause += " AND status = ?"
                params.append(status)

            cols = conn.execute("PRAGMA table_info(tickets)").fetchall()
            col_names = {c[1] for c in cols}
            type_col = (
                "type"
                if "type" in col_names
                else ("type_name" if "type_name" in col_names else "type")
            )

            cursor = conn.execute(
                f"""SELECT id, {type_col} as type, title, status, priority, has_new_reply, reply_count,
                   created_at, updated_at, last_reply_at, closed_at FROM tickets
                   {where_clause}
                   ORDER BY CASE WHEN has_new_reply = 1 THEN 0 ELSE 1 END, updated_at DESC LIMIT ? OFFSET ?""",
                (*params, page_size, offset),
            )
            rows = [dict(r) for r in cursor.fetchall()]

            count_cursor = conn.execute(
                f"SELECT COUNT(*) FROM tickets {where_clause}",
                params,
            )
            total = count_cursor.fetchone()[0]
            type_map = {t["id"]: t for t in self.get_ticket_types()}
            items = []
            for row in rows:
                info = type_map.get(row.get("type"), {})
                items.append(
                    {
                        **row,
                        "typeLabel": info.get("label", row.get("type")),
                        "typeIcon": info.get("icon", "🎫"),
                    }
                )

            return {
                "tickets": items,
                "pagination": {
                    "page": page,
                    "pageSize": page_size,
                    "total": total,
                    "totalPages": (total + page_size - 1) // page_size
                    if total > 0
                    else 1,
                },
            }
        finally:
            conn.close()

    def create_ticket(
        self,
        site: str,
        user_id: str,
        username: str,
        type_name: str,
        title: str,
        content: str,
        name: str | None = None,
        avatar: str | None = None,
        client_version: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        import time

        if not site or not user_id or not username:
            raise ValueError("缺少用户信息")
        if not type_name or not title or not content:
            raise ValueError("缺少工单信息")

        ticket_types = self.get_ticket_types()
        if not any(item.get("id") == type_name for item in ticket_types):
            raise ValueError("无效的工单类型")

        clean_title = self._sanitize_string(title, 100)
        clean_content = self._sanitize_string(content, 2000)
        if len(clean_title) < 5:
            raise ValueError("标题至少需要 5 个字符")
        if len(clean_content) < 10:
            raise ValueError("内容至少需要 10 个字符")

        now = int(time.time() * 1000)
        conn = self._get_conn()
        try:
            recent_count = conn.execute(
                "SELECT COUNT(*) as count FROM tickets WHERE site = ? AND user_id = ? AND created_at > ?",
                (site, user_id, now - 10 * 60 * 1000),
            ).fetchone()
            if recent_count and int(recent_count["count"] or 0) >= 3:
                raise ValueError("提交过于频繁，请 10 分钟后重试")

            cols = conn.execute("PRAGMA table_info(tickets)").fetchall()
            col_names = {c[1] for c in cols}
            type_col = (
                "type"
                if "type" in col_names
                else ("type_name" if "type_name" in col_names else "type")
            )

            cursor = conn.execute(
                f"""INSERT INTO tickets (
                   site, user_id, username, user_name, user_avatar,
                   {type_col}, title, content, status, priority,
                   client_version, user_ip, user_agent,
                   created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', 'normal', ?, ?, ?, ?, ?)""",
                (
                    site,
                    user_id,
                    username,
                    name or None,
                    avatar or None,
                    type_name,
                    clean_title,
                    clean_content,
                    client_version or None,
                    ip or None,
                    (user_agent or "")[:200] or None,
                    now,
                    now,
                ),
            )
            ticket_id = cursor.lastrowid
            conn.commit()
            return {"id": ticket_id, "title": clean_title}
        finally:
            conn.close()

    def user_reply(
        self, ticket_id: int, site: str, user_id: str, username: str, content: str
    ) -> dict:
        import time

        row = self.get_ticket_detail(ticket_id, site, user_id)
        if not row:
            raise ValueError("工单不存在")
        if row.get("ticket", {}).get("status") == "closed":
            raise ValueError("工单已关闭，无法回复")
        clean_content = self._sanitize_string(content, 2000)
        if len(clean_content) < 2:
            raise ValueError("回复内容至少需要 2 个字符")
        now = int(time.time() * 1000)
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO ticket_replies (ticket_id, is_admin, user_id, username, content, created_at) VALUES (?, 0, ?, ?, ?, ?)",
                (ticket_id, user_id, username, clean_content, now),
            )
            conn.execute(
                "UPDATE tickets SET reply_count = COALESCE(reply_count, 0) + 1, last_reply_at = ?, updated_at = ? WHERE id = ?",
                (now, now, ticket_id),
            )
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    def get_unread_count(self, site: str, user_id: str) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM tickets WHERE site = ? AND user_id = ? AND has_new_reply = 1",
                (site, user_id),
            ).fetchone()
            return int(row["count"] if row else 0)
        finally:
            conn.close()

    def get_ticket_detail(
        self, ticket_id: int, site: str, user_id: str | None = None
    ) -> dict | None:
        conn = self._get_conn()
        try:
            where = "WHERE id = ?"
            params: list = [ticket_id]
            if site:
                where += " AND site = ?"
                params.append(site)
            if user_id:
                where += " AND user_id = ?"
                params.append(user_id)

            cursor = conn.execute(f"SELECT * FROM tickets {where}", params)
            row = cursor.fetchone()
            if not row:
                return None

            # Get replies
            replies_cursor = conn.execute(
                "SELECT * FROM ticket_replies WHERE ticket_id = ? ORDER BY created_at ASC",
                (ticket_id,),
            )
            replies = [dict(r) for r in replies_cursor.fetchall()]

            ticket = dict(row)
            if ticket.get("has_new_reply"):
                conn.execute(
                    "UPDATE tickets SET has_new_reply = 0, updated_at = ? WHERE id = ?",
                    (int(__import__("time").time() * 1000), ticket_id),
                )
                conn.commit()
                ticket["has_new_reply"] = 0

            type_value = ticket.get("type") or ticket.get("type_name")
            type_info = next(
                (
                    item
                    for item in self.get_ticket_types()
                    if item.get("id") == type_value
                ),
                {"label": type_value, "icon": "🎫"},
            )

            return {
                "ticket": {
                    **ticket,
                    "type": type_value,
                    "typeLabel": type_info.get("label", type_value),
                    "typeIcon": type_info.get("icon", "🎫"),
                    "replies": replies,
                }
            }
        finally:
            conn.close()

    def get_ticket_types(self) -> list[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM system_config WHERE key = 'ticket_types'"
            ).fetchone()
            if not row or not row[0]:
                return DEFAULT_TICKET_TYPES
            import json

            data = json.loads(row[0])
            return data.get("types") or DEFAULT_TICKET_TYPES
        except Exception:
            return DEFAULT_TICKET_TYPES
        finally:
            conn.close()

    def update_ticket_types(self, types: list[dict]) -> list[dict]:
        if not isinstance(types, list) or not types:
            raise ValueError("工单类型不能为空")
        if len(types) > 10:
            raise ValueError("工单类型最多允许 10 个")
        clean_types = []
        seen = set()
        for idx, item in enumerate(types):
            type_id = str(item.get("id") or "").strip().lower().replace("-", "_")
            label = str(item.get("label") or item.get("name") or "").strip()
            if not type_id or not label:
                raise ValueError(f"第 {idx + 1} 个类型缺少必填字段")
            if type_id in seen:
                raise ValueError("工单类型 ID 必须唯一")
            seen.add(type_id)
            clean_types.append(
                {
                    "id": type_id,
                    "label": self._sanitize_string(label, 50),
                    "icon": str(item.get("icon") or "ticket")[:30],
                    "description": self._sanitize_string(
                        item.get("description") or "", 200
                    ),
                }
            )

        import json
        import time

        now = str(int(time.time() * 1000))
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO system_config (key, value, description, updated_at)
                   VALUES ('ticket_types', ?, '工单类型配置', ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (json.dumps({"types": clean_types}, ensure_ascii=False), now),
            )
            conn.commit()
            return clean_types
        finally:
            conn.close()

    def get_admin_tickets(self, options: dict | None = None) -> dict:
        options = options or {}
        page = max(1, int(options.get("page") or 1))
        page_size = min(
            100, max(1, int(options.get("pageSize") or options.get("limit") or 20))
        )
        offset = (page - 1) * page_size

        where_clauses = []
        params: list = []
        if options.get("site"):
            where_clauses.append("site = ?")
            params.append(options["site"])
        if options.get("status"):
            where_clauses.append("status = ?")
            params.append(options["status"])
        conn = self._get_conn()
        try:
            cols = conn.execute("PRAGMA table_info(tickets)").fetchall()
            col_names = {c[1] for c in cols}
            type_col = (
                "type_name"
                if "type_name" in col_names
                else ("type" if "type" in col_names else None)
            )

            if options.get("type") and type_col:
                where_clauses.append(f"{type_col} = ?")
                params.append(options["type"])
            if options.get("search"):
                clean_search = (
                    self._sanitize_string(options["search"], 100)
                    .replace("%", "")
                    .replace("_", "")
                    .replace("\\", "")
                )
                if len(clean_search) >= 2:
                    keyword = f"%{clean_search}%"
                    where_clauses.append(
                        "(title LIKE ? OR username LIKE ? OR user_name LIKE ?)"
                    )
                    params.extend([keyword, keyword, keyword])

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            total = conn.execute(
                f"SELECT COUNT(*) FROM tickets {where_sql}", params
            ).fetchone()[0]
            cursor = conn.execute(
                f"""SELECT t.*, (
                        SELECT is_admin FROM ticket_replies WHERE ticket_id = t.id ORDER BY created_at DESC LIMIT 1
                    ) as last_reply_is_admin
                    FROM tickets t {where_sql}
                    ORDER BY
                      CASE WHEN t.status = 'open' THEN 0 ELSE 1 END,
                      CASE WHEN t.status = 'open' AND (COALESCE(t.reply_count, 0) = 0 OR (
                        SELECT is_admin FROM ticket_replies WHERE ticket_id = t.id ORDER BY created_at DESC LIMIT 1
                      ) = 0) THEN 0 ELSE 1 END,
                      COALESCE(t.last_reply_at, t.created_at) DESC
                    LIMIT ? OFFSET ?""",
                [*params, page_size, offset],
            )
            items = [dict(r) for r in cursor.fetchall()]
            type_map = {t["id"]: t for t in self.get_ticket_types()}
            for item in items:
                ticket_type = item.get("type_name") or item.get("type")
                info = type_map.get(ticket_type, {})
                item["typeLabel"] = info.get("label", ticket_type)
                item["typeIcon"] = info.get("icon", "ticket")
                item["has_new_reply"] = item.get("status") == "open" and (
                    int(item.get("reply_count") or 0) == 0
                    or item.get("last_reply_is_admin") == 0
                )
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            return {
                "items": items,
                "tickets": items,
                "total": total,
                "page": page,
                "pageSize": page_size,
                "totalPages": total_pages,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": page_size,
                    "totalPages": total_pages,
                },
            }
        finally:
            conn.close()

    def get_admin_ticket_detail(self, ticket_id: int) -> dict:
        ticket = self.get_ticket_detail(ticket_id, site=None, user_id=None)
        if not ticket:
            raise ValueError("工单不存在")
        return ticket

    def admin_reply(self, ticket_id: int, admin_name: str, content: str) -> dict:
        import time

        if not content or len(content.strip()) < 2:
            raise ValueError("回复内容至少需要 2 个字符")
        clean_content = self._sanitize_string(content, 2000)
        now = int(time.time() * 1000)
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
            if not row:
                raise ValueError("工单不存在")
            conn.execute(
                "INSERT INTO ticket_replies (ticket_id, is_admin, admin_name, content, created_at) VALUES (?, 1, ?, ?, ?)",
                (ticket_id, admin_name or "管理员", clean_content, now),
            )
            conn.execute(
                """UPDATE tickets SET has_new_reply = 1,
                   reply_count = COALESCE(reply_count, 0) + 1,
                   last_reply_at = ?, updated_at = ?, status = 'open'
                   WHERE id = ?""",
                (now, now, ticket_id),
            )
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    def close_ticket(self, ticket_id: int, admin_name: str) -> dict:
        import time

        now = str(int(time.time() * 1000))
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ?, updated_at = ? WHERE id = ? AND status = 'open'",
                (now, admin_name or "管理员", now, ticket_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ValueError("工单不存在或已关闭")
            return {"success": True}
        finally:
            conn.close()

    def reopen_ticket(self, ticket_id: int) -> dict:
        import time

        now = str(int(time.time() * 1000))
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "UPDATE tickets SET status = 'open', closed_at = NULL, closed_by = NULL, updated_at = ? WHERE id = ? AND status = 'closed'",
                (now, ticket_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ValueError("工单不存在或未处于关闭状态")
            return {"success": True}
        finally:
            conn.close()

    def get_stats(self) -> dict:
        import time

        now = int(time.time() * 1000)
        day_ms = 24 * 60 * 60 * 1000
        today_start = now - (now % day_ms)
        week7 = today_start - 7 * day_ms
        month30 = today_start - 30 * day_ms
        conn = self._get_conn()
        try:
            cols = conn.execute("PRAGMA table_info(tickets)").fetchall()
            col_names = {c[1] for c in cols}
            type_col = (
                "type_name"
                if "type_name" in col_names
                else ("type" if "type" in col_names else None)
            )
            created_expr = (
                "CAST(created_at AS INTEGER)" if "created_at" in col_names else "0"
            )

            row = conn.execute(
                f"""SELECT
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                   SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_count,
                   SUM(CASE WHEN {created_expr} >= ? THEN 1 ELSE 0 END) as today_count,
                   SUM(CASE WHEN {created_expr} >= ? THEN 1 ELSE 0 END) as week_count,
                   SUM(CASE WHEN {created_expr} >= ? THEN 1 ELSE 0 END) as month_count
                   FROM tickets""",
                (str(today_start), str(week7), str(month30)),
            ).fetchone()
            type_rows = []
            if type_col:
                type_rows = conn.execute(
                    f"SELECT {type_col} as ticket_type, COUNT(*) as count FROM tickets GROUP BY {type_col}"
                ).fetchall()
            type_map = {t["id"]: t for t in self.get_ticket_types()}
            by_type = []
            for r in type_rows:
                ticket_type = r["ticket_type"]
                info = type_map.get(ticket_type, {})
                by_type.append(
                    {
                        "type": ticket_type,
                        "label": info.get("label", ticket_type),
                        "icon": info.get("icon", "ticket"),
                        "count": r["count"],
                    }
                )
            return {
                "total": row["total"] if row else 0,
                "open": row["open_count"] if row else 0,
                "closed": row["closed_count"] if row else 0,
                "today": row["today_count"] if row else 0,
                "week7": row["week_count"] if row else 0,
                "month30": row["month_count"] if row else 0,
                "byType": by_type,
            }
        finally:
            conn.close()
