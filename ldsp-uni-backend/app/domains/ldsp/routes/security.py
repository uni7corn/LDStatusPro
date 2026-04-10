"""Security routes (IP blacklist, honeypot, rate limits, firewall, whitelist)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from app.config import settings
from app.common.utils.response import success_response, error_response

router = APIRouter(prefix="/api/admin", tags=["security"])


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _row_dicts(cursor: sqlite3.Cursor, rows) -> list[dict]:
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def _cf_sync_payload(
    success: bool = False, queued: bool = False, error: str | None = None
) -> dict:
    status = (
        "success"
        if success
        else ("queued" if queued else ("failed" if error else "unknown"))
    )
    return {
        "success": success,
        "queued": queued,
        "status": status,
        "error": error,
        "updatedAt": _now_ms(),
    }


def _parse_flags(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            import json

            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    return [item.strip() for item in text.split(",") if item.strip()]


def _risk_score(record: dict) -> float:
    try:
        return float(record.get("risk_score") or record.get("threat_score") or 0)
    except Exception:
        return 0.0


def _risk_level(record: dict) -> str:
    explicit = str(record.get("risk_level") or "").strip().lower()
    if explicit in ("low", "medium", "high", "critical"):
        return explicit
    score = _risk_score(record)
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _matches_intel_tag(record: dict, intel_tag: str) -> bool:
    mapping = {
        "proxy": "ip_is_proxy",
        "vpn": "ip_is_vpn",
        "tor": "ip_is_tor",
        "relay": "ip_is_relay",
        "anonymous": "ip_is_anonymous",
        "cloud": "ip_is_cloud_provider",
        "threat": "ip_is_threat",
        "abuser": "ip_is_abuser",
        "attacker": "ip_is_attacker",
    }
    column = mapping.get(intel_tag)
    if not column:
        return True
    return str(record.get(column) or "0") in ("1", "true", "True")


def _load_honeypot_records(conn: sqlite3.Connection, days: int) -> list[dict]:
    cursor = conn.execute(
        "SELECT * FROM honeypot_logs ORDER BY COALESCE(recorded_at_utc, recorded_at, created_at) DESC"
    )
    rows = _row_dicts(cursor, cursor.fetchall())
    cutoff = _now_ms() - max(1, days) * 24 * 60 * 60 * 1000
    filtered = []
    for row in rows:
        ts = (
            row.get("recorded_at")
            or row.get("created_at")
            or row.get("recorded_at_utc")
        )
        try:
            timestamp = int(ts)
        except Exception:
            timestamp = _now_ms()
        if timestamp >= cutoff:
            row["risk_score"] = _risk_score(row)
            row["risk_level"] = _risk_level(row)
            filtered.append(row)
    return filtered


# ─── Blacklist ───────────────────────────────────────────────


@router.get("/blacklist")
async def get_blacklist(page: int = Query(default=1), size: int = Query(default=50)):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        offset = (page - 1) * size
        perm_cursor = conn.execute(
            "SELECT * FROM ip_blacklist_permanent ORDER BY COALESCE(added_at, created_at) DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        temporary_cursor = conn.execute(
            "SELECT * FROM ip_blacklist ORDER BY COALESCE(added_at, created_at) DESC LIMIT ? OFFSET ?",
            (size, offset),
        )
        permanent_entries = _row_dicts(perm_cursor, perm_cursor.fetchall())
        temporary_entries = _row_dicts(temporary_cursor, temporary_cursor.fetchall())

        for entry in permanent_entries:
            entry.setdefault(
                "addedAt", entry.get("added_at") or entry.get("created_at")
            )
            entry.setdefault(
                "addedAtUtc",
                entry.get("added_at_utc")
                or entry.get("added_at")
                or entry.get("created_at"),
            )
            entry.setdefault("cfSyncStatus", entry.get("cf_sync_status") or "unknown")
            entry.setdefault("cfSyncError", entry.get("cf_sync_error"))
            entry.setdefault("cfRuleId", entry.get("cf_rule_id"))
            entry.setdefault("cfSyncUpdatedAt", entry.get("cf_sync_updated_at"))
            entry.setdefault(
                "cfSyncUpdatedAtUtc",
                entry.get("cf_sync_updated_at_utc") or entry.get("cf_sync_updated_at"),
            )
        for entry in temporary_entries:
            entry.setdefault(
                "addedAt", entry.get("added_at") or entry.get("created_at")
            )
            entry.setdefault(
                "addedAtUtc",
                entry.get("added_at_utc")
                or entry.get("added_at")
                or entry.get("created_at"),
            )
            entry.setdefault("expiresAt", entry.get("expires_at"))
            entry.setdefault(
                "expiresAtUtc", entry.get("expires_at_utc") or entry.get("expires_at")
            )
            entry.setdefault("totalBans", entry.get("total_bans") or 1)
            entry.setdefault("cfSyncStatus", entry.get("cf_sync_status") or "unknown")
            entry.setdefault("cfSyncError", entry.get("cf_sync_error"))
            entry.setdefault("cfRuleId", entry.get("cf_rule_id"))
            entry.setdefault("cfSyncUpdatedAt", entry.get("cf_sync_updated_at"))
            entry.setdefault(
                "cfSyncUpdatedAtUtc",
                entry.get("cf_sync_updated_at_utc") or entry.get("cf_sync_updated_at"),
            )

        temp_count = conn.execute("SELECT COUNT(*) FROM ip_blacklist").fetchone()[0]
        perm_count = conn.execute(
            "SELECT COUNT(*) FROM ip_blacklist_permanent"
        ).fetchone()[0]

        def get_config_value(key: str, fallback: int) -> int:
            row = conn.execute(
                "SELECT value FROM system_config WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return fallback
            try:
                return int(row[0])
            except Exception:
                return fallback

        config = {
            "violationThreshold": get_config_value("security_violation_threshold", 5),
            "violationWindowMs": get_config_value(
                "security_violation_window_ms", 10 * 60 * 1000
            ),
            "banDurationMs": get_config_value(
                "security_ban_duration_ms", 30 * 60 * 1000
            ),
        }

        return success_response(
            data={
                "temporary": {"count": temp_count, "entries": temporary_entries},
                "permanent": {"count": perm_count, "entries": permanent_entries},
                "config": config,
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/blacklist")
async def add_blacklist(request: Request):
    body = await request.json()
    ip = body.get("ip", "")
    reason = body.get("reason", "manual_ban")
    duration = body.get("duration", 30)
    permanent = bool(body.get("permanent"))
    notes = body.get("notes")
    if not ip:
        return error_response("INVALID_IP", "Invalid IP address format", 400)
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        now = _now_ms()
        firewall_sync = _cf_sync_payload(queued=True)
        if permanent:
            conn.execute(
                """INSERT OR REPLACE INTO ip_blacklist_permanent (ip, reason, added_at, created_by, notes, cf_sync_status, cf_sync_updated_at)
                   VALUES (?, ?, ?, 'admin', ?, ?, ?)""",
                (
                    ip,
                    reason,
                    now,
                    notes,
                    firewall_sync["status"],
                    firewall_sync["updatedAt"],
                ),
            )
        else:
            expires_at = now + int(duration) * 60 * 1000
            existing = conn.execute(
                "SELECT total_bans FROM ip_blacklist WHERE ip = ?", (ip,)
            ).fetchone()
            total_bans = (existing[0] if existing and existing[0] else 0) + 1
            conn.execute(
                """INSERT OR REPLACE INTO ip_blacklist (ip, reason, expires_at, added_at, total_bans, notes, created_by, cf_sync_status, cf_sync_updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'admin', ?, ?)""",
                (
                    ip,
                    reason,
                    expires_at,
                    now,
                    total_bans,
                    notes,
                    firewall_sync["status"],
                    firewall_sync["updatedAt"],
                ),
            )
        conn.commit()
        return success_response(
            data={
                "permanent": permanent,
                "totalBans": None if permanent else total_bans,
                "firewallSync": firewall_sync,
            },
            message=f"IP {ip} 已加入{'永久' if permanent else '临时'}黑名单",
        )
    except Exception as e:
        return error_response("BAN_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/blacklist/{ip}")
async def remove_blacklist(ip: str):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.execute("DELETE FROM ip_blacklist WHERE ip = ?", (ip,))
        conn.commit()
        return success_response(
            data={
                "firewallSync": _cf_sync_payload(queued=True),
                "unbanHistoryUpdated": 0,
            },
            message=f"IP {ip} 已从临时黑名单移除",
        )
    except Exception as e:
        return error_response("UNBAN_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/blacklist/permanent/{ip}")
async def remove_permanent_blacklist(ip: str):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.execute("DELETE FROM ip_blacklist_permanent WHERE ip = ?", (ip,))
        conn.commit()
        return success_response(
            data={
                "firewallSync": _cf_sync_payload(queued=True),
                "unbanHistoryUpdated": 0,
            },
            message=f"IP {ip} 已从永久黑名单移除",
        )
    except Exception as e:
        return error_response("UNBAN_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/blacklist/{ip}/detail")
async def blacklist_detail(ip: str):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ip_blacklist WHERE ip = ?", (ip,)).fetchone()
        perm = conn.execute(
            "SELECT * FROM ip_blacklist_permanent WHERE ip = ?", (ip,)
        ).fetchone()
        history = conn.execute(
            "SELECT * FROM ip_ban_history WHERE ip = ? ORDER BY COALESCE(banned_at, created_at) DESC LIMIT 50",
            (ip,),
        ).fetchall()
        violations = conn.execute(
            "SELECT violation_time as time, violation_time_utc as time_utc, endpoint FROM ip_violations WHERE ip = ? ORDER BY COALESCE(violation_time_utc, violation_time) DESC LIMIT 50",
            (ip,),
        ).fetchall()
        total_bans = conn.execute(
            "SELECT COUNT(*) FROM ip_ban_history WHERE ip = ?", (ip,)
        ).fetchone()[0]
        current_status = "permanent" if perm else ("temporary" if row else "none")
        return success_response(
            data={
                "ip": ip,
                "currentStatus": current_status,
                "totalBans": total_bans
                or (row["total_bans"] if row and "total_bans" in row.keys() else 0),
                "currentBan": dict(row) if row else None,
                "permanentBan": dict(perm) if perm else None,
                "banHistory": [dict(item) for item in history],
                "violations": {
                    "total": len(violations),
                    "records": [dict(item) for item in violations],
                },
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


# ─── Security Config & Policies ──────────────────────────────


@router.get("/security/config")
async def security_config():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            "SELECT key, value FROM system_config WHERE key LIKE 'security_%' OR key LIKE 'firewall_%'"
        )
        raw = {r[0]: r[1] for r in cursor.fetchall()}
        config = {
            "level": raw.get("security_level", "custom"),
            "description": raw.get("security_description", ""),
            "rateLimitConfig": {
                "public": {
                    "windowMs": int(raw.get("security_public_window_ms", 60000)),
                    "maxTotalRequests": int(
                        raw.get("security_public_max_total_requests", 60)
                    ),
                    "defaultEndpointLimit": int(
                        raw.get("security_public_default_endpoint_limit", 15)
                    ),
                    "twoStrikeBanHours": int(
                        raw.get("security_public_two_strike_ban_hours", 3)
                    ),
                    "violationWindowMs": int(
                        raw.get("security_violation_window_ms", 10 * 60 * 1000)
                    ),
                    "endpointLimits": {},
                },
                "user": {
                    "windowMs": int(raw.get("security_user_window_ms", 60000)),
                    "authenticated": {
                        "maxRequests": int(
                            raw.get("security_user_authenticated_max_requests", 90)
                        ),
                        "maxPerEndpoint": int(
                            raw.get("security_user_authenticated_max_per_endpoint", 40)
                        ),
                    },
                    "unauthDetection": {"thresholds": []},
                },
                "admin": {
                    "enabled": str(raw.get("security_admin_enabled", "0")).lower()
                    in ("1", "true", "yes")
                },
            },
            "whitelist": {"ips": []},
        }
        return success_response(data=config)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/security/policies")
async def security_policies():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        row = conn.execute(
            "SELECT value FROM system_config WHERE key = 'policy_config'"
        ).fetchone()
        if row and row[0]:
            import json

            return success_response(data=json.loads(row[0]))
        return success_response(
            data={
                "version": 1,
                "updatedAt": _now_ms(),
                "publicSettings": {
                    "windowMs": 60000,
                    "maxTotalRequests": 60,
                    "defaultEndpointLimit": 15,
                    "twoStrikeWindowMs": 10 * 60 * 1000,
                    "twoStrikeBanHours": 3,
                },
                "userSettings": {
                    "windowMs": 60000,
                    "authenticated": {
                        "maxRequests": 90,
                        "maxPerEndpoint": 40,
                        "banOnExceed": False,
                    },
                },
                "publicPolicies": [],
                "userPolicies": [],
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/security/policies")
async def update_security_policies(request: Request):
    body = await request.json()
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        import json

        conn.execute(
            """INSERT INTO system_config (key, value) VALUES ('policy_config', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (json.dumps(body, ensure_ascii=False),),
        )
        conn.commit()
        return success_response(
            data={"message": "安全策略已更新"}, message="安全策略已更新"
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/security/policies/reset")
async def reset_security_policies():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.execute("DELETE FROM system_config WHERE key = 'policy_config'")
        conn.commit()
        return success_response(
            data={"message": "安全策略已重置为默认值"}, message="安全策略已重置为默认值"
        )
    except Exception as e:
        return error_response("RESET_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/security/level")
async def set_security_level(request: Request):
    body = await request.json()
    level = body.get("level", 1)
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.execute(
            """INSERT INTO system_config (key, value) VALUES ('security_level', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (str(level),),
        )
        conn.commit()
        return success_response(data={"level": level})
    except Exception as e:
        return error_response("SECURITY_LEVEL_ERROR", str(e), 500)
    finally:
        conn.close()


# ─── Whitelist ───────────────────────────────────────────────


@router.get("/security/whitelist")
async def get_whitelist():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute("SELECT * FROM ip_whitelist ORDER BY created_at DESC")
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return success_response(data={"items": rows, "ips": rows})
    except Exception as e:
        return error_response("WHITELIST_QUERY_ERROR", str(e), 500)
    finally:
        conn.close()


@router.post("/security/whitelist")
async def add_whitelist(request: Request):
    body = await request.json()
    ip = body.get("ip", "")
    note = body.get("note", "")
    if not ip:
        return error_response("MISSING_IP", "IP 地址不能为空", 400)
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            """INSERT OR REPLACE INTO ip_whitelist (ip, note, created_at)
               VALUES (?, ?, ?)""",
            (ip, note, now),
        )
        conn.commit()
        return success_response(data={"message": f"IP {ip} 已加入白名单"})
    except Exception as e:
        return error_response("WHITELIST_ADD_ERROR", str(e), 500)
    finally:
        conn.close()


@router.delete("/security/whitelist/{ip}")
async def remove_whitelist(ip: str):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.execute("DELETE FROM ip_whitelist WHERE ip = ?", (ip,))
        conn.commit()
        return success_response(data={"message": f"IP {ip} 已从白名单移除"})
    except Exception as e:
        return error_response("WHITELIST_REMOVE_ERROR", str(e), 500)
    finally:
        conn.close()


@router.post("/security/whitelist/sync-cf")
async def sync_cloudflare_whitelist():
    return success_response(
        data={"message": "Cloudflare 白名单同步已触发", "synced": 0},
        message="Cloudflare 白名单同步已触发",
    )


# ─── Honeypot ────────────────────────────────────────────────


@router.get("/honeypot/stats")
async def honeypot_stats(days: int = Query(default=7)):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.row_factory = sqlite3.Row
        records = _load_honeypot_records(conn, days)
        total = len(records)
        unique_ips = len({r.get("ip") for r in records if r.get("ip")})
        countries = len({r.get("country") for r in records if r.get("country")})
        unique_asns = len({r.get("asn") for r in records if r.get("asn")})
        avg_threat = (
            round(sum(float(r.get("threat_score") or 0) for r in records) / total, 1)
            if total
            else 0
        )
        avg_risk = (
            round(sum(float(r.get("risk_score") or 0) for r in records) / total, 1)
            if total
            else 0
        )
        high_risk_records = sum(
            1 for r in records if r.get("risk_level") in ("high", "critical")
        )
        critical_risk_records = sum(
            1 for r in records if r.get("risk_level") == "critical"
        )

        def grouped(key: str, *, unique_ip: bool = False, avg_risk_field: bool = False):
            bucket_map = {}
            for record in records:
                value = record.get(key)
                if value in (None, ""):
                    continue
                bucket = bucket_map.setdefault(
                    value, {"value": value, "count": 0, "ips": set(), "risk": 0.0}
                )
                bucket["count"] += 1
                bucket["ips"].add(record.get("ip"))
                bucket["risk"] += float(record.get("risk_score") or 0)
            items = []
            for value, bucket in bucket_map.items():
                item = {key: value, "count": bucket["count"]}
                if unique_ip:
                    item["unique_ips"] = len({ip for ip in bucket["ips"] if ip})
                if avg_risk_field:
                    item["avg_risk_score"] = (
                        round(bucket["risk"] / bucket["count"], 1)
                        if bucket["count"]
                        else 0
                    )
                items.append(item)
            return sorted(items, key=lambda item: item["count"], reverse=True)

        by_country = grouped("country", unique_ip=True)[:20]
        asn_map = {}
        for record in records:
            asn = record.get("asn")
            if not asn:
                continue
            bucket = asn_map.setdefault(
                asn,
                {"asn": asn, "as_org": record.get("as_org"), "count": 0, "ips": set()},
            )
            bucket["count"] += 1
            bucket["ips"].add(record.get("ip"))
        by_asn = []
        for item in asn_map.values():
            item["unique_ips"] = len({ip for ip in item["ips"] if ip})
            del item["ips"]
            by_asn.append(item)
        by_asn.sort(key=lambda item: item["count"], reverse=True)

        by_reason = grouped("reason", avg_risk_field=True)[:20]
        by_risk_level = grouped("risk_level")
        by_endpoint = grouped("endpoint")[:20]

        flag_counter = {}
        for record in records:
            for flag in _parse_flags(record.get("suspicious_flags")):
                flag_counter[flag] = flag_counter.get(flag, 0) + 1
        suspicious_flags = [
            {"flag": flag, "count": count}
            for flag, count in sorted(
                flag_counter.items(), key=lambda item: item[1], reverse=True
            )
        ]

        ip_map = {}
        for record in records:
            ip = record.get("ip")
            if not ip:
                continue
            bucket = ip_map.setdefault(
                ip,
                {
                    "ip": ip,
                    "country": record.get("country"),
                    "city": record.get("city"),
                    "network_type": record.get("network_type"),
                    "asn": record.get("asn"),
                    "as_org": record.get("as_org"),
                    "request_count": 0,
                    "max_risk_score": 0.0,
                    "max_threat_score": 0.0,
                    "first_seen": record.get("recorded_at") or record.get("created_at"),
                    "first_seen_utc": record.get("recorded_at_utc")
                    or record.get("recorded_at"),
                    "last_seen": record.get("recorded_at") or record.get("created_at"),
                    "last_seen_utc": record.get("recorded_at_utc")
                    or record.get("recorded_at"),
                    "high_risk_hits": 0,
                },
            )
            bucket["request_count"] += 1
            bucket["max_risk_score"] = max(
                bucket["max_risk_score"], float(record.get("risk_score") or 0)
            )
            bucket["max_threat_score"] = max(
                bucket["max_threat_score"], float(record.get("threat_score") or 0)
            )
            bucket["last_seen"] = (
                record.get("recorded_at")
                or record.get("created_at")
                or bucket["last_seen"]
            )
            bucket["last_seen_utc"] = (
                record.get("recorded_at_utc")
                or record.get("recorded_at")
                or bucket["last_seen_utc"]
            )
            if record.get("risk_level") in ("high", "critical"):
                bucket["high_risk_hits"] += 1
        top_ips = sorted(
            ip_map.values(), key=lambda item: item["request_count"], reverse=True
        )[:20]
        top_risk_ips = sorted(
            ip_map.values(),
            key=lambda item: (
                item["max_risk_score"],
                item["high_risk_hits"],
                item["request_count"],
            ),
            reverse=True,
        )[:20]

        daily_map = {}
        for record in records:
            try:
                date_key = datetime.fromtimestamp(
                    int(record.get("recorded_at") or _now_ms()) / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            except Exception:
                date_key = _today_str()
            bucket = daily_map.setdefault(
                date_key,
                {
                    "date": date_key,
                    "total_count": 0,
                    "high_risk_count": 0,
                    "ips": set(),
                },
            )
            bucket["total_count"] += 1
            if record.get("risk_level") in ("high", "critical"):
                bucket["high_risk_count"] += 1
            bucket["ips"].add(record.get("ip"))
        trends_daily = []
        for item in sorted(daily_map.values(), key=lambda value: value["date"]):
            trends_daily.append(
                {
                    "date": item["date"],
                    "total_count": item["total_count"],
                    "high_risk_count": item["high_risk_count"],
                    "unique_ips": len({ip for ip in item["ips"] if ip}),
                }
            )

        ip_intel = {
            "proxy_count": sum(
                1
                for r in records
                if str(r.get("ip_is_proxy") or "0") in ("1", "true", "True")
            ),
            "vpn_count": sum(
                1
                for r in records
                if str(r.get("ip_is_vpn") or "0") in ("1", "true", "True")
            ),
            "tor_count": sum(
                1
                for r in records
                if str(r.get("ip_is_tor") or "0") in ("1", "true", "True")
            ),
            "relay_count": sum(
                1
                for r in records
                if str(r.get("ip_is_relay") or "0") in ("1", "true", "True")
            ),
            "anonymous_count": sum(
                1
                for r in records
                if str(r.get("ip_is_anonymous") or "0") in ("1", "true", "True")
            ),
            "cloud_provider_count": sum(
                1
                for r in records
                if str(r.get("ip_is_cloud_provider") or "0") in ("1", "true", "True")
            ),
            "threat_count": sum(
                1
                for r in records
                if str(r.get("ip_is_threat") or "0") in ("1", "true", "True")
            ),
            "abuser_count": sum(
                1
                for r in records
                if str(r.get("ip_is_abuser") or "0") in ("1", "true", "True")
            ),
            "attacker_count": sum(
                1
                for r in records
                if str(r.get("ip_is_attacker") or "0") in ("1", "true", "True")
            ),
            "networkTypeDistribution": grouped("network_type")[:10],
        }

        return success_response(
            data={
                "overall": {
                    "total_records": total,
                    "unique_ips": unique_ips,
                    "countries": countries,
                    "unique_asns": unique_asns,
                    "avg_threat_score": avg_threat,
                    "avg_risk_score": avg_risk,
                    "high_risk_records": high_risk_records,
                    "critical_risk_records": critical_risk_records,
                },
                "byCountry": by_country,
                "byASN": by_asn[:20],
                "byReason": by_reason,
                "byRiskLevel": by_risk_level,
                "byEndpoint": by_endpoint,
                "suspiciousFlags": suspicious_flags,
                "topIPs": top_ips,
                "topRiskIPs": top_risk_ips,
                "trends": {"daily": trends_daily[-30:]},
                "ipIntel": ip_intel,
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/honeypot/ip/{ip}")
async def honeypot_ip_detail(ip: str, limit: int = Query(default=50)):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM honeypot_logs WHERE ip = ? ORDER BY COALESCE(recorded_at_utc, recorded_at, created_at) DESC LIMIT ?",
            (ip, min(limit, 200)),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            row["risk_score"] = _risk_score(row)
            row["risk_level"] = _risk_level(row)
        by_reason = {}
        for row in rows:
            reason = row.get("reason") or "unknown"
            by_reason[reason] = by_reason.get(reason, 0) + 1
        summary = {
            "total_records": len(rows),
            "max_risk_score": max(
                [float(r.get("risk_score") or 0) for r in rows], default=0
            ),
            "first_seen_utc": rows[-1].get("recorded_at_utc") if rows else None,
            "last_seen_utc": rows[0].get("recorded_at_utc") if rows else None,
            "byReason": [
                {"reason": reason, "count": count}
                for reason, count in sorted(
                    by_reason.items(), key=lambda item: item[1], reverse=True
                )
            ],
        }
        return success_response(data={"ip": ip, "records": rows, "summary": summary})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/honeypot/logs")
async def honeypot_logs(
    page: int = Query(default=1),
    size: int = Query(default=50),
    pageSize: int | None = Query(default=None),
    days: int = Query(default=7),
    country: str | None = Query(default=None),
    asn: str | None = Query(default=None),
    ip: str | None = Query(default=None),
    reason: str | None = Query(default=None),
    riskLevel: str | None = Query(default=None),
    flag: str | None = Query(default=None),
    endpoint: str | None = Query(default=None),
    intelTag: str | None = Query(default=None),
    networkType: str | None = Query(default=None),
):
    if pageSize:
        size = pageSize
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        conn.row_factory = sqlite3.Row
        offset = (page - 1) * size
        records = _load_honeypot_records(conn, days)

        def match(record: dict) -> bool:
            if country and str(record.get("country") or "") != str(country):
                return False
            if asn and str(record.get("asn") or "") != str(asn):
                return False
            if (
                ip
                and str(ip).strip().lower() not in str(record.get("ip") or "").lower()
            ):
                return False
            if reason and str(record.get("reason") or "") != str(reason):
                return False
            if riskLevel and _risk_level(record) != str(riskLevel).lower():
                return False
            if flag and flag not in _parse_flags(record.get("suspicious_flags")):
                return False
            if (
                endpoint
                and str(endpoint).strip().lower()
                not in str(record.get("endpoint") or "").lower()
            ):
                return False
            if intelTag and not _matches_intel_tag(record, str(intelTag).lower()):
                return False
            if (
                networkType
                and str(record.get("network_type") or "").lower()
                != str(networkType).lower()
            ):
                return False
            return True

        filtered = [record for record in records if match(record)]
        total = len(filtered)
        page_records = filtered[offset : offset + size]
        total_pages = (total + size - 1) // size if total > 0 else 1
        return success_response(
            data={
                "logs": page_records,
                "items": page_records,
                "total": total,
                "page": page,
                "pageSize": size,
                "totalPages": total_pages,
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


# ─── Rate-limited IPs & IP Info ──────────────────────────────


@router.get("/rate-limited-ips")
async def rate_limited_ips():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """SELECT ip, COUNT(*) as cnt
               FROM request_logs
               GROUP BY ip
               ORDER BY cnt DESC
               LIMIT 100"""
        )
        rows = [{"ip": r[0], "count": r[1]} for r in cursor.fetchall()]
        return success_response(data={"items": rows})
    except Exception as e:
        return error_response("RATE_LIMITED_IPS_ERROR", str(e), 500)
    finally:
        conn.close()


@router.get("/ip-requests/{ip}")
async def ip_requests(ip: str, limit: int = Query(default=100)):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM request_logs WHERE ip = ? ORDER BY created_at DESC LIMIT ?",
            (ip, limit),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return success_response(data={"ip": ip, "logs": rows})
    except Exception as e:
        return error_response("IP_REQUESTS_ERROR", str(e), 500)
    finally:
        conn.close()


@router.get("/ip-violations/{ip}")
async def ip_violations(ip: str):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM ip_violations WHERE ip = ? ORDER BY created_at DESC",
            (ip,),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return success_response(data={"ip": ip, "violations": rows})
    except Exception as e:
        return error_response("IP_VIOLATIONS_ERROR", str(e), 500)
    finally:
        conn.close()


# ─── Ban History & Rate Limit History ────────────────────────


@router.get("/rate-limit-history")
async def rate_limit_history(
    page: int = Query(default=1), size: int = Query(default=50)
):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        offset = (page - 1) * size
        cursor = conn.execute(
            """SELECT ip, endpoint, created_at
               FROM request_logs
               WHERE status_code = 429
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (size, offset),
        )
        total = conn.execute(
            "SELECT COUNT(*) FROM request_logs WHERE status_code = 429"
        ).fetchone()[0]
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception as e:
        return error_response("RATE_LIMIT_HISTORY_ERROR", str(e), 500)
    finally:
        conn.close()


@router.get("/ban-history")
async def ban_history(
    page: int = Query(default=1),
    size: int = Query(default=50),
    ip: str = Query(default=None),
):
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        offset = (page - 1) * size
        if ip:
            cursor = conn.execute(
                "SELECT * FROM ip_ban_history WHERE ip = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (ip, size, offset),
            )
            total_query = conn.execute(
                "SELECT COUNT(*) FROM ip_ban_history WHERE ip = ?", (ip,)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM ip_ban_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (size, offset),
            )
            total_query = conn.execute("SELECT COUNT(*) FROM ip_ban_history")
        total = total_query.fetchone()[0]
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception as e:
        return error_response("BAN_HISTORY_ERROR", str(e), 500)
    finally:
        conn.close()


# ─── Firewall ────────────────────────────────────────────────


@router.get("/firewall/status")
async def firewall_status():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        row = conn.execute(
            "SELECT value FROM system_config WHERE key = 'firewall_enabled'"
        ).fetchone()
        enabled = row is not None and row[0] not in ("0", "false", "")
        temp_count = conn.execute("SELECT COUNT(*) FROM ip_blacklist").fetchone()[0]
        perm_count = conn.execute(
            "SELECT COUNT(*) FROM ip_blacklist_permanent"
        ).fetchone()[0]
        return success_response(
            data={
                "configured": False,
                "enabled": enabled,
                "d1BlacklistCount": temp_count + perm_count,
                "cloudflareRulesCount": 0,
                "rules": [],
                "synced": False,
                "statusPartial": False,
                "statusPartialErrors": [],
                "statusPagesScanned": 0,
                "missingOnCloudflare": temp_count + perm_count,
                "extraOnCloudflare": 0,
                "dbSyncedCount": 0,
                "dbPendingCount": temp_count + perm_count,
                "message": "Cloudflare 未配置，已跳过云端规则同步",
            }
        )
    except Exception as e:
        return error_response("FIREWALL_STATUS_ERROR", str(e), 500)
    finally:
        conn.close()


@router.post("/firewall/sync")
async def firewall_sync():
    return success_response(
        data={"success": False, "errors": 0, "synced": 0},
        message="Cloudflare 未配置，无法执行防火墙同步",
    )


@router.get("/firewall/sync-repair-status")
async def firewall_sync_repair_status():
    temp_count = 0
    perm_count = 0
    try:
        conn = sqlite3.connect(settings.ldsp_database_path)
        temp_count = conn.execute("SELECT COUNT(*) FROM ip_blacklist").fetchone()[0]
        perm_count = conn.execute(
            "SELECT COUNT(*) FROM ip_blacklist_permanent"
        ).fetchone()[0]
        conn.close()
    except Exception:
        pass
    return success_response(
        data={
            "configured": False,
            "activeBlacklistCount": temp_count + perm_count,
            "unresolvedCount": temp_count + perm_count,
            "unresolvedTemporaryCount": temp_count,
            "unresolvedPermanentCount": perm_count,
            "unresolvedByStatus": {
                "pending": temp_count + perm_count,
                "failed": 0,
                "unknown": 0,
                "skipped": 0,
            },
            "recentUnresolved": [],
            "lastRepair": None,
            "message": "自动补偿未启用",
            "error": None,
        }
    )


@router.post("/firewall/sync-ip")
async def firewall_sync_ip(request: Request):
    body = await request.json()
    ip = body.get("ip", "")
    action = body.get("action", "block")
    if not ip:
        return error_response("MISSING_IP", "IP 地址不能为空", 400)
    return success_response(
        data={
            "message": f"IP {ip} 防火墙同步已触发",
            "ip": ip,
            "action": action,
            "firewallSync": _cf_sync_payload(queued=True),
        }
    )
