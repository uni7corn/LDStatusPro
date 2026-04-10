"""Annual report routes (2025)."""

from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Query, Request

from app.config import settings
from app.common.utils.response import error_response, success_response

router = APIRouter(tags=["ldsp-annual-report"])

REPORT_YEAR = "2025"


@router.get(f"/api/annual-report/{REPORT_YEAR}")
async def annual_report(request: Request, site: str = Query("linux.do")):
    user = getattr(request.state, "user", {})
    user_id = user.get("user_id")
    if not user_id:
        return error_response("UNAUTHORIZED", "需要登录", 401)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """SELECT COALESCE(SUM(minutes), 0) as total_minutes,
                      COUNT(*) as total_days,
                      COALESCE(MAX(minutes), 0) as max_minutes,
                      MIN(date) as first_date,
                      MAX(date) as last_date
               FROM reading_daily
               WHERE site = ? AND user_id = ?
               AND strftime('%Y', date) = ?""",
            (site, user_id, REPORT_YEAR),
        )
        row = cursor.fetchone()
        if not row or row[0] == 0:
            return error_response("NO_DATA", f"暂无 {REPORT_YEAR} 年数据", 404)

        cursor = conn.execute(
            """SELECT COUNT(*) FROM reading_daily
               WHERE site = ? AND minutes = (SELECT MAX(minutes) FROM reading_daily WHERE site = ? AND user_id = ? AND strftime('%Y', date) = ?)
               AND user_id = ? AND strftime('%Y', date) = ?
               ORDER BY date ASC LIMIT 1""",
            (site, site, user_id, REPORT_YEAR, user_id, REPORT_YEAR),
        )
        best_day_row = cursor.fetchone()

        cursor = conn.execute(
            """SELECT COUNT(DISTINCT week) FROM reading_weekly
               WHERE site = ? AND user_id = ? AND substr(week, 1, 4) = ?""",
            (site, user_id, REPORT_YEAR),
        )
        weeks_active = cursor.fetchone()[0]

        return success_response(
            data={
                "year": REPORT_YEAR,
                "site": site,
                "totalMinutes": round(row[0]),
                "totalDays": row[1],
                "maxMinutes": round(row[2]),
                "firstDate": row[3],
                "lastDate": row[4],
                "totalHours": round(row[0] / 60 * 10) / 10,
                "weeksActive": weeks_active,
                "bestDay": best_day_row[0] if best_day_row else None,
            }
        )
    finally:
        conn.close()


@router.get(f"/api/annual-report/{REPORT_YEAR}/leaderboard")
async def annual_report_leaderboard(
    site: str = Query("linux.do"), page: int = Query(1), limit: int = Query(50)
):
    effective_limit = min(limit, 100)
    offset = (page - 1) * effective_limit

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            f"""SELECT ut.user_id, ut.total_minutes, u.username, u.name, u.avatar_url, u.trust_level
                FROM user_totals ut
                JOIN users u ON ut.site = u.site AND ut.user_id = u.user_id
                WHERE ut.site = ? AND ut.year = ?
                ORDER BY ut.total_minutes DESC
                LIMIT ? OFFSET ?""",
            (site, REPORT_YEAR, effective_limit, offset),
        )
        rows = cursor.fetchall()
        leaderboard = [
            {
                "user_id": r[0],
                "totalMinutes": round(r[1]),
                "username": r[2],
                "name": r[3],
                "avatar_url": r[4],
                "trust_level": r[5],
                "rank": offset + i + 1,
            }
            for i, r in enumerate(rows)
        ]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM user_totals WHERE site = ? AND year = ?",
            (site, REPORT_YEAR),
        )
        total = cursor.fetchone()[0]

        return success_response(
            data={
                "year": REPORT_YEAR,
                "site": site,
                "leaderboard": leaderboard,
                "total": total,
                "page": page,
                "limit": effective_limit,
                "totalPages": (total + effective_limit - 1) // effective_limit,
            }
        )
    finally:
        conn.close()


@router.post(f"/api/admin/annual-report/{REPORT_YEAR}/compute")
async def admin_annual_report_compute(
    site: str = Query(None), force: str = Query(None)
):
    target_site = site or "linux.do"
    should_force = force == "true"

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        now = int(__import__("time").time() * 1000)

        if should_force:
            conn.execute(
                "DELETE FROM user_totals WHERE site = ? AND year = ?",
                (target_site, REPORT_YEAR),
            )

        cursor = conn.execute(
            """INSERT OR REPLACE INTO user_totals (site, user_id, year, total_minutes, updated_at)
               SELECT site, user_id, ?, SUM(minutes), ?
               FROM reading_daily
               WHERE site = ? AND strftime('%Y', date) = ?
               GROUP BY site, user_id""",
            (REPORT_YEAR, now, target_site, REPORT_YEAR),
        )
        computed = cursor.rowcount
        conn.commit()

        return success_response(
            data={"computed": computed, "site": target_site, "year": REPORT_YEAR},
            message=f"{REPORT_YEAR} 年年报计算完成",
        )
    except Exception as e:
        return error_response("COMPUTE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get(f"/api/admin/annual-report/{REPORT_YEAR}/status")
async def admin_annual_report_status(site: str = Query("linux.do")):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            "SELECT COUNT(*), MAX(updated_at) FROM user_totals WHERE site = ? AND year = ?",
            (site, REPORT_YEAR),
        )
        row = cursor.fetchone()
        total = row[0] if row else 0
        last_updated = row[1] if row else None

        return success_response(
            data={
                "year": REPORT_YEAR,
                "site": site,
                "computed": total,
                "lastUpdated": last_updated,
            }
        )
    finally:
        conn.close()
