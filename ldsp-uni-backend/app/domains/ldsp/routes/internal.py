"""Internal compatibility routes aligned with ldsp-backend."""

from __future__ import annotations

import os
import sqlite3

from fastapi import APIRouter, Request

from app.common.utils.response import error_response
from app.config import settings

router = APIRouter(tags=["ldsp-internal"])


def _backend_image_internal_key() -> str:
    return (
        settings.backend_image_internal_key
        or settings.backend_firewall_secret
        or settings.admin_secret
        or ""
    ).strip()


@router.post("/api/internal/users/basic")
async def internal_users_basic(request: Request):
    internal_key = _backend_image_internal_key()
    if not internal_key:
        return error_response(
            "INTERNAL_KEY_MISSING", "服务端未配置图床内部鉴权密钥", 500
        )

    request_key = (request.headers.get("X-Internal-Key") or "").strip()
    if not request_key or request_key != internal_key:
        return error_response("FORBIDDEN", "内部鉴权失败", 403)

    try:
        body = await request.json()
    except Exception:
        body = None

    raw_users = body.get("users") if isinstance(body, dict) else None
    raw_users = raw_users if isinstance(raw_users, list) else []
    if not raw_users:
        return {"users": []}
    if len(raw_users) > 500:
        return error_response("INVALID_PARAMS", "users 最多支持 500 条", 400)

    normalized = []
    dedup = set()
    for item in raw_users:
        try:
            user_id = int(item.get("userId"))
        except Exception:
            continue
        if user_id <= 0:
            continue
        site = str(item.get("site") or "linux.do").strip() or "linux.do"
        dedup_key = f"{site}:{user_id}"
        if dedup_key in dedup:
            continue
        dedup.add(dedup_key)
        normalized.append({"userId": user_id, "site": site})

    if not normalized:
        return {"users": []}

    grouped_by_site: dict[str, list[int]] = {}
    for item in normalized:
        grouped_by_site.setdefault(item["site"], []).append(item["userId"])

    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        user_map: dict[str, dict] = {}
        for site, user_ids in grouped_by_site.items():
            unique_user_ids = list(dict.fromkeys(user_ids))
            chunk_size = 100
            for index in range(0, len(unique_user_ids), chunk_size):
                chunk = unique_user_ids[index : index + chunk_size]
                placeholders = ", ".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT site, user_id, username, name FROM users WHERE site = ? AND user_id IN ({placeholders})",
                    [site, *chunk],
                ).fetchall()
                for row in rows:
                    key = f"{row['site']}:{row['user_id']}"
                    user_map[key] = {
                        "userId": int(row["user_id"]),
                        "site": row["site"] or site,
                        "username": row["username"] or None,
                        "name": row["name"] or None,
                    }

        users = []
        for item in normalized:
            key = f"{item['site']}:{item['userId']}"
            matched = user_map.get(key)
            users.append(
                {
                    "userId": item["userId"],
                    "site": item["site"],
                    "username": matched.get("username") if matched else None,
                    "name": matched.get("name") if matched else None,
                    "exists": bool(matched),
                }
            )

        return {"users": users}
    finally:
        conn.close()
