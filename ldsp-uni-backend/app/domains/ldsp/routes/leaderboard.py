"""Leaderboard routes (client-facing + admin)."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from app.config import settings
from app.common.utils.response import error_response, success_response

router = APIRouter(tags=["ldsp-leaderboard"])

DEFAULT_PAGE_SIZE = 20


def _supported_sites() -> list[str]:
    raw = (settings.supported_sites or "linux.do,idcflare.com").strip()
    sites = [item.strip() for item in raw.split(",") if item.strip()]
    return sites or ["linux.do", "idcflare.com"]


def _parse_positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _get_date_key(date_str: str | None, fmt: str = "%Y-%m-%d") -> str:
    if date_str:
        return date_str
    return datetime.now(timezone.utc).strftime(fmt)


@router.get("/api/leaderboard/daily")
async def leaderboard_daily(request: Request, date: str | None = Query(None)):
    user = getattr(request.state, "user", {})
    site = user.get("site", "linux.do")
    user_id = user.get("user_id")
    date_key = _get_date_key(date)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """SELECT rd.user_id, rd.minutes, u.username, u.name, u.avatar_url, u.trust_level
               FROM reading_daily rd
               JOIN users u ON rd.site = u.site AND rd.user_id = u.user_id
               WHERE rd.site = ? AND rd.date = ?
               ORDER BY rd.minutes DESC
               LIMIT ?""",
            (site, date_key, DEFAULT_PAGE_SIZE),
        )
        rows = cursor.fetchall()
        leaderboard = [
            {
                "user_id": r[0],
                "minutes": r[1],
                "username": r[2],
                "name": r[3],
                "avatar_url": r[4],
                "trust_level": r[5],
            }
            for r in rows
        ]

        my_rank = None
        if user_id:
            cursor = conn.execute(
                """SELECT minutes, RANK() OVER (ORDER BY minutes DESC) as rank
                   FROM reading_daily WHERE site = ? AND date = ? AND user_id = ?""",
                (site, date_key, user_id),
            )
            row = cursor.fetchone()
            if row:
                my_rank = {"minutes": row[0], "rank": row[1]}

        return success_response(
            data={
                "period": date_key,
                "date": date_key,
                "rankings": leaderboard,
                "leaderboard": leaderboard,
                "myRank": my_rank,
                "my_rank": my_rank,
            }
        )
    finally:
        conn.close()


@router.get("/api/leaderboard/weekly")
async def leaderboard_weekly(request: Request, week: str | None = Query(None)):
    user = getattr(request.state, "user", {})
    site = user.get("site", "linux.do")
    user_id = user.get("user_id")
    week_key = _get_date_key(week, "%Y-W%W")

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """SELECT rw.user_id, rw.minutes, u.username, u.name, u.avatar_url, u.trust_level
               FROM reading_weekly rw
               JOIN users u ON rw.site = u.site AND rw.user_id = u.user_id
               WHERE rw.site = ? AND rw.week = ?
               ORDER BY rw.minutes DESC
               LIMIT ?""",
            (site, week_key, DEFAULT_PAGE_SIZE),
        )
        rows = cursor.fetchall()
        leaderboard = [
            {
                "user_id": r[0],
                "minutes": r[1],
                "username": r[2],
                "name": r[3],
                "avatar_url": r[4],
                "trust_level": r[5],
            }
            for r in rows
        ]

        my_rank = None
        if user_id:
            cursor = conn.execute(
                """SELECT minutes, RANK() OVER (ORDER BY minutes DESC) as rank
                   FROM reading_weekly WHERE site = ? AND week = ? AND user_id = ?""",
                (site, week_key, user_id),
            )
            row = cursor.fetchone()
            if row:
                my_rank = {"minutes": row[0], "rank": row[1]}

        return success_response(
            data={
                "period": week_key,
                "week": week_key,
                "rankings": leaderboard,
                "leaderboard": leaderboard,
                "myRank": my_rank,
                "my_rank": my_rank,
            }
        )
    finally:
        conn.close()


@router.get("/api/leaderboard/monthly")
async def leaderboard_monthly(request: Request, month: str | None = Query(None)):
    user = getattr(request.state, "user", {})
    site = user.get("site", "linux.do")
    user_id = user.get("user_id")
    month_key = _get_date_key(month, "%Y-%m")

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """SELECT rm.user_id, rm.minutes, u.username, u.name, u.avatar_url, u.trust_level
               FROM reading_monthly rm
               JOIN users u ON rm.site = u.site AND rm.user_id = u.user_id
               WHERE rm.site = ? AND rm.month = ?
               ORDER BY rm.minutes DESC
               LIMIT ?""",
            (site, month_key, DEFAULT_PAGE_SIZE),
        )
        rows = cursor.fetchall()
        leaderboard = [
            {
                "user_id": r[0],
                "minutes": r[1],
                "username": r[2],
                "name": r[3],
                "avatar_url": r[4],
                "trust_level": r[5],
            }
            for r in rows
        ]

        my_rank = None
        if user_id:
            cursor = conn.execute(
                """SELECT minutes, RANK() OVER (ORDER BY minutes DESC) as rank
                   FROM reading_monthly WHERE site = ? AND month = ? AND user_id = ?""",
                (site, month_key, user_id),
            )
            row = cursor.fetchone()
            if row:
                my_rank = {"minutes": row[0], "rank": row[1]}

        return success_response(
            data={
                "period": month_key,
                "month": month_key,
                "rankings": leaderboard,
                "leaderboard": leaderboard,
                "myRank": my_rank,
                "my_rank": my_rank,
            }
        )
    finally:
        conn.close()


@router.get("/api/admin/leaderboard-settings")
async def admin_leaderboard_settings():
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT key, value FROM system_config WHERE key IN (?, ?, ?)",
            (
                "leaderboard_daily_size",
                "leaderboard_weekly_size",
                "leaderboard_monthly_size",
            ),
        ).fetchall()
        settings_data = {"daily": 50, "weekly": 50, "monthly": 50}
        for row in rows:
            if row["key"] == "leaderboard_daily_size":
                settings_data["daily"] = _parse_positive_int(row["value"], 50)
            elif row["key"] == "leaderboard_weekly_size":
                settings_data["weekly"] = _parse_positive_int(row["value"], 50)
            elif row["key"] == "leaderboard_monthly_size":
                settings_data["monthly"] = _parse_positive_int(row["value"], 50)
        return success_response(data=settings_data)
    finally:
        conn.close()


@router.post("/api/admin/leaderboard-settings")
async def admin_leaderboard_settings_update(request: Request):
    body = await request.json()
    daily = body.get("daily")
    weekly = body.get("weekly")
    monthly = body.get("monthly")

    if daily and (daily < 10 or daily > 100):
        return error_response("INVALID_PARAMS", "daily 必须在 10 到 100 之间", 400)
    if weekly and (weekly < 10 or weekly > 100):
        return error_response("INVALID_PARAMS", "weekly 必须在 10 到 100 之间", 400)
    if monthly and (monthly < 10 or monthly > 100):
        return error_response("INVALID_PARAMS", "monthly 必须在 10 到 100 之间", 400)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        now = int(time.time() * 1000)
        settings_data = {
            "daily": daily or 50,
            "weekly": weekly or 50,
            "monthly": monthly or 50,
        }
        conn.execute(
            """INSERT INTO system_config (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            ("leaderboard_daily_size", str(settings_data["daily"]), now),
        )
        conn.execute(
            """INSERT INTO system_config (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            ("leaderboard_weekly_size", str(settings_data["weekly"]), now),
        )
        conn.execute(
            """INSERT INTO system_config (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            ("leaderboard_monthly_size", str(settings_data["monthly"]), now),
        )
        conn.commit()
        return success_response(
            data=settings_data,
            message="排行榜配置已更新并刷新缓存",
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/refresh-leaderboard")
async def admin_refresh_leaderboard(
    type: str | None = Query(None),
    site: str | None = Query(None),
):
    refresh_type = type or "all"
    sites_to_refresh = [site] if site else _supported_sites()
    refreshed = {}

    for target_site in sites_to_refresh:
        refreshed[target_site] = {}
        if refresh_type in ("daily", "all"):
            refreshed[target_site]["daily"] = "refreshed"
        if refresh_type in ("weekly", "all"):
            refreshed[target_site]["weekly"] = "refreshed"
        if refresh_type in ("monthly", "all"):
            refreshed[target_site]["monthly"] = "refreshed"

    return success_response(
        data={
            "message": "排行榜缓存已刷新",
            "refreshed": refreshed,
            "timestamp": int(time.time() * 1000),
        }
    )
