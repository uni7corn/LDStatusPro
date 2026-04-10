"""Database engine configuration (multi-database)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    async_scoped_session,
    create_async_engine,
)

from app.config import settings

# LDStatusPro engine
_ldsp_engine = create_async_engine(
    settings.ldsp_database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)
ldsp_session_factory = async_sessionmaker(
    _ldsp_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

# LD Store engine
_store_engine = create_async_engine(
    settings.store_database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)
store_session_factory = async_sessionmaker(
    _store_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_ldsp_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencies: FastAPI Depends compatible generator."""
    async with ldsp_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_store_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencies: FastAPI Depends compatible generator."""
    async with store_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_ldsp_session_context():
    async with ldsp_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_store_session_context():
    async with store_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_databases() -> None:
    """Ensure database files exist."""
    import sqlite3

    for path in [settings.ldsp_database_path, settings.store_database_path]:
        conn = sqlite3.connect(path)
        conn.close()
