"""CDK management routes."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user

router = APIRouter(tags=["store"])


def _db() -> sqlite3.Connection:
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


class CDKBatchDelete(BaseModel):
    cdk_ids: list[int] = []


# ---------------------------------------------------------------------------
# User Auth Routes
# ---------------------------------------------------------------------------


@router.get("/api/shop/products/{product_id}/cdk/export")
async def export_cdk(
    product_id: int,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT * FROM shop_products WHERE id = ? AND seller_user_id = ? AND seller_site = ?",
            (product_id, user_id, site),
        )
        product = _row_to_dict(cur.fetchone())
        if product is None:
            return error_response("PRODUCT_NOT_FOUND", "商品不存在或无权限", 404)
        cur = conn.execute(
            "SELECT * FROM shop_cdk WHERE product_id = ? ORDER BY created_at DESC",
            (product_id,),
        )
        cdks = _rows_to_dicts(cur.fetchall())
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "code", "status", "created_at", "used_at", "used_by"])
        for cdk in cdks:
            writer.writerow(
                [
                    cdk.get("id", ""),
                    cdk.get("code", ""),
                    cdk.get("status", ""),
                    cdk.get("created_at", ""),
                    cdk.get("used_at", ""),
                    cdk.get("used_by", ""),
                ]
            )
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=cdks_product_{product_id}.csv"
            },
        )
    except Exception as e:
        return error_response("EXPORT_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/products/{product_id}/cdk/batch-delete")
async def batch_delete_cdk(
    product_id: int,
    payload: CDKBatchDelete,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT * FROM shop_products WHERE id = ? AND seller_user_id = ? AND seller_site = ?",
            (product_id, user_id, site),
        )
        if not _row_to_dict(cur.fetchone()):
            return error_response("PRODUCT_NOT_FOUND", "商品不存在或无权限", 404)
        if not payload.cdk_ids:
            return error_response("NO_CDKS_SELECTED", "请选择要删除的CDK", 400)
        placeholders = ",".join("?" for _ in payload.cdk_ids)
        cur = conn.execute(
            f"DELETE FROM shop_cdk WHERE id IN ({placeholders}) AND product_id = ?",
            [*payload.cdk_ids, product_id],
        )
        deleted = cur.rowcount
        conn.commit()
        return success_response(data={"deleted_count": deleted})
    except Exception as e:
        return error_response("BATCH_DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/products/{product_id}/cdk/clear")
async def clear_deletable_cdk(
    product_id: int,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT * FROM shop_products WHERE id = ? AND seller_user_id = ? AND seller_site = ?",
            (product_id, user_id, site),
        )
        if not _row_to_dict(cur.fetchone()):
            return error_response("PRODUCT_NOT_FOUND", "商品不存在或无权限", 404)
        cur = conn.execute(
            "DELETE FROM shop_cdk WHERE product_id = ? AND (status = 'sold' OR status = 'expired' OR status = 'deleted')",
            (product_id,),
        )
        deleted = cur.rowcount
        conn.commit()
        return success_response(data={"cleared_count": deleted})
    except Exception as e:
        return error_response("CLEAR_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/shop/products/{product_id}/cdk/{cdk_id}")
async def delete_single_cdk(
    product_id: int,
    cdk_id: int,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT * FROM shop_products WHERE id = ? AND seller_user_id = ? AND seller_site = ?",
            (product_id, user_id, site),
        )
        if not _row_to_dict(cur.fetchone()):
            return error_response("PRODUCT_NOT_FOUND", "商品不存在或无权限", 404)
        cur = conn.execute(
            "DELETE FROM shop_cdk WHERE id = ? AND product_id = ?",
            (cdk_id, product_id),
        )
        deleted = cur.rowcount
        conn.commit()
        if deleted == 0:
            return error_response("CDK_NOT_FOUND", "CDK不存在或不属于该商品", 404)
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()
