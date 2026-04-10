"""Tools routes (admin-only: migration, buffer)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.config import settings
from app.common.utils.response import error_response, success_response
from app.scheduler.scheduler import audit_flush_job, buffer_flush_job

router = APIRouter(tags=["ldsp-tools"])


@router.post("/api/admin/migrate")
async def admin_migrate(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    source_path = body.get("sourcePath") or body.get("source")
    if not source_path:
        return error_response("INVALID_PARAMS", "sourcePath 为必填项", 400)

    if not Path(source_path).exists():
        return error_response(
            "INVALID_PARAMS", f"源数据库文件不存在: {source_path}", 400
        )

    tables = (
        body.get("tables")
        if body.get("tables") and isinstance(body.get("tables"), list)
        else None
    )

    results = {}
    try:
        src_conn = sqlite3.connect(source_path)
        dst_conn = sqlite3.connect(settings.ldsp_database_path)

        if tables is None:
            cursor = src_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = [r[0] for r in cursor.fetchall()]

        total_migrated = 0
        for table in tables:
            cursor = src_conn.execute(f"SELECT COUNT(*) FROM {table}")
            src_count = cursor.fetchone()[0]
            cursor = src_conn.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            dst_columns = [desc[0] for desc in cursor.description]
            placeholders = ", ".join(["?"] * len(dst_columns))

            dst_conn.executemany(
                f"INSERT OR IGNORE INTO {table} ({', '.join(dst_columns)}) VALUES ({placeholders})",
                rows,
            )
            migrated = dst_conn.total_changes - total_migrated
            total_migrated = dst_conn.total_changes
            results[table] = {"migrated": src_count, "sourceCount": src_count}

        dst_conn.commit()
        dst_conn.close()
        src_conn.close()

        return success_response(
            data={
                "success": True,
                "sourcePath": source_path,
                "tables": results,
                "totalMigrated": total_migrated,
            },
            message="迁移完成",
        )
    except Exception as e:
        return error_response("MIGRATE_FAILED", str(e), 500)


@router.get("/api/admin/buffer/stats")
async def admin_buffer_stats():
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    try:
        request_logs_recent = 0
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM request_logs WHERE created_at > datetime('now', '-1 hour')"
            ).fetchone()
            request_logs_recent = int(row["cnt"] if row else 0)
        except Exception:
            request_logs_recent = 0

        return success_response(
            data={
                "mode": "direct_write",
                "reading": {
                    "records": 0,
                    "size": 0,
                    "note": "统一后端当前采用直写数据库，不维护内存阅读缓冲区",
                },
                "requirements": {
                    "records": 0,
                    "size": 0,
                    "note": "统一后端当前采用直写数据库，不维护内存要求缓冲区",
                },
                "audit": {
                    "recentRequestLogs": request_logs_recent,
                    "flushMode": "scheduled_check",
                },
                "shouldFlush": False,
                "flushReason": "当前阅读/requirements 为直写模式；仅审计 flush 可手动触发",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    finally:
        conn.close()


@router.post("/api/admin/buffer/flush")
async def admin_buffer_flush():
    before = {
        "readingRecords": 0,
        "requirementsRecords": 0,
        "mode": "direct_write",
    }
    try:
        await buffer_flush_job("manual")
        await audit_flush_job("manual")
        result = {
            "readingFlushed": 0,
            "requirementsFlushed": 0,
            "totalFlushed": 0,
            "totalErrors": 0,
            "readingDuration": 0,
            "requirementsDuration": 0,
            "auditTriggered": True,
            "note": "统一后端当前阅读/requirements 为直写模式，本次主要触发了审计 flush 检查。",
        }
        after = {
            "readingRecords": 0,
            "requirementsRecords": 0,
            "mode": "direct_write",
        }
        return success_response(
            data={
                "message": "缓冲刷新完成",
                "before": before,
                "result": result,
                "after": after,
            }
        )
    except Exception as e:
        return error_response("FLUSH_FAILED", str(e), 500)
