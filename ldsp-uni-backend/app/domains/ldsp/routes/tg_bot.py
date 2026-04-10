"""Telegram bot admin routes."""

from __future__ import annotations

import json
import sqlite3
import time

from fastapi import APIRouter, Request

from app.config import settings
from app.common.utils.response import error_response, success_response

router = APIRouter(tags=["ldsp-tg-bot-admin"])


def _tg_internal_key() -> str:
    return (
        settings.tg_bot_internal_key
        or settings.tg_bot_internal_token
        or settings.admin_secret
        or ""
    ).strip()


def _tg_webhook_secret() -> str:
    return (
        settings.tg_bot_webhook_secret or settings.telegram_webhook_secret or ""
    ).strip()


def _ensure_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tg_bot_notification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            message TEXT,
            status TEXT,
            sent_at INTEGER
        )"""
    )
    conn.commit()


@router.post("/api/tg-bot/webhook")
async def tg_bot_webhook(request: Request):
    secret = _tg_webhook_secret()
    if secret:
        header_secret = (
            request.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
        ).strip()
        if not header_secret or header_secret != secret:
            return error_response("FORBIDDEN", "invalid webhook secret", 403)

    try:
        body = await request.json()
    except Exception:
        body = None
    if not body:
        return error_response("INVALID_JSON", "invalid telegram webhook payload", 400)

    update_id = body.get("update_id") if isinstance(body, dict) else None
    event_type = "unknown"
    if isinstance(body, dict):
        for key in ("message", "edited_message", "callback_query", "inline_query"):
            if key in body:
                event_type = key
                break

    return {
        "success": True,
        "updateId": update_id,
        "eventType": event_type,
        "handled": True,
    }


@router.post("/api/internal/tg-bot/notify")
async def tg_bot_internal_notify(request: Request):
    internal_key = _tg_internal_key()
    if not internal_key:
        return error_response(
            "INTERNAL_KEY_MISSING", "服务端未配置 TG 内部鉴权密钥", 500
        )

    request_key = (request.headers.get("X-Internal-Key") or "").strip()
    if not request_key or request_key != internal_key:
        return error_response("FORBIDDEN", "内部鉴权失败", 403)

    try:
        body = await request.json()
    except Exception:
        body = None
    if not body:
        return error_response("INVALID_JSON", "无效的 JSON 请求体", 400)

    event_type = str(body.get("eventType") or body.get("event") or "").strip()
    if not event_type:
        return error_response("INVALID_PARAMS", "eventType 不能为空", 400)

    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    source = str(
        body.get("source") or request.headers.get("X-Source-Service") or ""
    ).strip()[:60]

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        _ensure_log_table(conn)
        row = conn.execute(
            "SELECT value FROM system_config WHERE key = ?",
            ("tg_bot_config",),
        ).fetchone()
        config = json.loads(row[0]) if row and row[0] else {}
        enabled = bool(config.get("enabled"))
        chat_id = str(config.get("chat_id") or "").strip()
        delivered = enabled and bool(chat_id)
        skipped = not delivered
        message = json.dumps(
            {"eventType": event_type, "source": source, "payload": payload},
            ensure_ascii=False,
        )[:2000]
        conn.execute(
            "INSERT INTO tg_bot_notification_logs (chat_id, message, status, sent_at) VALUES (?, ?, ?, ?)",
            (
                chat_id or None,
                message,
                "success" if delivered else "skipped",
                int(time.time() * 1000),
            ),
        )
        conn.commit()
        status_code = 200 if delivered else 202
        return {
            "success": delivered,
            "delivered": delivered,
            "skipped": skipped,
            "eventType": event_type,
            "source": source,
            "statusCode": status_code,
        }
    except Exception as e:
        return error_response("NOTIFY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/tg-bot/config")
async def tg_bot_get_config():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        row = conn.execute(
            "SELECT value FROM system_config WHERE key = ?",
            ("tg_bot_config",),
        ).fetchone()

        config = json.loads(row[0]) if row and row[0] else {}

        return success_response(
            data={
                "bot_token": config.get("bot_token", ""),
                "chat_id": config.get("chat_id", ""),
                "enabled": config.get("enabled", False),
                "notify_on_sync": config.get("notify_on_sync", True),
                "notify_on_warning": config.get("notify_on_warning", True),
            }
        )
    except Exception as e:
        return error_response("GET_TG_CONFIG_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/tg-bot/config")
async def tg_bot_update_config(request: Request):
    body = await request.json()
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        existing = conn.execute(
            "SELECT value FROM system_config WHERE key = ?",
            ("tg_bot_config",),
        ).fetchone()

        current = json.loads(existing[0]) if existing and existing[0] else {}
        current.update(
            {
                k: v
                for k, v in body.items()
                if k
                in (
                    "bot_token",
                    "chat_id",
                    "enabled",
                    "notify_on_sync",
                    "notify_on_warning",
                )
            }
        )

        conn.execute(
            """INSERT INTO system_config (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            ("tg_bot_config", json.dumps(current, ensure_ascii=False)),
        )
        conn.commit()

        return success_response(data={"message": "TG Bot 配置已更新"})
    except Exception as e:
        return error_response("UPDATE_TG_CONFIG_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/tg-bot/test")
async def tg_bot_test_notification(request: Request):
    body = await request.json()
    message = body.get("message", "这是一条测试通知")

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        config_row = conn.execute(
            "SELECT value FROM system_config WHERE key = ?",
            ("tg_bot_config",),
        ).fetchone()

        if not config_row:
            return error_response("TG_CONFIG_NOT_FOUND", "TG Bot 未配置", 400)

        config = json.loads(config_row[0])
        bot_token = config.get("bot_token", "")
        chat_id = config.get("chat_id", "")

        if not bot_token or not chat_id:
            return error_response(
                "TG_CONFIG_INCOMPLETE", "缺少 bot_token 或 chat_id", 400
            )

        import urllib.request
        import urllib.error

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = json.dumps(
            {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                sent = result.get("ok", False)
        except urllib.error.URLError as e:
            return error_response("TG_SEND_FAILED", f"发送失败: {str(e)}", 500)

        conn.execute(
            "INSERT INTO tg_bot_notification_logs (chat_id, message, status, sent_at) VALUES (?, ?, ?, ?)",
            (
                chat_id,
                message,
                "success" if sent else "failed",
                int(__import__("time").time() * 1000),
            ),
        )
        conn.commit()

        return success_response(data={"message": "测试通知已发送", "success": sent})
    except Exception as e:
        return error_response("TG_TEST_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/tg-bot/audit/stats")
async def tg_bot_audit_stats(windowHours: int = 24):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM tg_bot_notification_logs"
        ).fetchone()[0]

        success_count = conn.execute(
            "SELECT COUNT(*) FROM tg_bot_notification_logs WHERE status = 'success'"
        ).fetchone()[0]

        failed_count = conn.execute(
            "SELECT COUNT(*) FROM tg_bot_notification_logs WHERE status = 'failed'"
        ).fetchone()[0]

        last_24h = conn.execute(
            "SELECT COUNT(*) FROM tg_bot_notification_logs WHERE sent_at > ?",
            (int(__import__("time").time() * 1000) - 86400000,),
        ).fetchone()[0]

        return success_response(
            data={
                "total_notifications": total,
                "success_count": success_count,
                "failed_count": failed_count,
                "last_24h_count": last_24h,
                "windowHours": windowHours,
                "success_rate": round(success_count / total * 100, 2)
                if total > 0
                else 0,
            }
        )
    except Exception as e:
        return error_response("TG_AUDIT_STATS_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/tg-bot/audit/logs")
async def tg_bot_audit_logs(request: Request):
    page = int(request.query_params.get("page", 1))
    per_page = int(
        request.query_params.get("per_page", request.query_params.get("limit", 20))
    )
    offset_param = request.query_params.get("offset")
    status_filter = request.query_params.get(
        "status", request.query_params.get("resultType", "")
    ).strip()
    offset = (page - 1) * per_page
    if offset_param is not None:
        try:
            offset = max(0, int(offset_param))
            page = offset // per_page + 1
        except Exception:
            pass

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        if status_filter:
            total = conn.execute(
                "SELECT COUNT(*) FROM tg_bot_notification_logs WHERE status = ?",
                (status_filter,),
            ).fetchone()[0]
            cursor = conn.execute(
                "SELECT id, chat_id, message, status, sent_at FROM tg_bot_notification_logs WHERE status = ? ORDER BY sent_at DESC LIMIT ? OFFSET ?",
                (status_filter, per_page, offset),
            )
        else:
            total = conn.execute(
                "SELECT COUNT(*) FROM tg_bot_notification_logs"
            ).fetchone()[0]
            cursor = conn.execute(
                "SELECT id, chat_id, message, status, sent_at FROM tg_bot_notification_logs ORDER BY sent_at DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            )

        rows = cursor.fetchall()
        logs = [
            {
                "id": r[0],
                "chat_id": r[1],
                "message": r[2],
                "status": r[3],
                "sent_at": r[4],
            }
            for r in rows
        ]

        return success_response(
            data={
                "logs": logs,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pagination": {
                    "page": page,
                    "pageSize": per_page,
                    "offset": offset,
                    "total": total,
                },
            }
        )
    except Exception as e:
        return error_response("TG_AUDIT_LOGS_FAILED", str(e), 500)
    finally:
        conn.close()
