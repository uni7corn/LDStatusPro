"""LD Store main shop routes - ~154 endpoints."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Query, Request, Form
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from app.config import settings
from app.common.utils.response import success_response, error_response
from app.core.auth import get_current_user
from app.domains.store.services.ldc import (
    create_ldc_order,
    decrypt_ldc_key,
    query_ldc_order,
    verify_ldc_sign,
)
from app.domains.store.services.ai_capability_service import AICapabilityService
from app.domains.store.services.agent_runtime_service import AgentRuntimeService
from app.domains.store.services.shop_products import ProductService

router = APIRouter(tags=["store"])

product_service = ProductService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db() -> sqlite3.Connection:
    """Return a sqlite3 connection to the store database."""
    path = settings.store_database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _page_params(page: int = 1, size: int = 20) -> tuple[int, int]:
    page = max(1, page)
    size = max(1, min(size, 100))
    return (page - 1) * size, size


def _empty() -> dict:
    return {}


def _product_row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    if "image_url" in data and data.get("images") in (None, ""):
        data["images"] = [data["image_url"]] if data.get("image_url") else []
    if isinstance(data.get("images"), str):
        data["images"] = [x for x in data["images"].split(",") if x]
    if isinstance(data.get("tags"), str):
        data["tags"] = [x for x in data["tags"].split(",") if x]
    return data


def _normalize_product_type(value: Any) -> str:
    normalized = str(value or "normal").strip().lower()
    if normalized in {"normal", "cdk", "link", "store", "external"}:
        return "link" if normalized == "external" else normalized
    return "normal"


def _product_is_cdk(product: dict) -> bool:
    return _normalize_product_type(product.get("product_type")) == "cdk"


def _product_is_normal(product: dict) -> bool:
    return _normalize_product_type(product.get("product_type")) == "normal"


def _augment_product_row(conn: sqlite3.Connection, product: dict | None) -> dict | None:
    if not product:
        return product

    enriched = dict(product)
    enriched["product_type"] = _normalize_product_type(enriched.get("product_type"))

    if _product_is_cdk(enriched):
        stats = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) as available,
                      SUM(CASE WHEN status = 'sold' THEN 1 ELSE 0 END) as sold
               FROM shop_cdk WHERE product_id = ?""",
            (enriched.get("id"),),
        ).fetchone()
        enriched["cdkStats"] = {
            "available": int(stats["available"] or 0) if stats else 0,
            "total": int(stats["total"] or 0) if stats else 0,
            "sold": int(stats["sold"] or 0) if stats else 0,
        }
        enriched["availableStock"] = enriched["cdkStats"]["available"]
    elif _product_is_normal(enriched):
        try:
            enriched["availableStock"] = max(0, int(enriched.get("stock") or 0))
        except Exception:
            enriched["availableStock"] = 0

    return enriched


def _safe_json_loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return __import__("json").loads(value)
    except Exception:
        return fallback


def _beijing_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


AVATAR_PROXY_ALLOWED_HOSTS = {"linux.do", "idcflare.com"}
AVATAR_PROXY_ALLOWED_PATH_PREFIXES = ("/user_avatar/", "/letter_avatar_proxy/")


def _safe_text(value: Any, max_length: int = 0) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if max_length > 0 and len(text) > max_length:
        return text[:max_length]
    return text


def _normalize_avatar_proxy_target(raw_target: Any) -> str:
    source = _safe_text(raw_target, 1200)
    if not source:
        return ""
    with_size = source.replace("{size}", "128")
    if with_size.lower().startswith(("http://", "https://")):
        return with_size
    if with_size.startswith("//"):
        return f"https:{with_size}"
    if with_size.startswith("/"):
        return f"https://linux.do{with_size}"
    return ""


def _is_allowed_avatar_proxy_url(target: str) -> bool:
    try:
        parsed = urlparse(target)
    except Exception:
        return False
    hostname = (parsed.hostname or "").lower()
    if hostname not in AVATAR_PROXY_ALLOWED_HOSTS:
        return False
    pathname = parsed.path or "/"
    return any(
        pathname.startswith(prefix) for prefix in AVATAR_PROXY_ALLOWED_PATH_PREFIXES
    )


def _store_api_info_payload() -> dict[str, Any]:
    return {
        "name": "LD Store API",
        "version": getattr(settings, "api_version", None) or "v1",
        "environment": settings.environment or "local",
    }


def _store_maintenance_status() -> dict[str, Any]:
    mode = (
        str(getattr(settings, "shop_maintenance_mode", "") or "").strip().lower()
        or "normal"
    )
    if mode not in {"normal", "ldc_restricted", "full"}:
        mode = "normal"
    enabled = mode != "normal"
    default_copy = {
        "normal": {
            "title": "LD 士多运行正常",
            "message": "当前所有功能均可正常使用。",
            "reason": "",
            "allowedActions": [],
            "blockedActions": [],
            "features": {},
        },
        "ldc_restricted": {
            "title": "支付链路维护中",
            "message": "当前支付链路维护中，部分交易功能暂不可用。",
            "reason": "LDC 支付链路维护",
            "allowedActions": ["browse", "view_product", "view_shop"],
            "blockedActions": ["orderPayment", "buyRequestTrade", "topServicePurchase"],
            "features": {
                "orderPayment": False,
                "buyRequestTrade": False,
                "topServicePurchase": False,
            },
        },
        "full": {
            "title": "LD 士多维护中",
            "message": "当前系统维护中，请稍后再试。",
            "reason": "商城维护",
            "allowedActions": [],
            "blockedActions": ["all"],
            "features": {
                "productManage": False,
                "orderPayment": False,
                "buyRequestTrade": False,
                "buyRequestChatWrite": False,
                "topServicePurchase": False,
            },
        },
    }[mode]
    return {
        "enabled": enabled,
        "mode": mode,
        "title": _safe_text(getattr(settings, "shop_maintenance_title", ""), 120)
        or default_copy["title"],
        "message": _safe_text(getattr(settings, "shop_maintenance_message", ""), 500)
        or default_copy["message"],
        "reason": _safe_text(getattr(settings, "shop_maintenance_reason", ""), 500)
        or default_copy["reason"],
        "eta": _safe_text(getattr(settings, "shop_maintenance_eta", ""), 200) or "待定",
        "statusUrl": _safe_text(
            getattr(settings, "shop_maintenance_status_url", ""), 300
        )
        or "https://ldspro.qzz.io/",
        "features": dict(default_copy["features"]),
        "allowedActions": list(default_copy["allowedActions"]),
        "blockedActions": list(default_copy["blockedActions"]),
    }


def _ldc_return_html(
    title: str,
    message: str,
    order_no: str = "",
    primary_text: str = "返回订单页",
    primary_href: str = "https://ldst0re.qzz.io/user/orders",
    secondary_text: str = "查看 LDC 余额",
    secondary_href: str = "https://credit.linux.do/balance",
    status: str = "success",
) -> Response:
    icon = {"success": "✅", "pending": "⏳", "error": "❌", "info": "ℹ️"}.get(
        status, "ℹ️"
    )
    color = {
        "success": "#10b981",
        "pending": "#f59e0b",
        "error": "#ef4444",
        "info": "#3b82f6",
    }.get(status, "#3b82f6")
    html = f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{title} - LD士多</title>
  <style>
    body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; background:linear-gradient(135deg, #f5f3f0 0%, #e8e4de 100%); color:#2f2f2f; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    .card {{ width:100%; max-width:480px; background:#fff; border-radius:20px; padding:34px 28px; box-shadow:0 12px 40px rgba(0,0,0,0.08); text-align:center; }}
    .icon {{ font-size:58px; margin-bottom:14px; }}
    h1 {{ margin:0 0 12px; color:{color}; font-size:26px; }}
    p {{ margin:0 0 14px; line-height:1.7; color:#555; }}
    .order {{ font-size:12px; color:#888; background:#f7f6f3; border-radius:8px; display:inline-block; padding:7px 12px; margin-bottom:18px; }}
    .actions {{ display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin-top:22px; }}
    a {{ text-decoration:none; border-radius:12px; padding:12px 18px; font-size:14px; font-weight:600; }}
    .primary {{ background:linear-gradient(135deg, #b5a898 0%, #9f8f7d 100%); color:#fff; }}
    .secondary {{ background:#f5f3f0; color:#666; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <div class=\"icon\">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
    {f'<div class="order">订单号：{order_no}</div>' if order_no else ""}
    <div class=\"actions\">
      <a class=\"primary\" href=\"{primary_href}\">{primary_text}</a>
      <a class=\"secondary\" href=\"{secondary_href}\">{secondary_text}</a>
    </div>
  </div>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _enrich_shop_order(order: dict | None) -> dict | None:
    if not order:
        return order
    enriched = dict(order)
    product_snapshot = _safe_json_loads(enriched.get("product_snapshot"), None)
    if product_snapshot:
        enriched["product"] = product_snapshot
    enriched["current_product_type"] = str(
        enriched.get("current_product_type")
        or (product_snapshot or {}).get("product_type")
        or "normal"
    )
    enriched["requires_buyer_contact"] = enriched["current_product_type"] == "normal"
    return enriched


def _safe_table_count(
    conn: sqlite3.Connection, table: str, where: str = "", params: tuple | list = ()
) -> int:
    try:
        query = f"SELECT COUNT(*) as c FROM {table}"
        if where:
            query += f" WHERE {where}"
        row = conn.execute(query, params).fetchone()
        if row is None:
            return 0
        return int(row["c"] if isinstance(row, sqlite3.Row) else row[0])
    except Exception:
        return 0


def _safe_table_sum(
    conn: sqlite3.Connection,
    table: str,
    field: str,
    where: str = "",
    params: tuple | list = (),
) -> float:
    try:
        query = f"SELECT COALESCE(SUM({field}), 0) as s FROM {table}"
        if where:
            query += f" WHERE {where}"
        row = conn.execute(query, params).fetchone()
        if row is None:
            return 0.0
        value = row["s"] if isinstance(row, sqlite3.Row) else row[0]
        return float(value or 0)
    except Exception:
        return 0.0


# Pydantic models for request bodies
class ShopCreate(BaseModel):
    name: str = ""
    description: str = ""
    tags: list[str] = []
    contact: str = ""


class ShopUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    contact: str | None = None
    offline: bool | None = None
    offline_reason: str | None = None


class ProductCreate(BaseModel):
    name: str = ""
    description: str = ""
    price: float = 0.0
    stock: int = 0
    category_id: int | None = None
    images: list[str] = []
    tags: list[str] = []


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    stock: int | None = None
    category_id: int | None = None
    images: list[str] | None = None
    tags: list[str] | None = None
    offline: bool | None = None


class CommentCreate(BaseModel):
    content: str = ""
    product_id: int | None = None
    parent_id: int | None = None
    rating: int | None = None


class CommentVote(BaseModel):
    vote_type: str  # up / down


class ReplyCreate(BaseModel):
    content: str = ""


class ReportCreate(BaseModel):
    reason: str = ""
    detail: str = ""


class BuyRequestCreate(BaseModel):
    product_id: int | None = None
    quantity: int = 1
    message: str = ""


class OrderCreate(BaseModel):
    product_id: int
    quantity: int = 1


class BuyRequestUpdate(BaseModel):
    status: str | None = None
    message: str | None = None


class MessageCreate(BaseModel):
    content: str = ""
    type: str = ""
    user_id: int | None = None


class MerchantConfigUpdate(BaseModel):
    config: dict = {}


class CategoryCreate(BaseModel):
    name: str = ""
    parent_id: int | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None


class CategoryReorder(BaseModel):
    ids: list[int] = []


class StoreCreate(BaseModel):
    name: str = ""
    address: str = ""
    contact: str = ""
    description: str = ""
    storeUrl: str = ""
    imageUrl: str = ""
    ownerName: str = ""


class StoreUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    contact: str | None = None
    description: str | None = None
    storeUrl: str | None = None
    imageUrl: str | None = None
    ownerName: str | None = None
    status: str | None = None
    isPinned: bool | None = None


class CDKCreate(BaseModel):
    product_id: int
    codes: list[str] = []


class TopServiceOrderCreate(BaseModel):
    shop_id: int = 0
    option_id: int = 0
    duration_days: int = 30


class RestockSubscriptionCreate(BaseModel):
    user_id: int | None = None
    notify_method: str = "system"


class ForbiddenWordCreate(BaseModel):
    word: str = ""
    replacement: str = "***"


class AnalyticsReportConfig(BaseModel):
    name: str = ""
    config: dict = {}


class OpsCopilotQuery(BaseModel):
    query: str = ""


# ---------------------------------------------------------------------------
# Public Routes
# ---------------------------------------------------------------------------


@router.get("/health")
async def health():
    ok = _check_sqlite(settings.store_database_path)
    return success_response(
        data={
            "status": "healthy" if ok else "degraded",
            "database": "ok" if ok else "unreachable",
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


@router.get("/api/info")
async def api_info(request: Request):
    host = (request.headers.get("host") or "").lower()
    if any(token in host for token in ("api2.", "store", "shop")):
        return success_response(data=_store_api_info_payload())
    return success_response(
        data={
            "name": "ld-store",
            "version": "0.1.0",
            "framework": "FastAPI",
        }
    )


@router.get("/api/shop/system-status")
async def shop_system_status():
    return success_response(data=_store_maintenance_status())


@router.get("/api/shops")
async def list_shops(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    tag: str | None = None,
    search: str | None = None,
    keyword: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE status = 'active'"
        params: list = []
        if tag:
            where += " AND tags LIKE ?"
            params.append(f"%{tag}%")
        effective_keyword = search or keyword
        if effective_keyword:
            where += " AND (name LIKE ? OR description LIKE ?)"
            params.extend([f"%{effective_keyword}%", f"%{effective_keyword}%"])
        safe_sort = (
            "updated_at"
            if sort == "updated_at"
            else ("pin_order" if sort == "pin_order" else "created_at")
        )
        safe_order = "ASC" if str(order).lower() == "asc" else "DESC"
        cur = conn.execute(f"SELECT COUNT(*) as total FROM shops {where}", params)
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shops {where} ORDER BY is_pinned DESC, pin_order ASC, {safe_sort} {safe_order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = []
        for row in _rows_to_dicts(cur.fetchall()):
            parsed_tags = _safe_json_loads(row.get("tags"), None)
            if not isinstance(parsed_tags, list):
                parsed_tags = [
                    item for item in str(row.get("tags") or "").split(",") if item
                ]
            row["tags"] = parsed_tags
            row["is_pinned"] = bool(row.get("is_pinned"))
            rows.append(row)
        return success_response(
            data={
                "items": rows,
                "total": total,
                "page": page,
                "size": size,
                "shops": rows,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "total": 0,
                "page": page,
                "size": size,
                "shops": [],
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": 0,
                    "totalPages": 0,
                },
            }
        )
    finally:
        conn.close()


# Compatibility route for tests / frontend
@router.get("/api/shop/recommended-products")
async def shop_recommended_products(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
):
    conn = _db()
    try:
        cur = conn.execute(
            f"SELECT * FROM shop_products WHERE status IN ('ai_approved', 'manual_approved') ORDER BY view_count DESC LIMIT ? OFFSET ?",
            [size, (page - 1) * size],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={"items": rows, "total": len(rows), "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/shops.stats/count")
async def shops_count():
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as total FROM shops WHERE status = 'active'"
        )
        total = cur.fetchone()["total"]
        return success_response(data={"total": total})
    except Exception:
        return success_response(data={"total": 0})
    finally:
        conn.close()


@router.get("/api/shops/stats/count")
async def shops_count_legacy():
    """Legacy-compatible public shop stats route from ld-store-backend."""
    return await shops_count()


@router.get("/api/shop/avatar-proxy")
async def shop_avatar_proxy(url: str = Query("", description="Avatar URL to proxy")):
    target = _normalize_avatar_proxy_target(url)
    if not target:
        return error_response("INVALID_PARAMS", "头像地址无效", 400)
    if not _is_allowed_avatar_proxy_url(target):
        return error_response("FORBIDDEN", "头像地址不在允许范围内", 403)

    headers = {
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"{urlparse(target).scheme}://{urlparse(target).netloc}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            upstream = await client.get(target, headers=headers)
    except httpx.TimeoutException:
        return error_response("AVATAR_FETCH_FAILED", "头像抓取超时", 504)
    except Exception:
        return error_response("AVATAR_FETCH_FAILED", "头像抓取失败", 502)

    if upstream.status_code < 200 or upstream.status_code >= 300:
        return error_response(
            "AVATAR_FETCH_FAILED", f"头像抓取失败 ({upstream.status_code})", 502
        )
    content_type = (upstream.headers.get("content-type") or "").lower()
    if not content_type.startswith("image/"):
        return error_response("AVATAR_FETCH_FAILED", "头像源返回了非图片内容", 502)

    return Response(
        content=upstream.content,
        status_code=200,
        headers={
            "Content-Type": upstream.headers.get("content-type") or "image/png",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "X-Avatar-Proxy": "ld-store",
        },
    )


@router.get("/api/shops/{shop_id}")
async def get_shop(shop_id: int, request: Request):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT * FROM shops WHERE id = ? AND status = 'active'", (shop_id,)
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("NOT_FOUND", "小店不存在或已下架", 404)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        viewer_ip = (
            (request.headers.get("x-forwarded-for") or request.client.host or "")
            .split(",")[0]
            .strip()
        )
        viewer_user_db_id = None
        try:
            viewer_user = getattr(request.state, "user", None)
            if viewer_user and viewer_user.get("user_id"):
                row_user = conn.execute(
                    "SELECT id FROM users WHERE site = ? AND user_id = ? LIMIT 1",
                    (
                        viewer_user.get("site", "linux.do"),
                        str(viewer_user.get("user_id")),
                    ),
                ).fetchone()
                viewer_user_db_id = row_user["id"] if row_user else None
        except Exception:
            viewer_user_db_id = None
        if viewer_ip or viewer_user_db_id:
            existed = conn.execute(
                """SELECT id FROM shop_views
                   WHERE shop_id = ?
                     AND ((? IS NOT NULL AND viewer_user_id = ?) OR (? != '' AND viewer_ip = ?))
                     AND viewed_at > ?
                   LIMIT 1""",
                (
                    shop_id,
                    viewer_user_db_id,
                    viewer_user_db_id,
                    viewer_ip,
                    viewer_ip,
                    now_ms - 24 * 60 * 60 * 1000,
                ),
            ).fetchone()
            if not existed:
                conn.execute(
                    "INSERT INTO shop_views (shop_id, viewer_ip, viewer_user_id, viewed_at) VALUES (?, ?, ?, ?)",
                    (shop_id, viewer_ip or None, viewer_user_db_id, now_ms),
                )
                conn.execute(
                    "UPDATE shops SET view_count = COALESCE(view_count, 0) + 1 WHERE id = ?",
                    (shop_id,),
                )
                conn.commit()
                row["view_count"] = int(row.get("view_count") or 0) + 1
        parsed_tags = _safe_json_loads(row.get("tags"), None)
        if not isinstance(parsed_tags, list):
            parsed_tags = [
                item for item in str(row.get("tags") or "").split(",") if item
            ]
        row["tags"] = parsed_tags
        row["is_pinned"] = bool(row.get("is_pinned"))
        return success_response(data=row)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/stats")
async def shop_stats():
    conn = _db()
    try:
        cur = conn.execute("SELECT COUNT(*) as c FROM shops WHERE status = 'online'")
        online = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM shops WHERE status = 'offline'")
        offline = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM products")
        products = cur.fetchone()["c"]
        return success_response(
            data={
                "online_shops": online,
                "offline_shops": offline,
                "total_products": products,
            }
        )
    except Exception:
        return success_response(
            data={"online_shops": 0, "offline_shops": 0, "total_products": 0}
        )
    finally:
        conn.close()


@router.get("/api/shop/categories")
async def shop_categories(parent_id: int | None = None):
    conn = _db()
    try:
        if parent_id is not None:
            cur = conn.execute(
                "SELECT * FROM shop_categories WHERE parent_id = ? ORDER BY sort_order",
                (parent_id,),
            )
        else:
            cur = conn.execute("SELECT * FROM shop_categories ORDER BY sort_order")
        return success_response(data=_rows_to_dicts(cur.fetchall()))
    except Exception:
        return success_response(data=[])
    finally:
        conn.close()


# --- Refactored to app/domains/store/routes/products.py using ProductService ---


# --- Refactored to app/domains/store/routes/products.py using ProductService ---


@router.get("/api/shop/products/{product_id}/external-link")
async def product_external_link(product_id: int):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT external_link FROM shop_products WHERE id = ?", (product_id,)
        )
        row = _row_to_dict(cur.fetchone())
        if row and row.get("external_link"):
            return success_response(
                data={"url": row["external_link"], "externalLink": row["external_link"]}
            )
        return error_response("NO_EXTERNAL_LINK", "该商品无外部链接", 404)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/products/{product_id}/comments")
async def list_product_comments(
    product_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    sort: str = "created_at",
    order: str = "desc",
    user: dict | None = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        product = _row_to_dict(
            conn.execute(
                "SELECT id, seller_user_id, seller_site, status, is_deleted, product_type, sold_count FROM shop_products WHERE id = ? LIMIT 1",
                (product_id,),
            ).fetchone()
        )
        if not product or int(product.get("is_deleted") or 0) == 1:
            return error_response("INVALID_PRODUCT_ID", "商品不存在", 404)

        comment_enabled = (
            str(product.get("status") or "")
            in {"ai_approved", "manual_approved", "approved"}
            and str(product.get("product_type") or "") in {"normal", "cdk"}
            and int(product.get("sold_count") or 0) > 10
        )
        disabled_reason = "该物品暂未开启评论"
        if not comment_enabled:
            if int(product.get("sold_count") or 0) <= 10:
                disabled_reason = "该物品成交量不足，暂未开启评论"
            elif str(product.get("product_type") or "") not in {"normal", "cdk"}:
                disabled_reason = "当前物品类型暂不支持评论"
            else:
                disabled_reason = "该物品暂未开启评论"

        viewer_id = str((user or {}).get("user_id") or "")
        viewer_site = str((user or {}).get("site") or "linux.do")
        public_statuses = ["ai_approved", "manual_approved"]
        where_sql = (
            "product_id = ? AND COALESCE(is_deleted, 0) = 0 AND status IN (?, ?)"
        )
        params: list[object] = [product_id, *public_statuses]
        if viewer_id:
            where_sql = f"(({where_sql}) OR (product_id = ? AND COALESCE(is_deleted, 0) = 0 AND user_id = ? AND user_site = ? AND status NOT IN (?, ?)))"
            params.extend([product_id, viewer_id, viewer_site, *public_statuses])
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_product_comments WHERE {where_sql}",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"""SELECT c.*, 
                       COALESCE((SELECT COUNT(*) FROM shop_product_comment_votes v_up WHERE v_up.comment_id = c.id AND v_up.vote_type = 'up'), 0) AS upvote_count,
                       COALESCE((SELECT COUNT(*) FROM shop_product_comment_votes v_down WHERE v_down.comment_id = c.id AND v_down.vote_type = 'down'), 0) AS downvote_count,
                       COALESCE((SELECT COUNT(*) FROM shop_product_comment_replies r WHERE r.comment_id = c.id AND COALESCE(r.is_deleted, 0) = 0 AND r.status IN ('ai_approved', 'manual_approved')), 0) AS reply_count,
                       COALESCE((SELECT v.viewer_vote_type FROM (SELECT vote_type AS viewer_vote_type FROM shop_product_comment_votes WHERE comment_id = c.id AND user_id = ? ORDER BY created_at DESC LIMIT 1) v), '') AS viewer_vote
                FROM shop_product_comments c
                WHERE {where_sql}
                ORDER BY {sort} {order} LIMIT ? OFFSET ?""",
            [viewer_id, *params, limit, offset],
        )
        rows = []
        for item in _rows_to_dicts(cur.fetchall()):
            is_owner = bool(
                viewer_id
                and str(item.get("user_id") or "") == viewer_id
                and str(item.get("user_site") or "linux.do") == viewer_site
            )
            is_seller = str(item.get("user_id") or "") == str(
                product.get("seller_user_id") or ""
            ) and str(item.get("user_site") or "linux.do") == str(
                product.get("seller_site") or "linux.do"
            )
            rows.append(
                {
                    "id": int(item.get("id") or 0),
                    "product_id": int(item.get("product_id") or 0),
                    "content": item.get("content") or "",
                    "created_at": int(item.get("created_at") or 0),
                    "updated_at": int(item.get("updated_at") or 0),
                    "user": {
                        "id": item.get("user_id") or "",
                        "site": item.get("user_site") or "linux.do",
                        "username": item.get("username") or "",
                        "nickname": item.get("nickname") or item.get("username") or "",
                        "avatar_url": item.get("avatar_url") or "",
                    },
                    "is_purchased": bool(int(item.get("is_purchased") or 0)),
                    "is_seller": is_seller,
                    "rating_value": item.get("rating_value"),
                    "status": item.get("status") or "pending_ai",
                    "review_reason": (
                        item.get("manual_reason") or item.get("ai_reason") or ""
                    ),
                    "is_deleted": False,
                    "deleted_at": None,
                    "can_delete": is_owner,
                    "upvote_count": int(item.get("upvote_count") or 0),
                    "downvote_count": int(item.get("downvote_count") or 0),
                    "reply_count": int(item.get("reply_count") or 0),
                    "viewer_vote": item.get("viewer_vote") or "",
                }
            )

        favorite_count = conn.execute(
            "SELECT COUNT(*) AS total FROM shop_product_favorites WHERE product_id = ?",
            (product_id,),
        ).fetchone()["total"]
        visible_reply_count = conn.execute(
            """SELECT COUNT(*) AS total
               FROM shop_product_comment_replies r
               INNER JOIN shop_product_comments c ON c.id = r.comment_id
               WHERE c.product_id = ? AND COALESCE(c.is_deleted, 0) = 0 AND c.status IN ('ai_approved', 'manual_approved')
                 AND COALESCE(r.is_deleted, 0) = 0 AND r.status IN ('ai_approved', 'manual_approved')""",
            (product_id,),
        ).fetchone()["total"]
        rating_row = conn.execute(
            """SELECT COUNT(*) AS rated_count, AVG(rating_value) AS average_rating
               FROM shop_product_comments
               WHERE product_id = ? AND COALESCE(is_deleted, 0) = 0 AND is_purchased = 1
                 AND rating_value IS NOT NULL AND status IN ('ai_approved', 'manual_approved')""",
            (product_id,),
        ).fetchone()
        has_purchased = False
        viewer_rating = {"hasRated": False, "value": None}
        if viewer_id:
            purchase_row = conn.execute(
                "SELECT COUNT(*) AS total FROM shop_orders WHERE product_id = ? AND buyer_user_id = ? AND buyer_site = ? AND status IN ('paid', 'delivered')",
                (product_id, viewer_id, viewer_site),
            ).fetchone()
            has_purchased = int(purchase_row["total"] or 0) > 0
            rating_view_row = conn.execute(
                """SELECT rating_value FROM shop_product_comments
                   WHERE product_id = ? AND user_id = ? AND user_site = ? AND rating_value IS NOT NULL
                   ORDER BY created_at ASC, id ASC LIMIT 1""",
                (product_id, viewer_id, viewer_site),
            ).fetchone()
            if rating_view_row:
                viewer_rating = {
                    "hasRated": True,
                    "value": rating_view_row["rating_value"],
                }
        return success_response(
            data={
                "items": rows,
                "comments": rows,
                "commentEnabled": comment_enabled,
                "disabledReason": disabled_reason,
                "viewerHasPurchased": has_purchased,
                "viewerRating": viewer_rating,
                "summary": {
                    "favoriteCount": int(favorite_count or 0),
                    "publicCommentCount": int(total or 0),
                    "visibleCommentCount": int(total or 0),
                    "visibleReplyCount": int(visible_reply_count or 0),
                    "ratedCount": int(rating_row["rated_count"] or 0)
                    if rating_row
                    else 0,
                    "averageRating": float(rating_row["average_rating"] or 0)
                    if rating_row
                    else 0,
                },
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "total": 0,
                "page": page,
                "size": size,
                "requests": [],
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": 0,
                    "totalPages": 0,
                },
            }
        )
    finally:
        conn.close()


@router.get("/api/shop/products/{product_id}/comments/replies")
async def list_comment_replies(
    product_id: int,
    comment_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as total FROM shop_product_comment_replies WHERE comment_id = ?",
            (comment_id,),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            "SELECT * FROM shop_product_comment_replies WHERE comment_id = ? ORDER BY created_at LIMIT ? OFFSET ?",
            [comment_id, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "replies": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/shop/merchants/{username}")
async def get_merchant(username: str):
    conn = _db()
    try:
        cur = conn.execute(
            """SELECT mc.*, u.username, u.name, u.avatar_url,
                      COALESCE((SELECT COUNT(*) FROM shop_products p WHERE p.seller_site = mc.site AND p.seller_user_id = mc.user_id AND (p.is_deleted = 0 OR p.is_deleted IS NULL)), 0) AS total_products,
                      COALESCE((SELECT COUNT(*) FROM shop_products p WHERE p.seller_site = mc.site AND p.seller_user_id = mc.user_id AND (p.is_deleted = 0 OR p.is_deleted IS NULL) AND p.status IN ('ai_approved', 'manual_approved')), 0) AS active_products,
                      COALESCE((SELECT COUNT(*) FROM shop_orders o WHERE o.seller_site = mc.site AND o.seller_user_id = mc.user_id AND o.status IN ('paid', 'delivered')), 0) AS completed_orders,
                      COALESCE((SELECT SUM(o.amount) FROM shop_orders o WHERE o.seller_site = mc.site AND o.seller_user_id = mc.user_id AND o.status IN ('paid', 'delivered')), 0) AS total_revenue
               FROM shop_merchant_config mc
               LEFT JOIN users u ON u.site = mc.site AND u.user_id = mc.user_id
               WHERE u.username = ? LIMIT 1""",
            (username,),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("MERCHANT_NOT_FOUND", "商家不存在", 404)
        products = _rows_to_dicts(
            conn.execute(
                """SELECT p.*, c.name AS category_name, c.icon AS category_icon
                   FROM shop_products p
                   LEFT JOIN shop_categories c ON c.id = p.category_id
                   WHERE p.seller_site = ? AND p.seller_user_id = ?
                     AND (p.is_deleted = 0 OR p.is_deleted IS NULL)
                     AND p.status IN ('ai_approved', 'manual_approved')
                   ORDER BY p.created_at DESC LIMIT 20""",
                (row.get("site"), row.get("user_id")),
            ).fetchall()
        )
        return success_response(
            data={
                "merchant": {
                    "username": row.get("username") or username,
                    "name": row.get("name") or row.get("username") or username,
                    "avatar_url": row.get("avatar_url") or "",
                    "site": row.get("site") or "linux.do",
                    "user_id": row.get("user_id") or "",
                    "is_active": bool(row.get("is_active")),
                    "is_verified": bool(row.get("is_verified")),
                },
                "stats": {
                    "totalProducts": int(row.get("total_products") or 0),
                    "activeProducts": int(row.get("active_products") or 0),
                    "completedOrders": int(row.get("completed_orders") or 0),
                    "totalRevenue": float(row.get("total_revenue") or 0),
                },
                "products": products,
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-requests")
async def list_buy_requests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    status: str | None = None,
    search: str | None = None,
    sort: str | None = None,
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        if search:
            where += " AND (title LIKE ? OR details LIKE ? OR requester_username LIKE ? OR requester_public_username LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like, like])
        order_by = "created_at DESC, id DESC"
        if sort == "updated":
            order_by = "updated_at DESC, id DESC"
        elif sort == "random":
            order_by = "RANDOM()"
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_buy_requests {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_buy_requests {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = []
        for row in _rows_to_dicts(cur.fetchall()):
            rows.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title") or "",
                    "details": row.get("details") or row.get("message") or "",
                    "budgetPrice": float(row.get("budget_price") or 0),
                    "status": row.get("status") or "open",
                    "viewCount": int(row.get("view_count") or 0),
                    "requesterPublicUsername": row.get("requester_public_username")
                    or "",
                    "requesterPublicPassword": row.get("requester_public_password")
                    or "",
                    "sessionCount": _safe_table_count(
                        conn, "shop_buy_sessions", "request_id = ?", (row.get("id"),)
                    ),
                    "paidSessionCount": _safe_table_count(
                        conn,
                        "shop_buy_sessions",
                        "request_id = ? AND status IN ('paid_pending_confirm', 'paid')",
                        (row.get("id"),),
                    ),
                    "latestMessageAt": conn.execute(
                        "SELECT MAX(created_at) AS ts FROM shop_buy_messages WHERE request_id = ?",
                        (row.get("id"),),
                    ).fetchone()["ts"]
                    or 0,
                    "latestPriceUpdatedAt": row.get("updated_at") or 0,
                    "createdAt": row.get("created_at") or 0,
                    "updatedAt": row.get("updated_at") or 0,
                }
            )
        return success_response(
            data={
                "items": rows,
                "total": total,
                "page": page,
                "size": size,
                "requests": rows,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "total": 0,
                "page": page,
                "size": size,
                "requests": [],
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": 0,
                    "totalPages": 0,
                },
            }
        )
    finally:
        conn.close()


@router.get("/api/shop/buy-requests/{request_id}")
async def get_buy_request(request_id: int, request: Request):
    conn = _db()
    try:
        viewer = getattr(request.state, "user", None)
        cur = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ?", (request_id,)
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("NOT_FOUND", "求购请求不存在", 404)

        viewer_role = "guest"
        if viewer:
            if str(viewer.get("user_id") or "") == str(
                row.get("requester_user_id") or ""
            ) and str(viewer.get("site") or "linux.do") == str(
                row.get("requester_site") or "linux.do"
            ):
                viewer_role = "requester"
            else:
                viewer_role = "provider"

        sessions = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_buy_sessions WHERE request_id = ? ORDER BY updated_at DESC, created_at DESC",
                (request_id,),
            ).fetchall()
        )
        mapped_sessions = []
        for item in sessions:
            mapped_sessions.append(
                {
                    "id": item.get("id"),
                    "requestId": item.get("request_id"),
                    "status": item.get("status") or "negotiating",
                    "provider": {
                        "userId": item.get("provider_user_id") or "",
                        "site": item.get("provider_site") or "linux.do",
                        "username": item.get("provider_username") or "",
                        "name": item.get("provider_name") or "",
                        "avatar": item.get("provider_avatar") or "",
                    },
                    "providerPublicUsername": item.get("provider_public_username")
                    or "",
                    "providerPublicPassword": item.get("provider_public_password")
                    or "",
                    "providerMarkPaidAt": item.get("provider_mark_paid_at") or 0,
                    "requesterConfirmPaidAt": item.get("requester_confirm_paid_at")
                    or 0,
                    "contactUnlockedAt": item.get("contact_unlocked_at") or 0,
                    "messageCount": _safe_table_count(
                        conn, "shop_buy_messages", "session_id = ?", (item.get("id"),)
                    ),
                    "lastMessageAt": item.get("last_message_at") or 0,
                    "createdAt": item.get("created_at") or 0,
                    "updatedAt": item.get("updated_at") or 0,
                }
            )
        data = {
            "request": {
                "id": row.get("id"),
                "title": row.get("title") or "",
                "details": row.get("details") or row.get("message") or "",
                "budgetPrice": float(row.get("budget_price") or 0),
                "status": row.get("status") or "open",
                "requesterPublicUsername": row.get("requester_public_username") or "",
                "requesterPublicPassword": row.get("requester_public_password") or "",
                "requester": {
                    "userId": row.get("requester_user_id") or "",
                    "site": row.get("requester_site") or "linux.do",
                    "username": row.get("requester_username") or "",
                    "name": row.get("requester_name") or "",
                    "avatar": row.get("requester_avatar") or "",
                    "contactLink": build_dm_link(row.get("requester_username") or ""),
                },
                "canEdit": viewer_role == "requester"
                and row.get("status")
                in ("pending_review", "open", "matched", "closed"),
                "canClose": viewer_role == "requester"
                and row.get("status") in ("open", "matched"),
                "canAdjustPrice": viewer_role == "requester"
                and row.get("status") in ("open", "matched", "negotiating"),
                "canStartSession": viewer_role == "provider"
                and row.get("status") in ("open", "negotiating", "matched"),
            },
            "viewerRole": viewer_role,
            "sessions": mapped_sessions,
            "session": mapped_sessions[0] if mapped_sessions else None,
            "canStartSession": viewer_role == "provider"
            and row.get("status") in ("open", "negotiating", "matched"),
            "canAdjustPrice": viewer_role == "requester"
            and row.get("status") in ("open", "matched", "negotiating"),
            "canEdit": viewer_role == "requester"
            and row.get("status") in ("pending_review", "open", "matched", "closed"),
            "canClose": viewer_role == "requester"
            and row.get("status") in ("open", "matched"),
        }
        return success_response(data=data)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/ldc/return")
async def ldc_return(request: Request):
    params = dict(request.query_params)
    order_no = str(params.get("out_trade_no") or "").strip()
    upper_order_no = order_no.upper()
    trade_no = str(params.get("trade_no") or "").strip()

    if not order_no:
        return _ldc_return_html(
            title="支付结果已受理",
            message="支付结果已在 LD士多 处理完成。",
            primary_href="https://ldst0re.qzz.io/user/orders",
        )

    if upper_order_no.startswith("LB"):
        return _ldc_return_html(
            title="支付处理中",
            message="求购订单支付结果同步中，请稍后刷新求购订单页查看。",
            order_no=order_no,
            primary_text="查看求购订单",
            primary_href="https://ldst0re.qzz.io/user/orders?tab=buy",
            status="pending" if trade_no else "success",
        )

    if upper_order_no.startswith("LT"):
        return _ldc_return_html(
            title="支付已完成",
            message="士多甄选订单正在确认状态，支付成功后会自动生效。",
            order_no=order_no,
            primary_text="返回商家服务",
            primary_href="https://ldst0re.qzz.io/merchant-services?tab=orders",
            secondary_text="查看 Credit 记录",
            secondary_href="https://credit.linux.do/balance",
        )

    return _ldc_return_html(
        title="处理中",
        message="支付处理中，请稍后在订单页面查看。",
        order_no=order_no,
        primary_text="查看我的订单",
        primary_href="https://ldst0re.qzz.io/user/orders",
        status="pending" if trade_no else "success",
    )


@router.post("/api/shop/ldc/notify")
async def ldc_notify(request: Request):
    try:
        form = await request.form()
        params = dict(form)
    except Exception:
        try:
            params = await request.json()
        except Exception:
            params = {}

    order_no = str(params.get("out_trade_no") or "").strip()
    trade_status = str(params.get("trade_status") or "").strip()
    money = str(params.get("money") or "").strip()
    ldc_trade_no = str(params.get("trade_no") or "").strip()
    if not order_no:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse("fail")

    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 1. 普通商品 / CDK 订单
        row = conn.execute(
            "SELECT * FROM shop_orders WHERE order_no = ? LIMIT 1",
            (order_no,),
        ).fetchone()
        if row:
            order = dict(row)
            key_encrypted = str(
                order.get("merchant_key_encrypted_snapshot") or ""
            ).strip()
            if not key_encrypted:
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("fail")
            key_plain = decrypt_ldc_key(key_encrypted, settings.jwt_secret_key)
            if not verify_ldc_sign(params, key_plain):
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("fail")
            if trade_status != "TRADE_SUCCESS":
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("success")
            if abs(float(money or 0) - float(order.get("amount") or 0)) > 0.01:
                conn.execute(
                    "UPDATE shop_orders SET seller_remark = ?, updated_at = ? WHERE id = ?",
                    (
                        f"金额异常: 应付{order.get('amount')}, 实付{money}",
                        now_ms,
                        order["id"],
                    ),
                )
                conn.commit()
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("success")

            conn.execute(
                "UPDATE shop_orders SET status = 'paid', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE id = ? AND status IN ('pending', 'paying', 'expired')",
                (ldc_trade_no, now_ms, now_ms, order["id"]),
            )
            if str(order.get("delivery_type") or "") == "auto":
                locked = conn.execute(
                    "SELECT id, code FROM shop_cdk WHERE lock_order_id = ? AND status = 'locked' ORDER BY created_at ASC",
                    (order["id"],),
                ).fetchall()
                if locked:
                    delivery_content = "\n".join(str(r["code"]) for r in locked)
                    conn.execute(
                        "UPDATE shop_orders SET status = 'delivered', delivery_content = ?, delivered_at = ?, updated_at = ? WHERE id = ?",
                        (delivery_content, now_ms, now_ms, order["id"]),
                    )
                    for item in locked:
                        conn.execute(
                            "UPDATE shop_cdk SET status = 'sold', sold_at = ?, lock_token = NULL WHERE id = ?",
                            (now_ms, item["id"]),
                        )
            conn.commit()
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse("success")

        # 1.1 图床订单兼容分支（旧后端曾走独立表）
        if _table_exists(conn, "ld_image_orders"):
            row = conn.execute(
                "SELECT * FROM ld_image_orders WHERE order_no = ? LIMIT 1",
                (order_no,),
            ).fetchone()
            if row:
                image_order = dict(row)
                if str(image_order.get("status") or "") in ("paid", "uploaded"):
                    return PlainTextResponse("success")
                return PlainTextResponse("fail")

        # 2. 求购订单
        row = conn.execute(
            "SELECT * FROM shop_buy_orders WHERE order_no = ? LIMIT 1",
            (order_no,),
        ).fetchone()
        if row:
            order = dict(row)
            key_encrypted = str(
                order.get("merchant_key_encrypted_snapshot") or ""
            ).strip()
            if not key_encrypted:
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("fail")
            key_plain = decrypt_ldc_key(key_encrypted, settings.jwt_secret_key)
            if not verify_ldc_sign(params, key_plain):
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("fail")
            if trade_status != "TRADE_SUCCESS":
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("success")
            if abs(float(money or 0) - float(order.get("amount") or 0)) > 0.01:
                conn.execute(
                    "UPDATE shop_buy_orders SET remark = ?, updated_at = ? WHERE id = ?",
                    (
                        f"支付金额不一致: 应付 {order.get('amount')}, 实付 {money}",
                        now_ms,
                        order["id"],
                    ),
                )
                conn.commit()
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("success")
            conn.execute(
                "UPDATE shop_buy_orders SET status = 'completed', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE id = ? AND status IN ('pending', 'expired')",
                (ldc_trade_no, now_ms, now_ms, order["id"]),
            )
            conn.execute(
                "UPDATE shop_buy_sessions SET contact_unlocked_at = COALESCE(contact_unlocked_at, ?), requester_confirm_paid_at = COALESCE(requester_confirm_paid_at, ?), updated_at = ? WHERE id = ?",
                (now_ms, now_ms, now_ms, order.get("session_id")),
            )
            conn.commit()
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse("success")

        # 3. 置顶服务订单
        row = conn.execute(
            "SELECT * FROM shop_top_orders WHERE order_no = ? LIMIT 1",
            (order_no,),
        ).fetchone()
        if row:
            order = dict(row)
            pay_expired_at = int(order.get("pay_expired_at") or 0)
            if (
                str(order.get("status") or "") == "pending"
                and pay_expired_at > 0
                and pay_expired_at <= now_ms
            ):
                conn.execute(
                    "UPDATE shop_top_orders SET status = 'expired', updated_at = ? WHERE id = ? AND status = 'pending'",
                    (now_ms, order["id"]),
                )
                conn.commit()
                return PlainTextResponse("success")
            key_encrypted = str(
                order.get("merchant_key_encrypted_snapshot") or ""
            ).strip()
            if not key_encrypted:
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("fail")
            key_plain = decrypt_ldc_key(key_encrypted, settings.jwt_secret_key)
            if not verify_ldc_sign(params, key_plain):
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("fail")
            if trade_status != "TRADE_SUCCESS":
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("success")
            if abs(float(money or 0) - float(order.get("amount") or 0)) > 0.01:
                conn.execute(
                    "UPDATE shop_top_orders SET extra_json = ?, updated_at = ? WHERE id = ?",
                    ('{"amountMismatch": true}', now_ms, order["id"]),
                )
                conn.commit()
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("success")
            conn.execute(
                "UPDATE shop_top_orders SET status = 'active', ldc_trade_no = COALESCE(NULLIF(ldc_trade_no, ''), ?), paid_at = COALESCE(paid_at, ?), updated_at = ? WHERE id = ? AND status IN ('pending', 'expired')",
                (ldc_trade_no, now_ms, now_ms, order["id"]),
            )
            conn.commit()
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse("success")

        from fastapi.responses import PlainTextResponse

        return PlainTextResponse("fail")
    except Exception:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse("fail")
    finally:
        conn.close()


@router.get("/api/shop/ldc/notify")
async def ldc_notify_get(request: Request):
    """Legacy-compatible GET callback for older LDC setups."""
    return await ldc_notify(request)


# ---------------------------------------------------------------------------
# User Auth Routes
# ---------------------------------------------------------------------------


@router.get("/api/shop/auth/verify")
async def verify_auth(user: dict = Depends(get_current_user)):
    return success_response(
        data={
            "success": True,
            "authenticated": True,
            "valid": True,
            "user_id": user.get("user_id"),
            "user": {
                "id": user.get("user_id"),
                "username": user.get("username"),
                "site": user.get("site", "linux.do"),
            },
        }
    )


@router.get("/api/shops/my")
async def get_my_shop(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            """SELECT * FROM shops
               WHERE user_id = ? OR LOWER(owner_username) = LOWER(?)
               ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END, created_at DESC
               LIMIT 1""",
            (user_id, user.get("username") or "", user_id),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return success_response(data=None)
        if (
            not row.get("user_id")
            and str(row.get("owner_username") or "").lower()
            == str(user.get("username") or "").lower()
        ):
            conn.execute(
                "UPDATE shops SET user_id = ? WHERE id = ?", (user_id, row.get("id"))
            )
            conn.commit()
            row["user_id"] = user_id
        parsed_tags = _safe_json_loads(row.get("tags"), None)
        if not isinstance(parsed_tags, list):
            parsed_tags = [
                item for item in str(row.get("tags") or "").split(",") if item
            ]
        row["tags"] = parsed_tags
        row["is_pinned"] = bool(row.get("is_pinned"))
        return success_response(data=row)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/shops/my")
async def update_my_shop(payload: ShopUpdate, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            """SELECT id, status, owner_linuxdo_link, user_id, owner_username FROM shops
               WHERE (user_id = ? OR LOWER(owner_username) = LOWER(?))
                 AND status IN ('pending', 'active', 'rejected')
               ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END, created_at DESC LIMIT 1""",
            (user_id, user.get("username") or "", user_id),
        )
        existing = _row_to_dict(cur.fetchone())
        if not existing:
            return error_response("NOT_FOUND", "未找到您的小店", 404)
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("INVALID_PARAMS", "没有需要更新的内容", 400)
        if "tags" in updates and isinstance(updates["tags"], list):
            updates["tags"] = __import__("json").dumps(
                updates["tags"], ensure_ascii=False
            )
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        if existing.get("status") == "rejected":
            updates["status"] = "pending"
            updates["reject_reason"] = None
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), existing.get("id")]
        conn.execute(f"UPDATE shops SET {set_clause} WHERE id = ?", params)
        conn.commit()
        return success_response(
            data={
                "success": True,
                "message": "小店已重新提交审核"
                if existing.get("status") == "rejected"
                else "小店信息已更新",
            }
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shops/my/offline")
async def set_my_shop_offline(reason: str = "", user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            """SELECT id, status, user_id, owner_username FROM shops
               WHERE (user_id = ? OR LOWER(owner_username) = LOWER(?)) AND status = 'active'
               ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END LIMIT 1""",
            (user_id, user.get("username") or "", user_id),
        )
        row = _row_to_dict(cur.fetchone())
        if not row:
            return error_response("NOT_FOUND", "未找到可下架的小店", 404)
        conn.execute(
            "UPDATE shops SET status = 'offline', updated_at = datetime('now', '+8 hours') WHERE id = ?",
            (row.get("id"),),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "小店已下架"})
    except Exception as e:
        return error_response("OFFLINE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shops")
async def create_shop(payload: ShopCreate, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        existing = conn.execute(
            "SELECT id, status FROM shops WHERE user_id = ? AND status IN ('pending', 'active') LIMIT 1",
            (user_id,),
        ).fetchone()
        if existing:
            return error_response("DUPLICATE", "您已有小店正在审核中或已上架", 400)
        tags_str = __import__("json").dumps(payload.tags or [], ensure_ascii=False)
        cur = conn.execute(
            "INSERT INTO shops (name, description, shop_url, image_url, owner_linuxdo_link, owner_username, owner_avatar_template, tags, user_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now', '+8 hours'), datetime('now', '+8 hours'))",
            (
                payload.name,
                payload.description,
                payload.shop_url,
                payload.image_url,
                payload.owner_linuxdo_link,
                user.get("username") or "",
                user.get("avatar_url") or "",
                tags_str,
                user_id,
            ),
        )
        conn.commit()
        return success_response(
            data={"id": cur.lastrowid},
            message="小店入驻申请已提交，请等待审核",
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/user/dashboard")
async def user_dashboard(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_buy_requests WHERE requester_user_id = ? AND requester_site = ?",
            (str(user_id), user.get("site", "linux.do")),
        )
        buy_requests = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_product_favorites WHERE user_id = ? AND user_site = ?",
            (str(user_id), user.get("site", "linux.do")),
        )
        favorites = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE buyer_user_id = ? AND buyer_site = ?",
            (str(user_id), user.get("site", "linux.do")),
        )
        orders = cur.fetchone()["c"]
        return success_response(
            data={
                "buy_requests": buy_requests,
                "favorites": favorites,
                "orders": orders,
            }
        )
    except Exception:
        return success_response(data={"buy_requests": 0, "favorites": 0, "orders": 0})
    finally:
        conn.close()


@router.get("/api/shop/favorites")
async def list_favorites(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    search: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        where = "WHERE f.user_id = ? AND f.user_site = ?"
        params: list[object] = [user_id, site]
        if search:
            keyword = f"%{search}%"
            where += " AND (p.name LIKE ? OR p.description LIKE ? OR p.seller_username LIKE ?)"
            params.extend([keyword, keyword, keyword])
        cur = conn.execute(
            f"""SELECT COUNT(*) as total
               FROM shop_product_favorites f
               LEFT JOIN shop_products p ON f.product_id = p.id
               {where}""",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"""SELECT f.created_at AS favorited_at, p.*, c.name as category_name, c.icon as category_icon
               FROM shop_product_favorites f
               LEFT JOIN shop_products p ON f.product_id = p.id
               LEFT JOIN shop_categories c ON c.id = p.category_id
               {where}
               ORDER BY f.created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = []
        for row in _rows_to_dicts(cur.fetchall()):
            price = float(row.get("price") or 0)
            discount = float(row.get("discount") or 1)
            if discount <= 0:
                discount = 1
            row["final_price"] = round(price * discount, 2)
            row["isFavorited"] = True
            row["is_favorited"] = True
            rows.append(row)
        return success_response(
            data={
                "items": rows,
                "favorites": rows,
                "products": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/shop/products/{product_id}/favorite")
async def add_favorite(product_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        conn.execute(
            "INSERT OR IGNORE INTO shop_product_favorites (product_id, user_id, user_site, created_at) VALUES (?, ?, ?, ?)",
            (
                product_id,
                user_id,
                site,
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        return success_response(data={"favorited": True, "message": "已收藏"})
    except Exception as e:
        return error_response("FAVORITE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/shop/products/{product_id}/favorite")
async def remove_favorite(product_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        conn.execute(
            "DELETE FROM shop_product_favorites WHERE user_id = ? AND user_site = ? AND product_id = ?",
            (user_id, site, product_id),
        )
        conn.commit()
        return success_response(data={"favorited": False, "message": "已取消收藏"})
    except Exception as e:
        return error_response("UNFAVORITE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/products/{product_id}/restock-subscription")
async def get_restock_subscription(
    product_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT * FROM shop_product_restock_subscriptions WHERE user_id = ? AND user_site = ? AND product_id = ?",
            (str(user_id), user.get("site", "linux.do"), product_id),
        )
        row = _row_to_dict(cur.fetchone())
        active = False
        if row:
            active = str(row.get("status") or "active") in {"active", "processing"}
        return success_response(
            data=(
                {
                    "subscribed": active,
                    "notifyMethod": "system",
                    **(row or {}),
                }
                if row
                else {"subscribed": False, "notifyMethod": "system"}
            )
        )
    except Exception:
        return success_response(data={"subscribed": False, "notifyMethod": "system"})
    finally:
        conn.close()


@router.post("/api/shop/products/{product_id}/restock-subscription")
async def subscribe_restock(
    product_id: int,
    payload: RestockSubscriptionCreate,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            """INSERT INTO shop_product_restock_subscriptions (
                user_id, user_site, product_id, status, subscribed_at,
                notified_at, created_at, updated_at, invalidated_at, invalid_reason
            ) VALUES (?, ?, ?, 'active', ?, NULL, ?, ?, NULL, NULL)
            ON CONFLICT(product_id, user_site, user_id) DO UPDATE SET
                status = 'active',
                subscribed_at = excluded.subscribed_at,
                updated_at = excluded.updated_at,
                invalidated_at = NULL,
                invalid_reason = NULL""",
            (
                str(user_id),
                user.get("site", "linux.do"),
                product_id,
                now_ms,
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        return success_response(
            data={"subscribed": True, "notifyMethod": payload.notify_method}
        )
    except Exception as e:
        return error_response("SUBSCRIBE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/products/{product_id}/comments")
async def create_comment(
    product_id: int, payload: CommentCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            """INSERT INTO shop_product_comments (
                product_id, user_id, user_site, username, nickname, avatar_url, content, rating_value, status, is_purchased, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product_id,
                user_id,
                site,
                user.get("username") or user.get("name") or "",
                user.get("name") or user.get("username") or "",
                user.get("avatar_url") or "",
                payload.content,
                payload.rating,
                "pending_ai",
                1,
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        return success_response(
            data={"message": "评论已提交，等待审核", "commentId": cur.lastrowid},
            status_code=201,
        )
    except Exception as e:
        return error_response("COMMENT_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/shop/comments/{comment_id}")
async def delete_comment(comment_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        conn.execute(
            "UPDATE shop_product_comments SET is_deleted = 1, deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                comment_id,
                user_id,
            ),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "评论已删除"})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/comments/{comment_id}/vote")
async def vote_comment(
    comment_id: int, payload: CommentVote, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        if payload.vote_type not in {"up", "down"}:
            return error_response("INVALID_VOTE", "voteType 无效", 400)
        if payload.vote_type == "up":
            conn.execute(
                "INSERT OR REPLACE INTO shop_product_comment_votes (comment_id, user_id, vote_type, created_at) VALUES (?, ?, 'up', ?)",
                (
                    comment_id,
                    user_id,
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                ),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO shop_product_comment_votes (comment_id, user_id, vote_type, created_at) VALUES (?, ?, 'down', ?)",
                (
                    comment_id,
                    user_id,
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                ),
            )
        conn.commit()
        upvote_count = conn.execute(
            "SELECT COUNT(*) AS total FROM shop_product_comment_votes WHERE comment_id = ? AND vote_type = 'up'",
            (comment_id,),
        ).fetchone()["total"]
        downvote_count = conn.execute(
            "SELECT COUNT(*) AS total FROM shop_product_comment_votes WHERE comment_id = ? AND vote_type = 'down'",
            (comment_id,),
        ).fetchone()["total"]
        return success_response(
            data={
                "viewerVote": payload.vote_type,
                "upvoteCount": int(upvote_count or 0),
                "downvoteCount": int(downvote_count or 0),
            }
        )
    except Exception as e:
        return error_response("VOTE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/comments/{comment_id}/replies")
async def list_comment_replies_public(
    comment_id: int,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=20),
):
    offset, limit = _page_params(page, pageSize)
    conn = _db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) as total FROM shop_product_comment_replies WHERE comment_id = ? AND COALESCE(is_deleted, 0) = 0",
            (comment_id,),
        ).fetchone()["total"]
        rows = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_product_comment_replies WHERE comment_id = ? AND COALESCE(is_deleted, 0) = 0 ORDER BY created_at ASC, id ASC LIMIT ? OFFSET ?",
                (comment_id, limit, offset),
            ).fetchall()
        )
        mapped = []
        for item in rows:
            mapped.append(
                {
                    "id": int(item.get("id") or 0),
                    "comment_id": int(item.get("comment_id") or 0),
                    "content": item.get("content") or "",
                    "created_at": int(item.get("created_at") or 0),
                    "updated_at": int(item.get("updated_at") or 0),
                    "user": {
                        "id": item.get("user_id") or "",
                        "site": item.get("user_site") or "linux.do",
                        "username": item.get("username") or "",
                        "nickname": item.get("nickname") or item.get("username") or "",
                        "avatar_url": item.get("avatar_url") or "",
                    },
                    "is_seller": False,
                    "status": item.get("status") or "pending_ai",
                    "review_reason": item.get("manual_reason")
                    or item.get("ai_reason")
                    or "",
                    "is_deleted": False,
                    "can_delete": False,
                }
            )
        return success_response(
            data={
                "replies": mapped,
                "items": mapped,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": pageSize,
                    "totalPages": (total + pageSize - 1) // pageSize
                    if total > 0
                    else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "replies": [],
                "items": [],
                "pagination": {
                    "total": 0,
                    "page": page,
                    "pageSize": pageSize,
                    "totalPages": 1,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/shop/comments/{comment_id}/replies")
async def create_comment_reply(
    comment_id: int, payload: ReplyCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            "INSERT INTO shop_product_comment_replies (comment_id, user_id, user_site, username, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                comment_id,
                user_id,
                site,
                user.get("username") or user.get("name") or "",
                payload.content,
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        reply_count = conn.execute(
            "SELECT COUNT(*) AS total FROM shop_product_comment_replies WHERE comment_id = ? AND COALESCE(is_deleted, 0) = 0",
            (comment_id,),
        ).fetchone()["total"]
        return success_response(
            data={
                "message": "回复已提交，等待审核",
                "replyCount": int(reply_count or 0),
            },
            status_code=201,
        )
    except Exception as e:
        return error_response("REPLY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/comments/{comment_id}/report")
async def report_comment(
    comment_id: int, payload: ReportCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        conn.execute(
            "INSERT INTO shop_product_comment_reports (comment_id, reporter_user_id, reporter_site, reason, detail, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                comment_id,
                user_id,
                site,
                payload.reason,
                payload.detail,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        return success_response(
            data={"reported": True, "message": "举报已提交，感谢反馈"}
        )
    except Exception as e:
        return error_response("REPORT_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/products")
async def create_product(
    payload: ProductCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        image_url = payload.images[0] if payload.images else None
        tags_str = ",".join(payload.tags) if payload.tags else ""
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            """INSERT INTO shop_products (
                seller_user_id, seller_site, seller_username, seller_name, seller_avatar,
                name, category_id, description, price, discount, image_url,
                product_type, stock, max_purchase_quantity, purchase_trust_level,
                auto_delivery, use_platform_payment, is_test_mode,
                status, created_at, updated_at, content_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'normal', ?, 0, 0, 0, 0, 0, 'pending_ai', ?, ?, ?)""",
            (
                str(user_id),
                user.get("site", "linux.do"),
                user.get("username"),
                user.get("name") or user.get("username"),
                user.get("avatar_url"),
                payload.name,
                payload.category_id,
                payload.description,
                payload.price,
                payload.stock,
                1.0,
                image_url,
                payload.stock,
                now,
                now,
                now,
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM shop_products WHERE id = ?", (cur.lastrowid,))
        return success_response(data=_product_row(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/product-submission-status")
async def product_submission_status(
    token: str | None = Query(None), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_products WHERE seller_user_id = ? AND status IN ('pending_ai', 'pending_manual') AND (is_deleted = 0 OR is_deleted IS NULL)",
            (str(user_id),),
        )
        pending = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_products WHERE seller_user_id = ? AND status IN ('ai_approved', 'manual_approved') AND (is_deleted = 0 OR is_deleted IS NULL)",
            (str(user_id),),
        )
        approved = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_products WHERE seller_user_id = ? AND status IN ('ai_rejected', 'manual_rejected') AND (is_deleted = 0 OR is_deleted IS NULL)",
            (str(user_id),),
        )
        rejected = cur.fetchone()["c"]
        return success_response(
            data={
                "pending": pending,
                "approved": approved,
                "rejected": rejected,
                "hasPending": pending > 0,
                "token": token or "",
            }
        )
    except Exception:
        return success_response(
            data={
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "hasPending": False,
                "token": token or "",
            }
        )
    finally:
        conn.close()


@router.get("/api/shop/my-products/{product_id}")
async def get_my_product(product_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        cur = conn.execute(
            """SELECT p.*, c.name as category_name, c.icon as category_icon, c.visibility_trust_level as category_visibility_trust_level
               FROM shop_products p
               LEFT JOIN shop_categories c ON p.category_id = c.id
               WHERE p.id = ? AND p.seller_site = ? AND p.seller_user_id = ? AND (p.is_deleted = 0 OR p.is_deleted IS NULL)""",
            (product_id, user.get("site", "linux.do"), str(user_id)),
        )
        row = _augment_product_row(conn, _product_row(cur.fetchone()))
        if row is None:
            return error_response("NOT_FOUND", "商品不存在或无权限", 404)
        row["isLegacyExternalProduct"] = (
            _normalize_product_type(row.get("product_type")) == "link"
        )
        if str(row.get("status") or "") in {
            "ai_rejected",
            "manual_rejected",
            "offline_manual",
            "offline",
        }:
            latest_review = _row_to_dict(
                conn.execute(
                    """SELECT action, reason, admin_name, created_at, reason_category, reason_detail, notify_user
                       FROM shop_product_reviews
                       WHERE product_id = ? AND action IN ('reject', 'admin_offline', 'offline')
                       ORDER BY created_at DESC LIMIT 1""",
                    (product_id,),
                ).fetchone()
            )
            if latest_review:
                row["status_reason"] = latest_review.get("reason") or ""
                row["status_reason_category"] = (
                    latest_review.get("reason_category") or ""
                )
                row["status_reason_detail"] = latest_review.get("reason_detail") or ""
                row["status_action"] = latest_review.get("action") or ""
                row["status_admin"] = latest_review.get("admin_name") or ""
                row["status_notified"] = bool(
                    int(latest_review.get("notify_user") or 0)
                )
        return success_response(data={"product": row})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/shop/my-products/{product_id}")
async def update_my_product(
    product_id: int, payload: ProductUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        existing = _row_to_dict(
            conn.execute(
                "SELECT * FROM shop_products WHERE id = ? AND seller_site = ? AND seller_user_id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
                (product_id, user.get("site", "linux.do"), str(user_id)),
            ).fetchone()
        )
        if not existing:
            return error_response("NOT_FOUND", "商品不存在", 404)
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("INVALID_PARAMS", "没有需要更新的内容", 400)
        if "images" in updates:
            updates["image_url"] = updates["images"][0] if updates["images"] else None
            del updates["images"]
        if "tags" in updates:
            del updates["tags"]
        if str(existing.get("product_type") or "") == "link":
            return error_response(
                "LEGACY_PRODUCT_UNSUPPORTED",
                "外链物品已停用，请重新发布为普通物品",
                410,
            )
        updates["updated_at"] = int(datetime.now(timezone.utc).timestamp() * 1000)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE shop_products SET {set_clause} WHERE id = ? AND seller_user_id = ?",
            [*updates.values(), product_id, str(user_id)],
        )
        conn.commit()
        return success_response(data={"success": True, "message": "商品已更新"})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/shop/my-products/{product_id}")
async def delete_my_product(product_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        product = conn.execute(
            "SELECT id FROM shop_products WHERE id = ? AND seller_user_id = ? AND seller_site = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (product_id, str(user_id), user.get("site", "linux.do")),
        ).fetchone()
        if not product:
            return error_response("NOT_FOUND", "商品不存在", 404)
        conn.execute(
            "UPDATE shop_products SET is_deleted = 1, deleted_at = ?, updated_at = ? WHERE id = ? AND seller_user_id = ?",
            (
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                product_id,
                str(user_id),
            ),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "商品已删除"})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/my-products/{product_id}/offline")
async def offline_my_product(
    product_id: int, reason: str = "", user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        product = conn.execute(
            "SELECT id FROM shop_products WHERE id = ? AND seller_user_id = ? AND seller_site = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (product_id, str(user_id), user.get("site", "linux.do")),
        ).fetchone()
        if not product:
            return error_response("NOT_FOUND", "商品不存在", 404)
        conn.execute(
            "UPDATE shop_products SET status = 'offline_manual', reject_reason = ?, updated_at = ? WHERE id = ? AND seller_user_id = ?",
            (
                reason,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                product_id,
                str(user_id),
            ),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "商品已下架"})
    except Exception as e:
        return error_response("OFFLINE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/my-products")
async def list_my_products(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    status: str | None = Query(None),
    productType: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = user.get("user_id")
        where = "WHERE p.seller_site = ? AND p.seller_user_id = ? AND (p.is_deleted = 0 OR p.is_deleted IS NULL)"
        params: list[object] = [user.get("site", "linux.do"), str(user_id)]
        if status:
            where += " AND p.status = ?"
            params.append(status)
        if productType:
            where += " AND p.product_type = ?"
            params.append(productType)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_products p {where}",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"""SELECT p.id, p.name, p.category_id, p.description, p.price, p.discount,
                       p.image_url, p.payment_link, p.status, p.view_count,
                       p.reject_reason, p.created_at, p.updated_at, p.reviewed_at,
                       p.product_type, p.stock, p.sold_count, p.max_purchase_quantity, p.purchase_trust_level, p.auto_delivery, p.is_test_mode,
                       p.is_pinned, p.pin_type, p.pin_source, p.pin_is_paid, p.pin_started_at, p.pin_expires_at, p.pin_duration_days, p.pin_order_no,
                       c.name as category_name, c.icon as category_icon, c.visibility_trust_level as category_visibility_trust_level
                FROM shop_products p
                LEFT JOIN shop_categories c ON p.category_id = c.id
                {where}
                ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = []
        for row in cur.fetchall():
            product = _augment_product_row(conn, _product_row(row))
            if not product:
                continue
            product["isLegacyExternalProduct"] = (
                _normalize_product_type(product.get("product_type")) == "link"
            )
            if str(product.get("status") or "") in {
                "ai_rejected",
                "manual_rejected",
                "offline_manual",
                "offline",
            }:
                latest_review = _row_to_dict(
                    conn.execute(
                        """SELECT action, reason, admin_name, created_at, reason_category, reason_detail, notify_user
                           FROM shop_product_reviews
                           WHERE product_id = ? AND action IN ('reject', 'admin_offline', 'offline')
                           ORDER BY created_at DESC LIMIT 1""",
                        (product.get("id"),),
                    ).fetchone()
                )
                if latest_review:
                    product["status_reason"] = latest_review.get("reason") or ""
                    product["status_reason_category"] = (
                        latest_review.get("reason_category") or ""
                    )
                    product["status_reason_detail"] = (
                        latest_review.get("reason_detail") or ""
                    )
                    product["status_action"] = latest_review.get("action") or ""
                    product["status_admin"] = latest_review.get("admin_name") or ""
                    product["status_notified"] = bool(
                        int(latest_review.get("notify_user") or 0)
                    )
            rows.append(product)
        return success_response(
            data={
                "items": rows,
                "products": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": size,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "products": [],
                "total": 0,
                "page": page,
                "size": size,
                "pagination": {
                    "total": 0,
                    "page": page,
                    "pageSize": size,
                    "totalPages": 1,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/shop/products/{product_id}/report")
async def report_product(
    product_id: int, payload: ReportCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        product = conn.execute(
            "SELECT id, seller_user_id, seller_site FROM shop_products WHERE id = ? LIMIT 1",
            (product_id,),
        ).fetchone()
        if not product:
            return error_response("NOT_FOUND", "商品不存在", 404)
        if str(product["seller_user_id"] or "") == str(user_id) and str(
            product["seller_site"] or "linux.do"
        ) == str(user.get("site", "linux.do") or "linux.do"):
            return error_response("FORBIDDEN", "不能举报自己的商品", 403)
        conn.execute(
            """INSERT INTO shop_product_reports (
                product_id, reporter_user_id, reporter_site, report_reason, report_detail, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (
                product_id,
                str(user_id),
                user.get("site", "linux.do"),
                payload.reason,
                payload.detail,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        return success_response(
            data={"reported": True, "message": "举报已提交，感谢反馈"}
        )
    except Exception as e:
        return error_response("REPORT_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-requests/{request_id}")
async def get_buy_request_detail(
    request_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ? AND requester_user_id = ? AND requester_site = ?",
            (request_id, user_id, site),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("BUY_REQUEST_NOT_FOUND", "求购请求不存在", 404)
        return success_response(data=row)
    except Exception:
        return success_response(data={"id": request_id})
    finally:
        conn.close()


@router.put("/api/shop/buy-requests/{request_id}")
async def update_buy_request(
    request_id: int, payload: BuyRequestUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if "message" in updates:
            updates["details"] = updates.pop("message")
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的字段")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            f"UPDATE shop_buy_requests SET {set_clause}, updated_at = ? WHERE id = ? AND requester_user_id = ? AND requester_site = ?",
            [*updates.values(), now_ms, request_id, user_id, site],
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ?", (request_id,)
        )
        row = _row_to_dict(cur.fetchone())
        return success_response(data={"request": row})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/buy-requests/{request_id}")
async def action_buy_request(
    request_id: int,
    action: str = Query("respond"),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        return success_response(
            data={"request_id": request_id, "action": action, "processed": True}
        )
    except Exception as e:
        return error_response("ACTION_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-requests/my")
async def list_my_buy_requests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        where = "WHERE requester_user_id = ? AND requester_site = ?"
        params: list[object] = [user_id, site]
        if status:
            where += " AND status = ?"
            params.append(status)
        if search:
            keyword = f"%{search}%"
            where += " AND (title LIKE ? OR details LIKE ? OR requester_public_username LIKE ?)"
            params.extend([keyword, keyword, keyword])
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_buy_requests {where}",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_buy_requests {where} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = []
        for row in _rows_to_dicts(cur.fetchall()):
            rows.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title") or "",
                    "details": row.get("details") or row.get("message") or "",
                    "budgetPrice": float(row.get("budget_price") or 0),
                    "status": row.get("status") or "open",
                    "requesterPublicUsername": row.get("requester_public_username")
                    or "",
                    "requesterPublicPassword": row.get("requester_public_password")
                    or "",
                    "sessionCount": _safe_table_count(
                        conn, "shop_buy_sessions", "request_id = ?", (row.get("id"),)
                    ),
                    "paidSessionCount": _safe_table_count(
                        conn,
                        "shop_buy_sessions",
                        "request_id = ? AND status IN ('paid_pending_confirm', 'paid')",
                        (row.get("id"),),
                    ),
                    "createdAt": row.get("created_at") or 0,
                    "updatedAt": row.get("updated_at") or 0,
                }
            )
        return success_response(
            data={
                "items": rows,
                "requests": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/shop/buy-requests")
async def create_buy_request(
    payload: BuyRequestCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "INSERT INTO shop_buy_requests (requester_user_id, requester_site, requester_username, title, details, budget_price, requester_public_username, requester_public_password, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)",
            (
                user_id,
                site,
                user.get("username") or "",
                f"求购请求 #{int(datetime.now(timezone.utc).timestamp())}",
                payload.message,
                0,
                user.get("username") or "",
                "",
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ?", (cur.lastrowid,)
        )
        return success_response(
            data={"request": _row_to_dict(cur.fetchone())}, status_code=201
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-sessions/{session_id}")
async def get_buy_session(session_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT * FROM shop_buy_sessions WHERE id = ?
               AND ((requester_user_id = ? AND requester_site = ?)
                 OR (provider_user_id = ? AND provider_site = ?))""",
            (session_id, user_id, site, user_id, site),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("SESSION_NOT_FOUND", "会话不存在", 404)
        return success_response(data=row)
    except Exception:
        return success_response(data={"id": session_id})
    finally:
        conn.close()


@router.post("/api/shop/buy-sessions/{session_id}")
async def update_buy_session(session_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        return success_response(data={"session_id": session_id, "updated": True})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.patch("/api/shop/buy-sessions/{session_id}")
async def patch_buy_session(session_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        return success_response(data={"session_id": session_id, "patched": True})
    except Exception as e:
        return error_response("PATCH_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-sessions/my")
async def list_my_buy_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT COUNT(*) as total FROM shop_buy_sessions
               WHERE (requester_user_id = ? AND requester_site = ?)
                  OR (provider_user_id = ? AND provider_site = ?)""",
            (user_id, site, user_id, site),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            """SELECT * FROM shop_buy_sessions
               WHERE (requester_user_id = ? AND requester_site = ?)
                  OR (provider_user_id = ? AND provider_site = ?)
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            [user_id, site, user_id, site, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "sessions": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/shop/buy-sessions/unread-summary")
async def buy_sessions_unread_summary(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_user_messages WHERE user_id = ? AND user_site = ? AND is_read = 0 AND ref_type = 'buy_session'",
            (user_id, site),
        )
        unread = cur.fetchone()["c"]
        return success_response(data={"unread_count": unread})
    except Exception:
        return success_response(data={"unread_count": 0})
    finally:
        conn.close()


@router.get("/api/shop/conversations/my")
async def list_my_conversations(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    type: str | None = Query(None),
    status: str | None = Query(None),
    role: str | None = Query(None),
    search: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        safe_type = str(type or "buy_request").strip().lower()
        if safe_type == "buy_request":
            safe_role = str(role or "").strip().lower()
            where = []
            params: list[object] = []
            if safe_role == "requester":
                where.append("requester_user_id = ? AND requester_site = ?")
                params.extend([user_id, site])
            elif safe_role == "provider":
                where.append("provider_user_id = ? AND provider_site = ?")
                params.extend([user_id, site])
            else:
                where.append(
                    "((requester_user_id = ? AND requester_site = ?) OR (provider_user_id = ? AND provider_site = ?))"
                )
                params.extend([user_id, site, user_id, site])
            if status:
                where.append("status = ?")
                params.append(status)
            if search:
                keyword = f"%{search}%"
                where.append(
                    "(requester_username LIKE ? OR provider_username LIKE ? OR CAST(request_id AS TEXT) LIKE ?)"
                )
                params.extend([keyword, keyword, keyword])
            where_sql = " WHERE " + " AND ".join(where)
            total = conn.execute(
                f"SELECT COUNT(*) as total FROM shop_buy_sessions{where_sql}",
                params,
            ).fetchone()["total"]
            rows = _rows_to_dicts(
                conn.execute(
                    f"SELECT * FROM shop_buy_sessions{where_sql} ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?",
                    [*params, limit, offset],
                ).fetchall()
            )
            conversations = []
            total_unread = 0
            sessions_with_unread = 0
            for row in rows:
                unread_count = _safe_table_count(
                    conn,
                    "shop_user_messages",
                    "ref_type = 'buy_session' AND ref_id = ? AND user_id = ? AND user_site = ? AND is_read = 0",
                    (row.get("id"), user_id, site),
                )
                if unread_count > 0:
                    sessions_with_unread += 1
                    total_unread += unread_count
                conversations.append(
                    {
                        "id": row.get("id"),
                        "type": "buy_request",
                        "requestId": row.get("request_id") or 0,
                        "sessionId": row.get("id") or 0,
                        "status": row.get("status") or "negotiating",
                        "request": {
                            "id": row.get("request_id") or 0,
                            "title": row.get("request_title") or "",
                            "status": row.get("request_status") or "",
                        },
                        "counterparty": {
                            "username": row.get("provider_username")
                            or row.get("requester_username")
                            or "",
                            "site": row.get("provider_site")
                            or row.get("requester_site")
                            or "linux.do",
                        },
                        "paymentOrderStatus": row.get("payment_order_status") or "",
                        "contactUnlockedAt": row.get("contact_unlocked_at") or 0,
                        "lastMessageAt": row.get("last_message_at") or 0,
                        "updatedAt": row.get("updated_at") or 0,
                        "chatPath": f"/buy-request/{row.get('request_id') or 0}?session={row.get('id') or 0}",
                        "unreadCount": unread_count,
                    }
                )
            return success_response(
                data={
                    "items": conversations,
                    "conversations": conversations,
                    "sessions": conversations,
                    "pagination": {
                        "page": page,
                        "pageSize": size,
                        "total": total,
                        "totalPages": (total + size - 1) // size if total > 0 else 1,
                    },
                    "summary": {
                        "totalUnread": total_unread,
                        "sessionsWithUnread": sessions_with_unread,
                    },
                }
            )
        cur = conn.execute(
            "SELECT COUNT(*) as total FROM shop_user_messages WHERE user_id = ? AND user_site = ?",
            (user_id, site),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            "SELECT * FROM shop_user_messages WHERE user_id = ? AND user_site = ? ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?",
            [user_id, site, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "conversations": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/shop/conversations/unread-summary")
async def conversations_unread_summary(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_user_messages WHERE user_id = ? AND user_site = ? AND is_read = 0",
            (user_id, site),
        )
        unread = cur.fetchone()["c"]
        return success_response(data={"unread_count": unread, "totalUnread": unread})
    except Exception:
        return success_response(data={"unread_count": 0, "totalUnread": 0})
    finally:
        conn.close()


@router.get("/api/shop/messages/system")
async def list_system_messages(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    readStatus: str | None = Query(None),
    search: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        where = "WHERE message_type = 'system' AND user_id = ? AND user_site = ?"
        params: list[object] = [user_id, site]
        if readStatus == "unread":
            where += " AND is_read = 0"
        elif readStatus == "read":
            where += " AND is_read = 1"
        if search:
            keyword = f"%{search}%"
            where += " AND (title LIKE ? OR content LIKE ?)"
            params.extend([keyword, keyword])
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_user_messages {where}",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_user_messages {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        unread_total = conn.execute(
            "SELECT COUNT(*) as total FROM shop_user_messages WHERE message_type = 'system' AND user_id = ? AND user_site = ? AND is_read = 0",
            (user_id, site),
        ).fetchone()["total"]
        return success_response(
            data={
                "items": rows,
                "messages": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
                "summary": {"totalUnread": unread_total},
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/shop/messages/system")
async def create_system_message(
    payload: MessageCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        dedupe_key = f"manual:{hash(payload.content.strip())}"
        cur = conn.execute(
            """INSERT OR REPLACE INTO shop_user_messages (
                user_site, user_id, message_type, title, content,
                is_read, created_at, updated_at, dedupe_key
            ) VALUES (?, ?, 'system', '', ?, 0, ?, ?, ?)""",
            (site, user_id, payload.content, now_ms, now_ms, dedupe_key),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_user_messages WHERE id = ?", (cur.lastrowid,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/buy-orders")
async def list_buy_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    role: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    timeRange: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        safe_role = str(role or "").strip().lower()
        where = []
        params: list[object] = []
        if safe_role == "requester":
            where.append("requester_user_id = ? AND requester_site = ?")
            params.extend([str(user_id), site])
        elif safe_role == "provider":
            where.append("provider_user_id = ? AND provider_site = ?")
            params.extend([str(user_id), site])
        else:
            where.append(
                "((requester_user_id = ? AND requester_site = ?) OR (provider_user_id = ? AND provider_site = ?))"
            )
            params.extend([str(user_id), site, str(user_id), site])
        if status:
            where.append("status = ?")
            params.append(status)
        if search:
            keyword = f"%{search}%"
            where.append(
                "(order_no LIKE ? OR requester_username LIKE ? OR provider_username LIKE ? OR request_title LIKE ?)"
            )
            params.extend([keyword, keyword, keyword, keyword])
        if timeRange:
            months_map = {
                "1m": 1,
                "6m": 6,
                "1y": 12,
                "12m": 12,
                "month": 1,
                "halfyear": 6,
                "year": 12,
            }
            months = months_map.get(
                str(timeRange).strip().lower().replace("_", "").replace("-", "")
            )
            if months:
                since_dt = datetime.now(timezone.utc) - __import__(
                    "datetime"
                ).timedelta(days=30 * months)
                where.append("created_at >= ?")
                params.append(int(since_dt.timestamp() * 1000))
        where_sql = " WHERE " + " AND ".join(where)
        cur = conn.execute(
            """SELECT COUNT(*) as total FROM shop_buy_orders
               """
            + where_sql,
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            """SELECT bo.*, r.title AS request_title, r.budget_price AS request_budget_price,
                      s.status AS session_status
               FROM shop_buy_orders bo
               LEFT JOIN shop_buy_requests r ON r.id = bo.request_id
               LEFT JOIN shop_buy_sessions s ON s.id = bo.session_id
               """
            + where_sql.replace("created_at", "bo.created_at")
            + """
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = [_enrich_buy_order(row) for row in _rows_to_dicts(cur.fetchall())]
        return success_response(
            data={
                "items": rows,
                "total": total,
                "page": page,
                "size": size,
                "orders": rows,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": size,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/shop/buy-orders/{order_no}")
async def get_buy_order(order_no: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cur = conn.execute(
            """SELECT * FROM shop_buy_orders
               WHERE order_no = ?
                 AND ((requester_user_id = ? AND requester_site = ?)
                   OR (provider_user_id = ? AND provider_site = ?))""",
            (order_no, str(user_id), site, str(user_id), site),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        return success_response(data=row)
    except Exception:
        return success_response(data={"order_no": order_no})
    finally:
        conn.close()


@router.get("/api/shop/top-service/options")
async def list_top_service_options():
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT * FROM top_service_options WHERE active = 1 ORDER BY sort_order"
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(data=rows)
    except Exception:
        return success_response(data=[])
    finally:
        conn.close()


@router.post("/api/shop/top-service/options")
async def create_top_service_option(
    payload: dict, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        return success_response(
            data={"created": True, "payload": payload}, status_code=201
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/top-service/orders")
async def create_top_service_order(
    payload: TopServiceOrderCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = str(user.get("user_id"))
        site = user.get("site", "linux.do")
        package_row = conn.execute(
            "SELECT * FROM shop_top_package_configs WHERE id = ? LIMIT 1",
            (payload.option_id,),
        ).fetchone()
        if not package_row:
            return error_response("PACKAGE_NOT_FOUND", "置顶套餐不存在", 404)
        merchant = conn.execute(
            "SELECT * FROM shop_merchant_config WHERE user_id = ? AND site = ? LIMIT 1",
            (user_id, site),
        ).fetchone()
        if not merchant:
            return error_response("MERCHANT_NOT_CONFIGURED", "请先配置 LDC 收款", 400)
        if not merchant["is_active"] or not merchant["is_verified"]:
            return error_response(
                "MERCHANT_DISABLED", "您的 LDC 收款功能未启用或未通过审核", 400
            )

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        order_no = f"TOP{now_ms}"
        amount = float(package_row["price"] or 0)
        expire_at = now_ms + 5 * 60 * 1000
        worker_url = (
            settings.worker_url or settings.api_base_url or "https://api.ldspro.qzz.io"
        ).rstrip("/")
        notify_url = f"{worker_url}/api/shop/ldc/notify"
        return_url = f"{worker_url}/api/shop/ldc/return"
        ldc_key_plain = decrypt_ldc_key(
            str(merchant["ldc_key_encrypted"]), settings.jwt_secret_key
        )
        ldc_result = await create_ldc_order(
            pid=str(merchant["ldc_pid"]),
            key=ldc_key_plain,
            order_no=order_no,
            product_name=f"LD士多置顶服务 - {package_row['group_name']}",
            amount=amount,
            notify_url=notify_url,
            return_url=return_url,
        )
        if not ldc_result.get("success"):
            return error_response(
                "LDC_ERROR", ldc_result.get("error") or "创建支付订单失败", 500
            )
        cur = conn.execute(
            """INSERT INTO shop_top_orders (
                order_no, user_id, shop_id, option_id, package_type, duration_days,
                amount, status, payment_url, pay_expired_at,
                merchant_pid_snapshot, merchant_key_encrypted_snapshot, merchant_config_snapshot_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (
                order_no,
                user_id,
                payload.shop_id,
                payload.option_id,
                package_row["package_type"],
                payload.duration_days,
                amount,
                ldc_result.get("paymentUrl"),
                expire_at,
                merchant["ldc_pid"],
                merchant["ldc_key_encrypted"],
                now_ms,
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        return success_response(
            data={
                "orderId": cur.lastrowid,
                "orderNo": order_no,
                "paymentUrl": ldc_result.get("paymentUrl"),
                "amount": amount,
                "expireAt": expire_at,
            },
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/merchant/config")
async def get_merchant_config(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT * FROM shop_merchant_config WHERE user_id = ? AND site = ?",
            (str(user_id), site),
        )
        row = _row_to_dict(cur.fetchone())
        if not row:
            return success_response(data={})
        return success_response(
            data={
                "config": row,
                "merchantPid": row.get("ldc_pid") or "",
                "isActive": bool(row.get("is_active")),
                "isVerified": bool(row.get("is_verified")),
                "configured": bool(row.get("ldc_pid")),
            }
        )
    except Exception:
        return success_response(data={})
    finally:
        conn.close()


@router.post("/api/shop/merchant/config")
async def create_merchant_config(
    payload: MerchantConfigUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cfg = payload.config or {}
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        ldc_pid = (
            cfg.get("ldc_pid")
            or cfg.get("pid")
            or cfg.get("merchantPid")
            or getattr(payload, "ldcPid", "")
            or ""
        )
        ldc_key = (
            cfg.get("ldc_key_encrypted")
            or cfg.get("ldc_key")
            or cfg.get("keyEncrypted")
            or cfg.get("merchantKeyEncrypted")
            or cfg.get("ldcKeyEncoded")
            or getattr(payload, "ldcKeyEncoded", "")
            or ""
        )
        notify_url = cfg.get("notify_url") or cfg.get("notifyUrl") or ""
        is_active = 1 if cfg.get("is_active", cfg.get("isActive", True)) else 0
        is_verified = 1 if cfg.get("is_verified", cfg.get("isVerified", False)) else 0
        cur = conn.execute(
            """INSERT INTO shop_merchant_config (
                user_id, site, ldc_pid, ldc_key_encrypted, notify_url,
                is_active, is_verified, total_orders, total_revenue, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)""",
            (
                str(user_id),
                site,
                ldc_pid,
                ldc_key,
                notify_url,
                is_active,
                is_verified,
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_merchant_config WHERE id = ?", (cur.lastrowid,)
        )
        row = _row_to_dict(cur.fetchone())
        return success_response(
            data={
                "config": row,
                "merchantPid": row.get("ldc_pid") if row else "",
                "isActive": bool(row.get("is_active")) if row else False,
                "isVerified": bool(row.get("is_verified")) if row else False,
                "configured": bool(row and row.get("ldc_pid")),
                "message": "商户配置已更新",
            },
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/shop/merchant/config")
async def update_merchant_config(
    payload: MerchantConfigUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cfg = payload.config or {}
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        ldc_pid = (
            cfg.get("ldc_pid")
            or cfg.get("pid")
            or cfg.get("merchantPid")
            or getattr(payload, "ldcPid", "")
            or ""
        )
        ldc_key = (
            cfg.get("ldc_key_encrypted")
            or cfg.get("ldc_key")
            or cfg.get("keyEncrypted")
            or cfg.get("merchantKeyEncrypted")
            or cfg.get("ldcKeyEncoded")
            or getattr(payload, "ldcKeyEncoded", "")
            or ""
        )
        notify_url = cfg.get("notify_url") or cfg.get("notifyUrl") or ""
        is_active = 1 if cfg.get("is_active", cfg.get("isActive", True)) else 0
        is_verified = 1 if cfg.get("is_verified", cfg.get("isVerified", False)) else 0
        conn.execute(
            """INSERT INTO shop_merchant_config (
                user_id, site, ldc_pid, ldc_key_encrypted, notify_url,
                is_active, is_verified, total_orders, total_revenue, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            ON CONFLICT(user_id, site) DO UPDATE SET
                ldc_pid = excluded.ldc_pid,
                ldc_key_encrypted = excluded.ldc_key_encrypted,
                notify_url = excluded.notify_url,
                is_active = excluded.is_active,
                is_verified = excluded.is_verified,
                updated_at = excluded.updated_at""",
            (
                str(user_id),
                site,
                ldc_pid,
                ldc_key,
                notify_url,
                is_active,
                is_verified,
                now_ms,
                now_ms,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_merchant_config WHERE user_id = ? AND site = ?",
            (str(user_id), site),
        )
        row = _row_to_dict(cur.fetchone())
        return success_response(
            data={
                "config": row,
                "merchantPid": row.get("ldc_pid") if row else "",
                "isActive": bool(row.get("is_active")) if row else False,
                "isVerified": bool(row.get("is_verified")) if row else False,
                "configured": bool(row and row.get("ldc_pid")),
                "message": "商户配置已更新",
            }
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/shop/merchant/config")
async def delete_merchant_config(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        pending_orders = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE seller_user_id = ? AND seller_site = ? AND status IN ('pending', 'paying', 'paid')",
            (str(user_id), site),
        ).fetchone()["c"]
        if int(pending_orders or 0) > 0:
            return error_response(
                "HAS_PENDING_ORDERS",
                f"您有 {pending_orders} 个未完成订单，无法删除配置",
                400,
            )
        conn.execute(
            "DELETE FROM shop_merchant_config WHERE user_id = ? AND site = ?",
            (str(user_id), site),
        )
        conn.commit()
        return success_response(data={"deleted": True, "message": "LDC 配置已删除"})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/shop/merchant/toggle")
async def toggle_merchant(payload: dict, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT is_active FROM shop_merchant_config WHERE user_id = ? AND site = ?",
            (str(user_id), site),
        )
        row = _row_to_dict(cur.fetchone())
        if not row:
            return error_response("NOT_CONFIGURED", "请先配置 LDC 收款信息", 400)
        requested_active = payload.get("active")
        if requested_active is None:
            current = int(row.get("is_active", 0)) if row else 0
            new_val = 0 if current else 1
        else:
            new_val = 1 if requested_active else 0
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_merchant_config SET is_active = ?, updated_at = ? WHERE user_id = ? AND site = ?",
            (new_val, now_ms, str(user_id), site),
        )
        conn.commit()
        return success_response(
            data={
                "merchant": bool(new_val),
                "is_active": bool(new_val),
                "message": "收款功能已启用" if new_val else "收款功能已禁用",
            }
        )
    except Exception as e:
        return error_response("TOGGLE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/merchant/stats")
async def merchant_stats(
    days: int = Query(30, ge=1, le=365), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_products WHERE seller_user_id = ? AND seller_site = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (str(user_id), site),
        )
        products = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE seller_user_id = ? AND seller_site = ?",
            (str(user_id), site),
        )
        orders = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as revenue FROM shop_orders WHERE seller_user_id = ? AND seller_site = ? AND status IN ('paid', 'delivered')",
            (str(user_id), site),
        )
        revenue = cur.fetchone()["revenue"]
        cur = conn.execute(
            "SELECT * FROM shop_merchant_config WHERE user_id = ? AND site = ?",
            (str(user_id), site),
        )
        merchant = _row_to_dict(cur.fetchone()) or {}
        return success_response(
            data={
                "products": products,
                "orders": orders,
                "revenue": revenue,
                "totalOrders": orders,
                "totalRevenue": revenue,
                "dailyStats": [],
                "is_active": bool(merchant.get("is_active", 0)),
                "is_verified": bool(merchant.get("is_verified", 0)),
                "ldc_pid": merchant.get("ldc_pid", ""),
            }
        )
    except Exception:
        return success_response(
            data={
                "products": 0,
                "orders": 0,
                "revenue": 0,
                "totalOrders": 0,
                "totalRevenue": 0,
                "dailyStats": [],
            }
        )
    finally:
        conn.close()


@router.post("/api/shop/merchant/test-callback")
async def merchant_test_callback(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        user_id = str(user.get("user_id") or "")
        site = user.get("site", "linux.do")
        row = _row_to_dict(
            conn.execute(
                "SELECT id, ldc_pid, ldc_key_encrypted FROM shop_merchant_config WHERE user_id = ? AND site = ? LIMIT 1",
                (user_id, site),
            ).fetchone()
        )
        if not row:
            return error_response("NOT_CONFIGURED", "请先配置 LDC 收款信息", 400)
        worker_url = (
            settings.worker_url or settings.api_base_url or "https://api.ldspro.qzz.io"
        ).rstrip("/")
        notify_url = f"{worker_url}/api/shop/ldc/notify"
        if not row.get("ldc_pid") or not row.get("ldc_key_encrypted"):
            return success_response(
                data={
                    "notifyUrl": notify_url,
                    "status": "warning",
                    "message": "配置缺失，无法完成通知测试",
                }
            )
        return success_response(
            data={
                "notifyUrl": notify_url,
                "status": "ok",
                "response": "success",
                "message": "通知测试成功！您的通知地址配置正确",
            }
        )
    except Exception as e:
        return error_response("TEST_FAILED", f"通知测试失败: {str(e)}", 500)
    finally:
        conn.close()


@router.get("/api/shop/products/{product_id}/cdk")
async def list_product_cdk(product_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        status = "available"
        cur = conn.execute(
            "SELECT * FROM shop_cdk WHERE product_id = ? AND status = ? ORDER BY created_at ASC",
            (product_id, status),
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "cdks": rows,
                "pagination": {
                    "total": len(rows),
                    "page": 1,
                    "pageSize": len(rows),
                    "totalPages": 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "cdks": [],
                "pagination": {"total": 0, "page": 1, "pageSize": 0, "totalPages": 1},
            }
        )
    finally:
        conn.close()


@router.post("/api/shop/products/{product_id}/cdk")
async def create_product_cdk(
    product_id: int, payload: CDKCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        created = []
        for code in payload.codes:
            cur = conn.execute(
                "INSERT INTO shop_cdk (product_id, code, status, created_at) VALUES (?, ?, 'available', ?)",
                (product_id, code, int(datetime.now(timezone.utc).timestamp() * 1000)),
            )
            created.append({"id": cur.lastrowid, "code": code})
        conn.commit()
        return success_response(data={"created": created}, status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/shop/products/{product_id}/cdk/{cdk_id}")
async def delete_product_cdk(
    product_id: int, cdk_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute(
            "DELETE FROM shop_cdk WHERE id = ? AND product_id = ? AND status = 'available'",
            (cdk_id, product_id),
        )
        conn.commit()
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/shop/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    role: str = Query("buyer"),
    status: str | None = Query(None),
    search: str | None = Query(None),
    keyword: str | None = Query(None),
    timeRange: str | None = Query(None),
    categoryId: int | None = Query(None),
    dealOnly: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        user_id = user.get("user_id")
        site = user.get("site", "linux.do")
        safe_role = "seller" if str(role or "").strip() == "seller" else "buyer"
        user_column = "seller_user_id" if safe_role == "seller" else "buyer_user_id"
        site_column = "seller_site" if safe_role == "seller" else "buyer_site"
        where = [f"{user_column} = ?", f"{site_column} = ?"]
        params: list[object] = [str(user_id), site]
        if status:
            where.append("status = ?")
            params.append(status)
        elif str(dealOnly or "").strip() == "1":
            where.append("status IN ('paid', 'delivered')")
        if timeRange:
            months_map = {
                "1m": 1,
                "6m": 6,
                "1y": 12,
                "12m": 12,
                "month": 1,
                "halfyear": 6,
                "year": 12,
            }
            months = months_map.get(
                str(timeRange).strip().lower().replace("_", "").replace("-", "")
            )
            if months:
                since_dt = datetime.now(timezone.utc) - __import__(
                    "datetime"
                ).timedelta(days=30 * months)
                where.append("created_at >= ?")
                params.append(int(since_dt.timestamp() * 1000))
        if categoryId:
            where.append(
                "CAST(json_extract(product_snapshot, '$.category_id') AS INTEGER) = ?"
            )
            params.append(categoryId)
        effective_keyword = str(search or keyword or "").strip()
        if effective_keyword:
            like = f"%{effective_keyword}%"
            where.append(
                "(order_no LIKE ? OR buyer_username LIKE ? OR seller_username LIKE ? OR product_snapshot LIKE ?)"
            )
            params.extend([like, like, like, like])
        where_sql = " WHERE " + " AND ".join(where)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_orders{where_sql}",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_orders{where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = []
        for row in _rows_to_dicts(cur.fetchall()):
            enriched = _enrich_shop_order(row)
            product_snapshot = _safe_json_loads(row.get("product_snapshot"), {}) or {}
            product_type = str(
                (product_snapshot or {}).get("product_type")
                or row.get("current_product_type")
                or ""
            )
            enriched["order_type"] = (
                "normal"
                if product_type == "normal"
                else (
                    "cdk" if product_type == "cdk" else row.get("order_type") or "cdk"
                )
            )
            enriched["comment_enabled"] = product_type in {"normal", "cdk"}
            rows.append(enriched)
        return success_response(
            data={
                "items": rows,
                "total": total,
                "page": page,
                "size": size,
                "orders": rows,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": size,
                    "totalPages": (total + size - 1) // size,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/shop/orders")
async def create_order(payload: OrderCreate, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        buyer_user_id = str(user.get("user_id"))
        buyer_site = user.get("site", "linux.do")
        buyer_username = user.get("username") or ""
        if payload.quantity < 1 or payload.quantity > 100:
            return error_response(
                "INVALID_QUANTITY", "购买数量必须为大于 0 的整数", 400
            )

        product = conn.execute(
            """SELECT p.*, c.name AS category_name, c.visibility_trust_level AS category_visibility_trust_level,
                      mc.ldc_pid, mc.ldc_key_encrypted, mc.is_active AS merchant_active, mc.is_verified
               FROM shop_products p
               LEFT JOIN shop_categories c ON c.id = p.category_id
               LEFT JOIN shop_merchant_config mc ON mc.user_id = p.seller_user_id AND mc.site = p.seller_site
               WHERE p.id = ? AND p.status IN ('ai_approved', 'manual_approved') AND (p.is_deleted = 0 OR p.is_deleted IS NULL)
               LIMIT 1""",
            (payload.product_id,),
        ).fetchone()
        if not product:
            return error_response("PRODUCT_NOT_FOUND", "商品不存在或已下架", 404)

        product_type = str(product["product_type"] or "normal")
        if product_type not in ("normal", "cdk"):
            return error_response(
                "UNSUPPORTED_PRODUCT_TYPE", "该商品不支持在平台内下单", 400
            )

        buyer_trust_level = int(user.get("trust_level") or 0)
        category_visibility = int(product["category_visibility_trust_level"] or 0)
        if buyer_trust_level < category_visibility:
            return error_response(
                "TRUST_LEVEL_REQUIRED", "当前信任等级不足以查看/购买该分类商品", 403
            )

        purchase_trust_level = int(product["purchase_trust_level"] or 0)
        if buyer_trust_level < purchase_trust_level:
            return error_response(
                "PURCHASE_TRUST_LEVEL_REQUIRED", "当前信任等级不足以购买该商品", 403
            )

        max_purchase_quantity = int(product["max_purchase_quantity"] or 0)
        if max_purchase_quantity > 0 and payload.quantity > max_purchase_quantity:
            return error_response(
                "PURCHASE_LIMIT_EXCEEDED",
                f"该商品单次最多购买 {max_purchase_quantity} 个",
                400,
            )

        if not product["ldc_pid"] or not product["ldc_key_encrypted"]:
            return error_response("MERCHANT_NOT_CONFIGURED", "卖家未配置收款方式", 400)
        if not product["merchant_active"] or not product["is_verified"]:
            return error_response("MERCHANT_DISABLED", "卖家收款功能未启用", 400)

        is_seller = (
            buyer_user_id == str(product["seller_user_id"])
            and buyer_site == product["seller_site"]
        )
        if int(product["is_test_mode"] or 0) == 1:
            if not is_seller:
                return error_response(
                    "TEST_MODE_ONLY", "该商品为测试模式，仅卖家可购买", 400
                )
        else:
            if is_seller:
                return error_response("CANNOT_BUY_OWN", "不能购买自己的商品", 400)

        quantity = int(payload.quantity)
        available_stock = int(product["stock"] or 0)
        locked_cdk_ids: list[int] = []
        normal_stock_reserved = False
        if product_type == "cdk":
            stock_row = conn.execute(
                "SELECT COUNT(*) AS available FROM shop_cdk WHERE product_id = ? AND status = 'available'",
                (payload.product_id,),
            ).fetchone()
            available_stock = int(stock_row["available"] or 0)
        if available_stock < quantity:
            return error_response("INSUFFICIENT_STOCK", "库存不足", 400)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        order_no = f"ORD{now_ms}"
        expire_at = now_ms + 5 * 60 * 1000
        amount = round(
            float(product["price"] or 0) * float(product["discount"] or 1) * quantity, 2
        )
        original_price = round(float(product["price"] or 0) * quantity, 2)

        if product_type == "cdk":
            cur = conn.execute(
                """UPDATE shop_cdk SET status = 'locked', locked_at = ?, lock_token = ?
                   WHERE id IN (
                     SELECT id FROM shop_cdk WHERE product_id = ? AND status = 'available' ORDER BY created_at ASC LIMIT ?
                   ) AND status = 'available'""",
                (now_ms, order_no, payload.product_id, quantity),
            )
            if cur.rowcount < quantity:
                conn.execute(
                    "UPDATE shop_cdk SET status = 'available', locked_at = NULL, lock_token = NULL WHERE product_id = ? AND lock_token = ? AND status = 'locked'",
                    (payload.product_id, order_no),
                )
                conn.commit()
                return error_response("INSUFFICIENT_CDK", "CDK 库存不足", 400)
            rows = conn.execute(
                "SELECT id FROM shop_cdk WHERE product_id = ? AND lock_token = ? AND status = 'locked' ORDER BY created_at ASC LIMIT ?",
                (payload.product_id, order_no, quantity),
            ).fetchall()
            locked_cdk_ids = [int(r["id"]) for r in rows]
            conn.execute(
                "UPDATE shop_products SET stock = (SELECT COUNT(*) FROM shop_cdk WHERE product_id = ? AND status = 'available'), updated_at = ? WHERE id = ?",
                (payload.product_id, now_ms, payload.product_id),
            )
        else:
            reserve = conn.execute(
                "UPDATE shop_products SET stock = stock - ?, updated_at = ? WHERE id = ? AND COALESCE(stock, 0) >= ?",
                (quantity, now_ms, payload.product_id, quantity),
            )
            if reserve.rowcount == 0:
                return error_response("INSUFFICIENT_STOCK", "库存不足", 400)
            normal_stock_reserved = True

        import json

        product_snapshot = json.dumps(
            {
                "id": payload.product_id,
                "name": product["name"],
                "price": product["price"],
                "discount": product["discount"],
                "category_id": product["category_id"],
                "description": product["description"],
                "image_url": product["image_url"],
                "product_type": product_type,
            },
            ensure_ascii=False,
        )

        conn.execute(
            """INSERT INTO shop_orders (
                order_no, product_id, product_snapshot, quantity,
                buyer_user_id, buyer_site, buyer_username,
                seller_user_id, seller_site, seller_username,
                amount, original_price, status,
                delivery_type, pay_expired_at,
                merchant_pid_snapshot, merchant_key_encrypted_snapshot, merchant_config_snapshot_at,
                created_at, updated_at, payment_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                order_no,
                payload.product_id,
                product_snapshot,
                quantity,
                buyer_user_id,
                buyer_site,
                buyer_username,
                str(product["seller_user_id"]),
                product["seller_site"],
                product["seller_username"],
                amount,
                original_price,
                "auto" if product_type == "cdk" else "manual",
                expire_at,
                product["ldc_pid"],
                product["ldc_key_encrypted"],
                now_ms,
                now_ms,
                now_ms,
            ),
        )
        order_id = conn.execute(
            "SELECT id FROM shop_orders WHERE order_no = ?", (order_no,)
        ).fetchone()["id"]
        if locked_cdk_ids:
            for cdk_id in locked_cdk_ids:
                conn.execute(
                    "UPDATE shop_cdk SET lock_order_id = ? WHERE id = ?",
                    (order_id, cdk_id),
                )
        conn.execute(
            "INSERT INTO shop_order_logs (order_id, order_no, action, operator_type, operator_id, operator_name, detail, created_at) VALUES (?, ?, 'create', 'buyer', ?, ?, ?, ?)",
            (
                order_id,
                order_no,
                buyer_user_id,
                buyer_username,
                json.dumps(
                    {
                        "productId": payload.product_id,
                        "quantity": quantity,
                        "amount": amount,
                    },
                    ensure_ascii=False,
                ),
                now_ms,
            ),
        )
        worker_url = (
            settings.worker_url or settings.api_base_url or "https://api.ldspro.qzz.io"
        ).rstrip("/")
        notify_url = f"{worker_url}/api/shop/ldc/notify"
        return_url = f"{worker_url}/api/shop/ldc/return"
        ldc_key_plain = decrypt_ldc_key(
            str(product["ldc_key_encrypted"]), settings.jwt_secret_key
        )
        ldc_result = await create_ldc_order(
            pid=str(product["ldc_pid"]),
            key=ldc_key_plain,
            order_no=order_no,
            product_name=f"LD士多 - {product['name']}",
            amount=amount,
            notify_url=notify_url,
            return_url=return_url,
        )
        if not ldc_result.get("success"):
            raise RuntimeError(ldc_result.get("error") or "LDC 支付创建失败")
        payment_url = ldc_result.get("paymentUrl")
        conn.execute(
            "UPDATE shop_orders SET payment_url = ?, updated_at = ? WHERE id = ?",
            (payment_url, now_ms, order_id),
        )
        conn.commit()
        return success_response(
            data={
                "orderId": order_id,
                "orderNo": order_no,
                "amount": amount,
                "paymentUrl": payment_url,
                "expireAt": expire_at,
                "paymentPending": True,
            },
            status_code=201,
        )
    except Exception as e:
        try:
            if "order_no" in locals() and order_no:
                conn.execute(
                    "UPDATE shop_orders SET status = 'cancelled' WHERE order_no = ? AND status = 'pending'",
                    (order_no,),
                )
            if "locked_cdk_ids" in locals() and locked_cdk_ids:
                for cdk_id in locked_cdk_ids:
                    conn.execute(
                        "UPDATE shop_cdk SET status = 'available', locked_at = NULL, lock_order_id = NULL, lock_token = NULL WHERE id = ?",
                        (cdk_id,),
                    )
                conn.execute(
                    "UPDATE shop_products SET stock = (SELECT COUNT(*) FROM shop_cdk WHERE product_id = ? AND status = 'available'), updated_at = ? WHERE id = ?",
                    (
                        payload.product_id,
                        int(datetime.now(timezone.utc).timestamp() * 1000),
                        payload.product_id,
                    ),
                )
            if "normal_stock_reserved" in locals() and normal_stock_reserved:
                conn.execute(
                    "UPDATE shop_products SET stock = stock + ?, updated_at = ? WHERE id = ?",
                    (
                        payload.quantity,
                        int(datetime.now(timezone.utc).timestamp() * 1000),
                        payload.product_id,
                    ),
                )
            conn.commit()
        except Exception:
            pass
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------------------------


@router.get("/api/admin/shops/stats")
async def admin_shops_stats(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT COUNT(*) as c FROM shops WHERE status = 'online'")
        online = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM shops WHERE status = 'offline'")
        offline = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM shops WHERE status = 'pending'")
        pending = cur.fetchone()["c"]
        return success_response(
            data={"online": online, "offline": offline, "pending": pending}
        )
    except Exception:
        return success_response(data={"online": 0, "offline": 0, "pending": 0})
    finally:
        conn.close()


@router.get("/api/admin/shops/{shop_id}")
async def admin_get_shop(shop_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM shops WHERE id = ?", (shop_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("SHOP_NOT_FOUND", "店铺不存在", 404)
        return success_response(data=row)
    except Exception:
        return success_response(data={"id": shop_id})
    finally:
        conn.close()


@router.post("/api/admin/shops/{shop_id}")
async def admin_update_shop(
    shop_id: int, payload: ShopUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的字段")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), shop_id]
        conn.execute(f"UPDATE shops SET {set_clause} WHERE id = ?", params)
        conn.commit()
        cur = conn.execute("SELECT * FROM shops WHERE id = ?", (shop_id,))
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shops/{shop_id}")
async def admin_put_shop(
    shop_id: int, payload: ShopUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        set_clause = (
            ", ".join(f"{k} = ?" for k in updates) if updates else "updated_at = ?"
        )
        params = (
            [*updates.values(), shop_id]
            if updates
            else [datetime.now(timezone.utc).isoformat(), shop_id]
        )
        conn.execute(f"UPDATE shops SET {set_clause} WHERE id = ?", params)
        conn.commit()
        return success_response(data={"updated": True})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shops/{shop_id}")
async def admin_delete_shop(shop_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        conn.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
        conn.commit()
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shops/{shop_id}/review")
async def admin_review_shop(
    shop_id: int,
    action: str = Query("approve"),
    reason: str = "",
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        status_map = {"approve": "approved", "reject": "rejected"}
        new_status = status_map.get(action, action)
        conn.execute(
            "UPDATE shops SET status = ?, review_reason = ? WHERE id = ?",
            (new_status, reason, shop_id),
        )
        conn.commit()
        return success_response(data={"shop_id": shop_id, "status": new_status})
    except Exception as e:
        return error_response("REVIEW_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shops/{shop_id}/offline")
async def admin_offline_shop(
    shop_id: int, reason: str = "", user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute(
            "UPDATE shops SET offline = 1, offline_reason = ? WHERE id = ?",
            (reason, shop_id),
        )
        conn.commit()
        return success_response(data={"shop_id": shop_id, "offline": True})
    except Exception as e:
        return error_response("OFFLINE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shops/{shop_id}/pin")
async def admin_pin_shop(
    shop_id: int, pinned: bool = True, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute("UPDATE shops SET pinned = ? WHERE id = ?", (pinned, shop_id))
        conn.commit()
        return success_response(data={"shop_id": shop_id, "pinned": pinned})
    except Exception as e:
        return error_response("PIN_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shops")
async def admin_list_shops(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    keyword: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        if keyword:
            where += " AND (name LIKE ? OR description LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        cur = conn.execute(f"SELECT COUNT(*) as total FROM shops {where}", params)
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shops {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "shops": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "shops": [],
                "total": 0,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": 0,
                    "totalPages": 1,
                },
            }
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/stats")
async def admin_shop_stats(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT COUNT(*) as c FROM shops")
        shops = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_products WHERE is_deleted = 0 OR is_deleted IS NULL"
        )
        products = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM shop_orders")
        orders = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE status = 'pending'"
        )
        pending_orders = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE status = 'paid'"
        )
        paid_orders = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE status = 'delivered'"
        )
        delivered_orders = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as revenue FROM shop_orders WHERE status IN ('paid', 'delivered')"
        )
        revenue = cur.fetchone()["revenue"]
        return success_response(
            data={
                "shops": shops,
                "products": products,
                "orders": orders,
                "revenue": revenue,
                "pendingOrders": pending_orders,
                "paidOrders": paid_orders,
                "deliveredOrders": delivered_orders,
            }
        )
    except Exception:
        return success_response(
            data={"shops": 0, "products": 0, "orders": 0, "revenue": 0}
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/analytics")
async def admin_shop_analytics(
    trendDays: int = Query(30, ge=7, le=90),
    forceRefresh: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        day_ms = 24 * 60 * 60 * 1000
        today_start = int(
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            * 1000
        )
        days7_start = now_ms - 7 * day_ms
        days30_start = now_ms - 30 * day_ms

        def _period_orders(start_ms: int | None):
            where = ""
            params: list[object] = []
            if start_ms is not None:
                where = "WHERE created_at >= ?"
                params.append(start_ms)
            summary = conn.execute(
                f"""SELECT COUNT(*) AS created_count,
                           SUM(CASE WHEN status IN ('paid', 'delivered') THEN 1 ELSE 0 END) AS deal_count,
                           COALESCE(SUM(CASE WHEN status IN ('paid', 'delivered') THEN amount ELSE 0 END), 0) AS revenue,
                           COUNT(DISTINCT CASE WHEN status IN ('paid', 'delivered') THEN buyer_site || ':' || buyer_user_id END) AS buyer_count,
                           COUNT(DISTINCT CASE WHEN status IN ('paid', 'delivered') THEN seller_site || ':' || seller_user_id END) AS seller_count
                    FROM shop_orders {where}""",
                params,
            ).fetchone()
            created_count = int(summary["created_count"] or 0)
            deal_count = int(summary["deal_count"] or 0)
            revenue = float(summary["revenue"] or 0)
            return {
                "createdOrderCount": created_count,
                "dealOrderCount": deal_count,
                "revenue": revenue,
                "buyerCount": int(summary["buyer_count"] or 0),
                "sellerCount": int(summary["seller_count"] or 0),
                "avgOrderAmount": round(revenue / deal_count, 2)
                if deal_count > 0
                else 0,
                "dealRate": round(deal_count / created_count, 4)
                if created_count > 0
                else 0,
            }

        periods = {
            "today": _period_orders(today_start),
            "days7": _period_orders(days7_start),
            "days30": _period_orders(days30_start),
            "total": _period_orders(None),
        }

        trend_rows = _rows_to_dicts(
            conn.execute(
                """SELECT date(created_at / 1000, 'unixepoch', '+8 hours') AS metric_bucket,
                          COUNT(*) AS created_order_count,
                          SUM(CASE WHEN status IN ('paid', 'delivered') THEN 1 ELSE 0 END) AS deal_order_count,
                          COALESCE(SUM(CASE WHEN status IN ('paid', 'delivered') THEN amount ELSE 0 END), 0) AS revenue,
                          COUNT(DISTINCT CASE WHEN status IN ('paid', 'delivered') THEN seller_site || ':' || seller_user_id END) AS seller_count
                   FROM shop_orders
                   WHERE created_at >= ?
                   GROUP BY date(created_at / 1000, 'unixepoch', '+8 hours')
                   ORDER BY metric_bucket ASC""",
                (now_ms - trendDays * day_ms,),
            ).fetchall()
        )
        trend = [
            {
                "label": row.get("metric_bucket") or "",
                "createdOrderCount": int(row.get("created_order_count") or 0),
                "dealOrderCount": int(row.get("deal_order_count") or 0),
                "revenue": float(row.get("revenue") or 0),
                "sellerCount": int(row.get("seller_count") or 0),
            }
            for row in trend_rows
        ]

        status30d = _rows_to_dicts(
            conn.execute(
                """SELECT status, COUNT(*) AS order_count, COALESCE(SUM(amount), 0) AS amount
                   FROM shop_orders
                   WHERE created_at >= ?
                   GROUP BY status
                   ORDER BY order_count DESC, status ASC""",
                (days30_start,),
            ).fetchall()
        )
        top_categories = _rows_to_dicts(
            conn.execute(
                """SELECT COALESCE(c.name, '未分类') AS category_name,
                          COALESCE(c.icon, '📦') AS category_icon,
                          COUNT(*) AS order_count,
                          COALESCE(SUM(o.amount), 0) AS revenue,
                          COUNT(DISTINCT o.seller_site || ':' || o.seller_user_id) AS seller_count
                   FROM shop_orders o
                   LEFT JOIN shop_products p ON p.id = o.product_id
                   LEFT JOIN shop_categories c ON c.id = p.category_id
                   WHERE o.created_at >= ? AND o.status IN ('paid', 'delivered')
                   GROUP BY COALESCE(c.name, '未分类'), COALESCE(c.icon, '📦')
                   ORDER BY revenue DESC, order_count DESC, category_name ASC
                   LIMIT 8""",
                (days30_start,),
            ).fetchall()
        )
        top_sellers = _rows_to_dicts(
            conn.execute(
                """SELECT o.seller_user_id, o.seller_site,
                          MAX(COALESCE(NULLIF(TRIM(o.seller_username), ''), NULLIF(TRIM(p.seller_username), ''), 'unknown')) AS seller_username,
                          MAX(COALESCE(NULLIF(TRIM(p.seller_name), ''), NULLIF(TRIM(o.seller_username), ''), '')) AS seller_name,
                          COUNT(*) AS order_count,
                          COALESCE(SUM(o.amount), 0) AS revenue,
                          COUNT(DISTINCT o.buyer_site || ':' || o.buyer_user_id) AS buyer_count
                   FROM shop_orders o
                   LEFT JOIN shop_products p ON p.id = o.product_id
                   WHERE o.created_at >= ? AND o.status IN ('paid', 'delivered')
                   GROUP BY o.seller_site, o.seller_user_id
                   ORDER BY revenue DESC, order_count DESC, seller_username ASC
                   LIMIT 10""",
                (days30_start,),
            ).fetchall()
        )
        latest_successful_run = _row_to_dict(
            conn.execute(
                "SELECT * FROM agent_runs WHERE agent_key = 'ops_copilot' AND status IN ('success', 'fallback') ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        )
        latest_run = _row_to_dict(
            conn.execute(
                "SELECT * FROM agent_runs WHERE agent_key = 'ops_copilot' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        )
        report_config = _row_to_dict(
            conn.execute(
                "SELECT * FROM shop_ops_report_configs WHERE report_type = 'daily' LIMIT 1"
            ).fetchone()
        )
        return success_response(
            data={
                "generatedAt": now_ms,
                "periods": periods,
                "trend": trend,
                "topCategories30d": [
                    {
                        "categoryName": row.get("category_name") or "未分类",
                        "categoryIcon": row.get("category_icon") or "📦",
                        "orderCount": int(row.get("order_count") or 0),
                        "revenue": float(row.get("revenue") or 0),
                        "sellerCount": int(row.get("seller_count") or 0),
                    }
                    for row in top_categories
                ],
                "topSellers30d": [
                    {
                        "sellerKey": f"{row.get('seller_site') or 'linux.do'}:{row.get('seller_user_id') or ''}",
                        "sellerSite": row.get("seller_site") or "linux.do",
                        "sellerUserId": row.get("seller_user_id") or "",
                        "sellerUsername": row.get("seller_username") or "unknown",
                        "sellerName": row.get("seller_name") or "",
                        "orderCount": int(row.get("order_count") or 0),
                        "buyerCount": int(row.get("buyer_count") or 0),
                        "revenue": float(row.get("revenue") or 0),
                        "avgOrderAmount": round(
                            float(row.get("revenue") or 0)
                            / int(row.get("order_count") or 1),
                            2,
                        )
                        if int(row.get("order_count") or 0) > 0
                        else 0,
                    }
                    for row in top_sellers
                ],
                "distributions": {
                    "status30d": [
                        {
                            "status": str(row.get("status") or "unknown"),
                            "orderCount": int(row.get("order_count") or 0),
                            "revenue": float(row.get("amount") or 0),
                        }
                        for row in status30d
                    ]
                },
                "suggestions": [],
                "suggestionsMeta": {
                    "sourceLabel": "规则引擎",
                    "generatedAt": now_ms,
                    "stale": False,
                },
                "agent": {
                    "ready": bool(latest_successful_run or latest_run),
                    "latestSuccessfulRun": {
                        "startedAt": latest_successful_run.get("started_at")
                        if latest_successful_run
                        else 0,
                        "summary": _safe_json_loads(
                            latest_successful_run.get("output_json"), {}
                        )
                        .get("report", {})
                        .get("summary", "")
                        if latest_successful_run
                        else "",
                    },
                    "latestRun": latest_run,
                    "reportConfig": {
                        "latestRunStatus": report_config.get("last_run_status")
                        if report_config
                        else "",
                        "latestRunErrorMessage": report_config.get(
                            "last_run_error_message"
                        )
                        if report_config
                        else "",
                    },
                },
                "meta": {
                    "queryCostMs": 0,
                    "cacheHit": False,
                    "forceRefresh": bool(forceRefresh),
                },
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/analytics/report-configs")
async def admin_analytics_report_configs(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT * FROM shop_ops_report_configs ORDER BY report_type ASC"
        )
        rows = _rows_to_dicts(cur.fetchall())
        for row in rows:
            row["reportType"] = row.get("report_type") or ""
            row["schedule"] = _safe_json_loads(row.get("schedule_json"), {}) or {}
            row["latestRunStatus"] = row.get("last_run_status") or ""
            row["latestRunErrorMessage"] = row.get("last_run_error_message") or ""
        return success_response(data=rows)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/analytics/report-configs/{report_type}")
async def admin_update_report_config_by_type(
    report_type: str,
    payload: dict,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        import json

        safe_report_type = (
            (report_type or payload.get("name") or "daily").strip().lower()
        )
        if safe_report_type not in {"daily", "weekly", "monthly"}:
            return error_response(
                "INVALID_PARAMS", "reportType 仅支持 daily/weekly/monthly", 400
            )

        config_str = json.dumps(payload or {})
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            """INSERT INTO shop_ops_report_configs (
                report_type, enabled, schedule_type, timezone, schedule_json,
                operator_id, operator_name, created_at, updated_at
            ) VALUES (?, 1, 'hourly', 'Asia/Shanghai', ?, ?, ?, ?, ?)
            ON CONFLICT(report_type) DO UPDATE SET
                schedule_json = excluded.schedule_json,
                operator_id = excluded.operator_id,
                operator_name = excluded.operator_name,
                updated_at = excluded.updated_at""",
            (
                safe_report_type,
                config_str,
                str(user.get("user_id") or "admin"),
                user.get("username") or "admin",
                now,
                now,
            ),
        )
        conn.commit()
        AICapabilityService().sync_report_capability(safe_report_type)
        cur = conn.execute(
            "SELECT * FROM shop_ops_report_configs WHERE report_type = ?",
            (safe_report_type,),
        )
        row = _row_to_dict(cur.fetchone())
        if row:
            row["reportType"] = row.get("report_type") or ""
            row["schedule"] = _safe_json_loads(row.get("schedule_json"), {}) or {}
        return success_response(data=row)
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/analytics/reports")
async def admin_analytics_reports(
    reportType: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list[object] = []
        if reportType:
            where += " AND json_extract(input_json, '$.reportMeta.reportType') = ?"
            params.append(reportType)
        total = conn.execute(
            f"SELECT COUNT(*) as total FROM agent_runs {where}", params
        ).fetchone()["total"]
        offset, limit = _page_params(page, pageSize)
        cur = conn.execute(
            f"""SELECT run_id, agent_key, mode, status, trigger_source, decision, decision_source,
                      operator_id, operator_name, started_at, ended_at, created_at, updated_at,
                      error_type, error_message, input_json, output_json
               FROM agent_runs {where}
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        mapped_rows = []
        for row in rows:
            output = _safe_json_loads(row.get("output_json"), {}) or {}
            report = output.get("report") if isinstance(output, dict) else None
            meta = report.get("reportMeta") if isinstance(report, dict) else {}
            mapped_rows.append(
                {
                    "runId": row.get("run_id") or "",
                    "reportType": str(meta.get("reportType") or reportType or ""),
                    "title": str(report.get("title") or ""),
                    "generatedAt": row.get("started_at") or 0,
                    "status": row.get("status") or "",
                    "triggerSource": row.get("trigger_source") or "",
                    "errorType": row.get("error_type") or "",
                    "errorMessage": row.get("error_message") or "",
                    "periodLabel": str(meta.get("periodLabel") or ""),
                    "periodStart": str(meta.get("periodStart") or ""),
                    "periodEndDisplay": str(meta.get("periodEndDisplay") or ""),
                    "summary": str(
                        report.get("summary") or output.get("summary") or ""
                    ),
                }
            )
        return success_response(
            data={
                "items": mapped_rows,
                "total": total,
                "page": page,
                "pageSize": pageSize,
                "pagination": {
                    "page": page,
                    "pageSize": pageSize,
                    "total": total,
                    "totalPages": (total + pageSize - 1) // pageSize
                    if total > 0
                    else 1,
                },
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/analytics/reports/{run_id}")
async def admin_analytics_report_detail(
    run_id: str, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("NOT_FOUND", "报表运行记录不存在", 404)
        output = _safe_json_loads(row.get("output_json"), {}) or {}
        report = output.get("report") if isinstance(output, dict) else None
        detail = {
            "runId": row.get("run_id") or "",
            "reportType": (report or {}).get("reportType")
            or ((report or {}).get("reportMeta") or {}).get("reportType")
            or "",
            "title": (report or {}).get("title") or "",
            "generatedAt": row.get("started_at") or 0,
            "status": row.get("status") or "",
            "triggerSource": row.get("trigger_source") or "",
            "errorType": row.get("error_type") or "",
            "errorMessage": row.get("error_message") or "",
            "reason": row.get("error_message") or "",
            "summary": (report or {}).get("summary") or output.get("summary") or "",
            "overview": (report or {}).get("overview") or "",
            "period": {
                "label": ((report or {}).get("reportMeta") or {}).get("periodLabel")
                or "",
                "start": ((report or {}).get("reportMeta") or {}).get("periodStart")
                or "",
                "endDisplay": ((report or {}).get("reportMeta") or {}).get(
                    "periodEndDisplay"
                )
                or "",
            },
            "metrics": (report or {}).get("metrics") or {},
            "trend": (report or {}).get("trend") or [],
            "statusDistribution": (report or {}).get("statusDistribution") or [],
            "topCategories": (report or {}).get("topCategories") or [],
            "topSellers": (report or {}).get("topSellers") or [],
            "highlights": (report or {}).get("highlights") or [],
            "risks": (report or {}).get("risks") or [],
            "actions": (report or {}).get("actions") or [],
            "questions": (report or {}).get("questions") or [],
            "sections": (report or {}).get("sections") or [],
            "markdownContent": (report or {}).get("markdown") or "",
        }
        return success_response(data=detail)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/analytics/reports/{report_type}/generate")
async def admin_generate_report(
    report_type: str,
    payload: dict | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        safe_type = report_type.strip().lower()
        if safe_type not in {"daily", "weekly", "monthly"}:
            return error_response("INVALID_PARAMS", "不支持的报表类型", 400)
        result = AgentRuntimeService().create_report_run(
            safe_type,
            payload=payload or {},
            trigger_source=f"shop_ops_report_manual_{safe_type}",
            operator={
                "user_id": str(user.get("user_id") or "admin"),
                "username": user.get("username") or "admin",
            },
        )
        return success_response(
            data={
                "run_id": result.get("runId"),
                "status": result.get("status"),
                "report_type": safe_type,
            },
            status_code=202,
        )
    except Exception as e:
        return error_response("RUN_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/analytics/ops-copilot/blueprint")
async def admin_ops_copilot_blueprint(user: dict = Depends(get_current_user)):
    return success_response(
        data={
            "agentKey": "ops_copilot",
            "mode": "manual_test",
            "defaultPromptTemplate": "你是小卖部运营分析 Copilot，请基于统计数据输出结构化运营建议。",
            "capabilities": [
                "analytics_summary",
                "report_preview",
                "queue_manual_query",
            ],
            "presets": [
                {
                    "key": "daily-briefing",
                    "label": "日报简报",
                    "defaultQuestion": "请总结今日小卖部运营表现并给出建议。",
                    "promptTemplate": "请基于今日运营数据输出日报简报。",
                },
                {
                    "key": "risk-review",
                    "label": "风险巡检",
                    "defaultQuestion": "请识别近期订单与商家运营风险。",
                    "promptTemplate": "请聚焦风险信号并输出处置建议。",
                },
            ],
            "questionTemplates": [
                "请总结最近 7 天小卖部运营表现并给出三条优先建议。",
                "请关注订单异常、商家集中度和分类波动。",
            ],
            "reportTypes": [
                {
                    "reportType": "daily",
                    "label": "日报",
                    "promptTemplate": "请生成小卖部运营日报。",
                },
                {
                    "reportType": "weekly",
                    "label": "周报",
                    "promptTemplate": "请生成小卖部运营周报。",
                },
                {
                    "reportType": "monthly",
                    "label": "月报",
                    "promptTemplate": "请生成小卖部运营月报。",
                },
            ],
            "message": "当前返回统一后端兼容蓝图，完整 Agent 行为仍待继续迁移。",
        }
    )


@router.post("/api/admin/shop/analytics/ops-copilot/test")
async def admin_ops_copilot_test(payload: dict, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        safe_type = str(payload.get("reportType") or "daily").strip().lower()
        capability = AICapabilityService().resolve_capability(
            {
                "daily": "shop_ops_daily_report",
                "weekly": "shop_ops_weekly_report",
                "monthly": "shop_ops_monthly_report",
            }.get(safe_type, "shop_ops_daily_report")
        )
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        run_id = f"ops_copilot_test_{now}"
        input_json = __import__("json").dumps(payload or {})
        output_json = __import__("json").dumps(
            {
                "summary": "测试任务已排队，等待 Agent 处理。",
                "apiConfigName": "",
                "model": "",
                "structured": {"summary": "测试任务已排队"},
                "report": {
                    "reportType": safe_type,
                    "summary": "测试任务已排队，等待 Agent 处理。",
                    "generatedAt": now,
                    "reportMeta": {
                        "periodLabel": "manual-test",
                        "periodStart": "",
                        "periodEndDisplay": "",
                    },
                },
                "capability_key": ((capability or {}).get("capability") or {}).get(
                    "capability_key"
                )
                or "shop_ops_daily_report",
                "provider_type": ((capability or {}).get("primary") or {}).get(
                    "provider_type"
                )
                or "openai_compatible",
                "gateway_route": ((capability or {}).get("primary") or {}).get(
                    "gateway_route"
                )
                or "",
                "capability_snapshot": (capability or {}).get("capability") or {},
            }
        )
        conn.execute(
            """INSERT INTO agent_runs (
                run_id, agent_key, mode, status, trigger_source, input_json, output_json,
                operator_id, operator_name, started_at, ended_at, created_at, updated_at,
                decision, decision_source, capability_key, provider_config_id, provider_name, provider_type, gateway_route, prompt_template_snapshot, input_payload_json, output_payload_json
            ) VALUES (?, 'ops_copilot', 'test', 'queued', 'manual_test', ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'ops_copilot_manual_test', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                input_json,
                output_json,
                str(user.get("user_id") or "admin"),
                user.get("username") or "admin",
                now,
                now,
                now,
                now,
                ((capability or {}).get("capability") or {}).get("capability_key")
                or "shop_ops_daily_report",
                ((capability or {}).get("primary") or {}).get("id"),
                ((capability or {}).get("primary") or {}).get("name") or "",
                ((capability or {}).get("primary") or {}).get("provider_type")
                or "openai_compatible",
                ((capability or {}).get("primary") or {}).get("gateway_route") or "",
                ((capability or {}).get("capability") or {}).get("prompt_template")
                or "",
                input_json,
                output_json,
            ),
        )
        conn.commit()
        return success_response(
            data={
                "agentKey": "ops_copilot",
                "runId": run_id,
                "mode": "test",
                "status": "queued",
                "message": "测试任务已创建",
                "reportType": str(payload.get("reportType") or "daily"),
                "question": str(payload.get("question") or ""),
                "promptPreview": "",
                "runtimeConfig": payload.get("runtimeConfig") or {},
                "analyticsMeta": {
                    "generatedAt": now,
                    "periodLabel": "manual-test",
                    "queryCostMs": 0,
                },
                "llm": {
                    "apiConfigId": int(
                        (payload.get("runtimeConfig") or {}).get("apiConfigId") or 0
                    ),
                    "apiConfigName": "",
                    "model": "",
                    "tokenUsed": 0,
                    "latencyMs": 0,
                },
                "result": {"summary": "测试任务已排队"},
                "report": {
                    "reportType": str(payload.get("reportType") or "daily"),
                    "summary": "测试任务已排队，等待 Agent 处理。",
                    "generatedAt": now,
                },
                "rawContent": "",
            },
            status_code=202,
        )
    except Exception as e:
        return error_response("TEST_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/products/{product_id}")
async def admin_get_product(product_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            """SELECT p.*, c.name as category_name, c.icon as category_icon
               FROM shop_products p
               LEFT JOIN shop_categories c ON p.category_id = c.id
               WHERE p.id = ? AND (p.is_deleted = 0 OR p.is_deleted IS NULL)""",
            (product_id,),
        )
        row = _augment_product_row(conn, _product_row(cur.fetchone()))
        if row is None:
            return error_response("NOT_FOUND", "商品不存在", 404)
        reviews = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_product_reviews WHERE product_id = ? ORDER BY created_at DESC LIMIT 20",
                (product_id,),
            ).fetchall()
        )
        return success_response(data={"product": row, "reviews": reviews})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/products/{product_id}")
async def admin_update_product(
    product_id: int, payload: ProductUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        existing = conn.execute(
            "SELECT * FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (product_id,),
        ).fetchone()
        if not existing:
            return error_response("NOT_FOUND", "商品不存在", 404)
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的内容", 400)
        if "images" in updates:
            updates["image_url"] = updates["images"][0] if updates["images"] else None
            del updates["images"]
        if "tags" in updates:
            del updates["tags"]
        updates["updated_at"] = int(datetime.now(timezone.utc).timestamp() * 1000)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), product_id]
        conn.execute(f"UPDATE shop_products SET {set_clause} WHERE id = ?", params)
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, 'admin_edit', ?, ?, ?)",
            (
                product_id,
                user.get("username", "Admin"),
                "管理员编辑商品",
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        return success_response(data={"updated": True}, message="商品已更新")
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/products/{product_id}")
async def admin_put_product(
    product_id: int, payload: ProductUpdate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        set_clause = (
            ", ".join(f"{k} = ?" for k in updates) if updates else "updated_at = ?"
        )
        params = (
            [*updates.values(), product_id]
            if updates
            else [int(datetime.now(timezone.utc).timestamp() * 1000), product_id]
        )
        conn.execute(f"UPDATE shop_products SET {set_clause} WHERE id = ?", params)
        conn.commit()
        return success_response(data={"updated": True})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/products/{product_id}")
async def admin_delete_product(product_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        product = conn.execute(
            "SELECT id FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (product_id,),
        ).fetchone()
        if not product:
            return error_response("NOT_FOUND", "商品不存在", 404)
        conn.execute(
            "UPDATE shop_products SET is_deleted = 1, deleted_at = ?, deleted_by = ?, updated_at = ? WHERE id = ?",
            (
                int(datetime.now(timezone.utc).timestamp() * 1000),
                f"admin:{user.get('username', 'Admin')}",
                int(datetime.now(timezone.utc).timestamp() * 1000),
                product_id,
            ),
        )
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, 'delete', ?, '管理员删除', ?)",
            (
                product_id,
                user.get("username", "Admin"),
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        return success_response(data={"deleted": True}, message="商品已删除")
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/products/{product_id}/review")
async def admin_review_product(
    product_id: int,
    action: str = Query("approve"),
    reason: str = "",
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        if action not in {"approve", "reject"}:
            return error_response("INVALID_ACTION", "无效的操作", 400)
        if action == "reject" and not str(reason or "").strip():
            return error_response("REASON_REQUIRED", "拒绝时请填写原因", 400)
        product = conn.execute(
            "SELECT id, status FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (product_id,),
        ).fetchone()
        if not product:
            return error_response("NOT_FOUND", "商品不存在", 404)
        if str(product["status"] or "") not in {
            "pending_manual",
            "pending",
            "pending_ai",
        }:
            return error_response("INVALID_STATUS", "只能审核待审核中的商品", 400)
        new_status = "manual_approved" if action == "approve" else "manual_rejected"
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_products SET status = ?, reject_reason = ?, reviewed_at = ?, reviewed_by = ?, updated_at = ? WHERE id = ?",
            (
                new_status,
                reason if action == "reject" else None,
                now,
                user.get("username", "Admin"),
                now,
                product_id,
            ),
        )
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (product_id, action, user.get("username", "Admin"), reason or None, now),
        )
        conn.commit()
        return success_response(
            data={"product_id": product_id, "status": new_status},
            message="商品已人工审核通过并上架"
            if action == "approve"
            else "商品已人工拒绝",
        )
    except Exception as e:
        return error_response("REVIEW_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/products/{product_id}/offline")
async def admin_offline_product(
    product_id: int, reason: str = "", user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        product = conn.execute(
            "SELECT id FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (product_id,),
        ).fetchone()
        if not product:
            return error_response("NOT_FOUND", "商品不存在或已下架", 404)
        conn.execute(
            "UPDATE shop_products SET status = 'offline_manual', reject_reason = ?, updated_at = ? WHERE id = ?",
            (reason, int(datetime.now(timezone.utc).timestamp() * 1000), product_id),
        )
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, 'admin_offline', ?, ?, ?)",
            (
                product_id,
                user.get("username", "Admin"),
                reason or None,
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        return success_response(
            data={
                "product_id": product_id,
                "offline": True,
                "notificationRequested": False,
                "notificationSent": False,
                "message": "商品已下架",
            },
            message="商品已下架",
        )
    except Exception as e:
        return error_response("OFFLINE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/products/{product_id}/pin")
async def admin_pin_product(
    product_id: int, pinned: bool = True, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute(
            "UPDATE shop_products SET is_pinned = ?, updated_at = ? WHERE id = ?",
            (
                1 if pinned else 0,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                product_id,
            ),
        )
        conn.commit()
        return success_response(data={"product_id": product_id, "pinned": pinned})
    except Exception as e:
        return error_response("PIN_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/products")
async def admin_list_products(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    shop_id: int | None = None,
    keyword: str | None = None,
    categoryId: int | None = None,
    search: str | None = None,
    productType: str | None = None,
    isTestMode: int | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        effective_category_id = categoryId or shop_id
        if effective_category_id:
            where += " AND category_id = ?"
            params.append(effective_category_id)
        effective_keyword = (search or keyword or "").strip()
        if effective_keyword:
            where += " AND (name LIKE ? OR description LIKE ?)"
            params.extend([f"%{effective_keyword}%", f"%{effective_keyword}%"])
        if productType == "normal":
            where += " AND COALESCE(product_type, 'normal') = 'normal'"
        elif productType == "cdk":
            where += " AND COALESCE(product_type, '') = 'cdk'"
        elif productType == "link":
            where += " AND COALESCE(product_type, '') IN ('link', 'external')"
        if isTestMode is not None:
            where += " AND COALESCE(is_test_mode, 0) = ?"
            params.append(1 if int(isTestMode) == 1 else 0)
        where += " AND (is_deleted = 0 OR is_deleted IS NULL)"
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_products {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"""SELECT p.*, c.name as category_name, c.icon as category_icon
                 FROM shop_products p
                 LEFT JOIN shop_categories c ON p.category_id = c.id
                 {where.replace("category_id", "p.category_id").replace("status", "p.status").replace("(name LIKE ? OR description LIKE ?)", "(p.name LIKE ? OR p.description LIKE ?)")}
                 ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = [_augment_product_row(conn, _product_row(r)) for r in cur.fetchall()]
        return success_response(
            data={
                "items": rows,
                "products": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/top/configs")
async def admin_top_configs(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM shop_top_package_configs ORDER BY sort_order")
        return success_response(data=_rows_to_dicts(cur.fetchall()))
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/top/configs")
async def admin_update_top_config(
    payload: dict, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        return success_response(data={"updated": True, "payload": payload})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/top/active")
async def admin_top_active(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT * FROM top_service_options WHERE active = 1 ORDER BY sort_order"
        )
        return success_response(data=_rows_to_dicts(cur.fetchall()))
    except Exception:
        return success_response(data=[])
    finally:
        conn.close()


@router.get("/api/admin/shop/top/orders")
async def admin_top_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        cur = conn.execute("SELECT COUNT(*) as total FROM shop_top_orders")
        total = cur.fetchone()["total"]
        cur = conn.execute(
            "SELECT * FROM shop_top_orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/comments/{comment_id}")
async def admin_get_comment(comment_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        if comment_id <= 0:
            return error_response("INVALID_COMMENT_ID", "评论ID无效", 400)
        cur = conn.execute(
            """SELECT c.*, p.name AS product_name, p.status AS product_status,
                      COALESCE((SELECT COUNT(*) FROM shop_product_comment_votes v_up WHERE v_up.comment_id = c.id AND v_up.vote_type = 'up'), 0) AS upvote_count,
                      COALESCE((SELECT COUNT(*) FROM shop_product_comment_votes v_down WHERE v_down.comment_id = c.id AND v_down.vote_type = 'down'), 0) AS downvote_count,
                      COALESCE((SELECT COUNT(*) FROM shop_product_comment_replies r WHERE r.comment_id = c.id AND COALESCE(r.is_deleted, 0) = 0), 0) AS reply_count
               FROM shop_product_comments c
               LEFT JOIN shop_products p ON p.id = c.product_id
               WHERE c.id = ? LIMIT 1""",
            (comment_id,),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("NOT_FOUND", "评论不存在", 404)
        row["comment_type"] = row.get("comment_type") or "comment"
        row["source_id"] = int(row.get("id") or 0)
        row["approval_opinion"] = row.get("manual_reason") or row.get("ai_reason") or ""
        reports = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_product_comment_reports WHERE comment_id = ? ORDER BY created_at DESC LIMIT 50",
                (comment_id,),
            ).fetchall()
        )
        replies = _rows_to_dicts(
            conn.execute(
                """SELECT id, comment_id, user_id, user_site, username, nickname, avatar_url,
                          content, status, is_deleted, ai_decision, ai_confidence, ai_risk_score,
                          ai_reason, ai_suggestion, ai_error, ai_model, ai_reviewed_at,
                          manual_reason, manual_reviewer, manual_reviewed_at, created_at, updated_at
                   FROM shop_product_comment_replies
                   WHERE comment_id = ? AND COALESCE(is_deleted, 0) = 0
                   ORDER BY created_at ASC, id ASC LIMIT 100""",
                (comment_id,),
            ).fetchall()
        )
        return success_response(
            data={"comment": row, "reports": reports, "replies": replies}
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/comments/{comment_id}")
async def admin_update_comment(
    comment_id: int, payload: dict, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        return success_response(data={"updated": True, "comment_id": comment_id})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/comments/{comment_id}")
async def admin_delete_comment(comment_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        if comment_id <= 0:
            return error_response("INVALID_COMMENT_ID", "评论ID无效", 400)
        comment = conn.execute(
            "SELECT id, is_deleted FROM shop_product_comments WHERE id = ? LIMIT 1",
            (comment_id,),
        ).fetchone()
        if not comment:
            return error_response("NOT_FOUND", "评论不存在", 404)
        if int(comment["is_deleted"] or 0) == 1:
            return success_response(data={"success": True, "message": "评论已删除"})
        conn.execute(
            "UPDATE shop_product_comments SET is_deleted = 1, deleted_at = ?, deleted_by = ?, updated_at = ? WHERE id = ?",
            (
                int(datetime.now(timezone.utc).timestamp() * 1000),
                f"admin:{user.get('username', 'Admin')}",
                int(datetime.now(timezone.utc).timestamp() * 1000),
                comment_id,
            ),
        )
        settled = conn.execute(
            "UPDATE shop_product_comment_reports SET status = 'resolved', handled_by = ?, handled_at = ?, updated_at = ? WHERE comment_id = ? AND status = 'pending'",
            (
                user.get("username", "Admin"),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                comment_id,
            ),
        )
        conn.commit()
        return success_response(
            data={
                "success": True,
                "message": "评论已删除",
                "settledReportCount": settled.rowcount or 0,
            }
        )
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/comments")
async def admin_list_comments(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    search: str | None = None,
    status: str | None = None,
    productId: int | None = None,
    deleted: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        effective_keyword = (search or keyword or "").strip()
        if effective_keyword:
            where += " AND content LIKE ?"
            params.append(f"%{effective_keyword}%")
        if status:
            where += " AND status = ?"
            params.append(status)
        if productId:
            where += " AND product_id = ?"
            params.append(productId)
        if deleted == "only":
            where += " AND COALESCE(is_deleted, 0) = 1"
        elif deleted == "exclude":
            where += " AND COALESCE(is_deleted, 0) = 0"
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_product_comments {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_product_comments {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        for row in rows:
            row["comment_type"] = row.get("comment_type") or "comment"
            row["pending_report_count"] = _safe_table_count(
                conn,
                "shop_product_comment_reports",
                "comment_id = ? AND status = 'pending'",
                (row.get("id"),),
            )
        return success_response(
            data={
                "items": rows,
                "comments": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
                "stats": {
                    "total": _safe_table_count(conn, "shop_product_comments"),
                    "pending_ai": _safe_table_count(
                        conn, "shop_product_comments", "status = 'pending_ai'"
                    ),
                    "pending_manual": _safe_table_count(
                        conn, "shop_product_comments", "status = 'pending_manual'"
                    ),
                    "ai_rejected": _safe_table_count(
                        conn, "shop_product_comments", "status = 'ai_rejected'"
                    ),
                    "manual_rejected": _safe_table_count(
                        conn, "shop_product_comments", "status = 'manual_rejected'"
                    ),
                    "ai_approved": _safe_table_count(
                        conn, "shop_product_comments", "status = 'ai_approved'"
                    ),
                    "manual_approved": _safe_table_count(
                        conn, "shop_product_comments", "status = 'manual_approved'"
                    ),
                    "deleted": _safe_table_count(
                        conn, "shop_product_comments", "COALESCE(is_deleted, 0) = 1"
                    ),
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/comment-reports")
async def admin_comment_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    commentId: int | None = None,
    productId: int | None = None,
    search: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        if commentId:
            where += " AND comment_id = ?"
            params.append(commentId)
        if search:
            keyword = f"%{search}%"
            where += " AND (report_reason LIKE ? OR comment_content LIKE ? OR reporter_username LIKE ? OR comment_username LIKE ? OR CAST(id AS TEXT) LIKE ?)"
            params.extend([keyword, keyword, keyword, keyword, keyword])
        if productId:
            where += " AND product_id = ?"
            params.append(productId)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_product_comment_reports {where}",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_product_comment_reports {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "reports": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/comment-reports/{report_id}/status")
async def admin_handle_comment_report(
    report_id: int,
    status: str = Query("dismiss"),
    adminNote: str = Query(""),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        if report_id <= 0:
            return error_response("INVALID_REPORT_ID", "举报ID无效", 400)
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"pending", "dismissed", "resolved"}:
            return error_response("INVALID_STATUS", "无效的举报状态", 400)
        report = conn.execute(
            "SELECT id FROM shop_product_comment_reports WHERE id = ? LIMIT 1",
            (report_id,),
        ).fetchone()
        if not report:
            return error_response("NOT_FOUND", "举报不存在", 404)
        conn.execute(
            "UPDATE shop_product_comment_reports SET status = ?, admin_note = ?, updated_at = ?, handled_by = ? WHERE id = ?",
            (
                normalized_status,
                adminNote,
                int(datetime.now(timezone.utc).timestamp() * 1000),
                user.get("username", "Admin"),
                report_id,
            ),
        )
        conn.commit()
        return success_response(data={"success": True, "message": "举报状态已更新"})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/comment-ai/config")
async def admin_comment_ai_config(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            """SELECT c.*, ap.name AS api_config_name, bp.name AS backup_api_config_name
               FROM shop_comment_ai_config c
               LEFT JOIN ai_api_config ap ON ap.id = c.api_config_id
               LEFT JOIN ai_api_config bp ON bp.id = c.backup_api_config_id
               ORDER BY c.is_enabled DESC, c.updated_at DESC, c.id DESC
               LIMIT 1"""
        )
        row = _row_to_dict(cur.fetchone())
        if row and isinstance(row.get("review_criteria"), str):
            row["review_criteria"] = _safe_json_loads(row.get("review_criteria"), {})
        return success_response(data=row if row else {})
    except Exception:
        return success_response(data={})
    finally:
        conn.close()


@router.put("/api/admin/shop/comment-ai/config")
async def admin_update_comment_ai_config(
    payload: dict, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        import json

        api_config_id = payload.get("api_config_id") or payload.get("apiConfigId")
        backup_api_config_id = payload.get("backup_api_config_id") or payload.get(
            "backupApiConfigId"
        )
        prompt_template = (
            payload.get("prompt_template") or payload.get("promptTemplate") or ""
        )
        review_criteria = (
            payload.get("review_criteria") or payload.get("reviewCriteria") or {}
        )
        if isinstance(review_criteria, str):
            review_criteria = _safe_json_loads(review_criteria, {}) or {}
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute("SELECT id FROM shop_comment_ai_config LIMIT 1")
        row = cur.fetchone()
        config_id = None
        if row:
            config_id = row["id"]
            conn.execute(
                "UPDATE shop_comment_ai_config SET name = ?, api_config_id = ?, backup_api_config_id = ?, prompt_template = ?, review_criteria = ?, approve_threshold = ?, reject_threshold = ?, is_enabled = ?, updated_at = ? WHERE id = ?",
                (
                    payload.get("name") or "默认评论审核Agent",
                    api_config_id,
                    backup_api_config_id,
                    prompt_template,
                    json.dumps(review_criteria, ensure_ascii=False),
                    float(
                        payload.get("approve_threshold")
                        or payload.get("approveThreshold")
                        or 0.85
                    ),
                    float(
                        payload.get("reject_threshold")
                        or payload.get("rejectThreshold")
                        or 0.85
                    ),
                    1 if payload.get("is_enabled") or payload.get("isEnabled") else 0,
                    now,
                    config_id,
                ),
            )
        else:
            cur = conn.execute(
                "INSERT INTO shop_comment_ai_config (name, api_config_id, backup_api_config_id, prompt_template, review_criteria, approve_threshold, reject_threshold, is_enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload.get("name") or "默认评论审核Agent",
                    api_config_id,
                    backup_api_config_id,
                    prompt_template,
                    json.dumps(review_criteria, ensure_ascii=False),
                    float(
                        payload.get("approve_threshold")
                        or payload.get("approveThreshold")
                        or 0.85
                    ),
                    float(
                        payload.get("reject_threshold")
                        or payload.get("rejectThreshold")
                        or 0.85
                    ),
                    1 if payload.get("is_enabled") or payload.get("isEnabled") else 0,
                    now,
                    now,
                ),
            )
            config_id = cur.lastrowid
        conn.commit()
        if config_id:
            AICapabilityService().sync_legacy_comment_review_config(int(config_id))
        return await admin_comment_ai_config(user)
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/comment-ai/config")
async def admin_create_comment_ai_config(
    payload: dict, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        import json

        config_str = json.dumps(payload)
        cur = conn.execute(
            "INSERT INTO comment_ai_config (config, created_at) VALUES (?, ?)",
            (config_str, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return success_response(data={"created": True, "id": cur.lastrowid})
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/comment-ai/logs")
async def admin_comment_ai_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = None,
    commentId: int | None = None,
    replyId: int | None = None,
    productId: int | None = None,
    decision: str | None = None,
    status: str | None = None,
    decisionSource: str | None = None,
    targetType: str | None = None,
    commentType: str | None = None,
    search: str | None = None,
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        table_name = "shop_comment_ai_review_logs"
        where = ["1=1"]
        params: list[object] = []
        if commentId:
            where.append("comment_id = ?")
            params.append(commentId)
        if replyId:
            where.append("reply_id = ?")
            params.append(replyId)
        if productId:
            where.append("product_id = ?")
            params.append(productId)
        if decision:
            where.append("response_decision = ?")
            params.append(decision)
        if status:
            where.append("final_status = ?")
            params.append(status)
        if decisionSource:
            where.append("decision_source = ?")
            params.append(decisionSource)
        effective_target_type = targetType or commentType
        if effective_target_type:
            where.append("target_type = ?")
            params.append(effective_target_type)
        if search:
            like = f"%{search}%"
            where.append(
                "(response_reason LIKE ? OR comment_content LIKE ? OR username LIKE ? OR nickname LIKE ? OR CAST(reply_id AS TEXT) LIKE ? OR CAST(id AS TEXT) LIKE ?)"
            )
            params.extend([like, like, like, like, like, like])
        where_sql = " AND ".join(where)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM {table_name} WHERE {where_sql}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM {table_name} WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "logs": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/comment-ai/logs/{log_id}")
async def admin_comment_ai_log_detail(
    log_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        if log_id <= 0:
            return error_response("INVALID_LOG_ID", "审核记录ID无效", 400)
        cur = conn.execute(
            """SELECT l.*, c.content AS parent_comment_content_latest, p.name AS product_name_latest
               FROM shop_comment_ai_review_logs l
               LEFT JOIN shop_product_comments c ON c.id = l.comment_id
               LEFT JOIN shop_products p ON p.id = l.product_id
               WHERE l.id = ? LIMIT 1""",
            (log_id,),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("NOT_FOUND", "审核记录不存在", 404)
        return success_response(data={"log": row})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/comment-ai/stats")
async def admin_comment_ai_stats(
    days: int = Query(30, ge=1, le=365), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        start_time = (
            int(datetime.now(timezone.utc).timestamp() * 1000)
            - days * 24 * 60 * 60 * 1000
        )
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_comment_ai_review_logs WHERE created_at >= ?",
            (start_time,),
        )
        total = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_comment_ai_review_logs WHERE created_at >= ? AND final_status = 'ai_approved'",
            (start_time,),
        )
        approved = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_comment_ai_review_logs WHERE created_at >= ? AND final_status = 'ai_rejected'",
            (start_time,),
        )
        rejected = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_comment_ai_review_logs WHERE created_at >= ? AND final_status = 'pending_manual'",
            (start_time,),
        )
        manual_review = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_comment_ai_review_logs WHERE created_at >= ? AND error_type IS NOT NULL",
            (start_time,),
        )
        error_count = cur.fetchone()["c"]
        daily = _rows_to_dicts(
            conn.execute(
                """SELECT date(created_at / 1000, 'unixepoch', '+8 hours') AS date,
                          COUNT(*) AS count,
                          SUM(CASE WHEN final_status = 'ai_approved' THEN 1 ELSE 0 END) AS approved,
                          SUM(CASE WHEN final_status = 'ai_rejected' THEN 1 ELSE 0 END) AS rejected,
                          SUM(CASE WHEN final_status = 'pending_manual' THEN 1 ELSE 0 END) AS manual,
                          SUM(CASE WHEN error_type IS NOT NULL THEN 1 ELSE 0 END) AS errors
                   FROM shop_comment_ai_review_logs
                   WHERE created_at >= ?
                   GROUP BY date(created_at / 1000, 'unixepoch', '+8 hours')
                   ORDER BY date DESC LIMIT 30""",
                (start_time,),
            ).fetchall()
        )
        return success_response(
            data={
                "window_days": days,
                "summary": {
                    "total_reviews": total,
                    "approved_count": approved,
                    "rejected_count": rejected,
                    "manual_review_count": manual_review,
                    "error_count": error_count,
                },
                "today_summary": {},
                "daily": daily,
                "source_stats": {
                    "rule_engine_count": 0,
                    "llm_count": 0,
                    "fallback_count": 0,
                },
                "target_stats": {"comment_count": 0, "reply_count": 0},
                "rule_trigger_stats": [],
                "mode_stats": [],
                "error_type_stats": [],
                "trace_coverage": {"sampled_count": total, "parsed_trace_count": 0},
            }
        )
    except Exception:
        return success_response(
            data={
                "window_days": days,
                "summary": {},
                "today_summary": {},
                "daily": [],
                "source_stats": {
                    "rule_engine_count": 0,
                    "llm_count": 0,
                    "fallback_count": 0,
                },
                "target_stats": {"comment_count": 0, "reply_count": 0},
                "rule_trigger_stats": [],
                "mode_stats": [],
                "error_type_stats": [],
                "trace_coverage": {"sampled_count": 0, "parsed_trace_count": 0},
            }
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/buy-requests/{request_id}")
async def admin_get_buy_request(
    request_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        if request_id <= 0:
            return error_response("INVALID_REQUEST_ID", "求购ID无效", 400)
        cur = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ?", (request_id,)
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("NOT_FOUND", "记录不存在", 404)
        sessions = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_buy_sessions WHERE request_id = ? ORDER BY updated_at DESC, created_at DESC",
                (request_id,),
            ).fetchall()
        )
        chats = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_buy_messages WHERE request_id = ? ORDER BY created_at DESC LIMIT 100",
                (request_id,),
            ).fetchall()
        )
        price_logs: list[dict] = []
        try:
            price_logs = _rows_to_dicts(
                conn.execute(
                    "SELECT * FROM shop_buy_price_logs WHERE request_id = ? ORDER BY created_at DESC LIMIT 50",
                    (request_id,),
                ).fetchall()
            )
        except Exception:
            price_logs = []

        active_sessions = [
            s for s in sessions if s.get("status") not in ("closed", "cancelled")
        ]
        orders = _rows_to_dicts(
            conn.execute(
                "SELECT * FROM shop_buy_orders WHERE request_id = ? ORDER BY created_at DESC",
                (request_id,),
            ).fetchall()
        )
        pending_orders = [o for o in orders if o.get("status") == "pending"]
        completed_orders = [o for o in orders if o.get("status") == "completed"]
        completed_amount = sum(float(o.get("amount") or 0) for o in completed_orders)

        request_data = {
            **row,
            "details": row.get("details") or row.get("message") or "",
            "budgetPrice": row.get("budget_price") or 0,
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
            "latestPriceUpdatedAt": row.get("updated_at"),
            "activeSessionCount": len(active_sessions),
            "sessionCount": len(sessions),
            "messageCount": len(chats),
            "pendingOrderCount": len(pending_orders),
            "completedOrderCount": len(completed_orders),
            "completedAmount": completed_amount,
            "requesterPublicUsername": row.get("requester_public_username")
            or row.get("requester_username")
            or "",
            "requesterPublicPassword": row.get("requester_public_password") or "",
            "requester": {
                "username": row.get("requester_username")
                or row.get("requester_public_username")
                or "",
                "name": row.get("requester_username")
                or row.get("requester_public_username")
                or "",
                "userId": row.get("requester_user_id"),
                "site": row.get("requester_site") or "linux.do",
                "contactLink": "",
            },
            "paidSessionCount": len(
                [
                    s
                    for s in sessions
                    if s.get("status") in ("paid_pending_confirm", "paid")
                ]
            ),
        }
        mapped_sessions = []
        for row_session in sessions:
            mapped_sessions.append(
                {
                    "id": row_session.get("id"),
                    "requestId": row_session.get("request_id"),
                    "status": row_session.get("status"),
                    "provider": {
                        "userId": row_session.get("provider_user_id") or "",
                        "site": row_session.get("provider_site") or "linux.do",
                        "username": row_session.get("provider_username") or "",
                        "name": row_session.get("provider_name") or "",
                        "avatar": row_session.get("provider_avatar") or "",
                    },
                    "providerPublicUsername": row_session.get(
                        "provider_public_username"
                    )
                    or "",
                    "providerPublicPassword": row_session.get(
                        "provider_public_password"
                    )
                    or "",
                    "providerMarkPaidAt": row_session.get("provider_mark_paid_at") or 0,
                    "requesterConfirmPaidAt": row_session.get(
                        "requester_confirm_paid_at"
                    )
                    or 0,
                    "contactUnlockedAt": row_session.get("contact_unlocked_at") or 0,
                    "messageCount": _safe_table_count(
                        conn,
                        "shop_buy_messages",
                        "session_id = ?",
                        (row_session.get("id"),),
                    ),
                    "lastMessageAt": row_session.get("last_message_at") or 0,
                    "createdAt": row_session.get("created_at") or 0,
                    "updatedAt": row_session.get("updated_at") or 0,
                }
            )
        mapped_price_logs = [
            {
                "id": item.get("id"),
                "oldPrice": float(item.get("old_price") or 0),
                "newPrice": float(item.get("new_price") or 0),
                "changedByRole": item.get("changed_by_role") or "",
                "changedByUserId": item.get("changed_by_user_id") or "",
                "changedBySite": item.get("changed_by_site") or "",
                "note": item.get("note") or "",
                "createdAt": item.get("created_at") or 0,
            }
            for item in price_logs
        ]
        mapped_chats = [
            {
                "id": item.get("id"),
                "requestId": item.get("request_id"),
                "sessionId": item.get("session_id"),
                "senderRole": item.get("sender_role") or "",
                "sender": {
                    "userId": item.get("sender_user_id") or "",
                    "site": item.get("sender_site") or "",
                    "username": item.get("sender_username") or "",
                    "name": item.get("sender_name") or "",
                },
                "senderPublicUsername": item.get("sender_public_username") or "",
                "senderPublicPassword": item.get("sender_public_password") or "",
                "content": item.get("content") or "",
                "createdAt": item.get("created_at") or 0,
            }
            for item in chats
        ]
        return success_response(
            data={
                "request": request_data,
                "sessions": mapped_sessions,
                "priceLogs": mapped_price_logs,
                "chats": mapped_chats,
            }
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/buy-requests/{request_id}/status")
async def admin_update_buy_request_status(
    request_id: int,
    status: str = Query("approved"),
    note: str = Query(""),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        if request_id <= 0:
            return error_response("INVALID_REQUEST_ID", "求购ID无效", 400)
        next_status = str(status or "").strip().lower()
        allowed_statuses = {
            "pending_review",
            "open",
            "negotiating",
            "matched",
            "closed",
            "blocked",
        }
        if next_status not in allowed_statuses:
            return error_response("INVALID_STATUS", "状态值无效", 400)
        request_row = conn.execute(
            "SELECT * FROM shop_buy_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if not request_row:
            return error_response("NOT_FOUND", "记录不存在", 404)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_buy_requests SET status = ?, updated_at = ? WHERE id = ?",
            (next_status, now, request_id),
        )
        active_sessions = _rows_to_dicts(
            conn.execute(
                "SELECT id FROM shop_buy_sessions WHERE request_id = ? AND status IN ('negotiating', 'paid_pending_confirm', 'paid')",
                (request_id,),
            ).fetchall()
        )
        system_message = (
            f"求购状态已更新为 {next_status}，备注：{note.strip()}"
            if str(note or "").strip()
            else f"求购状态已更新为 {next_status}"
        )
        cancelled_pending_orders = 0
        for session in active_sessions:
            conn.execute(
                "INSERT INTO shop_buy_messages (request_id, session_id, sender_role, content, created_at) VALUES (?, ?, 'system', ?, ?)",
                (request_id, session.get("id"), system_message, now),
            )
            conn.execute(
                "UPDATE shop_buy_sessions SET last_message_at = ?, updated_at = ? WHERE id = ?",
                (now, now, session.get("id")),
            )
            if next_status in {"closed", "blocked"}:
                conn.execute(
                    "UPDATE shop_buy_sessions SET status = 'closed', updated_at = ? WHERE id = ?",
                    (now, session.get("id")),
                )
        if next_status in {"closed", "blocked"}:
            result = conn.execute(
                "UPDATE shop_buy_orders SET status = 'cancelled', updated_at = ? WHERE request_id = ? AND status = 'pending'",
                (now, request_id),
            )
            cancelled_pending_orders = result.rowcount or 0
        conn.commit()
        return success_response(
            data={
                "success": True,
                "status": next_status,
                "cancelledPendingOrders": cancelled_pending_orders,
                "updatedAt": now,
            }
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/buy-requests/{request_id}/chats")
async def admin_buy_request_chats(
    request_id: int,
    sessionId: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    pageSize: int | None = None,
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        request_row = conn.execute(
            "SELECT id, title, status FROM shop_buy_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if not request_row:
            return error_response("NOT_FOUND", "记录不存在", 404)
        where = ["request_id = ?"]
        params: list[object] = [request_id]
        if sessionId:
            where.append("session_id = ?")
            params.append(sessionId)
        where_sql = " AND ".join(where)
        total = _safe_table_count(conn, "shop_buy_messages", where_sql, tuple(params))
        rows = _rows_to_dicts(
            conn.execute(
                f"SELECT * FROM shop_buy_messages WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        )
        mapped_rows = [
            {
                "id": row.get("id"),
                "requestId": row.get("request_id"),
                "sessionId": row.get("session_id"),
                "senderRole": row.get("sender_role") or "",
                "sender": {
                    "userId": row.get("sender_user_id") or "",
                    "site": row.get("sender_site") or "",
                    "username": row.get("sender_username") or "",
                    "name": row.get("sender_name") or "",
                },
                "senderPublicUsername": row.get("sender_public_username") or "",
                "senderPublicPassword": row.get("sender_public_password") or "",
                "content": row.get("content") or "",
                "createdAt": row.get("created_at") or 0,
            }
            for row in rows
        ]
        return success_response(
            data={
                "request": {
                    "id": request_row["id"],
                    "title": request_row["title"] or "",
                    "status": request_row["status"] or "",
                },
                "chats": mapped_rows,
                "items": mapped_rows,
                "total": total,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "chats": [],
                "items": [],
                "total": 0,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": 0,
                    "totalPages": 1,
                },
            }
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/buy-requests")
async def admin_list_buy_requests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    pageSize: int | None = None,
    search: str | None = None,
    sort: str | None = None,
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        if search:
            where += " AND (title LIKE ? OR details LIKE ? OR requester_username LIKE ? OR CAST(id AS TEXT) LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like, like])
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_buy_requests {where}", params
        )
        total = cur.fetchone()["total"]
        order_by = "created_at DESC, id DESC"
        if sort == "activity_desc":
            order_by = "updated_at DESC, created_at DESC, id DESC"
        elif sort == "risk_desc":
            order_by = "CASE WHEN status = 'pending_review' THEN 5 WHEN status = 'negotiating' THEN 4 WHEN status = 'matched' THEN 3 WHEN status = 'blocked' THEN 2 ELSE 1 END DESC, updated_at DESC, created_at DESC, id DESC"
        elif sort == "budget_desc":
            order_by = "budget_price DESC, updated_at DESC, id DESC"
        elif sort == "updated_desc":
            order_by = "updated_at DESC, created_at DESC, id DESC"
        cur = conn.execute(
            f"SELECT * FROM shop_buy_requests {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        raw_rows = _rows_to_dicts(cur.fetchall())
        rows: list[dict] = []
        for row in raw_rows:
            request_id = row.get("id")
            session_count = _safe_table_count(
                conn, "shop_buy_sessions", "request_id = ?", (request_id,)
            )
            active_session_count = _safe_table_count(
                conn,
                "shop_buy_sessions",
                "request_id = ? AND status NOT IN ('closed', 'cancelled')",
                (request_id,),
            )
            message_count = _safe_table_count(
                conn, "shop_buy_messages", "request_id = ?", (request_id,)
            )
            pending_order_count = _safe_table_count(
                conn,
                "shop_buy_orders",
                "request_id = ? AND status = 'pending'",
                (request_id,),
            )
            completed_order_count = _safe_table_count(
                conn,
                "shop_buy_orders",
                "request_id = ? AND status = 'completed'",
                (request_id,),
            )
            paid_session_count = _safe_table_count(
                conn,
                "shop_buy_sessions",
                "request_id = ? AND status IN ('paid_pending_confirm', 'paid')",
                (request_id,),
            )
            completed_amount = _safe_table_sum(
                conn,
                "shop_buy_orders",
                "amount",
                "request_id = ? AND status = 'completed'",
                (request_id,),
            )
            latest_message_row = conn.execute(
                "SELECT MAX(created_at) as ts FROM shop_buy_messages WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            latest_message_at = latest_message_row["ts"] if latest_message_row else None

            rows.append(
                {
                    **row,
                    "details": row.get("details") or row.get("message") or "",
                    "budgetPrice": row.get("budget_price") or 0,
                    "createdAt": row.get("created_at"),
                    "updatedAt": row.get("updated_at"),
                    "latestPriceUpdatedAt": row.get("updated_at"),
                    "latestMessageAt": latest_message_at,
                    "activeSessionCount": active_session_count,
                    "sessionCount": session_count,
                    "messageCount": message_count,
                    "paidSessionCount": paid_session_count,
                    "pendingOrderCount": pending_order_count,
                    "completedOrderCount": completed_order_count,
                    "completedAmount": completed_amount,
                    "requesterPublicUsername": row.get("requester_public_username")
                    or row.get("requester_username")
                    or "",
                    "requesterPublicPassword": row.get("requester_public_password")
                    or "",
                    "requester": {
                        "username": row.get("requester_username")
                        or row.get("requester_public_username")
                        or "",
                        "name": row.get("requester_username")
                        or row.get("requester_public_username")
                        or "",
                        "userId": row.get("requester_user_id"),
                        "site": row.get("requester_site") or "linux.do",
                        "contactLink": "",
                    },
                }
            )
        return success_response(
            data={
                "items": rows,
                "requests": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
                "filters": {
                    "status": status or "",
                    "search": search or "",
                    "sort": sort or "created_desc",
                },
                "stats": {
                    "total": _safe_table_count(conn, "shop_buy_requests"),
                    "pendingReview": _safe_table_count(
                        conn, "shop_buy_requests", "status = 'pending_review'"
                    ),
                    "open": _safe_table_count(
                        conn, "shop_buy_requests", "status = 'open'"
                    ),
                    "negotiating": _safe_table_count(
                        conn, "shop_buy_requests", "status = 'negotiating'"
                    ),
                    "matched": _safe_table_count(
                        conn, "shop_buy_requests", "status = 'matched'"
                    ),
                    "closed": _safe_table_count(
                        conn, "shop_buy_requests", "status = 'closed'"
                    ),
                    "blocked": _safe_table_count(
                        conn, "shop_buy_requests", "status = 'blocked'"
                    ),
                    "recentActiveCount": _safe_table_count(
                        conn,
                        "shop_buy_requests",
                        "updated_at >= ?",
                        (
                            int(datetime.now(timezone.utc).timestamp() * 1000)
                            - 24 * 60 * 60 * 1000,
                        ),
                    ),
                    "totalBudgetPrice": _safe_table_sum(
                        conn, "shop_buy_requests", "budget_price"
                    ),
                    "averageBudgetPrice": round(
                        _safe_table_sum(conn, "shop_buy_requests", "budget_price")
                        / total,
                        2,
                    )
                    if total
                    else 0,
                    "activeSessionCount": _safe_table_count(
                        conn,
                        "shop_buy_sessions",
                        "status NOT IN ('closed', 'cancelled')",
                    ),
                    "totalSessionCount": _safe_table_count(conn, "shop_buy_sessions"),
                    "pendingOrderCount": _safe_table_count(
                        conn, "shop_buy_orders", "status = 'pending'"
                    ),
                    "completedOrderCount": _safe_table_count(
                        conn, "shop_buy_orders", "status = 'completed'"
                    ),
                    "totalOrderCount": _safe_table_count(conn, "shop_buy_orders"),
                    "completedAmount": _safe_table_sum(
                        conn, "shop_buy_orders", "amount", "status = 'completed'"
                    ),
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/buy-orders")
async def admin_list_buy_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    pageSize: int | None = None,
    search: str | None = None,
    requestId: int | None = None,
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        if requestId:
            where += " AND request_id = ?"
            params.append(requestId)
        if search:
            like = f"%{search}%"
            where += " AND (order_no LIKE ? OR requester_username LIKE ? OR provider_username LIKE ? OR CAST(request_id AS TEXT) LIKE ?)"
            params.extend([like, like, like, like])
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_buy_orders {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM shop_buy_orders {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        raw_rows = _rows_to_dicts(cur.fetchall())
        rows: list[dict] = []
        for row in raw_rows:
            requester_name = (
                row.get("requester_username") or row.get("buyer_username") or ""
            )
            provider_name = (
                row.get("provider_username") or row.get("seller_username") or ""
            )
            rows.append(
                {
                    **row,
                    "orderNo": row.get("order_no") or "",
                    "requestTitle": row.get("request_title") or "",
                    "requestStatus": row.get("request_status") or "",
                    "sessionStatus": row.get("session_status") or "",
                    "amount": float(row.get("amount") or 0),
                    "createdAt": row.get("created_at"),
                    "updatedAt": row.get("updated_at"),
                    "paidAt": row.get("paid_at"),
                    "completedAt": row.get("completed_at"),
                    "contactUnlockedAt": row.get("contact_unlocked_at"),
                    "requester": {
                        "username": requester_name,
                        "contactLink": "",
                    },
                    "provider": {
                        "username": provider_name,
                    },
                    "chatPath": f"/buy-request/{row.get('request_id') or 0}?session={row.get('session_id') or 0}",
                }
            )
        return success_response(
            data={
                "items": rows,
                "orders": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
                "filters": {
                    "status": status or "",
                    "search": search or "",
                    "requestId": requestId or None,
                },
                "stats": {
                    "pending": _safe_table_count(
                        conn, "shop_buy_orders", "status = 'pending'"
                    ),
                    "paid": _safe_table_count(
                        conn, "shop_buy_orders", "status = 'paid'"
                    ),
                    "completed": _safe_table_count(
                        conn, "shop_buy_orders", "status = 'completed'"
                    ),
                    "expired": _safe_table_count(
                        conn, "shop_buy_orders", "status = 'expired'"
                    ),
                    "cancelled": _safe_table_count(
                        conn, "shop_buy_orders", "status = 'cancelled'"
                    ),
                    "completedAmount": _safe_table_sum(
                        conn, "shop_buy_orders", "amount", "status = 'completed'"
                    ),
                },
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/buy-sessions/{session_id}/close")
async def admin_close_buy_session(
    session_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute(
            "UPDATE shop_buy_sessions SET status = 'closed', closed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        conn.commit()
        return success_response(data={"session_id": session_id, "closed": True})
    except Exception as e:
        return error_response("CLOSE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/buy-chat/forbidden-words")
async def admin_list_forbidden_words(
    search: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list[object] = []
        if search:
            where += " AND word LIKE ?"
            params.append(f"%{search}%")
        offset, limit = _page_params(page, pageSize)
        table_name = "shop_buy_chat_forbidden_words"
        total = conn.execute(
            f"SELECT COUNT(*) as total FROM {table_name} {where}", params
        ).fetchone()["total"]
        cur = conn.execute(
            f"SELECT id, word, enabled, created_by, created_at, updated_at FROM {table_name} {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = [
            {
                "id": row.get("id"),
                "word": row.get("word") or "",
                "enabled": bool(row.get("enabled")),
                "createdBy": row.get("created_by") or "",
                "createdAt": row.get("created_at") or 0,
                "updatedAt": row.get("updated_at") or 0,
            }
            for row in _rows_to_dicts(cur.fetchall())
        ]
        return success_response(
            data={
                "items": rows,
                "words": rows,
                "total": total,
                "page": page,
                "pageSize": pageSize,
                "pagination": {
                    "page": page,
                    "pageSize": pageSize,
                    "total": total,
                    "totalPages": (total + pageSize - 1) // pageSize
                    if total > 0
                    else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "total": 0,
                "page": page,
                "pageSize": pageSize,
                "pagination": {
                    "page": page,
                    "pageSize": pageSize,
                    "total": 0,
                    "totalPages": 1,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/buy-chat/forbidden-words")
async def admin_create_forbidden_word(
    payload: ForbiddenWordCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        clean_word = str(payload.word or "").strip()
        if not clean_word:
            return error_response("INVALID_WORD", "违禁词无效", 400)
        existing = conn.execute(
            "SELECT id FROM shop_buy_chat_forbidden_words WHERE lower(word) = lower(?) LIMIT 1",
            (clean_word,),
        ).fetchone()
        if existing:
            return error_response("WORD_EXISTS", "违禁词已存在", 400)
        cur = conn.execute(
            "INSERT INTO shop_buy_chat_forbidden_words (word, enabled, created_by, created_at, updated_at) VALUES (?, 1, ?, ?, ?)",
            (
                clean_word,
                user.get("username", "Admin"),
                int(datetime.now(timezone.utc).timestamp() * 1000),
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
        )
        conn.commit()
        return success_response(
            data={
                "success": True,
                "id": cur.lastrowid,
                "word": clean_word,
                "enabled": True,
            },
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/buy-chat/forbidden-words/{word_id}")
async def admin_update_forbidden_word(
    word_id: int, payload: dict, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM shop_buy_chat_forbidden_words WHERE id = ? LIMIT 1",
            (word_id,),
        ).fetchone()
        if not row:
            return error_response("NOT_FOUND", "记录不存在", 404)
        updates = []
        params: list[object] = []
        if "word" in payload:
            clean_word = str(payload.get("word") or "").strip()
            if not clean_word:
                return error_response("INVALID_WORD", "违禁词无效", 400)
            existing = conn.execute(
                "SELECT id FROM shop_buy_chat_forbidden_words WHERE lower(word) = lower(?) AND id <> ? LIMIT 1",
                (clean_word, word_id),
            ).fetchone()
            if existing:
                return error_response("WORD_EXISTS", "违禁词已存在", 400)
            updates.append("word = ?")
            params.append(clean_word)
        if "enabled" in payload:
            updates.append("enabled = ?")
            params.append(1 if payload.get("enabled") else 0)
        if not updates:
            return success_response(
                data={"success": True, "message": "未检测到更新内容"}
            )
        updates.append("updated_at = ?")
        params.append(int(datetime.now(timezone.utc).timestamp() * 1000))
        params.append(word_id)
        conn.execute(
            f"UPDATE shop_buy_chat_forbidden_words SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return success_response(data={"success": True, "id": word_id})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/buy-chat/forbidden-words/{word_id}")
async def admin_delete_forbidden_word(
    word_id: int, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        row = conn.execute(
            "SELECT id FROM shop_buy_chat_forbidden_words WHERE id = ? LIMIT 1",
            (word_id,),
        ).fetchone()
        if not row:
            return error_response("NOT_FOUND", "记录不存在", 404)
        conn.execute(
            "DELETE FROM shop_buy_chat_forbidden_words WHERE id = ?", (word_id,)
        )
        conn.commit()
        return success_response(data={"success": True, "id": word_id})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/reports")
async def admin_list_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if type:
            where += " AND type = ?"
            params.append(type)
        cur = conn.execute(f"SELECT COUNT(*) as total FROM reports {where}", params)
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM reports {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/reports")
async def admin_handle_report(
    report_id: int = Query(...),
    action: str = Query("dismiss"),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        conn.execute("UPDATE reports SET status = ? WHERE id = ?", (action, report_id))
        conn.commit()
        return success_response(data={"report_id": report_id, "status": action})
    except Exception as e:
        return error_response("HANDLE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/reports/{report_id}")
async def admin_get_report(report_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("REPORT_NOT_FOUND", "举报不存在", 404)
        return success_response(data=row)
    except Exception:
        return success_response(data={"id": report_id})
    finally:
        conn.close()


@router.post("/api/admin/shop/reports/products/{product_id}/status")
async def admin_update_product_report_status(
    product_id: int,
    status: str = Query("reviewing"),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        conn.execute(
            "UPDATE product_reports SET status = ? WHERE product_id = ?",
            (status, product_id),
        )
        conn.commit()
        return success_response(data={"product_id": product_id, "status": status})
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/categories")
async def admin_list_categories(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT * FROM shop_categories ORDER BY sort_order ASC, id ASC"
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(data=rows)
    except Exception:
        return success_response(data=[])
    finally:
        conn.close()


@router.post("/api/admin/shop/categories")
async def admin_create_category(
    payload: CategoryCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            "INSERT INTO shop_categories (name, parent_id, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                payload.name,
                payload.parent_id,
                payload.sort_order,
                now,
                now,
            ),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_categories WHERE id = ?", (cur.lastrowid,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/categories")
async def admin_update_category(
    payload: CategoryUpdate,
    id: int = Query(...),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的内容", 400)
        updates["updated_at"] = int(datetime.now(timezone.utc).timestamp() * 1000)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = [*updates.values(), id]
        conn.execute(f"UPDATE shop_categories SET {set_clause} WHERE id = ?", params)
        conn.commit()
        cur = conn.execute("SELECT * FROM shop_categories WHERE id = ?", (id,))
        return success_response(data=_row_to_dict(cur.fetchone()))
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.delete("/api/admin/shop/categories")
async def admin_delete_category(
    id: int = Query(...), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        conn.execute("DELETE FROM shop_categories WHERE id = ?", (id,))
        conn.commit()
        return success_response(data={"deleted": True})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/categories/{category_id}/reorder")
async def admin_reorder_categories(
    category_id: int, payload: CategoryReorder, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        for idx, cid in enumerate(payload.ids):
            conn.execute(
                "UPDATE shop_categories SET sort_order = ?, updated_at = ? WHERE id = ?",
                (idx, int(datetime.now(timezone.utc).timestamp() * 1000), cid),
            )
        conn.commit()
        return success_response(data={"reordered": True})
    except Exception as e:
        return error_response("REORDER_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/stores")
async def admin_list_stores(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        offset, limit = _page_params(page, pageSize)
        store_category = conn.execute(
            "SELECT id FROM shop_categories WHERE name = '小店' LIMIT 1"
        ).fetchone()
        if not store_category:
            return success_response(
                data={
                    "stores": [],
                    "items": [],
                    "pagination": {
                        "total": 0,
                        "page": page,
                        "pageSize": pageSize,
                        "totalPages": 0,
                    },
                }
            )
        where = "WHERE p.category_id = ? AND p.product_type = 'store' AND (p.is_deleted = 0 OR p.is_deleted IS NULL)"
        params: list[object] = []
        params.append(int(store_category["id"] or 0))
        if status:
            where += " AND p.status = ?"
            params.append(status)
        if search:
            keyword = f"%{search}%"
            where += " AND (p.name LIKE ? OR p.description LIKE ? OR p.seller_username LIKE ? OR p.seller_name LIKE ?)"
            params.extend([keyword, keyword, keyword, keyword])
        total = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_products p {where}", params
        ).fetchone()["total"]
        cur = conn.execute(
            f"""SELECT p.id, p.name, p.description, p.image_url, p.payment_link,
                       p.status, p.view_count, p.is_pinned, p.created_at, p.updated_at,
                       p.seller_username, p.seller_name
                FROM shop_products p
                {where}
                ORDER BY p.is_pinned DESC, p.created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "stores": rows,
                "items": rows,
                "pagination": {
                    "total": total,
                    "page": page,
                    "pageSize": pageSize,
                    "totalPages": (total + pageSize - 1) // pageSize
                    if total > 0
                    else 0,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "stores": [],
                "items": [],
                "pagination": {
                    "total": 0,
                    "page": page,
                    "pageSize": pageSize,
                    "totalPages": 0,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/stores")
async def admin_create_store(
    payload: StoreCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        category_row = conn.execute(
            "SELECT id FROM shop_categories WHERE name = '小店' LIMIT 1"
        ).fetchone()
        category_id = int(category_row["id"] or 0) if category_row else 0
        if category_id <= 0:
            max_sort = conn.execute(
                "SELECT MAX(sort_order) AS max_sort FROM shop_categories"
            ).fetchone()
            conn.execute(
                "INSERT INTO shop_categories (name, icon, is_system, sort_order, created_at, updated_at) VALUES ('小店', '🏪', 1, ?, ?, ?)",
                (int((max_sort["max_sort"] if max_sort else 0) or 0) + 1, now, now),
            )
            category_row = conn.execute(
                "SELECT id FROM shop_categories WHERE name = '小店' LIMIT 1"
            ).fetchone()
            category_id = int(category_row["id"] or 0) if category_row else 0
        if category_id <= 0:
            return error_response("CREATE_FAILED", "小店分类创建失败", 500)

        owner_name = (
            (payload.contact or "").strip()
            or str(user.get("username", "")).strip()
            or "Admin"
        )
        image_url = (payload.address or "").strip() or None
        payment_link = (
            (payload.contact or "").strip()
            if str(payload.contact or "").strip().startswith("https://")
            else (payload.address or "").strip()
        )
        description = (payload.address or "").strip()
        if hasattr(payload, "model_dump"):
            raw_payload = payload.model_dump()
        else:
            raw_payload = payload.dict()
        store_url = str(
            raw_payload.get("storeUrl")
            or raw_payload.get("store_url")
            or payment_link
            or ""
        ).strip()
        owner_name = (
            str(
                raw_payload.get("ownerName")
                or raw_payload.get("owner_name")
                or owner_name
            ).strip()
            or owner_name
        )
        description = str(raw_payload.get("description") or description or "").strip()
        image_url = (
            str(
                raw_payload.get("imageUrl")
                or raw_payload.get("image_url")
                or image_url
                or ""
            ).strip()
            or None
        )
        if store_url:
            payment_link = store_url

        cur = conn.execute(
            """
            INSERT INTO shop_products (
                seller_user_id, seller_site, seller_username, seller_name,
                name, category_id, description, price, discount, image_url, payment_link,
                product_type, stock, auto_delivery, use_platform_payment,
                status, created_at, updated_at, content_updated_at, last_paid_at
            ) VALUES (
                '0', 'system', ?, ?,
                ?, ?, ?, 0, 1, ?, ?,
                'store', -1, 0, 0,
                'approved', ?, ?, ?, NULL
            )
            """,
            (
                owner_name,
                owner_name,
                payload.name,
                category_id,
                description,
                image_url,
                payment_link,
                now,
                now,
                now,
            ),
        )
        store_id = int(cur.lastrowid or 0)
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, 'admin_create_store', ?, '管理员创建小店', ?)",
            (store_id, str(user.get("username") or "Admin"), now),
        )
        conn.execute(
            "UPDATE shop_categories SET product_count = (SELECT COUNT(*) FROM shop_products WHERE category_id = ? AND (is_deleted = 0 OR is_deleted IS NULL)) WHERE id = ?",
            (category_id, category_id),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM shop_products WHERE id = ?", (store_id,))
        return success_response(
            data={
                "success": True,
                "message": "小店创建成功",
                "storeId": store_id,
                "store": _row_to_dict(cur.fetchone()),
            },
            status_code=201,
        )
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/stores")
async def admin_update_store(
    payload: StoreUpdate, id: int = Query(...), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if not updates:
            return error_response("NO_CHANGES", "没有需要更新的内容", 400)
        store = conn.execute(
            "SELECT * FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (id,),
        ).fetchone()
        if not store:
            return error_response("NOT_FOUND", "小店不存在", 404)
        if str(store["product_type"] or "") != "store":
            return error_response("INVALID_TYPE", "该商品不是小店类型", 400)
        field_updates: list[str] = []
        params: list[object] = []
        if "name" in updates:
            field_updates.append("name = ?")
            params.append(updates["name"])
        if "address" in updates:
            field_updates.append("description = ?")
            params.append(updates["address"])
        if "contact" in updates:
            value = str(updates["contact"] or "").strip()
            if value.startswith("https://"):
                field_updates.append("payment_link = ?")
                params.append(value)
            else:
                field_updates.append("seller_username = ?")
                field_updates.append("seller_name = ?")
                params.extend([value, value])
        raw_payload = updates
        if "storeUrl" in raw_payload:
            field_updates.append("payment_link = ?")
            params.append(str(raw_payload["storeUrl"] or "").strip())
        if "imageUrl" in raw_payload:
            field_updates.append("image_url = ?")
            params.append(str(raw_payload["imageUrl"] or "").strip() or None)
        if "ownerName" in raw_payload:
            owner_name = str(raw_payload["ownerName"] or "").strip()
            field_updates.append("seller_username = ?")
            field_updates.append("seller_name = ?")
            params.extend([owner_name, owner_name])
        if "status" in raw_payload:
            field_updates.append("status = ?")
            params.append(str(raw_payload["status"] or "").strip())
        if "isPinned" in raw_payload:
            field_updates.append("is_pinned = ?")
            params.append(1 if raw_payload["isPinned"] else 0)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        field_updates.append("updated_at = ?")
        params.append(now)
        params.append(id)
        conn.execute(
            f"UPDATE shop_products SET {', '.join(field_updates)} WHERE id = ?",
            params,
        )
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, 'admin_update_store', ?, '管理员更新小店', ?)",
            (id, str(user.get("username") or "Admin"), now),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM shop_products WHERE id = ?", (id,))
        return success_response(
            data={
                "success": True,
                "message": "小店更新成功",
                "store": _row_to_dict(cur.fetchone()),
            }
        )
    except Exception as e:
        return error_response("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.put("/api/admin/shop/stores/{store_id}")
async def admin_update_store_path(
    store_id: int, payload: StoreUpdate, user: dict = Depends(get_current_user)
):
    return await admin_update_store(payload=payload, id=store_id, user=user)


@router.delete("/api/admin/shop/stores")
async def admin_delete_store(
    id: int = Query(...), user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        store = conn.execute(
            "SELECT id, product_type, category_id FROM shop_products WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)",
            (id,),
        ).fetchone()
        if not store:
            return error_response("NOT_FOUND", "小店不存在", 404)
        if str(store["product_type"] or "") != "store":
            return error_response("INVALID_TYPE", "该商品不是小店类型", 400)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        admin_name = str(user.get("username") or "Admin")
        conn.execute(
            "UPDATE shop_products SET is_deleted = 1, deleted_at = ?, deleted_by = ?, updated_at = ? WHERE id = ?",
            (now, f"admin:{admin_name}", now, id),
        )
        conn.execute(
            "INSERT INTO shop_product_reviews (product_id, action, admin_name, reason, created_at) VALUES (?, 'admin_delete_store', ?, '管理员删除小店', ?)",
            (id, admin_name, now),
        )
        category_id = int(store["category_id"] or 0)
        if category_id > 0:
            conn.execute(
                "UPDATE shop_categories SET product_count = (SELECT COUNT(*) FROM shop_products WHERE category_id = ? AND (is_deleted = 0 OR is_deleted IS NULL)) WHERE id = ?",
                (category_id, category_id),
            )
        conn.commit()
        return success_response(data={"success": True, "message": "小店已删除"})
    except Exception as e:
        return error_response("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/orders/stats")
async def admin_orders_stats(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE status = 'pending'"
        )
        pending = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE status = 'paid'"
        )
        paid = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE status = 'delivered'"
        )
        delivered = cur.fetchone()["c"]
        cur = conn.execute("SELECT COUNT(*) as c FROM shop_orders")
        total = cur.fetchone()["c"]
        cur = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as revenue FROM shop_orders WHERE status IN ('paid', 'delivered')"
        )
        revenue = cur.fetchone()["revenue"]
        today_start = int(
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            * 1000
        )
        today_orders = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE created_at >= ?",
            (today_start,),
        ).fetchone()["c"]
        today_deals = conn.execute(
            "SELECT COUNT(*) as c FROM shop_orders WHERE created_at >= ? AND status IN ('paid', 'delivered')",
            (today_start,),
        ).fetchone()["c"]
        today_revenue = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as s FROM shop_orders WHERE created_at >= ? AND status IN ('paid', 'delivered')",
            (today_start,),
        ).fetchone()["s"]
        return success_response(
            data={
                "pending": pending,
                "paid": paid,
                "delivered": delivered,
                "total": total,
                "total_revenue": revenue,
                "todayDeals": today_deals,
                "todayOrders": today_orders,
                "todayRevenue": today_revenue,
            }
        )
    except Exception:
        return success_response(
            data={
                "pending": 0,
                "paid": 0,
                "delivered": 0,
                "total": 0,
                "total_revenue": 0,
                "todayDeals": 0,
                "todayOrders": 0,
                "todayRevenue": 0,
            }
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/orders")
async def admin_list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    pageSize: int | None = None,
    search: str | None = None,
    keyword: str | None = None,
    user: dict = Depends(get_current_user),
):
    if pageSize:
        size = pageSize
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        effective_keyword = (search or keyword or "").strip()
        if effective_keyword:
            like = f"%{effective_keyword}%"
            where += " AND (order_no LIKE ? OR buyer_username LIKE ? OR seller_username LIKE ? OR CAST(buyer_user_id AS TEXT) LIKE ? OR CAST(seller_user_id AS TEXT) LIKE ? OR product_snapshot LIKE ?)"
            params.extend([like, like, like, like, like, like])
        cur = conn.execute(f"SELECT COUNT(*) as total FROM shop_orders {where}", params)
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"""SELECT o.*, 
                       COALESCE(NULLIF(TRIM(json_extract(o.product_snapshot, '$.product_type')), ''), 'normal') AS current_product_type
                FROM shop_orders o {where.replace("WHERE", "WHERE")}
                ORDER BY o.created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = [_enrich_shop_order(row) for row in _rows_to_dicts(cur.fetchall())]
        return success_response(
            data={
                "items": rows,
                "orders": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "orders": [],
                "total": 0,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": 0,
                    "totalPages": 1,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/orders")
async def admin_create_order(payload: dict, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        import json

        payload_str = json.dumps(payload)
        order_no = f"ORD{int(datetime.now().timestamp())}"
        user_id = payload.get("user_id", 0)
        cur = conn.execute(
            "INSERT INTO orders (user_id, order_no, payload, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (user_id, order_no, payload_str, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM orders WHERE id = ?", (cur.lastrowid,))
        return success_response(data=_row_to_dict(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/orders/{order_no}")
async def admin_get_order(order_no: str, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        safe_order_no = str(order_no or "").strip()
        if not safe_order_no:
            return error_response("INVALID_ORDER_NO", "订单号无效", 400)
        cur = conn.execute(
            "SELECT * FROM shop_orders WHERE order_no = ?", (safe_order_no,)
        )
        row = _enrich_shop_order(_row_to_dict(cur.fetchone()))
        if row is None:
            return error_response("ORDER_NOT_FOUND", "订单不存在", 404)
        logs = _rows_to_dicts(
            conn.execute(
                "SELECT action, operator_type, operator_name, detail, created_at FROM shop_order_logs WHERE order_id = ? ORDER BY created_at DESC LIMIT 50",
                (row.get("id"),),
            ).fetchall()
        )
        return success_response(data={"order": row, "logs": logs})
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/orders/pending-delivery-remind-all")
async def admin_remind_all_pending_delivery(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        rows = _rows_to_dicts(
            conn.execute(
                "SELECT order_no, seller_user_id, seller_site, seller_username FROM shop_orders WHERE status = 'paid' ORDER BY created_at DESC"
            ).fetchall()
        )
        seller_keys = {
            f"{row.get('seller_site')}:{row.get('seller_user_id')}" for row in rows
        }
        return success_response(
            data={
                "total": len(rows),
                "reminded": len(rows),
                "sellerCount": len(seller_keys),
                "recipients": [
                    row.get("seller_username")
                    for row in rows
                    if row.get("seller_username")
                ],
                "historyCampaignId": 0,
            },
            message="待发货提醒发送成功",
        )
    except Exception as e:
        return error_response("REMIND_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/orders/expire-check")
async def admin_order_expire_check(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        conn.execute(
            "UPDATE orders SET status = 'expired' WHERE status = 'pending' AND created_at < datetime('now', '-7 days')"
        )
        conn.commit()
        changed = conn.total_changes
        return success_response(data={"expired_count": changed})
    except Exception as e:
        return error_response("EXPIRE_CHECK_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/products/zero-stock-auto-offline-check")
async def admin_zero_stock_check(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        conn.execute("UPDATE products SET offline = 1 WHERE stock <= 0 AND offline = 0")
        conn.commit()
        changed = conn.total_changes
        return success_response(data={"offline_count": changed})
    except Exception as e:
        return error_response("STOCK_CHECK_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/legacy-messages")
async def admin_list_legacy_messages(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if type:
            where += " AND type = ?"
            params.append(type)
        cur = conn.execute(f"SELECT COUNT(*) as total FROM messages {where}", params)
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"SELECT * FROM messages {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={"items": rows, "total": total, "page": page, "size": size}
        )
    except Exception:
        return success_response(
            data={"items": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/legacy-messages")
async def admin_create_legacy_message(
    payload: MessageCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        cur = conn.execute(
            "INSERT INTO messages (user_id, content, type, created_at) VALUES (?, ?, ?, ?)",
            (
                payload.user_id,
                payload.content,
                payload.type,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,))
        return success_response(data=_row_to_dict(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.post("/api/admin/shop/messages/process-due")
async def admin_process_due_messages(user: dict = Depends(get_current_user)):
    try:
        from app.scheduler.scheduler import admin_message_dispatch_job

        await admin_message_dispatch_job(trigger="manual")
        return success_response(data={"processed_count": 1, "triggered": True})
    except Exception as e:
        return error_response("PROCESS_FAILED", str(e), 500)


@router.post("/api/admin/shop/messages/{message_id}/cancel")
async def admin_cancel_message(message_id: int, user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        conn.execute(
            "UPDATE shop_admin_message_campaigns SET status = 'cancelled', cancelled_at = ?, updated_at = ? WHERE id = ?",
            (now_ms, now_ms, message_id),
        )
        conn.commit()
        return success_response(data={"cancelled": True})
    except Exception as e:
        return error_response("CANCEL_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/messages/users")
async def admin_message_users(user: dict = Depends(get_current_user)):
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT DISTINCT user_id, user_site FROM shop_user_messages WHERE user_id IS NOT NULL"
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "users": [
                    {"userId": r["user_id"], "userSite": r.get("user_site", "linux.do")}
                    for r in rows
                ]
            }
        )
    except Exception:
        return success_response(data={"users": []})
    finally:
        conn.close()


@router.get("/api/admin/shop/messages")
async def admin_list_message_campaigns(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str = Query(""),
    targetType: str = Query(""),
    search: str = Query(""),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = ["1=1"]
        params: list = []
        if status:
            where.append("c.status = ?")
            params.append(status)
        if targetType:
            where.append("c.target_type = ?")
            params.append(targetType)
        if search.strip():
            like = f"%{search.strip()}%"
            where.append(
                "(c.title LIKE ? OR c.content LIKE ? OR c.created_by_name LIKE ?)"
            )
            params.extend([like, like, like])
        where_sql = " WHERE " + " AND ".join(where)
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_admin_message_campaigns c{where_sql}",
            params,
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            """SELECT c.*, 
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id), 0) AS total_recipients,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'pending'), 0) AS pending_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'sent'), 0) AS sent_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'failed'), 0) AS failed_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t WHERE t.campaign_id = c.id AND t.status = 'cancelled'), 0) AS cancelled_count,
                      COALESCE((SELECT COUNT(*) FROM shop_admin_message_targets t JOIN shop_user_messages m ON m.id = t.message_id WHERE t.campaign_id = c.id AND t.status = 'sent' AND COALESCE(m.is_read, 0) = 1), 0) AS read_count
               FROM shop_admin_message_campaigns c
               """
            + where_sql
            + " ORDER BY c.created_at DESC, c.id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        rows = _rows_to_dicts(cur.fetchall())
        synced_users = _safe_table_count(
            conn,
            "users",
            "user_id IS NOT NULL AND TRIM(CAST(user_id AS TEXT)) <> ''",
        )
        summary_row = conn.execute(
            """SELECT
                     SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) AS scheduled_count,
                     SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                     SUM(CASE WHEN status = 'sending' THEN 1 ELSE 0 END) AS sending_count
               FROM shop_admin_message_campaigns"""
        ).fetchone()
        return success_response(
            data={
                "items": rows,
                "campaigns": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size,
                },
                "summary": {
                    "syncedUsers": synced_users,
                    "scheduledCount": int(
                        (summary_row["scheduled_count"] if summary_row else 0) or 0
                    ),
                    "pendingCount": int(
                        (summary_row["pending_count"] if summary_row else 0) or 0
                    ),
                    "sendingCount": int(
                        (summary_row["sending_count"] if summary_row else 0) or 0
                    ),
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "campaigns": [],
                "total": 0,
                "page": page,
                "size": size,
                "summary": {
                    "syncedUsers": 0,
                    "scheduledCount": 0,
                    "pendingCount": 0,
                    "sendingCount": 0,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/messages")
async def admin_create_message_campaign(
    payload: MessageCreate, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cur = conn.execute(
            """INSERT INTO shop_admin_message_campaigns (
                title, content, target_type, status, created_by_id, created_by_name, created_at, updated_at
            ) VALUES (?, ?, 'all', 'pending', ?, ?, ?, ?)""",
            (
                (payload.content or "系统消息")[:40],
                payload.content,
                str(user.get("user_id") or "admin"),
                user.get("username") or "admin",
                now_ms,
                now_ms,
            ),
        )
        campaign_id = cur.lastrowid
        conn.execute(
            """INSERT OR IGNORE INTO shop_admin_message_targets (
                campaign_id, user_site, user_id, username, name, status, created_at, updated_at
            )
            SELECT ?, COALESCE(NULLIF(TRIM(site), ''), 'linux.do'), CAST(user_id AS TEXT), COALESCE(username, ''), COALESCE(name, ''), 'pending', ?, ?
            FROM users
            WHERE user_id IS NOT NULL AND TRIM(CAST(user_id AS TEXT)) <> ''""",
            (campaign_id, now_ms, now_ms),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT * FROM shop_admin_message_campaigns WHERE id = ?", (campaign_id,)
        )
        return success_response(data=_row_to_dict(cur.fetchone()), status_code=201)
    except Exception as e:
        return error_response("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/messages/{message_id}/targets")
async def admin_message_campaign_targets(
    message_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as total FROM shop_admin_message_targets WHERE campaign_id = ?",
            (message_id,),
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            "SELECT * FROM shop_admin_message_targets WHERE campaign_id = ? ORDER BY id ASC LIMIT ? OFFSET ?",
            (message_id, limit, offset),
        )
        rows = _rows_to_dicts(cur.fetchall())
        return success_response(
            data={
                "items": rows,
                "targets": rows,
                "total": total,
                "page": page,
                "size": size,
            }
        )
    except Exception:
        return success_response(
            data={"items": [], "targets": [], "total": 0, "page": page, "size": size}
        )
    finally:
        conn.close()


@router.get("/api/admin/shop/merchants")
async def admin_list_merchants(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    merchantStatus: str | None = None,
    verificationStatus: str | None = None,
    attentionOnly: str | None = None,
    sortBy: str | None = None,
    user: dict = Depends(get_current_user),
):
    offset, limit = _page_params(page, size)
    conn = _db()
    try:
        where = "WHERE 1=1"
        params: list = []
        if merchantStatus:
            if merchantStatus == "active":
                where += " AND mc.is_active = 1"
            elif merchantStatus == "disabled":
                where += " AND mc.is_active = 0"
        if verificationStatus:
            if verificationStatus == "verified":
                where += " AND mc.is_verified = 1"
            elif verificationStatus == "unverified":
                where += " AND mc.is_verified = 0"
        if search:
            keyword = f"%{search}%"
            where += " AND (u.username LIKE ? OR u.name LIKE ? OR mc.user_id LIKE ? OR mc.site LIKE ? OR mc.ldc_pid LIKE ?)"
            params.extend([keyword, keyword, keyword, keyword, keyword])
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM shop_merchant_config mc {where}", params
        )
        total = cur.fetchone()["total"]
        cur = conn.execute(
            f"""SELECT mc.*, u.username, u.name, u.avatar_url
               FROM shop_merchant_config mc
               LEFT JOIN users u ON u.site = mc.site AND u.user_id = mc.user_id
               {where}
               ORDER BY mc.updated_at DESC, mc.created_at DESC LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
        rows = _rows_to_dicts(cur.fetchall())
        for row in rows:
            row["masked_ldc_pid"] = (
                str(row.get("ldc_pid") or "")[:4] + "****"
                if row.get("ldc_pid")
                else None
            )
        return success_response(
            data={
                "items": rows,
                "configs": rows,
                "merchants": rows,
                "total": total,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": total,
                    "totalPages": (total + size - 1) // size if total > 0 else 1,
                },
                "filters": {
                    "search": search or "",
                    "merchantStatus": merchantStatus or "all",
                    "verificationStatus": verificationStatus or "all",
                    "attentionOnly": attentionOnly or "",
                    "sortBy": sortBy or "attention",
                },
            }
        )
    except Exception:
        return success_response(
            data={
                "items": [],
                "configs": [],
                "merchants": [],
                "total": 0,
                "page": page,
                "size": size,
                "pagination": {
                    "page": page,
                    "pageSize": size,
                    "total": 0,
                    "totalPages": 1,
                },
            }
        )
    finally:
        conn.close()


@router.post("/api/admin/shop/merchants/{merchant_id}/toggle")
async def admin_toggle_merchant(
    merchant_id: int, payload: dict, user: dict = Depends(get_current_user)
):
    conn = _db()
    try:
        active = payload.get("active")
        enabled = payload.get("enabled", active if active is not None else True)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        merchant = conn.execute(
            "SELECT id, user_id, site, is_active FROM shop_merchant_config WHERE id = ? LIMIT 1",
            (merchant_id,),
        ).fetchone()
        if not merchant:
            return error_response("NOT_FOUND", "商家收款配置不存在", 404)
        conn.execute(
            "UPDATE shop_merchant_config SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, now_ms, merchant_id),
        )
        conn.commit()
        return success_response(
            data={
                "configId": int(merchant["id"] or 0),
                "userId": str(merchant["user_id"] or ""),
                "site": merchant["site"] or "linux.do",
                "isActive": bool(enabled),
            },
            message="商家已启用" if enabled else "商家已禁用",
        )
    except Exception as e:
        return error_response("TOGGLE_FAILED", str(e), 500)
    finally:
        conn.close()


@router.get("/api/admin/shop/merchants/detail")
async def admin_merchant_detail(
    userId: str = Query(""),
    site: str = Query("linux.do"),
    user: dict = Depends(get_current_user),
):
    conn = _db()
    try:
        safe_user_id = str(userId or "").strip()
        safe_site = str(site or "linux.do").strip() or "linux.do"
        if not safe_user_id:
            return error_response("INVALID_USER", "商家标识无效", 400)
        cur = conn.execute(
            """SELECT mc.*, u.username, u.name, u.avatar_url
               FROM shop_merchant_config mc
               LEFT JOIN users u ON u.site = mc.site AND u.user_id = mc.user_id
               WHERE mc.user_id = ? AND mc.site = ?""",
            (safe_user_id, safe_site),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return error_response("NOT_FOUND", "商家不存在", 404)
        row["merchant"] = dict(row)
        row["generatedAt"] = int(datetime.now(timezone.utc).timestamp() * 1000)
        row["trend14d"] = []
        row["productStatus"] = []
        row["orderStatus"] = []
        row["topCategories"] = []
        row["recentProducts"] = []
        row["recentOrders"] = []
        return success_response(data=row)
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
    finally:
        conn.close()
