"""Admin authentication routes aligned with ldsp-backend."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path

from pydantic import BaseModel

from app.config import settings
from app.core.auth import create_access_token, hash_password, verify_password
from app.common.utils.response import error_response, success_response

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/admin/auth", tags=["auth"])

# In-memory password store for initial setup (migrate to DB later)
_ADMIN_PASSWORD_FILE = Path("./data/_admin_password.hash")


def _get_super_admin_hash() -> str:
    if _ADMIN_PASSWORD_FILE.exists():
        return _ADMIN_PASSWORD_FILE.read_text().strip()
    # First time: hash the env default
    h = hash_password(settings.super_admin_password)
    _ADMIN_PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ADMIN_PASSWORD_FILE.write_text(h)
    return h


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    # Super admin check
    if req.username == settings.super_admin_username:
        if not verify_password(req.password, _get_super_admin_hash()):
            return error_response("AUTH_FAILED", "用户名或密码错误", 401)
        token = create_access_token(
            {
                "sub": req.username,
                "username": req.username,
                "nickname": "Super Admin",
                "id": 0,
                "is_super_admin": True,
                "permissions": {"*": {"view": True, "operate": True}},
            }
        )
        return success_response(
            data={
                "id": 0,
                "username": req.username,
                "nickname": "Super Admin",
                "permissions": {"*": {"view": True, "operate": True}},
                "token": token,
                "is_super_admin": True,
            }
        )

    # Sub-admin: query ldsp DB
    try:
        conn = sqlite3.connect(settings.ldsp_database_path)
        cursor = conn.execute(
            "SELECT id, username, nickname, password_hash, permissions, is_active FROM sub_admins WHERE username = ?",
            (req.username,),
        )
        row = cursor.fetchone()
        conn.close()
    except Exception:
        return error_response("DATABASE_ERROR", "数据库查询失败", 500)

    if row is None:
        return error_response("AUTH_FAILED", "用户名或密码错误", 401)

    admin_id, username, nickname, password_hash, permissions_json, is_active = row
    if not is_active:
        return error_response("ACCOUNT_DISABLED", "账号已禁用", 403)
    if not verify_password(req.password, password_hash):
        return error_response("AUTH_FAILED", "用户名或密码错误", 401)

    permissions = json.loads(permissions_json) if permissions_json else {}
    token = create_access_token(
        {
            "id": admin_id,
            "sub": username,
            "username": username,
            "nickname": nickname,
            "is_super_admin": False,
            "permissions": permissions,
        }
    )
    return success_response(
        data={
            "id": admin_id,
            "username": username,
            "nickname": nickname,
            "permissions": permissions,
            "token": token,
            "is_super_admin": False,
        }
    )


@router.get("/me")
async def get_me(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        return error_response("UNAUTHORIZED", "未登录", 401)
    if user.get("is_super_admin"):
        return success_response(
            data={
                "type": "super",
                "nickname": "Super Admin",
                "permissions": None,
            }
        )

    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, username, nickname, permissions, is_active, last_login, created_at FROM sub_admins WHERE id = ?",
            (user.get("id"),),
        ).fetchone()
        if not row or not row["is_active"]:
            return error_response("NOT_FOUND", "账号不存在或已被禁用", 404)
        permissions = json.loads(row["permissions"]) if row["permissions"] else {}
        return success_response(
            data={
                "type": "sub",
                "id": row["id"],
                "username": row["username"],
                "nickname": row["nickname"],
                "permissions": permissions,
                "lastLogin": row["last_login"],
                "createdAt": row["created_at"],
            }
        )
    finally:
        conn.close()
