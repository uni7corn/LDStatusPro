"""Client configuration routes (admin + public)."""

from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Request

from app.config import settings
from app.common.utils.response import error_response, success_response

router = APIRouter(tags=["ldsp-config"])

DEFAULT_READING_LEVELS = [
    {"min": 0, "label": "刚起步"},
    {"min": 30, "label": "热身中"},
    {"min": 90, "label": "渐入佳境"},
    {"min": 180, "label": "沉浸阅读"},
    {"min": 300, "label": "深度学习"},
    {"min": 450, "label": "LD达人"},
    {"min": 600, "label": "超级水怪"},
]

DEFAULT_WEBSITE_URL = "https://ldspro.qzz.io/"
ANNOUNCEMENT_TYPES = {"info", "warning", "success"}


def _get_config(conn, key, default):
    import json

    cursor = conn.execute(
        "SELECT value, updated_at FROM system_config WHERE key = ?", (key,)
    )
    row = cursor.fetchone()
    if not row:
        return default, None
    return json.loads(row[0]) if row[0] else default, row[1]


def _set_config(conn, key, value, description=""):
    import json

    now = int(__import__("time").time() * 1000)
    conn.execute(
        """INSERT INTO system_config (key, value, description, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             value = excluded.value,
             updated_at = excluded.updated_at""",
        (key, json.dumps(value), description, now),
    )
    return now


def _validate_reading_levels(levels):
    if not isinstance(levels, list) or len(levels) == 0:
        return {"valid": False, "message": "等级配置必须是非空数组"}
    if len(levels) > 10:
        return {"valid": False, "message": "最多允许 10 个等级"}

    cleaned = []
    for level in levels:
        min_val = level.get("min")
        label = (level.get("label") or "").strip()
        try:
            min_val = float(min_val)
        except (ValueError, TypeError):
            return {"valid": False, "message": "每个等级都必须包含有效的最小值（>= 0）"}
        if min_val < 0:
            return {"valid": False, "message": "每个等级都必须包含有效的最小值（>= 0）"}
        if not label:
            return {"valid": False, "message": "每个等级都必须包含名称"}
        cleaned.append({"min": min_val, "label": label})

    cleaned.sort(key=lambda x: x["min"])
    if cleaned[0]["min"] != 0:
        return {"valid": False, "message": "第一个等级必须从 0 分钟开始"}

    return {"valid": True, "levels": cleaned}


def _parse_website_url(raw_value):
    if isinstance(raw_value, dict):
        return raw_value.get("url", DEFAULT_WEBSITE_URL)
    return DEFAULT_WEBSITE_URL


# ---------- Admin routes ----------


@router.get("/api/admin/config/reading-levels")
async def admin_reading_levels():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        levels, updated_at = _get_config(conn, "reading_levels", DEFAULT_READING_LEVELS)
        return success_response(
            data={
                "levels": levels,
                "updatedAt": updated_at or int(__import__("time").time() * 1000),
            }
        )
    finally:
        conn.close()


@router.put("/api/admin/config/reading-levels")
async def admin_reading_levels_update(request: Request):
    try:
        body = await request.json()
    except Exception:
        return error_response("INVALID_JSON", "无效的 JSON 请求体", 400)
    check = _validate_reading_levels(body.get("levels", []))
    if not check["valid"]:
        return error_response("INVALID_PARAMS", check["message"], 400)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        now = _set_config(
            conn, "reading_levels", check["levels"], "Reading level config"
        )
        conn.commit()
        return success_response(
            data={"levels": check["levels"], "updatedAt": now},
            message="阅读等级更新成功",
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/config/announcement")
async def admin_announcement():
    import time

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        data, updated_at = _get_config(conn, "announcement", None)
        if data is None:
            return success_response(
                data={
                    "enabled": False,
                    "items": [],
                    "updatedAt": int(time.time() * 1000),
                }
            )
        return success_response(data=data)
    finally:
        conn.close()


@router.put("/api/admin/config/announcement")
async def admin_announcement_update(request: Request):
    try:
        body = await request.json()
    except Exception:
        return error_response("INVALID_JSON", "无效的 JSON 请求体", 400)
    if "enabled" not in body or not isinstance(body["enabled"], bool):
        return error_response("INVALID_PARAMS", "enabled 必须是布尔值", 400)

    validated_items = []
    raw_items = body.get("items", []) or []
    for item in raw_items[:5]:
        content = (item.get("content") or "").strip()[:200]
        if not content:
            continue
        item_type = (
            item.get("type") if item.get("type") in ANNOUNCEMENT_TYPES else "info"
        )
        expires_at = None
        if item.get("expiresAt") is not None:
            try:
                ts = float(item["expiresAt"])
                if ts > 0:
                    expires_at = ts
            except (ValueError, TypeError):
                pass
        validated_items.append(
            {"content": content, "type": item_type, "expiresAt": expires_at}
        )

    now = int(__import__("time").time() * 1000)
    announcement = {
        "enabled": body["enabled"],
        "items": validated_items,
        "updatedAt": now,
    }

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        _set_config(conn, "announcement", announcement, "Public announcement config")
        conn.commit()
        return success_response(data=announcement, message="公告更新成功")
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/config/website-url")
async def admin_website_url():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        data, updated_at = _get_config(conn, "website_url", None)
        url = _parse_website_url(data) if data else DEFAULT_WEBSITE_URL
        return success_response(
            data={
                "url": url,
                "updatedAt": updated_at or int(__import__("time").time() * 1000),
            }
        )
    finally:
        conn.close()


@router.put("/api/admin/config/website-url")
async def admin_website_url_update(request: Request):
    try:
        body = await request.json()
    except Exception:
        return error_response("INVALID_JSON", "无效的 JSON 请求体", 400)
    url_value = (body.get("url") or "").strip()
    if not url_value:
        return error_response("INVALID_PARAMS", "url 不能为空", 400)

    try:
        from urllib.parse import urlparse

        result = urlparse(url_value)
        if not result.scheme or not result.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        return error_response("INVALID_URL", "URL 格式无效", 400)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        now = _set_config(
            conn, "website_url", {"url": url_value}, "Official website URL"
        )
        conn.commit()
        return success_response(
            data={"url": url_value, "updatedAt": now},
            message="官网地址更新成功",
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/config/max-daily-reading")
async def admin_max_daily_reading():
    import time

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        data, updated_at = _get_config(conn, "max_daily_reading", None)
        max_minutes = (
            data.get("maxMinutes") if isinstance(data, dict) else None
        ) or 1290
        now = int(time.time() * 1000)
        loaded_at = updated_at or now
        cache_age = max(0, now - loaded_at)
        cache_ttl = 12 * 60 * 60 * 1000
        return success_response(
            data={
                "maxMinutes": max_minutes,
                "updatedAt": loaded_at,
                "cacheInfo": {
                    "loadedAt": loaded_at,
                    "cacheAge": round(cache_age / 1000),
                    "cacheTTL": round(cache_ttl / 1000),
                    "expiresIn": max(0, round((cache_ttl - cache_age) / 1000)),
                },
            }
        )
    finally:
        conn.close()


@router.put("/api/admin/config/max-daily-reading")
async def admin_max_daily_reading_update(request: Request):
    try:
        body = await request.json()
    except Exception:
        return error_response("INVALID_JSON", "无效的 JSON 请求体", 400)
    max_minutes = float(body.get("maxMinutes", 0))
    if max_minutes < 60 or max_minutes > 1440:
        return error_response(
            "INVALID_PARAMS", "maxMinutes 必须在 60 到 1440 之间", 400
        )

    rounded = round(max_minutes)
    now = int(__import__("time").time() * 1000)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        _set_config(
            conn,
            "max_daily_reading",
            {"maxMinutes": rounded},
            "Max daily reading minutes",
        )
        conn.commit()
        return success_response(
            data={"maxMinutes": rounded, "updatedAt": now},
            message="每日阅读时长上限更新成功",
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/config/max-daily-reading/refresh")
async def admin_max_daily_reading_refresh():
    import time

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        data, updated_at = _get_config(conn, "max_daily_reading", None)
        max_minutes = (
            data.get("maxMinutes") if isinstance(data, dict) else None
        ) or 1290
        now = int(time.time() * 1000)
        return success_response(
            data={
                "message": "缓存刷新成功",
                "maxMinutes": max_minutes,
                "updatedAt": updated_at or now,
                "previousValue": max_minutes,
                "previousLoadedAt": updated_at,
                "newLoadedAt": now,
            }
        )
    finally:
        conn.close()


# ---------- Public routes ----------


@router.get("/api/config/reading-levels")
async def public_reading_levels():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        levels, updated_at = _get_config(conn, "reading_levels", DEFAULT_READING_LEVELS)
        return success_response(
            data={
                "levels": levels,
                "updatedAt": updated_at or int(__import__("time").time() * 1000),
                "fromCache": False,
            }
        )
    finally:
        conn.close()


@router.get("/api/config/announcement")
async def public_announcement():
    import time

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        data, updated_at = _get_config(conn, "announcement", None)
        if data is None:
            data = {"enabled": False, "items": []}

        enabled = bool(data.get("enabled", False))
        items = data.get("items", []) or []
        now = int(time.time() * 1000)
        active_items = [
            item
            for item in items
            if not item.get("expiresAt") or float(item["expiresAt"]) > now
        ]

        return success_response(
            data={
                "enabled": enabled,
                "items": active_items,
                "updatedAt": updated_at or now,
                "fromCache": False,
            }
        )
    finally:
        conn.close()


@router.get("/api/config/website-url")
async def public_website_url():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        data, updated_at = _get_config(conn, "website_url", None)
        url = _parse_website_url(data) if data else DEFAULT_WEBSITE_URL
        return success_response(
            data={
                "url": url,
                "updatedAt": updated_at or int(__import__("time").time() * 1000),
                "fromCache": False,
            }
        )
    finally:
        conn.close()


# Compatibility route for tests / old clients
@router.get("/api/config/reading-rules")
async def reading_rules_config():
    return success_response(data={"rules": []})
