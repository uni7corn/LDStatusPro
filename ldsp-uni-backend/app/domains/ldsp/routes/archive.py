"""Archive routes (admin-only)."""

from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Request

from app.config import settings
from app.common.utils.response import error_response, success_response

router = APIRouter(tags=["ldsp-archive"])


def _parse_positive_int(value, fallback=0) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (ValueError, TypeError):
        return fallback


@router.get("/api/admin/archive/stats")
async def archive_stats():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM reading_daily")
        daily_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM reading_weekly")
        weekly_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM reading_monthly")
        monthly_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT MIN(date) FROM reading_daily")
        oldest_date = cursor.fetchone()[0]

        cursor = conn.execute("SELECT MAX(date) FROM reading_daily")
        newest_date = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM archive_yearly")
        archive_count = cursor.fetchone()[0]

        return success_response(
            data={
                "dailyRecords": daily_count,
                "weeklyRecords": weekly_count,
                "monthlyRecords": monthly_count,
                "oldestDate": oldest_date,
                "newestDate": newest_date,
                "archiveRecords": archive_count,
            }
        )
    finally:
        conn.close()


@router.post("/api/admin/archive/yearly")
async def archive_yearly(request: Request):
    import time

    body = await request.json()
    year = body.get("year") or str(time.localtime().tm_year - 1)
    if not str(year).isdigit() or len(str(year)) != 4:
        return error_response("INVALID_YEAR", "年份格式必须为 YYYY", 400)

    current_year = time.localtime().tm_year
    if int(year) >= current_year:
        return error_response("INVALID_YEAR", "不能归档当前年份或未来年份", 400)

    delete_original = body.get("deleteOriginal", False)
    year_str = str(year)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        archived = 0

        cursor = conn.execute(
            """INSERT OR IGNORE INTO archive_yearly (site, user_id, year, minutes)
               SELECT site, user_id, ?, SUM(minutes)
               FROM reading_daily
               WHERE strftime('%Y', date) = ?
               GROUP BY site, user_id""",
            (year_str, year_str),
        )
        archived += cursor.rowcount

        if delete_original:
            conn.execute(
                "DELETE FROM reading_daily WHERE strftime('%Y', date) = ?", (year_str,)
            )

        conn.commit()
        return success_response(
            data={
                "year": year_str,
                "archived": archived,
                "deleteOriginal": delete_original,
            },
            message=f"{year_str} 年归档完成",
        )
    except Exception as e:
        return error_response("ARCHIVE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/archive/cleanup")
async def archive_cleanup(request: Request):
    body = await request.json()
    days_to_keep = _parse_positive_int(body.get("daysToKeep"), 90)
    if days_to_keep < 30:
        return error_response("INVALID_DAYS", "至少保留 30 天数据", 400)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cutoff_date = __import__("datetime").date.today() - __import__(
            "datetime"
        ).timedelta(days=days_to_keep)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        cursor = conn.execute(
            "SELECT COUNT(*) FROM reading_daily WHERE date < ?",
            (cutoff_str,),
        )
        count_before = cursor.fetchone()[0]

        conn.execute("DELETE FROM reading_daily WHERE date < ?", (cutoff_str,))
        deleted = conn.total_changes

        conn.commit()
        return success_response(
            data={"deleted": deleted, "daysToKeep": days_to_keep},
            message=f"清理完成，保留 {days_to_keep} 天数据",
        )
    except Exception as e:
        return error_response("CLEANUP_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/archive/rebuild-totals")
async def archive_rebuild_totals():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """INSERT OR REPLACE INTO user_totals (site, user_id, total_minutes, updated_at)
               SELECT site, user_id, SUM(minutes), ?
               FROM reading_daily
               GROUP BY site, user_id""",
            (int(__import__("time").time() * 1000),),
        )
        rebuilt = cursor.rowcount
        conn.commit()
        return success_response(
            data={"rebuilt": rebuilt},
            message="阅读总量重建成功",
        )
    except Exception as e:
        return error_response("REBUILD_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/user-total/{user_id}")
async def admin_user_total(user_id: int):
    uid = _parse_positive_int(user_id, 0)
    if not uid:
        return error_response("INVALID_PARAMS", "用户 ID 无效", 400)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute("SELECT user_id, site FROM users WHERE id = ?", (uid,))
        user = cursor.fetchone()
        if not user:
            return error_response("NOT_FOUND", "用户不存在", 404)

        site, db_user_id = user[1], user[0]

        cursor = conn.execute(
            """SELECT COALESCE(SUM(minutes), 0) as total_minutes,
                      COUNT(*) as total_days,
                      COALESCE(AVG(minutes), 0) as avg_minutes,
                      COALESCE(MAX(minutes), 0) as max_minutes,
                      MIN(date) as first_date,
                      MAX(date) as last_date
               FROM reading_daily
               WHERE site = ? AND user_id = ?""",
            (site, db_user_id),
        )
        row = cursor.fetchone()

        return success_response(
            data={
                "user_id": db_user_id,
                "site": site,
                "totalMinutes": round(row[0]),
                "totalDays": row[1],
                "avgMinutes": round(row[2] * 10) / 10 if row[2] else 0,
                "maxMinutes": round(row[3]),
                "firstDate": row[4],
                "lastDate": row[5],
                "totalHours": round(row[0] / 60 * 10) / 10 if row[0] else 0,
            }
        )
    finally:
        conn.close()
