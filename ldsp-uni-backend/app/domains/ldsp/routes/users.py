"""Async LDStatusPro user routes using Service Layer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.response import success_response, error_response
from app.config import settings
from app.domains.ldsp.schemas.users import (
    UserRegisterRequest,
    UserTrustLevelRequest,
)
from app.domains.ldsp.services.users import UserService
from app.db.engine import get_ldsp_session

router = APIRouter(prefix="/api", tags=["users"])
compat_router = APIRouter(tags=["users-compat"])

user_service = UserService()


@router.post("/user/register")
async def register_user(
    request: Request,
    req: UserRegisterRequest | None = None,
    db: AsyncSession = Depends(get_ldsp_session),
):
    """Register user to leaderboard."""
    user = request.state.user
    if not user:
        raise HTTPException(401, "未认证")

    if req is None:
        req = UserRegisterRequest(
            site=user.get("site", "linux.do"),
            user_id=str(user.get("user_id") or ""),
            username=user.get("username") or "",
        )

    if settings.registration_paused:
        status = await user_service.get_status(db, req.site, req.user_id)
        if not status.get("hasJoinedBefore"):
            return error_response("REGISTRATION_PAUSED", "已暂停新用户注册", 403)

    registered = await user_service.register_user(db, req)
    profile = await user_service.get_profile(db, req.site, req.user_id)
    return success_response(
        data={
            "message": "加入排行榜成功" if registered else "已加入排行榜",
            "user": {
                "id": req.user_id,
                "username": getattr(profile, "username", req.username),
                "name": getattr(profile, "name", None),
                "avatar_url": getattr(profile, "avatar_url", None),
                "trust_level": getattr(profile, "trust_level", 0),
                "joined_at": getattr(profile, "joined_at", None),
                "is_active": getattr(profile, "is_active", 1),
                "client_version": getattr(profile, "client_version", None),
            },
        }
    )


@compat_router.post("/api/user/register")
async def register_user_compat(
    request: Request,
    req: UserRegisterRequest | None = None,
    db: AsyncSession = Depends(get_ldsp_session),
):
    return await register_user(request, req, db)


@router.post("/user/quit")
async def quit_board(request: Request, db: AsyncSession = Depends(get_ldsp_session)):
    """Quit leaderboard."""
    user = request.state.user
    if not user:
        raise HTTPException(401, "未认证")
    await user_service.quit_leaderboard(db, user.get("site"), user.get("user_id"))
    return success_response(data={"message": "已退出排行榜"})


@compat_router.post("/api/user/quit")
async def quit_board_compat(
    request: Request, db: AsyncSession = Depends(get_ldsp_session)
):
    return await quit_board(request, db)


@router.get("/user/profile")
async def get_profile(request: Request, db: AsyncSession = Depends(get_ldsp_session)):
    """Get user profile."""
    user = request.state.user
    if not user:
        raise HTTPException(401, "未认证")
    profile = await user_service.get_profile(db, user.get("site"), user.get("user_id"))
    if not profile:
        return error_response("NOT_FOUND", "用户不存在", 404)
    data = profile.model_dump()
    return success_response(
        data={
            "user": {
                "id": data.get("user_id"),
                "username": data.get("username"),
                "name": data.get("name"),
                "avatar_url": data.get("avatar_url"),
                "trust_level": data.get("trust_level"),
                "joined_at": data.get("joined_at"),
                "is_active": data.get("is_active"),
                "client_version": data.get("client_version"),
            },
            "is_registered": data.get("is_active") == 1,
        }
    )


@compat_router.get("/api/user/profile")
async def get_profile_compat(
    request: Request, db: AsyncSession = Depends(get_ldsp_session)
):
    return await get_profile(request, db)


@router.get("/user/status")
async def get_status(request: Request, db: AsyncSession = Depends(get_ldsp_session)):
    """Get user join status and sync state."""
    user = request.state.user
    if not user:
        raise HTTPException(401, "未认证")
    client_version = request.headers.get("X-Client-Version")
    try:
        ensured_user, created = await user_service.ensure_user_from_jwt(
            db, user, client_version
        )
    except Exception as e:
        return error_response(
            "USER_INIT_FAILED", str(e) or "Failed to initialize user", 500
        )
    status = await user_service.get_status(db, user.get("site"), user.get("user_id"))
    status = {
        "isJoined": status.get("isJoined", False),
        "joinedAt": status.get("joinedAt"),
        "quitAt": ensured_user.get("quit_at"),
        "hasJoinedBefore": status.get("hasJoinedBefore", False),
        "autoCreated": bool(created),
        "lastSync": ensured_user.get("last_sync"),
        "registrationPaused": bool(settings.registration_paused),
    }
    return success_response(data=status)


@compat_router.get("/api/user/status")
async def get_status_compat(
    request: Request, db: AsyncSession = Depends(get_ldsp_session)
):
    return await get_status(request, db)


@router.post("/user/trust-level")
async def update_trust_level(
    req: UserTrustLevelRequest,
    request: Request,
    db: AsyncSession = Depends(get_ldsp_session),
):
    """Update/report user trust level."""
    user = request.state.user
    if not user:
        raise HTTPException(401, "未认证")
    if req.trust_level < 0 or req.trust_level > 4:
        return error_response("INVALID_TRUST_LEVEL", "信任等级必须是 0-4", 400)
    await user_service.update_trust_level(
        db, user.get("site"), user.get("user_id"), user.get("username"), req.trust_level
    )
    return success_response(data={"message": "信任等级已更新"})


@compat_router.post("/api/user/trust-level")
async def update_trust_level_compat(
    req: UserTrustLevelRequest,
    request: Request,
    db: AsyncSession = Depends(get_ldsp_session),
):
    return await update_trust_level(req, request, db)


@router.get("/user/rank")
async def get_user_rank(request: Request):
    """Get user's rank in a leaderboard type."""
    rank_type = request.query_params.get("type", "daily")
    return success_response(data={"type": rank_type, "rank": None, "message": "未上榜"})


@compat_router.get("/api/user/rank")
async def get_user_rank_compat(request: Request):
    return await get_user_rank(request)
