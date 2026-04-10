"""Store scheduled jobs admin/internal routes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.common.utils.response import success_response, error_response
from app.config import settings
from app.core.auth import get_current_user
from app.domains.store.services.schedule_service import StoreScheduleService

router = APIRouter(tags=["store-schedule"])


def _db() -> sqlite3.Connection:
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


class ScheduledJobUpdatePayload(BaseModel):
    enabled: bool = True
    runtime_config: dict = {}


@router.get("/api/admin/store/scheduled-jobs")
async def list_scheduled_jobs(user: dict = Depends(get_current_user)):
    try:
        rows = StoreScheduleService().list_jobs()
        return success_response(data={"items": rows, "total": len(rows)})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)


@router.get("/api/admin/shop/scheduled-jobs")
async def list_shop_scheduled_jobs(user: dict = Depends(get_current_user)):
    """Legacy-compatible alias for store scheduler metadata."""
    return await list_scheduled_jobs(user)


@router.get("/api/admin/store/scheduled-job-runs")
async def list_scheduled_job_runs(
    jobKey: str | None = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    service = StoreScheduleService()
    try:
        rows = service.list_runs(job_key=jobKey, limit=max(1, min(limit, 200)))
        return success_response(data={"items": rows, "total": len(rows)})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)


@router.get("/api/admin/shop/scheduled-job-runs")
async def list_shop_scheduled_job_runs(
    jobKey: str | None = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """Legacy-compatible alias for store scheduler run history."""
    return await list_scheduled_job_runs(jobKey=jobKey, limit=limit, user=user)


@router.put("/api/admin/store/scheduled-jobs/{job_key}")
async def update_scheduled_job(
    job_key: str,
    payload: ScheduledJobUpdatePayload,
    user: dict = Depends(get_current_user),
):
    service = StoreScheduleService()
    job = service.get_job(job_key)
    if not job:
        return error_response("NOT_FOUND", "任务不存在", 404)
    service.upsert_job(
        job_key=job_key,
        job_type=job.get("job_type") or job_key,
        enabled=payload.enabled,
        schedule_type=job.get("schedule_type") or "interval",
        interval_seconds=job.get("interval_seconds"),
        cron_expr=job.get("cron_expr"),
        runtime_config=payload.runtime_config or job.get("runtime_config_json") or {},
    )
    return success_response(data=service.get_job(job_key) or {"job_key": job_key})


@router.put("/api/admin/shop/scheduled-jobs/{job_key}")
async def update_shop_scheduled_job(
    job_key: str,
    payload: ScheduledJobUpdatePayload,
    user: dict = Depends(get_current_user),
):
    """Legacy-compatible alias for scheduler job updates."""
    return await update_scheduled_job(job_key=job_key, payload=payload, user=user)
