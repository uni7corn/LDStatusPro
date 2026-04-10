"""Health check and info endpoint."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.config import settings
from app.common.utils.response import success_response

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    ldsp_ok = _check_sqlite(settings.ldsp_database_path)
    store_ok = _check_sqlite(settings.store_database_path)

    return success_response(
        data={
            "status": "healthy" if (ldsp_ok and store_ok) else "degraded",
            "databases": {
                "ldsp": "ok" if ldsp_ok else "unreachable",
                "store": "ok" if store_ok else "unreachable",
            },
            "environment": settings.environment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def _check_sqlite(path: str) -> bool:
    try:
        if not Path(path).exists():
            return False
        conn = sqlite3.connect(path)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


@router.get("/info")
async def info(request: Request):
    host = (request.headers.get("host") or "").lower()
    if any(token in host for token in ("api2.", "store", "shop")):
        return success_response(
            data={
                "name": "LD Store API",
                "version": getattr(settings, "api_version", None) or "v1",
                "environment": settings.environment or "local",
            }
        )
    return success_response(
        data={
            "name": "LDStatus Pro Migrated API",
            "version": getattr(settings, "api_version", None) or "v1",
            "environment": settings.environment or "production",
            "storage": "sqlite",
        }
    )
