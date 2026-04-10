"""Sub-admin routes (admin-only)."""

from __future__ import annotations

import json
import sqlite3
import secrets
import time
from fastapi import APIRouter, Request

from app.config import settings
from app.common.utils.response import error_response, success_response
from app.core.auth import hash_password

router = APIRouter(tags=["ldsp-sub-admins"])

PERMISSION_MODULES = {
    "dashboard": {"label": "Dashboard", "icon": "dashboard"},
    "users": {"label": "User Management", "icon": "users"},
    "tickets": {"label": "Ticket Management", "icon": "tickets"},
    "suspicious": {"label": "Suspicious Data", "icon": "alert"},
    "client_settings": {"label": "Client Settings", "icon": "settings"},
    "website": {"label": "Website Management", "icon": "website"},
    "backups": {"label": "Backup Management", "icon": "backup"},
    "audit": {"label": "Service Audit", "icon": "audit"},
    "tools": {"label": "Tools", "icon": "tools"},
    "sub_admins": {"label": "Sub Admins", "icon": "sub_admin"},
}


def _parse_positive_int(value, fallback=0) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (ValueError, TypeError):
        return fallback


def _normalize_permissions(permissions) -> dict:
    if not isinstance(permissions, dict):
        raise ValueError("权限配置必须是对象")

    validated = {}
    for module in PERMISSION_MODULES.keys():
        if module == "sub_admins":
            validated[module] = {"view": False, "operate": False}
            continue
        perm = permissions.get(module)
        if isinstance(perm, dict):
            view = bool(perm.get("view"))
            operate = bool(perm.get("operate"))
            if operate and not view:
                view = True
            validated[module] = {"view": view, "operate": operate}
        else:
            validated[module] = {"view": False, "operate": False}
    return validated


def _validate_username(username: str) -> bool:
    import re

    return bool(re.fullmatch(r"[a-z0-9_]{3,20}", username))


def _validate_password(password: str) -> bool:
    import re

    return (
        len(password) >= 8
        and bool(re.search(r"[A-Za-z]", password))
        and bool(re.search(r"[0-9]", password))
    )


def _hash_sub_admin_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"{salt}:{hash_password(f'{salt}{password}{salt}')}"


@router.get("/api/admin/sub-admins")
async def sub_admin_list():
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """SELECT id, username, nickname, permissions, is_active, last_login, login_count, created_at, updated_at
               FROM sub_admins ORDER BY created_at DESC"""
        )
        rows = cursor.fetchall()
        admins = [
            {
                "id": r[0],
                "username": r[1],
                "nickname": r[2],
                "permissions": json.loads(r[3]) if r[3] else {},
                "is_active": bool(r[4]),
                "last_login": r[5],
                "login_count": r[6] if len(r) > 6 else 0,
                "created_at": r[7],
                "updated_at": r[8],
                "password_hash": None,
            }
            for r in rows
        ]
        return success_response(
            data={"admins": admins, "total": len(admins), "modules": PERMISSION_MODULES}
        )
    finally:
        conn.close()


@router.post("/api/admin/sub-admins")
async def sub_admin_create(request: Request):
    body = await request.json()
    username = body.get("username", "").strip().lower()
    password = body.get("password", "").strip()
    nickname = body.get("nickname", username)
    permissions = body.get("permissions", {})

    if not username or not password or not nickname:
        return error_response("INVALID_PARAMS", "用户名密码和昵称不能为空", 400)
    if not _validate_username(username):
        return error_response(
            "INVALID_USERNAME", "用户名只能包含小写字母数字和下划线，长度3-20", 400
        )
    if not _validate_password(password):
        return error_response("WEAK_PASSWORD", "密码至少 8 位且需包含字母和数字", 400)

    try:
        valid_permissions = _normalize_permissions(permissions or {})
    except ValueError as e:
        return error_response("INVALID_PERMISSIONS", str(e), 400)

    password_hash = _hash_sub_admin_password(password)
    permissions_json = json.dumps(valid_permissions)
    now = int(time.time() * 1000)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute(
            """INSERT INTO sub_admins (username, password_hash, nickname, permissions, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (username, password_hash, nickname, permissions_json, now, now),
        )
        conn.commit()
        return success_response(
            data={
                "message": "子管理员创建成功",
                "id": cursor.lastrowid,
                "username": username,
                "nickname": nickname,
                "permissions": valid_permissions,
            },
            message="子管理员创建成功",
        )
    except sqlite3.IntegrityError:
        return error_response("USERNAME_EXISTS", "用户名已存在", 400)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/sub-admins/{admin_id}")
async def sub_admin_update(request: Request, admin_id: int):
    aid = _parse_positive_int(admin_id, 0)
    if not aid:
        return error_response("INVALID_PARAMS", "子管理员 ID 无效", 400)

    body = await request.json()
    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute("SELECT id FROM sub_admins WHERE id = ?", (aid,))
        if not cursor.fetchone():
            return error_response("NOT_FOUND", "子管理员不存在", 404)

        updates = []
        params: list = []

        if "nickname" in body:
            nickname = str(body["nickname"] or "").strip()
            if nickname:
                updates.append("nickname = ?")
                params.append(nickname)
        if "password" in body and body["password"]:
            if not _validate_password(body["password"]):
                return error_response(
                    "WEAK_PASSWORD", "密码至少 8 位且需包含字母和数字", 400
                )
            updates.append("password_hash = ?")
            params.append(_hash_sub_admin_password(body["password"]))
        if "permissions" in body:
            try:
                normalized = _normalize_permissions(body["permissions"])
            except ValueError as e:
                return error_response("INVALID_PERMISSIONS", str(e), 400)
            updates.append("permissions = ?")
            params.append(json.dumps(normalized))
        if "is_active" in body:
            updates.append("is_active = ?")
            params.append(1 if body["is_active"] else 0)

        if not updates:
            return error_response("NO_UPDATES", "没有需要更新的内容", 400)

        now = int(time.time() * 1000)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(aid)

        conn.execute(
            f"UPDATE sub_admins SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return success_response(
            data={"message": "子管理员更新成功"}, message="子管理员更新成功"
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/sub-admins/{admin_id}")
async def sub_admin_delete(admin_id: int):
    aid = _parse_positive_int(admin_id, 0)
    if not aid:
        return error_response("INVALID_PARAMS", "子管理员 ID 无效", 400)

    conn = sqlite3.connect(settings.ldsp_database_path)
    try:
        cursor = conn.execute("DELETE FROM sub_admins WHERE id = ?", (aid,))
        conn.commit()
        if cursor.rowcount == 0:
            return error_response("NOT_FOUND", "子管理员不存在", 404)
        return success_response(
            data={"message": "子管理员已删除"}, message="子管理员已删除"
        )
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()
