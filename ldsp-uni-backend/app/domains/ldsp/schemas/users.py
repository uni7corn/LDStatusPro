"""Pydantic schemas for the Users domain."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    site: str = "linux.do"
    user_id: str
    username: str


class UserTrustLevelRequest(BaseModel):
    trust_level: int = 0


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    name: str | None = None
    avatar_url: str | None = None
    trust_level: int
    is_active: bool
    cloud_sync_only: bool
    joined_at: str | None = None
    last_sync: str | None = None


class UserStatusResponse(BaseModel):
    joined: bool
    is_active: bool | None = None
    cloud_sync_only: bool | None = None
    joined_at: str | None = None


class UserRankResponse(BaseModel):
    type: str
    rank: int | None = None
    minutes: int | None = None
