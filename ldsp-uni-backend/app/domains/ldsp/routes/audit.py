"""Audit log routes aligned with ldsp-backend audit APIs."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.config import settings
from app.common.utils.response import success_response, error_response

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])

DEFAULT_SAMPLE_RATE = 0.002


def _utc_now_ms() -> int:
    return int(time.time() * 1000)


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_ago_str(days: int) -> str:
    return (
        datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)
    ).strftime("%Y-%m-%d")


def _request_log_time_expr(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"COALESCE({prefix}created_at_utc, datetime({prefix}created_at, '-8 hours'))"


def _extract_request_type(row: sqlite3.Row) -> str:
    endpoint = str(row["endpoint"] or "")
    request_type = str(row["request_type"] or "").strip().lower()
    if request_type:
        return request_type
    return "admin" if endpoint.startswith("/api/admin") else "client"


def _result_type(row: sqlite3.Row) -> str:
    status_code = int(row["status_code"] or 0)
    if status_code in (403, 429):
        return "blocked"
    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "client_error"
    return "success"


def _row_to_dict(cursor: sqlite3.Cursor, row) -> dict:
    return {cursor.description[idx][0]: value for idx, value in enumerate(row)}


@router.get("/stats")
async def audit_stats(endpointRange: str | None = Query(default=None)):
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        endpoint_range = endpointRange or "week7"
        today = _today_str()
        week7 = _days_ago_str(7)
        month30 = _days_ago_str(30)

        rows = conn.execute(
            f"""SELECT id, endpoint, method, status_code, success, response_time, user_id, site,
               {_request_log_time_expr()} as created_at_utc,
               substr({_request_log_time_expr()}, 1, 10) as date_key,
               substr({_request_log_time_expr()}, 1, 13) || ':00' as hour_key,
               request_type, error_code
               FROM request_logs
               WHERE substr({_request_log_time_expr()}, 1, 10) >= ?
               ORDER BY {_request_log_time_expr()} DESC""",
            (month30,),
        ).fetchall()

        periods = {
            "today": lambda d: d == today,
            "week7": lambda d: d >= week7,
            "month30": lambda d: d >= month30,
        }

        def build_bucket(request_type: str, match_period):
            filtered = [
                r
                for r in rows
                if _extract_request_type(r) == request_type
                and match_period(r["date_key"])
            ]
            total = len(filtered)
            success_count = sum(1 for r in filtered if _result_type(r) == "success")
            blocked_count = sum(1 for r in filtered if _result_type(r) == "blocked")
            client_error_count = sum(
                1 for r in filtered if _result_type(r) == "client_error"
            )
            server_error_count = sum(
                1 for r in filtered if _result_type(r) == "server_error"
            )
            fail_count = total - success_count
            unique_ips = len(
                {
                    str(r["site"] or "") + ":" + str(r["user_id"] or "")
                    for r in filtered
                    if r["user_id"] is not None
                }
            )
            avg_response = (
                round(sum(float(r["response_time"] or 0) for r in filtered) / total, 1)
                if total
                else 0
            )
            return {
                "total": total,
                "success": success_count,
                "fail": fail_count,
                "blocked": blocked_count,
                "clientError": client_error_count,
                "serverError": server_error_count,
                "avgResponseTime": avg_response,
                "uniqueUsers": unique_ips,
            }

        admin = {
            key: build_bucket("admin", matcher) for key, matcher in periods.items()
        }
        client = {
            key: build_bucket("client", matcher) for key, matcher in periods.items()
        }
        combined = {}
        for key in periods.keys():
            combined[key] = {
                "total": admin[key]["total"] + client[key]["total"],
                "success": admin[key]["success"] + client[key]["success"],
                "fail": admin[key]["fail"] + client[key]["fail"],
                "blocked": admin[key]["blocked"] + client[key]["blocked"],
                "clientError": admin[key]["clientError"] + client[key]["clientError"],
                "serverError": admin[key]["serverError"] + client[key]["serverError"],
                "avgResponseTime": round(
                    (
                        admin[key]["avgResponseTime"] * admin[key]["total"]
                        + client[key]["avgResponseTime"] * client[key]["total"]
                    )
                    / (admin[key]["total"] + client[key]["total"]),
                    1,
                )
                if (admin[key]["total"] + client[key]["total"])
                else 0,
                "uniqueUsers": admin[key]["uniqueUsers"] + client[key]["uniqueUsers"],
            }

        hourly_map: dict[str, dict] = {}
        for row in rows:
            if row["date_key"] < today:
                continue
            hour_key = row["hour_key"]
            bucket = hourly_map.setdefault(
                hour_key, {"hour": hour_key, "client": 0, "admin": 0}
            )
            bucket[_extract_request_type(row)] += 1
        hourly_stats = [hourly_map[key] for key in sorted(hourly_map.keys())]

        endpoint_filtered = [
            r
            for r in rows
            if periods.get(endpoint_range, periods["week7"])(r["date_key"])
        ]
        endpoint_summary: dict[tuple[str, str], dict] = {}
        for row in endpoint_filtered:
            key = (str(row["endpoint"] or ""), str(row["method"] or "GET"))
            bucket = endpoint_summary.setdefault(
                key,
                {
                    "endpoint": key[0],
                    "method": key[1],
                    "count": 0,
                    "avgResponseTime": 0.0,
                    "responseSum": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["responseSum"] += float(row["response_time"] or 0)
        top_endpoints = sorted(
            endpoint_summary.values(), key=lambda item: item["count"], reverse=True
        )[:50]
        for item in top_endpoints:
            item["avgResponseTime"] = (
                round(item["responseSum"] / item["count"], 1) if item["count"] else 0
            )
            del item["responseSum"]

        error_distribution_map: dict[int, int] = {}
        for row in endpoint_filtered:
            status_code = int(row["status_code"] or 0)
            if status_code >= 400:
                error_distribution_map[status_code] = (
                    error_distribution_map.get(status_code, 0) + 1
                )
        error_distribution = [
            {"statusCode": status_code, "count": count}
            for status_code, count in sorted(
                error_distribution_map.items(), key=lambda item: item[1], reverse=True
            )
        ]

        return success_response(
            data={
                "admin": admin,
                "client": client,
                "combined": combined,
                "topEndpoints": top_endpoints,
                "hourlyStats": hourly_stats,
                "errorDistribution": error_distribution,
                "endpointRange": endpoint_range,
                "sampleRate": DEFAULT_SAMPLE_RATE,
                "sampling": {
                    "sampledScope": "client.success",
                    "fullCaptureScope": [
                        "admin.*",
                        "*.blocked",
                        "*.client_error",
                        "*.server_error",
                    ],
                },
                "generatedAt": _utc_now_ms(),
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/cleanup")
async def audit_cleanup(days: int = Query(default=30)):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            "DELETE FROM request_logs WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        return success_response(data={"deletedCount": cursor.rowcount})
    except Exception as e:
        return error_response("CLEANUP_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/recent")
async def audit_recent(limit: int = Query(default=20)):
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            f"""SELECT id, created_at, {_request_log_time_expr()} as created_at_utc,
               method, endpoint, status_code, user_id, response_time, error_code, user_agent, request_type
               FROM request_logs ORDER BY {_request_log_time_expr()} DESC LIMIT ?""",
            (min(limit, 50),),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        return success_response(data={"requests": rows, "fromCache": False})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/ip-requests")
async def audit_ip_requests(
    ip: str = Query(...), limit: int = Query(default=50), hours: int = Query(default=24)
):
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        if not ip.strip():
            return error_response("INVALID_PARAMS", "IP parameter is required", 400)

        cutoff_ms = _utc_now_ms() - hours * 60 * 60 * 1000
        cursor = conn.execute(
            f"""SELECT id, created_at, {_request_log_time_expr()} as created_at_utc,
               method, endpoint, status_code, user_id, response_time, error_code, user_agent, request_type
               FROM request_logs WHERE ip = ? ORDER BY {_request_log_time_expr()} DESC LIMIT ?""",
            (ip, min(limit, 100)),
        )
        requests = [dict(r) for r in cursor.fetchall()]

        filtered = []
        for row in requests:
            value = row.get("created_at")
            try:
                timestamp = int(value)
            except Exception:
                timestamp = 0
            if not timestamp or timestamp >= cutoff_ms:
                filtered.append(row)

        total_in_range = len(filtered)
        status_distribution_map: dict[int, int] = {}
        top_endpoints_map: dict[tuple[str, str], dict] = {}
        for row in filtered:
            status_code = int(row.get("status_code") or 0)
            status_distribution_map[status_code] = (
                status_distribution_map.get(status_code, 0) + 1
            )
            key = (str(row.get("endpoint") or ""), str(row.get("method") or "GET"))
            bucket = top_endpoints_map.setdefault(
                key,
                {
                    "endpoint": key[0],
                    "method": key[1],
                    "count": 0,
                    "avg_response_time": 0.0,
                    "sum": 0.0,
                },
            )
            bucket["count"] += 1
            bucket["sum"] += float(row.get("response_time") or 0)

        top_endpoints = sorted(
            top_endpoints_map.values(), key=lambda item: item["count"], reverse=True
        )[:10]
        for item in top_endpoints:
            item["avg_response_time"] = (
                round(item["sum"] / item["count"], 1) if item["count"] else 0
            )
            del item["sum"]

        temp_ban = conn.execute(
            "SELECT ip, reason, added_at, expires_at, total_bans FROM ip_blacklist WHERE ip = ?",
            (ip,),
        ).fetchone()
        perm_ban = conn.execute(
            "SELECT ip, reason, added_at FROM ip_blacklist_permanent WHERE ip = ?",
            (ip,),
        ).fetchone()
        ban_status = "none"
        ban_info = None
        if perm_ban:
            ban_status = "permanent"
            ban_info = {
                "reason": perm_ban["reason"],
                "addedAt": perm_ban["added_at"],
                "addedAtUtc": perm_ban["added_at"],
            }
        elif temp_ban:
            ban_status = "temporary"
            ban_info = {
                "reason": temp_ban["reason"],
                "addedAt": temp_ban["added_at"],
                "addedAtUtc": temp_ban["added_at"],
                "expiresAt": temp_ban["expires_at"],
                "expiresAtUtc": temp_ban["expires_at"],
                "totalBans": temp_ban["total_bans"],
            }

        return success_response(
            data={
                "ip": ip,
                "hours": hours,
                "totalInRange": total_in_range,
                "returnedCount": len(filtered),
                "requests": filtered,
                "statusDistribution": [
                    {"status_code": code, "count": count}
                    for code, count in sorted(
                        status_distribution_map.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                ],
                "topEndpoints": top_endpoints,
                "banStatus": ban_status,
                "banInfo": ban_info,
                "queryTime": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/endpoint-hot-data")
async def endpoint_hot_data():
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT endpoint, method, COUNT(*) as count, AVG(response_time) as avgResponseTime
               FROM request_logs GROUP BY endpoint, method ORDER BY count DESC LIMIT 50"""
        ).fetchall()
        items = [dict(r) for r in rows]
        return success_response(
            data={
                "endpoints": items,
                "endpointCount": len(items),
                "generatedAt": _utc_now_ms(),
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/endpoint-hot-data/flush")
async def flush_endpoint_hot_data():
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT endpoint, method, COUNT(*) as count, AVG(response_time) as avg_response_time
               FROM request_logs GROUP BY endpoint, method ORDER BY count DESC"""
        ).fetchall()
        endpoint_count = len(rows)
        return success_response(
            data={"flushed": endpoint_count > 0, "endpointCount": endpoint_count},
            message="端点热度数据已刷新并写入数据库"
            if endpoint_count > 0
            else "暂无可刷新的端点热度数据",
        )
    except Exception as e:
        return error_response("FLUSH_FAILED", str(e), 500)
    finally:
        conn.close()
