"""Image AI unified capability config routes.

The actual image moderation execution remains in the legacy backend for now.
This module only unifies configuration management inside ldsp-uni-backend.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.common.utils.response import success_response, error_response
from app.config import settings
from app.core.auth import get_current_user
from app.domains.store.services.ai_capability_service import (
    AICapabilityService,
    CAPABILITY_IMAGE_REVIEW,
)

router = APIRouter(tags=["store-image-ai-capability"])


def _internal_token() -> str:
    return (
        settings.store_internal_token
        or settings.gateway_internal_token
        or settings.admin_secret
        or ""
    ).strip()


def _check_internal_auth(request: Request):
    expected = _internal_token()
    if not expected:
        return error_response("INTERNAL_KEY_MISSING", "服务端未配置内部运行 token", 500)
    actual = (
        request.headers.get("X-Internal-Key")
        or request.headers.get("X-Internal-Token")
        or ""
    ).strip()
    if actual != expected:
        return error_response("FORBIDDEN", "内部鉴权失败", 403)
    return None


def _db() -> sqlite3.Connection:
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


class ImageAgentConfigPayload(BaseModel):
    enabled: int | bool = 0
    apiConfigId: int | None = None
    rejectThreshold: float = 0.75
    promptTemplate: str = ""


class ImageAgentTestPayload(BaseModel):
    enabled: int | bool = 0
    apiConfigId: int | None = None
    rejectThreshold: float = 0.75
    promptTemplate: str = ""
    imageUrl: str = ""
    filename: str = ""
    userId: str = ""
    userSite: str = ""
    username: str = ""


def _resolve_image_capability() -> dict:
    service = AICapabilityService()
    service.ensure_ready()
    resolved = service.resolve_capability(CAPABILITY_IMAGE_REVIEW) or {}
    capability = resolved.get("capability") or {}
    runtime_config = capability.get("runtime_config_json") or {}
    review_criteria = capability.get("review_criteria_json") or {}
    reject_threshold = (
        review_criteria.get("rejectThreshold")
        or review_criteria.get("reject_threshold")
        or runtime_config.get("rejectThreshold")
        or 0.75
    )
    return {
        "enabled": 1 if capability.get("enabled") else 0,
        "apiConfigId": capability.get("provider_config_id"),
        "rejectThreshold": float(reject_threshold or 0.75),
        "promptTemplate": capability.get("prompt_template") or "",
        "providerType": (resolved.get("primary") or {}).get("provider_type")
        or "openai_compatible",
        "gatewayRoute": (resolved.get("primary") or {}).get("gateway_route") or "",
        "gatewayWorkspace": (resolved.get("primary") or {}).get("gateway_workspace")
        or "",
        "provider": resolved.get("primary") or None,
        "capability": capability,
    }


@router.get("/api/admin/image/ai-agent-config")
async def get_image_ai_agent_config(user: dict = Depends(get_current_user)):
    return success_response(data=_resolve_image_capability())


@router.put("/api/admin/image/ai-agent-config")
async def update_image_ai_agent_config(
    payload: ImageAgentConfigPayload,
    user: dict = Depends(get_current_user),
):
    service = AICapabilityService()
    service.ensure_ready()
    conn = _db()
    try:
        now = __import__("time").time_ns() // 1_000_000
        conn.execute(
            """UPDATE ai_capability_configs SET
                name = ?,
                provider_config_id = ?,
                prompt_template = ?,
                review_criteria_json = ?,
                runtime_config_json = ?,
                enabled = ?,
                updated_at = ?
               WHERE capability_key = ?""",
            (
                "图片审核",
                payload.apiConfigId,
                payload.promptTemplate,
                json.dumps(
                    {"rejectThreshold": float(payload.rejectThreshold or 0.75)},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {"legacyExecution": "backend", "scene": "image_review"},
                    ensure_ascii=False,
                ),
                1 if payload.enabled else 0,
                now,
                CAPABILITY_IMAGE_REVIEW,
            ),
        )
        conn.commit()
        return success_response(data=_resolve_image_capability())
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/image/ai-agent-test")
async def test_image_ai_agent(
    payload: ImageAgentTestPayload,
    user: dict = Depends(get_current_user),
):
    image_url = str(payload.imageUrl or "").strip()
    if not image_url:
        return error_response("INVALID_IMAGE_URL", "测试图片链接不能为空", 400)
    if not image_url.lower().startswith(("http://", "https://")):
        return error_response(
            "INVALID_IMAGE_URL", "测试图片链接必须以 http:// 或 https:// 开头", 400
        )

    resolved = _resolve_image_capability()
    return success_response(
        data={
            "tested": True,
            "status": "delegated",
            "message": "图片审核执行仍由 legacy backend 提供，统一后端当前仅管理配置。",
            "capability_key": CAPABILITY_IMAGE_REVIEW,
            "provider_type": resolved.get("providerType") or "openai_compatible",
            "gateway_route": resolved.get("gatewayRoute") or "",
            "imageUrl": image_url,
            "filename": payload.filename or "",
            "username": payload.username or "",
            "rejectThreshold": float(
                payload.rejectThreshold or resolved.get("rejectThreshold") or 0.75
            ),
            "promptTemplate": payload.promptTemplate
            or resolved.get("promptTemplate")
            or "",
            "provider": resolved.get("provider") or {},
        }
    )


@router.get("/api/internal/store/image-ai/config")
async def get_internal_image_ai_config(request: Request):
    auth_error = _check_internal_auth(request)
    if auth_error:
        return auth_error
    resolved = _resolve_image_capability()
    provider = resolved.get("provider") or {}
    return success_response(
        data={
            "capabilityKey": CAPABILITY_IMAGE_REVIEW,
            "enabled": bool(resolved.get("enabled")),
            "apiConfigId": resolved.get("apiConfigId"),
            "rejectThreshold": float(resolved.get("rejectThreshold") or 0.75),
            "promptTemplate": resolved.get("promptTemplate") or "",
            "provider": {
                "id": provider.get("id"),
                "name": provider.get("name") or "",
                "providerType": provider.get("provider_type") or "openai_compatible",
                "baseUrl": provider.get("base_url") or "",
                "apiKeyEncrypted": provider.get("api_key_encrypted") or "",
                "model": provider.get("model") or "",
                "timeoutMs": int(provider.get("timeout_ms") or 30000),
                "gatewayRoute": provider.get("gateway_route") or "",
                "gatewayWorkspace": provider.get("gateway_workspace") or "",
                "extraConfig": provider.get("extra_config_json") or {},
            },
            "runtimeConfig": (resolved.get("capability") or {}).get(
                "runtime_config_json"
            )
            or {},
            "reviewCriteria": (resolved.get("capability") or {}).get(
                "review_criteria_json"
            )
            or {},
        }
    )
