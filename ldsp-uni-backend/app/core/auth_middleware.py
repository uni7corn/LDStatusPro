"""Populate request.state.user from Bearer JWT when present."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.core.auth import decode_access_token


class AuthStateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = {}

        admin_key = request.headers.get("X-Admin-Key", "")
        if admin_key and admin_key == settings.super_admin_password:
            request.state.user = {
                "user_id": settings.super_admin_username,
                "username": settings.super_admin_username,
                "name": "超级管理员",
                "site": "linux.do",
                "is_super_admin": True,
                "permissions": {"*": {"view": True, "operate": True}},
            }
            response = await call_next(request)
            return response

        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            payload = decode_access_token(token)
            if payload:
                request.state.user = {
                    "user_id": str(payload.get("sub") or payload.get("user_id") or ""),
                    "username": payload.get("username"),
                    "name": payload.get("name"),
                    "animated_avatar": payload.get("animated_avatar"),
                    "avatar_template": payload.get("avatar_template"),
                    "avatar_url": payload.get("avatar_url"),
                    "trust_level": payload.get("trust_level", 0),
                    "site": payload.get("site", "linux.do"),
                    "is_super_admin": payload.get("is_super_admin", False),
                    "permissions": payload.get("permissions", {}),
                }

        response = await call_next(request)
        return response
