"""Async User service for managing user data."""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

from app.domains.ldsp.schemas.users import (
    UserProfileResponse,
    UserRegisterRequest,
)

logger = structlog.get_logger(__name__)


class UserService:
    """Async Service for user-related database operations."""

    async def get_user_row(
        self, db: AsyncSession, site: str, user_id: str
    ) -> dict | None:
        query = text("SELECT * FROM users WHERE site = :site AND user_id = :user_id")
        result = await db.execute(query, {"site": site, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None

    async def upsert_oauth_user(
        self,
        db: AsyncSession,
        site: str,
        user_info: dict,
        trust_level: int,
    ) -> dict:
        existing = await self.get_user_row(db, site, str(user_info.get("id")))
        avatar_template = user_info.get("animated_avatar") or user_info.get(
            "avatar_template"
        )
        avatar_url = user_info.get("avatar_url") or avatar_template
        now = str(int(__import__("time").time() * 1000))

        if not existing:
            await db.execute(
                text(
                    """INSERT INTO users (
                        site, user_id, username, name, avatar_url, trust_level,
                        is_active, cloud_sync_only, created_at, updated_at
                    ) VALUES (
                        :site, :user_id, :username, :name, :avatar_url, :trust_level,
                        0, 1, :now, :now
                    )"""
                ),
                {
                    "site": site,
                    "user_id": str(user_info.get("id")),
                    "username": user_info.get("username")
                    or f"user_{user_info.get('id')}",
                    "name": user_info.get("name"),
                    "avatar_url": avatar_url,
                    "trust_level": trust_level,
                    "now": now,
                },
            )
            await db.commit()
            created = await self.get_user_row(db, site, str(user_info.get("id")))
            return created or {}

        await db.execute(
            text(
                """UPDATE users SET
                    username = COALESCE(:username, username),
                    name = :name,
                    avatar_url = COALESCE(:avatar_url, avatar_url),
                    trust_level = CASE WHEN :trust_level > COALESCE(trust_level, 0) THEN :trust_level ELSE trust_level END,
                    updated_at = :now
                WHERE site = :site AND user_id = :user_id"""
            ),
            {
                "site": site,
                "user_id": str(user_info.get("id")),
                "username": user_info.get("username"),
                "name": user_info.get("name"),
                "avatar_url": avatar_url,
                "trust_level": trust_level,
                "now": now,
            },
        )
        await db.commit()
        updated = await self.get_user_row(db, site, str(user_info.get("id")))
        return updated or {}

    async def ensure_user_from_jwt(
        self,
        db: AsyncSession,
        jwt_user: dict,
        client_version: str | None = None,
    ) -> tuple[dict, bool]:
        site = jwt_user.get("site", "linux.do")
        user_id = str(jwt_user.get("user_id") or jwt_user.get("sub") or "")
        if not user_id:
            raise ValueError("Invalid user id")

        existing = await self.get_user_row(db, site, user_id)
        trust_level = max(0, min(4, int(jwt_user.get("trust_level") or 0)))
        now = str(int(__import__("time").time() * 1000))
        avatar_url = (
            jwt_user.get("animated_avatar")
            or jwt_user.get("avatar_url")
            or jwt_user.get("avatar_template")
        )

        if not existing:
            if settings.registration_paused:
                raise ValueError("REGISTRATION_PAUSED")
            await db.execute(
                text(
                    """INSERT INTO users (
                        site, user_id, username, name, avatar_url, trust_level,
                        is_active, cloud_sync_only, client_version, created_at, updated_at
                    ) VALUES (
                        :site, :user_id, :username, :name, :avatar_url, :trust_level,
                        0, 1, :client_version, :now, :now
                    )"""
                ),
                {
                    "site": site,
                    "user_id": user_id,
                    "username": jwt_user.get("username") or f"user_{user_id}",
                    "name": jwt_user.get("name")
                    or jwt_user.get("username")
                    or f"user_{user_id}",
                    "avatar_url": avatar_url,
                    "trust_level": trust_level,
                    "client_version": client_version,
                    "now": now,
                },
            )
            await db.commit()
            created = await self.get_user_row(db, site, user_id)
            return created or {}, True

        updates = {
            "site": site,
            "user_id": user_id,
            "username": jwt_user.get("username"),
            "name": jwt_user.get("name"),
            "avatar_url": avatar_url,
            "trust_level": trust_level,
            "client_version": client_version,
            "now": now,
        }
        await db.execute(
            text(
                """UPDATE users SET
                    username = COALESCE(:username, username),
                    name = COALESCE(:name, name),
                    avatar_url = COALESCE(:avatar_url, avatar_url),
                    trust_level = CASE WHEN :trust_level > COALESCE(trust_level, 0) THEN :trust_level ELSE trust_level END,
                    client_version = COALESCE(:client_version, client_version),
                    updated_at = :now
                WHERE site = :site AND user_id = :user_id"""
            ),
            updates,
        )
        await db.commit()
        refreshed = await self.get_user_row(db, site, user_id)
        return refreshed or {}, False

    async def register_user(self, db: AsyncSession, req: UserRegisterRequest) -> bool:
        """Register a new user if not exists."""
        query = text(
            """INSERT INTO users (site, user_id, username, is_active, joined_at, created_at, updated_at, cloud_sync_only)
               VALUES (:site, :user_id, :username, 1, :now, :now, :now, 0)
               ON CONFLICT(site, user_id) DO UPDATE SET
                   username = excluded.username,
                   is_active = 1,
                   joined_at = COALESCE(users.joined_at, excluded.joined_at),
                   cloud_sync_only = 0,
                   updated_at = excluded.updated_at"""
        )
        try:
            await db.execute(
                query,
                {
                    "site": req.site,
                    "user_id": req.user_id,
                    "username": req.username,
                    "now": str(int(__import__("time").time() * 1000)),
                },
            )
            await db.commit()
            logger.info("user_registered", user_id=req.user_id)
            return True
        except Exception as e:
            await db.rollback()
            logger.error("user_registration_failed", error=e)
            return False

    async def quit_leaderboard(self, db: AsyncSession, site: str, user_id: str) -> None:
        """Mark user as inactive (quit)."""
        query = text(
            "UPDATE users SET is_active = 0, quit_at = :now WHERE site = :site AND user_id = :user_id"
        )
        await db.execute(
            query,
            {
                "site": site,
                "user_id": user_id,
                "now": str(int(__import__("time").time() * 1000)),
            },
        )
        await db.commit()
        logger.info("user_quit", site=site, user_id=user_id)

    async def get_profile(
        self, db: AsyncSession, site: str, user_id: str
    ) -> UserProfileResponse | None:
        """Get user profile."""
        query = text(
            """SELECT user_id, username, name, avatar_url, trust_level, is_active,
                      cloud_sync_only, joined_at, last_sync
               FROM users WHERE site = :site AND user_id = :user_id"""
        )
        result = await db.execute(query, {"site": site, "user_id": user_id})
        row = result.mappings().first()
        return UserProfileResponse(**dict(row)) if row else None

    async def get_status(self, db: AsyncSession, site: str, user_id: str) -> dict:
        """Get user join status."""
        query = text(
            "SELECT is_active, cloud_sync_only, joined_at FROM users WHERE site = :site AND user_id = :user_id"
        )
        result = await db.execute(query, {"site": site, "user_id": user_id})
        row = result.mappings().first()
        if row:
            return {
                "joined": True,
                "isJoined": bool(row["is_active"]),
                "is_active": row["is_active"],
                "cloud_sync_only": row["cloud_sync_only"],
                "joined_at": row["joined_at"],
                "joinedAt": row["joined_at"],
                "hasJoinedBefore": True,
            }
        return {"joined": False, "isJoined": False, "hasJoinedBefore": False}

    async def update_trust_level(
        self,
        db: AsyncSession,
        site: str,
        user_id: str,
        username: str | None,
        trust_level: int,
    ) -> None:
        """Upsert user with updated trust level."""
        now = str(int(__import__("time").time() * 1000))
        query = text(
            """INSERT INTO users (site, user_id, username, trust_level, is_active, created_at, updated_at)
               VALUES (:site, :user_id, :username, :trust_level, 1, :now, :now)
               ON CONFLICT(site, user_id) DO UPDATE SET
                   trust_level = excluded.trust_level,
                   username = IFNULL(excluded.username, users.username),
                   updated_at = excluded.updated_at"""
        )
        await db.execute(
            query,
            {
                "site": site,
                "user_id": user_id,
                "username": username,
                "trust_level": trust_level,
                "now": now,
            },
        )
        await db.commit()
