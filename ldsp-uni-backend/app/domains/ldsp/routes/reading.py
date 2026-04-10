"""LDStatusPro reading sync routes compatible with legacy ldsp-backend logic."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from app.common.utils.response import error_response, success_response
from app.config import settings
from app.db.engine import get_ldsp_session_context
from app.domains.ldsp.services.users import UserService

router = APIRouter(tags=["ldsp-reading"])

PROFILE_CHECK_INTERVAL_MS = 72 * 60 * 60 * 1000
LAST_SYNC_UPDATE_INTERVAL_MS = 30 * 60 * 1000
MIN_SYNC_INTERVAL_MS = 30 * 1000
HISTORY_MAX_INCREMENT = 30
DEFAULT_MAX_DAILY_MINUTES = 1290


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    return conn


def _today_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _format_reading_time(minutes: int | float) -> str:
    total = int(round(minutes or 0))
    hours = total // 60
    mins = total % 60
    if hours > 0:
        return f"{hours}小时{mins}分钟"
    return f"{mins}分钟"


def _build_avatar_url(
    site: str, avatar_template: str | None, size: int = 128
) -> str | None:
    if not avatar_template:
        return None
    base_url = "https://idcflare.com" if site == "idcflare.com" else "https://linux.do"
    url = avatar_template.replace("{size}", str(size))
    return url if url.startswith("http") else f"{base_url}{url}"


def _validate_date_format(value: str) -> tuple[bool, str | None]:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True, None
    except Exception:
        return False, "日期格式必须为 YYYY-MM-DD"


def _validate_minutes(value) -> tuple[bool, int, str | None]:
    try:
        parsed = int(float(value))
    except Exception:
        return False, 0, "分钟数无效"
    if parsed < 0:
        return False, 0, "分钟数不能为负数"
    if parsed > 1440:
        parsed = 1440
    return True, parsed, None


def _parse_date_key(date_key: str) -> str | None:
    if not date_key:
        return None
    text = str(date_key).strip()
    ok, _ = _validate_date_format(text)
    if ok:
        return text

    month_map = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }
    import re

    match = re.match(
        r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})$", text
    )
    if match:
        month = month_map.get(match.group(1))
        if month:
            day = str(int(match.group(2))).zfill(2)
            return f"{match.group(3)}-{month}-{day}"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        parsed = datetime.fromtimestamp(float(text) / 1000)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return None


def _get_max_daily_minutes(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT value FROM system_config WHERE key = 'max_daily_reading'"
        ).fetchone()
        if row and row[0]:
            import json

            parsed = json.loads(row[0])
            value = int(parsed.get("maxMinutes", DEFAULT_MAX_DAILY_MINUTES))
            return value if value > 0 else DEFAULT_MAX_DAILY_MINUTES
    except Exception:
        pass
    return DEFAULT_MAX_DAILY_MINUTES


def _get_user(conn: sqlite3.Connection, site: str, user_id: str):
    return conn.execute(
        "SELECT * FROM users WHERE site = ? AND user_id = ?",
        (site, user_id),
    ).fetchone()


async def _ensure_user(
    jwt_user: dict, client_version: str | None = None
) -> tuple[dict, bool]:
    async with get_ldsp_session_context() as db:
        service = UserService()
        return await service.ensure_user_from_jwt(db, jwt_user, client_version)


def _check_and_update_user_profile(
    conn: sqlite3.Connection, db_user: sqlite3.Row | dict, jwt_user: dict, now_ms: int
) -> dict:
    updates = {}
    profile_checked_at = int(
        (
            db_user.get("profile_checked_at")
            if isinstance(db_user, dict)
            else db_user["profile_checked_at"]
        )
        or 0
    )
    if profile_checked_at and (now_ms - profile_checked_at) < PROFILE_CHECK_INTERVAL_MS:
        return updates

    updates["profile_checked_at"] = now_ms
    username = jwt_user.get("username")
    if username and username != (
        db_user.get("username") if isinstance(db_user, dict) else db_user["username"]
    ):
        updates["username"] = username
    jwt_name = jwt_user.get("name")
    current_name = db_user.get("name") if isinstance(db_user, dict) else db_user["name"]
    if jwt_name != current_name:
        updates["name"] = jwt_name
    new_avatar_url = _build_avatar_url(
        jwt_user.get("site", "linux.do"), jwt_user.get("avatar_template")
    )
    current_avatar = (
        db_user.get("avatar_url")
        if isinstance(db_user, dict)
        else db_user["avatar_url"]
    )
    if new_avatar_url and new_avatar_url != current_avatar:
        updates["avatar_url"] = new_avatar_url
    jwt_trust_level = jwt_user.get("trust_level")
    current_tl = int(
        (
            db_user.get("trust_level")
            if isinstance(db_user, dict)
            else db_user["trust_level"]
        )
        or 0
    )
    if jwt_trust_level is not None and int(jwt_trust_level) != current_tl:
        updates["trust_level"] = int(jwt_trust_level)
    return updates


def _record_anomaly(
    conn: sqlite3.Connection, site: str, user_id: str, now_ms: int
) -> None:
    try:
        conn.execute(
            "UPDATE users SET anomaly_count = COALESCE(anomaly_count, 0) + 1, updated_at = ? WHERE site = ? AND user_id = ?",
            (str(now_ms), site, user_id),
        )
    except Exception:
        pass


def _validate_reading_data(
    conn: sqlite3.Connection,
    site: str,
    user_id: str,
    date: str,
    claimed_minutes: int,
) -> dict:
    now_ms = int(time.time() * 1000)
    today = _today_date()
    current_data = conn.execute(
        "SELECT minutes, last_update, created_at FROM reading_daily WHERE site = ? AND user_id = ? AND date = ?",
        (site, user_id, date),
    ).fetchone()
    current_minutes = int(current_data["minutes"] if current_data else 0)

    now_beijing = datetime.utcnow() + timedelta(hours=8)
    if date == today:
        max_possible_minutes = now_beijing.hour * 60 + now_beijing.minute
    elif date < today:
        max_possible_minutes = 1440
    else:
        return {"valid": False, "reason": "不允许使用未来日期"}

    max_daily_minutes = _get_max_daily_minutes(conn)
    absolute_max = min(max_possible_minutes, max_daily_minutes)
    minutes = min(claimed_minutes, absolute_max)

    if not current_data:
        return {"valid": True, "clampedMinutes": minutes}

    last_update = int(current_data["last_update"] or current_data["created_at"] or 0)
    time_since_last_update = now_ms - last_update
    if time_since_last_update < MIN_SYNC_INTERVAL_MS:
        return {"valid": True, "clampedMinutes": current_minutes, "rateLimited": True}

    claimed_increment = minutes - current_minutes
    if claimed_increment < 0:
        return {
            "valid": True,
            "clampedMinutes": current_minutes,
            "serverOverride": True,
        }

    minutes_since_last_update = time_since_last_update / 60000
    max_allowed_increment = max(minutes_since_last_update * 1.2 + 3, 5)
    if claimed_increment > max_allowed_increment:
        allowed_minutes = min(
            int(current_minutes + max_allowed_increment), absolute_max
        )
        _record_anomaly(conn, site, user_id, now_ms)
        return {"valid": True, "clampedMinutes": allowed_minutes, "truncated": True}

    if (
        date < today
        and current_minutes > 0
        and claimed_increment > HISTORY_MAX_INCREMENT
    ):
        return {
            "valid": True,
            "clampedMinutes": min(
                current_minutes + HISTORY_MAX_INCREMENT, absolute_max
            ),
            "historicalLock": True,
        }

    return {"valid": True, "clampedMinutes": minutes}


@router.post("/api/reading/sync")
@router.post("/api/reading/sync/incremental")
async def reading_sync(request: Request):
    user = request.state.user
    if not user:
        return error_response("UNAUTHORIZED", "需要登录", 401)
    body = await request.json()
    client_version = request.headers.get("X-Client-Version")
    raw_date = str(body.get("date") or "").strip()
    server_today = _today_date()
    target_date = server_today
    date_normalized = None

    if raw_date:
        ok, msg = _validate_date_format(raw_date)
        if not ok:
            return error_response("INVALID_DATE", msg or "日期无效", 400)
        if raw_date == server_today:
            target_date = raw_date
        else:
            utc_today = datetime.utcnow().strftime("%Y-%m-%d")
            utc_lag_detected = raw_date == utc_today and utc_today != server_today
            if not utc_lag_detected:
                return error_response(
                    "INVALID_DATE",
                    f"增量同步仅支持服务器当天日期（{server_today}）",
                    400,
                )
            target_date = server_today
            date_normalized = {
                "from": raw_date,
                "to": server_today,
                "reason": "utc_date_lag",
            }

    valid_minutes, parsed_minutes, err = _validate_minutes(body.get("minutes", 0))
    if not valid_minutes:
        return error_response("INVALID_MINUTES", err or "分钟数无效", 400)

    try:
        await _ensure_user(user, client_version)
    except Exception as e:
        if str(e) == "REGISTRATION_PAUSED":
            return error_response("REGISTRATION_PAUSED", "新用户注册已暂停", 403)
        return error_response("USER_INIT_FAILED", str(e) or "初始化用户失败", 500)
    conn = _conn()
    try:
        site = user.get("site", "linux.do")
        user_id = str(user.get("user_id") or user.get("sub") or "")
        db_user = _get_user(conn, site, user_id)
        if not db_user:
            return error_response("USER_INIT_FAILED", "初始化用户失败", 500)

        validation = _validate_reading_data(
            conn, site, user_id, target_date, parsed_minutes
        )
        if not validation.get("valid"):
            return error_response(
                "VALIDATION_FAILED", validation.get("reason", "校验失败"), 400
            )

        new_minutes = int(validation["clampedMinutes"])
        now_ms = int(time.time() * 1000)
        conn.execute(
            """INSERT INTO reading_daily (site, user_id, date, minutes, sync_count, last_update, created_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(site, user_id, date) DO UPDATE SET
                 minutes = excluded.minutes,
                 sync_count = COALESCE(reading_daily.sync_count, 0) + 1,
                 last_update = excluded.last_update""",
            (site, user_id, target_date, new_minutes, now_ms, now_ms),
        )

        update_data = _check_and_update_user_profile(conn, db_user, user, now_ms)
        last_sync = (
            int(db_user["last_sync"] or 0) if "last_sync" in db_user.keys() else 0
        )
        if not last_sync or (now_ms - last_sync) > LAST_SYNC_UPDATE_INTERVAL_MS:
            update_data["last_sync"] = now_ms
        if client_version and (
            "client_version" not in db_user.keys()
            or client_version != db_user["client_version"]
        ):
            update_data["client_version"] = client_version
        if update_data:
            set_clause = ", ".join(f"{k} = ?" for k in update_data.keys())
            conn.execute(
                f"UPDATE users SET {set_clause}, updated_at = ? WHERE site = ? AND user_id = ?",
                [*update_data.values(), str(now_ms), site, user_id],
            )
        conn.commit()

        response_data = {
            "server_date": target_date,
            "server_minutes": new_minutes,
            "synced_at": now_ms,
            "formatted_time": _format_reading_time(new_minutes),
            "persisted": True,
            "buffered": False,
        }
        if date_normalized:
            response_data["date_normalized"] = date_normalized
        if validation.get("serverOverride"):
            response_data["override"] = True
            response_data["message"] = "本地数据落后于服务器状态"
        if validation.get("truncated"):
            response_data["truncated"] = True
            response_data["message"] = "增量超过允许范围，已自动限制"
        if validation.get("historicalLock"):
            response_data["historicalLock"] = True
            response_data["message"] = "历史数据增量受限"
        if validation.get("rateLimited"):
            response_data["rateLimited"] = True
            response_data["message"] = "同步过于频繁"
        return success_response(data=response_data)
    except Exception as e:
        return error_response("SYNC_FAILED", f"持久化阅读数据失败：{e}", 500)
    finally:
        conn.close()


@router.post("/api/reading/sync-full")
async def reading_sync_full(request: Request):
    user = request.state.user
    if not user:
        return error_response("UNAUTHORIZED", "需要登录", 401)
    try:
        body = await request.json()
    except Exception:
        return error_response("INVALID_JSON", "无效的 JSON 请求体", 400)
    if not body or not isinstance(body, dict):
        return error_response("INVALID_BODY", "请求体必须是对象", 400)
    client_version = request.headers.get("X-Client-Version")
    daily_data = body.get("dailyData")
    if not isinstance(daily_data, dict):
        return error_response("INVALID_DATA", "dailyData 为必填且必须是对象", 400)

    try:
        await _ensure_user(user, client_version)
    except Exception as e:
        if str(e) == "REGISTRATION_PAUSED":
            return error_response("REGISTRATION_PAUSED", "新用户注册已暂停", 403)
        return error_response("USER_INIT_FAILED", str(e) or "初始化用户失败", 500)
    conn = _conn()
    try:
        site = user.get("site", "linux.do")
        user_id = str(user.get("user_id") or user.get("sub") or "")
        db_user = _get_user(conn, site, user_id)
        if not db_user:
            return error_response("USER_INIT_FAILED", "初始化用户失败", 500)

        today = _today_date()
        entries = []
        for date_key, day_data in daily_data.items():
            parsed_date = _parse_date_key(date_key)
            minutes = Number = None
            try:
                minutes = int(float((day_data or {}).get("totalMinutes", 0)))
            except Exception:
                minutes = 0
            if parsed_date and parsed_date <= today and minutes > 0:
                entries.append(
                    {"date": parsed_date, "minutes": minutes, "raw": date_key}
                )
        entries.sort(key=lambda x: x["date"], reverse=True)
        entries = entries[:500]

        if not entries:
            return success_response(
                data={
                    "synced_count": 0,
                    "synced_dates": [],
                    "synced_at": int(time.time() * 1000),
                }
            )

        min_date = min(i["date"] for i in entries)
        existing_rows = conn.execute(
            "SELECT date, minutes FROM reading_daily WHERE site = ? AND user_id = ? AND date >= ?",
            (site, user_id, min_date),
        ).fetchall()
        existing_map = {r["date"]: int(r["minutes"] or 0) for r in existing_rows}
        max_daily = _get_max_daily_minutes(conn)
        synced_dates = []
        errors = []
        now_ms = int(time.time() * 1000)
        now_beijing = datetime.utcnow() + timedelta(hours=8)

        for item in entries:
            try:
                max_possible = (
                    now_beijing.hour * 60 + now_beijing.minute
                    if item["date"] == today
                    else 1440
                )
                clamped = min(item["minutes"], max_possible, max_daily)
                existing = existing_map.get(item["date"], 0)
                final_minutes = (
                    max(existing, min(clamped, existing + HISTORY_MAX_INCREMENT))
                    if existing > 0
                    else clamped
                )
                if final_minutes <= 0:
                    continue
                conn.execute(
                    """INSERT INTO reading_daily (site, user_id, date, minutes, sync_count, last_update, created_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?)
                       ON CONFLICT(site, user_id, date) DO UPDATE SET
                         minutes = excluded.minutes,
                         sync_count = COALESCE(reading_daily.sync_count, 0) + 1,
                         last_update = excluded.last_update""",
                    (site, user_id, item["date"], final_minutes, now_ms, now_ms),
                )
                synced_dates.append(item["date"])
            except Exception as e:
                errors.append({"date": item["raw"], "error": str(e)})

        update_data = {"last_full_sync": now_ms}
        profile_update = _check_and_update_user_profile(conn, db_user, user, now_ms)
        update_data.update(profile_update)
        if client_version and (
            "client_version" not in db_user.keys()
            or client_version != db_user["client_version"]
        ):
            update_data["client_version"] = client_version
        set_clause = ", ".join(f"{k} = ?" for k in update_data.keys())
        conn.execute(
            f"UPDATE users SET {set_clause}, updated_at = ? WHERE site = ? AND user_id = ?",
            [*update_data.values(), str(now_ms), site, user_id],
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
        return error_response("SYNC_ERROR", str(e), 500)
    finally:
        conn.close()


@router.get("/api/reading/history")
async def reading_history(request: Request):
    user = request.state.user
    if not user:
        return error_response("UNAUTHORIZED", "需要登录", 401)
    days = int(request.query_params.get("days", 365))
    days = max(1, min(days, 365))
    conn = _conn()
    try:
        site = user.get("site", "linux.do")
        user_id = str(user.get("user_id") or user.get("sub") or "")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT date, minutes, last_update FROM reading_daily WHERE site = ? AND user_id = ? AND date >= ? AND minutes > 0 ORDER BY date DESC",
            (site, user_id, start_date),
        ).fetchall()
        daily_data = {}
        for row in rows:
            year_text, month_text, day_text = row["date"].split("-")
            js_date = datetime(int(year_text), int(month_text), int(day_text))
            frontend_date_key = js_date.strftime("%a %b %d %Y")
            daily_data[frontend_date_key] = {
                "totalMinutes": row["minutes"],
                "lastActive": row["last_update"] or int(time.time() * 1000),
            }
        user_row = _get_user(conn, site, user_id)
        return success_response(
            data={
                "dailyData": daily_data,
                "lastSync": (
                    user_row["last_full_sync"]
                    if user_row and "last_full_sync" in user_row.keys()
                    else None
                )
                or (
                    user_row["last_sync"]
                    if user_row and "last_sync" in user_row.keys()
                    else None
                ),
                "totalDays": len(daily_data),
            }
        )
    finally:
        conn.close()
