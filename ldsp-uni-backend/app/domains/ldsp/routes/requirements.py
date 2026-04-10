"""Requirements sync routes compatible with legacy ldsp-backend logic."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Request

from app.common.utils.response import error_response, success_response
from app.config import settings
from app.db.engine import get_ldsp_session_context
from app.domains.ldsp.services.users import UserService

router = APIRouter(tags=["ldsp-requirements"])

REQUIREMENTS_MIN_TRUST_LEVEL = 0


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    return conn


def _today_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _validate_minutes(value) -> tuple[bool, int, str | None]:
    try:
        parsed = int(float(value or 0))
    except Exception:
        return False, 0, "readingTime 无效"
    if parsed < 0:
        return False, 0, "readingTime 不能为负数"
    if parsed > 1440:
        parsed = 1440
    return True, parsed, None


def _validate_requirements_data(data) -> tuple[bool, dict, str | None]:
    if not isinstance(data, dict) or not data:
        return False, {}, "requirements 必须是对象且不能为空"
    clean = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            return False, {}, "requirements key 无效"
        if not isinstance(value, (int, float)):
            return False, {}, f"requirements.{key} 必须是数字"
        clean[key] = max(0, float(value))
    return True, clean, None


def _parse_history_date(ts) -> str | None:
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        except Exception:
            return None
    if isinstance(ts, str):
        text = ts.strip()
        if not text:
            return None
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return text
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime(
                "%Y-%m-%d"
            )
        except Exception:
            try:
                return datetime.fromtimestamp(float(text) / 1000).strftime("%Y-%m-%d")
            except Exception:
                return None
    return None


async def _ensure_user(jwt_user: dict, client_version: str | None = None) -> dict:
    async with get_ldsp_session_context() as db:
        service = UserService()
        user, _ = await service.ensure_user_from_jwt(db, jwt_user, client_version)
        return user


def _check_permission(user: dict) -> tuple[bool, str | None, str | None]:
    trust_level = int(user.get("trust_level") or 0)
    if trust_level < REQUIREMENTS_MIN_TRUST_LEVEL:
        return (
            False,
            "INSUFFICIENT_TRUST_LEVEL",
            f"信任等级需 >= {REQUIREMENTS_MIN_TRUST_LEVEL} 才可同步升级要求数据",
        )
    return True, None, None


def _get_requirements_for_date(
    conn: sqlite3.Connection, site: str, user_id: str, date: str
) -> dict | None:
    cols = conn.execute("PRAGMA table_info(requirements_history)").fetchall()
    col_names = {c[1] for c in cols}
    if {"date", "data", "reading_time"}.issubset(col_names):
        row = conn.execute(
            "SELECT data FROM requirements_history WHERE site = ? AND user_id = ? AND date = ?",
            (site, user_id, date),
        ).fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                return None
    return None


def _save_requirements_record(
    conn: sqlite3.Connection,
    site: str,
    user_id: str,
    date: str,
    data: dict,
    reading_time: int,
    now_ms: int,
) -> None:
    row = conn.execute(
        "SELECT id, reading_time FROM requirements_history WHERE site = ? AND user_id = ? AND date = ? ORDER BY id DESC LIMIT 1",
        (site, user_id, date),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE requirements_history SET data = ?, reading_time = ?, last_update = ? WHERE id = ?",
            (
                json.dumps(data, ensure_ascii=False),
                max(int(row["reading_time"] or 0), int(reading_time or 0)),
                now_ms,
                row["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO requirements_history (site, user_id, date, data, reading_time, last_update, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                site,
                user_id,
                date,
                json.dumps(data, ensure_ascii=False),
                reading_time,
                now_ms,
                now_ms,
            ),
        )


def _ensure_requirements_schema(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(requirements_history)").fetchall()
    col_names = {c[1] for c in cols}
    if not cols:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS requirements_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site TEXT NOT NULL,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                data TEXT NOT NULL,
                reading_time INTEGER DEFAULT 0,
                last_update INTEGER,
                created_at INTEGER,
                UNIQUE(site, user_id, date)
            )"""
        )
        conn.commit()
        return
    migrations = []
    if "date" not in col_names:
        migrations.append("ALTER TABLE requirements_history ADD COLUMN date TEXT")
    if "data" not in col_names:
        migrations.append("ALTER TABLE requirements_history ADD COLUMN data TEXT")
    if "reading_time" not in col_names:
        migrations.append(
            "ALTER TABLE requirements_history ADD COLUMN reading_time INTEGER DEFAULT 0"
        )
    if "last_update" not in col_names:
        migrations.append(
            "ALTER TABLE requirements_history ADD COLUMN last_update INTEGER"
        )
    if "created_at" not in col_names:
        migrations.append(
            "ALTER TABLE requirements_history ADD COLUMN created_at INTEGER"
        )
    for sql in migrations:
        conn.execute(sql)
    if migrations:
        conn.commit()


@router.get("/api/requirements/history")
async def requirements_history(request: Request):
    user = request.state.user
    if not user:
        return error_response("UNAUTHORIZED", "需要登录", 401)
    client_version = request.headers.get("X-Client-Version")
    try:
        ensured_user = await _ensure_user(user, client_version)
    except Exception as e:
        if str(e) == "REGISTRATION_PAUSED":
            return error_response("REGISTRATION_PAUSED", "已暂停新用户注册", 403)
        return error_response("USER_INIT_FAILED", str(e) or "初始化用户失败", 500)
    allowed, code, message = _check_permission(ensured_user)
    if not allowed:
        return error_response(code or "FORBIDDEN", message or "无权限", 403)

    days = int(request.query_params.get("days", 100))
    days = max(1, min(days, 365))
    conn = _conn()
    try:
        _ensure_requirements_schema(conn)
        site = user.get("site", "linux.do")
        user_id = str(user.get("user_id") or user.get("sub") or "")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT date, data, reading_time, last_update FROM requirements_history WHERE site = ? AND user_id = ? AND date >= ? ORDER BY date DESC",
            (site, user_id, start_date),
        ).fetchall()
        history = []
        for row in rows:
            try:
                data = json.loads(row["data"] or "{}")
            except Exception:
                data = {}
            ts = int(
                datetime.fromisoformat(f"{row['date']}T00:00:00").timestamp() * 1000
            )
            history.append(
                {
                    "ts": ts,
                    "data": data,
                    "readingTime": int(row["reading_time"] or 0),
                }
            )
        return success_response(
            data={
                "history": history,
                "totalDays": len(history),
                "lastSync": ensured_user.get("last_full_sync")
                or ensured_user.get("last_sync")
                or None,
            }
        )
    finally:
        conn.close()


@router.post("/api/requirements/sync")
async def requirements_sync(request: Request):
    user = request.state.user
    if not user:
        return error_response("UNAUTHORIZED", "需要登录", 401)
    body = await request.json()
    client_version = request.headers.get("X-Client-Version")
    try:
        ensured_user = await _ensure_user(user, client_version)
    except Exception as e:
        if str(e) == "REGISTRATION_PAUSED":
            return error_response("REGISTRATION_PAUSED", "已暂停新用户注册", 403)
        return error_response("USER_INIT_FAILED", str(e) or "初始化用户失败", 500)
    allowed, code, message = _check_permission(ensured_user)
    if not allowed:
        return error_response(code or "FORBIDDEN", message or "无权限", 403)

    target_date = body.get("date") or _today_date()
    requirements = body.get("requirements")
    reading_time = body.get("readingTime", 0)

    ok, clean_requirements, err = _validate_requirements_data(requirements)
    if not ok:
        return error_response("INVALID_DATA", err or "requirements 无效", 400)
    valid_rt, parsed_rt, rt_err = _validate_minutes(reading_time)
    if not valid_rt:
        return error_response("INVALID_DATA", rt_err or "readingTime 无效", 400)

    conn = _conn()
    try:
        _ensure_requirements_schema(conn)
        site = user.get("site", "linux.do")
        user_id = str(user.get("user_id") or user.get("sub") or "")
        server_data = _get_requirements_for_date(conn, site, user_id, target_date)
        final_data = dict(clean_requirements)
        if server_data:
            merged = dict(server_data)
            for key, value in clean_requirements.items():
                merged[key] = max(float(merged.get(key, 0) or 0), float(value))
            final_data = merged
        now_ms = int(time.time() * 1000)
        _save_requirements_record(
            conn, site, user_id, target_date, final_data, parsed_rt, now_ms
        )
        conn.execute(
            "UPDATE users SET last_sync = ?, updated_at = ? WHERE site = ? AND user_id = ?",
            (str(now_ms), str(now_ms), site, user_id),
        )
        conn.commit()
        return success_response(
            data={
                "date": target_date,
                "synced_at": now_ms,
                "data": final_data,
                "buffered": False,
            }
        )
    except Exception as e:
        return error_response("SYNC_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/requirements/sync-full")
async def requirements_full_sync(request: Request):
    user = request.state.user
    if not user:
        return error_response("UNAUTHORIZED", "需要登录", 401)
    try:
        body = await request.json()
    except Exception:
        return error_response("INVALID_JSON", "无效的 JSON 请求体", 400)
    client_version = request.headers.get("X-Client-Version")
    try:
        ensured_user = await _ensure_user(user, client_version)
    except Exception as e:
        if str(e) == "REGISTRATION_PAUSED":
            return error_response("REGISTRATION_PAUSED", "已暂停新用户注册", 403)
        return error_response("USER_INIT_FAILED", str(e) or "初始化用户失败", 500)
    allowed, code, message = _check_permission(ensured_user)
    if not allowed:
        return error_response(code or "FORBIDDEN", message or "无权限", 403)

    history = body.get("history")
    if not isinstance(history, list):
        return error_response("INVALID_DATA", "history 必须是数组", 400)
    history = history[:365]

    conn = _conn()
    try:
        _ensure_requirements_schema(conn)
        site = user.get("site", "linux.do")
        user_id = str(user.get("user_id") or user.get("sub") or "")
        valid_records = []
        errors = []
        dates_to_check = []
        for record in history:
            date = _parse_history_date(record.get("ts"))
            if not date:
                errors.append({"ts": record.get("ts"), "error": "日期无效"})
                continue
            ok, clean, err = _validate_requirements_data(record.get("data"))
            if not ok:
                errors.append({"ts": record.get("ts"), "error": err})
                continue
            valid_rt, parsed_rt, _ = _validate_minutes(record.get("readingTime", 0))
            if not valid_rt:
                parsed_rt = 0
            valid_records.append(
                {"date": date, "requirements": clean, "readingTime": parsed_rt}
            )
            dates_to_check.append(date)

        server_data_map = {}
        if dates_to_check:
            start_date = min(dates_to_check)
            rows = conn.execute(
                "SELECT date, data FROM requirements_history WHERE site = ? AND user_id = ? AND date >= ?",
                (site, user_id, start_date),
            ).fetchall()
            for row in rows:
                try:
                    server_data_map[row["date"]] = json.loads(row["data"] or "{}")
                except Exception:
                    server_data_map[row["date"]] = {}

        now_ms = int(time.time() * 1000)
        synced_dates = []
        for item in valid_records:
            try:
                server_data = server_data_map.get(item["date"])
                final_data = dict(item["requirements"])
                if server_data:
                    merged = dict(server_data)
                    for key, value in item["requirements"].items():
                        merged[key] = max(float(merged.get(key, 0) or 0), float(value))
                    final_data = merged
                _save_requirements_record(
                    conn,
                    site,
                    user_id,
                    item["date"],
                    final_data,
                    item["readingTime"],
                    now_ms,
                )
                synced_dates.append(item["date"])
            except Exception as e:
                errors.append({"date": item["date"], "error": str(e)})

        conn.execute(
            "UPDATE users SET last_full_sync = ?, updated_at = ? WHERE site = ? AND user_id = ?",
            (str(now_ms), str(now_ms), site, user_id),
        )
        conn.commit()
        payload = {
            "synced_count": len(synced_dates),
            "synced_dates": synced_dates[-10:],
            "synced_at": now_ms,
        }
        if errors:
            payload["errors"] = errors[:5]
        return success_response(data=payload)
    except Exception as e:
        return error_response("SYNC_FAILED", str(e), 500)
    finally:
        conn.close()
