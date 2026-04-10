"""Store scheduled job persistence helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import settings
from app.domains.store.services.ai_capability_service import AICapabilityService


def _db() -> sqlite3.Connection:
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _normalize_job_record(row: sqlite3.Row | dict | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    runtime_config = _parse_json(data.get("runtime_config_json"), {})
    data["runtime_config_json"] = runtime_config
    data["runtime_config"] = runtime_config
    data["runtimeConfig"] = runtime_config
    return data


class StoreScheduleService:
    def __init__(self) -> None:
        AICapabilityService().ensure_ready()

    def upsert_job(
        self,
        job_key: str,
        job_type: str,
        *,
        enabled: bool = True,
        schedule_type: str = "interval",
        interval_seconds: int | None = None,
        cron_expr: str | None = None,
        runtime_config: dict | None = None,
    ) -> None:
        conn = _db()
        try:
            now = __import__("time").time_ns() // 1_000_000
            conn.execute(
                """INSERT INTO scheduled_jobs (
                    job_key, job_type, enabled, schedule_type, interval_seconds, cron_expr,
                    runtime_config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_key) DO UPDATE SET
                    job_type = excluded.job_type,
                    enabled = excluded.enabled,
                    schedule_type = excluded.schedule_type,
                    interval_seconds = excluded.interval_seconds,
                    cron_expr = excluded.cron_expr,
                    runtime_config_json = excluded.runtime_config_json,
                    updated_at = excluded.updated_at""",
                (
                    job_key,
                    job_type,
                    1 if enabled else 0,
                    schedule_type,
                    interval_seconds,
                    cron_expr,
                    json.dumps(runtime_config or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def start_run(self, job_key: str, trigger_source: str) -> int:
        conn = _db()
        try:
            now = __import__("time").time_ns() // 1_000_000
            cur = conn.execute(
                "INSERT INTO scheduled_job_runs (job_key, trigger_source, status, started_at) VALUES (?, ?, 'running', ?)",
                (job_key, trigger_source, now),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def finish_run(
        self,
        run_id: int,
        job_key: str,
        *,
        status: str,
        result: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        conn = _db()
        try:
            now = __import__("time").time_ns() // 1_000_000
            started = conn.execute(
                "SELECT started_at FROM scheduled_job_runs WHERE id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            started_at = int(started["started_at"] or now) if started else now
            duration_ms = max(0, now - started_at)
            conn.execute(
                """UPDATE scheduled_job_runs SET
                    status = ?, ended_at = ?, duration_ms = ?, result_json = ?, error_message = ?
                   WHERE id = ?""",
                (
                    status,
                    now,
                    duration_ms,
                    json.dumps(result or {}, ensure_ascii=False),
                    error_message,
                    run_id,
                ),
            )
            conn.execute(
                "UPDATE scheduled_jobs SET last_run_at = ?, last_status = ?, last_error = ?, updated_at = ? WHERE job_key = ?",
                (now, status, error_message, now, job_key),
            )
            conn.commit()
        finally:
            conn.close()

    def get_job(self, job_key: str) -> dict | None:
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE job_key = ? LIMIT 1",
                (job_key,),
            ).fetchone()
            return _normalize_job_record(row)
        finally:
            conn.close()

    def list_jobs(self) -> list[dict]:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_jobs ORDER BY job_key ASC"
            ).fetchall()
            return [
                item for item in (_normalize_job_record(row) for row in rows) if item
            ]
        finally:
            conn.close()

    def is_job_enabled(self, job_key: str) -> bool:
        job = self.get_job(job_key)
        if not job:
            return True
        return bool(int(job.get("enabled") or 0))

    def list_runs(self, job_key: str | None = None, limit: int = 50) -> list[dict]:
        conn = _db()
        try:
            if job_key:
                rows = conn.execute(
                    "SELECT * FROM scheduled_job_runs WHERE job_key = ? ORDER BY started_at DESC LIMIT ?",
                    (job_key, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scheduled_job_runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["result_json"] = _parse_json(item.get("result_json"), {})
                result.append(item)
            return result
        finally:
            conn.close()
