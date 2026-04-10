"""Admin dashboard and user management routes."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.config import settings
from app.common.utils.response import error_response, success_response

router = APIRouter(tags=["ldsp-admin-dashboard"])


def _supported_sites() -> list[str]:
    raw = (settings.supported_sites or "linux.do,idcflare.com").strip()
    sites = [item.strip() for item in raw.split(",") if item.strip()]
    return sites or ["linux.do", "idcflare.com"]


@router.get("/api/admin/stats")
async def admin_stats():
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        days7_ago = (
            datetime.now(timezone.utc) - __import__("datetime").timedelta(days=7)
        ).strftime("%Y-%m-%d")
        days30_ago = (
            datetime.now(timezone.utc) - __import__("datetime").timedelta(days=30)
        ).strftime("%Y-%m-%d")
        total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        active_users = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE COALESCE(is_active, 0) = 1"
        ).fetchone()["c"]
        cloud_sync_only = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE COALESCE(cloud_sync_only, 0) = 1"
        ).fetchone()["c"]
        linuxdo_count = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE site = 'linux.do'"
        ).fetchone()["c"]
        idcflare_count = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE site = 'idcflare.com'"
        ).fetchone()["c"]
        new_today = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE substr(CAST(created_at AS TEXT), 1, 10) = ?",
            (today,),
        ).fetchone()["c"]
        new_last7 = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE CAST(created_at AS INTEGER) >= ?",
            (int((time.time() - 7 * 86400) * 1000),),
        ).fetchone()["c"]
        new_last30 = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE CAST(created_at AS INTEGER) >= ?",
            (int((time.time() - 30 * 86400) * 1000),),
        ).fetchone()["c"]
        today_active = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM reading_daily WHERE date = ?",
            (today,),
        ).fetchone()[0]
        week_start = (
            datetime.now(timezone.utc) - __import__("datetime").timedelta(days=6)
        ).strftime("%Y-%m-%d")
        month_start = (
            datetime.now(timezone.utc) - __import__("datetime").timedelta(days=29)
        ).strftime("%Y-%m-%d")
        weekly_active = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM reading_daily WHERE date >= ?",
            (days7_ago,),
        ).fetchone()[0]
        monthly_active = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM reading_daily WHERE date >= ?",
            (days30_ago,),
        ).fetchone()[0]
        total_records = conn.execute(
            "SELECT COUNT(*) AS c FROM reading_daily"
        ).fetchone()["c"]
        today_minutes = conn.execute(
            "SELECT COALESCE(SUM(minutes), 0) AS s FROM reading_daily WHERE date = ?",
            (today,),
        ).fetchone()["s"]
        weekly_minutes = conn.execute(
            "SELECT COALESCE(SUM(minutes), 0) AS s FROM reading_daily WHERE date >= ?",
            (days7_ago,),
        ).fetchone()["s"]
        monthly_minutes = conn.execute(
            "SELECT COALESCE(SUM(minutes), 0) AS s FROM reading_daily WHERE date >= ?",
            (days30_ago,),
        ).fetchone()["s"]
        trust_level_distribution = [
            dict(r)
            for r in conn.execute(
                "SELECT COALESCE(trust_level, 0) AS trust_level, COUNT(*) AS count FROM users GROUP BY COALESCE(trust_level, 0) ORDER BY trust_level ASC"
            ).fetchall()
        ]
        daily_active_history = [
            dict(r)
            for r in conn.execute(
                "SELECT date, COUNT(DISTINCT user_id) AS count FROM reading_daily WHERE date >= ? GROUP BY date ORDER BY date ASC",
                (days7_ago,),
            ).fetchall()
        ]
        monthly_active_history = [
            dict(r)
            for r in conn.execute(
                "SELECT date, COUNT(DISTINCT user_id) AS count FROM reading_daily WHERE date >= ? GROUP BY date ORDER BY date ASC",
                (days30_ago,),
            ).fetchall()
        ]
        daily_reading_minutes = [
            {"date": r["date"], "total": r["total"]}
            for r in conn.execute(
                "SELECT date, COALESCE(SUM(minutes), 0) AS total FROM reading_daily WHERE date >= ? GROUP BY date ORDER BY date ASC",
                (days7_ago,),
            ).fetchall()
        ]

        return success_response(
            data={
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "cloudSyncOnly": cloud_sync_only,
                    "linuxDoCount": linuxdo_count,
                    "idcflareCount": idcflare_count,
                    "newToday": new_today,
                    "newLast7Days": new_last7,
                    "newLast30Days": new_last30,
                },
                "activity": {
                    "todayActiveUsers": today_active,
                    "weeklyActiveUsers": weekly_active,
                    "monthlyActiveUsers": monthly_active,
                },
                "reading": {
                    "totalRecords": total_records,
                    "todayMinutes": int(today_minutes or 0),
                    "weeklyMinutes": int(weekly_minutes or 0),
                    "weeklyHours": round((weekly_minutes or 0) / 60, 1),
                    "monthlyHours": round((monthly_minutes or 0) / 60, 1),
                    "monthlyMinutes": int(monthly_minutes or 0),
                    "todayHours": round((today_minutes or 0) / 60, 1),
                },
                "trustLevelDistribution": trust_level_distribution,
                "history": {
                    "dailyActiveUsers": daily_active_history,
                    "monthlyActiveUsers": monthly_active_history,
                    "dailyReadingMinutes": daily_reading_minutes,
                },
                "generatedAt": int(time.time() * 1000),
            }
        )
    except Exception as e:
        return error_response("STATS_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/recent-users")
async def admin_recent_users(request: Request):
    page = int(request.query_params.get("page", 1))
    per_page = int(
        request.query_params.get(
            "per_page",
            request.query_params.get("pageSize", request.query_params.get("limit", 20)),
        )
    )
    search = request.query_params.get("search", "").strip()
    site = request.query_params.get("site", "").strip()
    status = request.query_params.get("status", "").strip()
    offset = (page - 1) * per_page

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        where = ["1=1"]
        params: list[object] = []

        if search:
            like = f"%{search}%"
            where.append(
                "(username LIKE ? OR CAST(user_id AS TEXT) LIKE ? OR name LIKE ?)"
            )
            params.extend([like, like, like])

        if site:
            where.append("COALESCE(site, 'linux.do') = ?")
            params.append(site)

        if status == "active":
            where.append("COALESCE(is_active, 0) = 1")
        elif status == "inactive":
            where.append("COALESCE(is_active, 0) = 0")

        where_sql = " WHERE " + " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) FROM users{where_sql}",
            params,
        ).fetchone()[0]
        cursor = conn.execute(
            "SELECT id, user_id, username, name, avatar_url, trust_level, is_active, joined_at, site, "
            "client_version, created_at, updated_at, last_sync "
            f"FROM users{where_sql} ORDER BY COALESCE(joined_at, created_at, updated_at) DESC LIMIT ? OFFSET ?",
            (*params, per_page, offset),
        )

        rows = cursor.fetchall()
        users = [
            {
                "id": r[0],
                "user_id": r[1],
                "username": r[2],
                "name": r[3],
                "avatar_url": r[4],
                "trust_level": r[5],
                "is_active": r[6],
                "joined_at": r[7],
                "created_at": r[10] or r[7],
                "site": r[8] or "linux.do",
                "client_version": r[9],
                "updated_at": r[11],
                "last_sync": r[12],
            }
            for r in rows
        ]

        return success_response(
            data={
                "users": users,
                "total": total,
                "page": page,
                "per_page": per_page,
                "totalPages": (total + per_page - 1) // per_page if total > 0 else 1,
                "pagination": {
                    "page": page,
                    "pageSize": per_page,
                    "total": total,
                    "totalPages": (total + per_page - 1) // per_page
                    if total > 0
                    else 1,
                },
            }
        )
    except Exception as e:
        return error_response("RECENT_USERS_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/user/{user_id}")
async def admin_user_detail(user_id: str, request: Request):
    days = int(request.query_params.get("days", 30) or 30)
    days = max(1, min(days, 365))
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        admin_user_id = int(user_id)
        if admin_user_id <= 0:
            return error_response("INVALID_PARAMS", "用户 ID 无效", 400)

        user_row = conn.execute(
            "SELECT id, user_id, site, username, name, avatar_url, trust_level, is_active, "
            "cloud_sync_only, joined_at, quit_at, created_at, last_sync, last_full_sync, client_version "
            "FROM users WHERE id = ?",
            (admin_user_id,),
        ).fetchone()
        if not user_row:
            return error_response("USER_NOT_FOUND", "用户不存在", 404)

        reading_history = conn.execute(
            "SELECT date, minutes, sync_count, last_update FROM reading_daily WHERE site = ? AND user_id = ? ORDER BY date DESC LIMIT ?",
            (user_row["site"], user_row["user_id"], days),
        ).fetchall()

        total_stats = conn.execute(
            "SELECT COUNT(*) as total_days, COALESCE(SUM(minutes), 0) as total_minutes, "
            "COALESCE(AVG(minutes), 0) as avg_minutes, COALESCE(MAX(minutes), 0) as max_minutes "
            "FROM reading_daily WHERE site = ? AND user_id = ?",
            (user_row["site"], user_row["user_id"]),
        ).fetchone()

        history_items = [
            {
                "date": r["date"],
                "minutes": r["minutes"],
                "sync_count": r["sync_count"],
                "last_update": r["last_update"],
            }
            for r in reading_history
        ]

        return success_response(
            data={
                "user": dict(user_row),
                "reading_history": history_items,
                "readingHistory": history_items,
                "stats": {
                    "totalDays": total_stats["total_days"] or 0,
                    "totalMinutes": round(total_stats["total_minutes"] or 0),
                    "avgMinutes": round((total_stats["avg_minutes"] or 0) * 10) / 10,
                    "maxMinutes": round(total_stats["max_minutes"] or 0),
                    "totalHours": round((total_stats["total_minutes"] or 0) / 60 * 10)
                    / 10,
                },
            }
        )
    except Exception as e:
        return error_response("USER_DETAIL_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/today-top-readers")
async def admin_today_top_readers(request: Request):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    limit = int(request.query_params.get("limit", 20))
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = conn.execute("PRAGMA table_info(reading_daily)").fetchall()
        col_names = {c[1] for c in cols}
        rank_col = "rank" if "rank" in col_names else "NULL"
        cursor = conn.execute(
            f"""SELECT rd.user_id, u.username, rd.minutes, {rank_col} as rank, COALESCE(u.site, rd.site) as site, COALESCE(u.is_active, 0) as is_active
               FROM reading_daily rd
               LEFT JOIN users u ON u.user_id = rd.user_id AND u.site = rd.site
               WHERE rd.date = ?
               ORDER BY rd.minutes DESC
               LIMIT ?""",
            (today, limit),
        )
        rows = cursor.fetchall()
        return success_response(
            data={
                "date": today,
                "readers": [
                    {
                        "user_id": r[0],
                        "username": r[1],
                        "minutes": r[2],
                        "rank": r[3],
                        "site": r[4],
                        "is_active": bool(r[5]),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        )
    except Exception as e:
        return error_response("TOP_READERS_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/monthly-top-readers")
async def admin_monthly_top_readers(request: Request):
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    limit = int(request.query_params.get("limit", 20))
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = conn.execute("PRAGMA table_info(reading_monthly)").fetchall()
        col_names = {c[1] for c in cols}
        month_col = "year_month" if "year_month" in col_names else "month"
        rank_col = "rank" if "rank" in col_names else "NULL"
        cursor = conn.execute(
            f"""SELECT rm.user_id, u.username, rm.minutes, {rank_col} as rank, COALESCE(u.site, rm.site) as site, COALESCE(u.is_active, 0) as is_active
               FROM reading_monthly rm
               LEFT JOIN users u ON u.user_id = rm.user_id AND u.site = rm.site
               WHERE rm.{month_col} = ?
               ORDER BY rm.minutes DESC
               LIMIT ?""",
            (year_month, limit),
        )
        rows = cursor.fetchall()
        return success_response(
            data={
                "month": year_month,
                "readers": [
                    {
                        "user_id": r[0],
                        "username": r[1],
                        "minutes": r[2],
                        "rank": r[3],
                        "site": r[4],
                        "is_active": bool(r[5]),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        )
    except Exception as e:
        return error_response("MONTHLY_READERS_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/suspicious-readings")
async def admin_suspicious_readings(request: Request):
    limit = int(request.query_params.get("limit", 50))
    date = request.query_params.get("date") or datetime.now(timezone.utc).strftime(
        "%Y-%m-%d"
    )
    threshold = int(request.query_params.get("threshold", 600))
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """SELECT rd.user_id, rd.site, rd.date, rd.minutes, rd.last_update,
               u.username, u.name, u.trust_level
               FROM reading_daily rd
               JOIN users u ON rd.site = u.site AND rd.user_id = u.user_id
               WHERE rd.date = ? AND rd.minutes > ?
               ORDER BY rd.minutes DESC
               LIMIT ?""",
            (date, threshold, limit),
        )
        rows = cursor.fetchall()

        max_possible_minutes = 1440
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if date == today:
            now = datetime.now(timezone.utc)
            max_possible_minutes = now.hour * 60 + now.minute

        return success_response(
            data={
                "date": date,
                "threshold": threshold,
                "maxPossibleMinutes": max_possible_minutes,
                "suspiciousCount": len(rows),
                "records": [
                    {
                        "user_id": r["user_id"],
                        "site": r["site"],
                        "date": r["date"],
                        "minutes": r["minutes"],
                        "last_update": r["last_update"],
                        "username": r["username"],
                        "name": r["name"],
                        "trust_level": r["trust_level"],
                    }
                    for r in rows
                ],
            }
        )
    except Exception as e:
        return error_response("SUSPICIOUS_READINGS_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/fix-reading")
async def admin_fix_reading(request: Request):
    body = await request.json()
    user_id = body.get("user_id") or body.get("userId")
    site = (body.get("site") or "").strip()
    date = body.get("date")
    minutes = body.get("minutes")

    if not user_id or not site or not date:
        return error_response("INVALID_PARAMS", "userId、site 和 date 为必填项", 400)
    if not isinstance(date, str) or len(date) != 10:
        return error_response("INVALID_DATE", "日期格式必须为 YYYY-MM-DD", 400)

    minutes_raw = float(minutes) if minutes is not None else 0
    valid_minutes = max(0, min(minutes_raw, 1440))

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        result = conn.execute(
            "UPDATE reading_daily SET minutes = ?, last_update = ? WHERE site = ? AND user_id = ? AND date = ?",
            (valid_minutes, int(time.time() * 1000), site, user_id, date),
        )
        conn.commit()

        if result.rowcount == 0:
            return error_response("NOT_FOUND", "阅读记录不存在", 404)

        return success_response(
            data={
                "message": "阅读时长已更新",
                "userId": int(user_id),
                "site": site,
                "date": date,
                "minutes": valid_minutes,
            }
        )
    except Exception as e:
        return error_response("FIX_READING_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/add-reading")
async def admin_add_reading(request: Request):
    body = await request.json()
    user_id = body.get("user_id") or body.get("userId")
    site = body.get("site", "linux.do")
    minutes = body.get("minutes")
    reading_date = body.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    if not user_id or not site or not reading_date:
        return error_response("INVALID_PARAMS", "userId、site 和 date 为必填项", 400)
    if not isinstance(reading_date, str) or len(reading_date) != 10:
        return error_response("INVALID_DATE", "日期格式必须为 YYYY-MM-DD", 400)
    if site not in _supported_sites():
        return error_response(
            "INVALID_SITE", f"site 必须是以下之一：{', '.join(_supported_sites())}", 400
        )

    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        now_ms = int(time.time() * 1000)
        user_row = conn.execute(
            "SELECT id, user_id, site FROM users WHERE site = ? AND user_id = ?",
            (site, user_id),
        ).fetchone()
        if not user_row:
            return error_response("USER_NOT_FOUND", "用户不存在", 404)

        existing_row = conn.execute(
            "SELECT COALESCE(minutes, 0) as minutes, COALESCE(sync_count, 0) as sync_count FROM reading_daily WHERE site = ? AND user_id = ? AND date = ?",
            (site, user_id, reading_date),
        ).fetchone()
        existing_minutes = float(existing_row["minutes"] or 0) if existing_row else 0
        incoming_minutes = max(0, min(float(minutes), 1440))
        new_minutes = max(existing_minutes, incoming_minutes)

        conn.execute(
            """INSERT INTO reading_daily (site, user_id, date, minutes, sync_count, last_update, created_at, rank)
               VALUES (?, ?, ?, ?, 1, ?, ?, NULL)
               ON CONFLICT(user_id, site, date) DO UPDATE SET
               minutes = MAX(reading_daily.minutes, excluded.minutes),
               sync_count = COALESCE(reading_daily.sync_count, 0) + 1,
               last_update = MAX(COALESCE(reading_daily.last_update, 0), excluded.last_update)""",
            (site, user_id, reading_date, new_minutes, now_ms, now_ms),
        )
        conn.commit()

        record = conn.execute(
            "SELECT * FROM reading_daily WHERE site = ? AND user_id = ? AND date = ?",
            (site, user_id, reading_date),
        ).fetchone()

        return success_response(
            data={
                "message": "阅读时长新增/更新成功",
                "userId": int(user_id),
                "site": site,
                "date": reading_date,
                "minutes": incoming_minutes,
                "record": dict(record) if record else None,
            }
        )
    except Exception as e:
        return error_response("ADD_READING_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/update-user-site")
async def admin_update_user_site(request: Request):
    body = await request.json()
    user_id = body.get("user_id") or body.get("userId")
    new_site = body.get("new_site") or body.get("newSite")

    if not user_id or not new_site:
        return error_response("INVALID_PARAMS", "userId 和 newSite 为必填项", 400)
    if new_site not in _supported_sites():
        return error_response(
            "INVALID_SITE", f"site 必须是以下之一：{', '.join(_supported_sites())}", 400
        )

    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        existing_user = conn.execute(
            "SELECT id, user_id, site FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not existing_user:
            return error_response("USER_NOT_FOUND", "用户不存在", 404)

        conflict = conn.execute(
            "SELECT id FROM users WHERE site = ? AND user_id = ? AND id != ? LIMIT 1",
            (new_site, existing_user["user_id"], user_id),
        ).fetchone()
        if conflict:
            return error_response("SITE_CONFLICT", "目标站点已存在该用户", 409)

        conn.execute(
            "UPDATE users SET site = ?, updated_at = ? WHERE id = ?",
            (new_site, int(time.time() * 1000), user_id),
        )
        conn.execute(
            "UPDATE reading_daily SET site = ? WHERE user_id = ?",
            (new_site, existing_user["user_id"]),
        )
        conn.execute(
            "UPDATE reading_weekly SET site = ? WHERE user_id = ?",
            (new_site, existing_user["user_id"]),
        )
        conn.execute(
            "UPDATE reading_monthly SET site = ? WHERE user_id = ?",
            (new_site, existing_user["user_id"]),
        )
        conn.execute(
            "UPDATE requirements_history SET site = ? WHERE user_id = ?",
            (new_site, existing_user["user_id"]),
        )
        conn.commit()

        user = conn.execute(
            "SELECT id, user_id, username, joined_at, site FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        return success_response(
            data={"message": "用户站点更新成功", "user": dict(user) if user else None}
        )
    except Exception as e:
        return error_response("MIGRATE_SITE_FAILED", str(e), 500)
    finally:
        conn.close()
