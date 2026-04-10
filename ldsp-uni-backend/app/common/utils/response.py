"""Unified API response helpers."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def success_response(
    data: Any = None,
    message: str = "操作成功",
    status_code: int = 200,
    meta: dict | None = None,
) -> JSONResponse:
    body = {"success": True, "data": data, "message": message}
    if meta is not None:
        body["meta"] = meta
    return JSONResponse(content=body, status_code=status_code)


def error_response(
    code: str,
    message: str,
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        content={"success": False, "error": {"code": code, "message": message}},
        status_code=status_code,
    )
