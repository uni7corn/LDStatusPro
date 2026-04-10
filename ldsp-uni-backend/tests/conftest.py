"""Test configuration."""

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db.engine import ldsp_session_factory
from app.config import settings

TEST_USER_ID = "99999"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    Path("./data").mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def ldsp_db() -> AsyncGenerator[AsyncSession, None]:
    """Provides an AsyncSession for testing LDSP DB. Creates table if needed."""
    Path("./data").mkdir(parents=True, exist_ok=True)
    async with ldsp_session_factory() as session:
        # Ensure users table exists
        await session.execute(
            text(
                """CREATE TABLE IF NOT EXISTS users (
                site TEXT, user_id TEXT, username TEXT, name TEXT, avatar_url TEXT,
                trust_level INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT 1,
                cloud_sync_only BOOLEAN DEFAULT 0, joined_at TEXT, last_sync TEXT,
                created_at TEXT, updated_at TEXT, quit_at TEXT, PRIMARY KEY(site, user_id)
            )"""
            )
        )
        await session.commit()
        try:
            yield session
        finally:
            await session.execute(
                text("DELETE FROM users WHERE user_id = :id"), {"id": TEST_USER_ID}
            )
            await session.commit()
            await session.close()
