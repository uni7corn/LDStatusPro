"""Backup management routes compatible with admin-panel expectations."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Request

from app.common.utils.response import error_response, success_response
from app.config import settings

router = APIRouter(tags=["ldsp-backups"])

BACKUP_ROOT = Path("./data/backups")
SETTINGS_KEY = "backup_settings"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.ldsp_database_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_max_backups(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM system_config WHERE key = ?", (SETTINGS_KEY,)
    ).fetchone()
    if not row or not row[0]:
        return 5
    try:
        return max(1, min(30, int(json.loads(row[0]).get("maxBackups", 5))))
    except Exception:
        return 5


def _set_max_backups(conn: sqlite3.Connection, value: int) -> None:
    now = int(time.time() * 1000)
    conn.execute(
        """INSERT INTO system_config (key, value, description, updated_at)
           VALUES (?, ?, 'Backup settings', ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (SETTINGS_KEY, json.dumps({"maxBackups": value}, ensure_ascii=False), now),
    )


def _list_backups() -> list[dict]:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    items = []
    for file in sorted(
        BACKUP_ROOT.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        stat = file.stat()
        items.append(
            {
                "name": file.name,
                "size": stat.st_size,
                "uploaded": int(stat.st_mtime * 1000),
            }
        )
    return items


def _prune_backups(max_backups: int) -> None:
    backups = _list_backups()
    for item in backups[max_backups:]:
        target = BACKUP_ROOT / item["name"]
        if target.exists():
            target.unlink(missing_ok=True)


@router.post("/api/admin/backup")
async def perform_backup():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    filename = f"ldsp_data_{timestamp}.db"
    target = BACKUP_ROOT / filename
    try:
        shutil.copy2(settings.ldsp_database_path, target)
        conn = _conn()
        try:
            max_backups = _get_max_backups(conn)
        finally:
            conn.close()
        _prune_backups(max_backups)
        return success_response(
            data={"name": filename, "key": filename}, message="备份创建成功"
        )
    except Exception as e:
        return error_response("BACKUP_FAILED", str(e), 500)


@router.get("/api/admin/backups")
async def list_backups():
    conn = _conn()
    try:
        max_backups = _get_max_backups(conn)
    finally:
        conn.close()
    return success_response(
        data={"backups": _list_backups(), "maxBackups": max_backups}
    )


@router.delete("/api/admin/backups/{filename}")
async def delete_backup(filename: str):
    target = BACKUP_ROOT / filename
    if not target.exists():
        return error_response("NOT_FOUND", "备份不存在", 404)
    try:
        target.unlink()
        return success_response(data={"name": filename}, message="备份删除成功")
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)


@router.post("/api/admin/backups/settings")
async def update_backup_settings(request: Request):
    body = await request.json()
    max_backups = int(body.get("maxBackups", 5))
    if max_backups < 1 or max_backups > 30:
        return error_response("INVALID_PARAMS", "maxBackups 必须在 1-30 之间", 400)
    conn = _conn()
    try:
        _set_max_backups(conn, max_backups)
        conn.commit()
    finally:
        conn.close()
    _prune_backups(max_backups)
    return success_response(
        data={"maxBackups": max_backups}, message="备份设置更新成功"
    )
