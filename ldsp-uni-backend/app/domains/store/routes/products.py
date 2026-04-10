"""Shop Product routes - Refactored Service Layer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.response import success_response, error_response
from app.db.engine import get_store_session
from app.domains.store.schemas.product import ProductCreateRequest
from app.domains.store.services.shop_products import ProductService

router = APIRouter(tags=["products"])
product_service = ProductService()


# Public Product Routes


@router.get("/api/shop/products")
async def list_products(
    request: Request,
    db: AsyncSession = Depends(get_store_session),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    pageSize: int | None = Query(None),
    category_id: int | None = Query(None),
    categoryId: int | None = Query(None),
    keyword: str | None = Query(None),
    search: str | None = Query(None),
    min_price: float | None = Query(None),
    priceMin: float | None = Query(None),
    max_price: float | None = Query(None),
    priceMax: float | None = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    sortBy: str | None = Query(None),
    sortOrder: str | None = Query(None),
    inStock: str | None = Query(None),
):
    safe_size = pageSize or size
    safe_category_id = categoryId or category_id
    safe_search = search or keyword or ""
    safe_price_min = priceMin if priceMin is not None else min_price
    safe_price_max = priceMax if priceMax is not None else max_price
    safe_sort_by = (sortBy or sort or "created_at").strip()
    safe_sort_order = (sortOrder or order or "desc").strip().lower()
    normalized_sort_map = {
        "updated_at": "updated_at",
        "created_at": "created_at",
        "view_count": "view_count",
        "sold_count": "sold_count",
        "final_price": "price",
        "price": "price",
    }
    effective_sort_by = normalized_sort_map.get(safe_sort_by, "created_at")
    result = await product_service.list_public_products(
        db,
        category_id=safe_category_id,
        page=page,
        limit=safe_size,
        sort_by=effective_sort_by,
        sort_order=safe_sort_order,
        search=safe_search,
        price_min=safe_price_min,
        price_max=safe_price_max,
    )
    items = result["products"]
    if str(inStock or "").lower() in {"1", "true", "yes"}:
        items = [item for item in items if int(item.get("stock") or 0) > 0]
    return success_response(
        data={
            "items": items,
            "products": items,
            "total": result["total"],
            "page": page,
            "size": safe_size,
            "pagination": {
                "total": result["total"],
                "page": page,
                "pageSize": safe_size,
                "totalPages": (result["total"] + safe_size - 1) // safe_size
                if result["total"] > 0
                else 1,
            },
        }
    )


@router.get("/api/shop/products/{product_id}")
async def get_product(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_store_session),
):
    product = await product_service.get_product_detail(db, product_id)
    if not product:
        return error_response("NOT_FOUND", "商品不存在", 404)
    viewer_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.client.host
        if request.client
        else ""
    )
    viewer_user_id = (
        request.state.user.get("user_id")
        if getattr(request.state, "user", None)
        else None
    )
    try:
        viewed = await product_service.record_product_view(
            db, product_id, viewer_ip, viewer_user_id
        )
        if viewed:
            product["view_count"] = int(product.get("view_count") or 0) + 1
    except Exception:
        pass
    product["isFavorited"] = bool(
        product.get("is_favorited") or product.get("isFavorited") or False
    )
    product["is_favorited"] = bool(product.get("isFavorited"))
    return success_response(data=product)


# User Product Routes


@router.post("/api/shop/products")
async def submit_product(
    req: ProductCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_store_session),
):
    user_id = request.state.user.get("user_id")
    product_type = (req.product_type or "normal").strip().lower()
    result = await product_service.create_product(
        db,
        user_id=user_id,
        product_type=product_type,
        name=req.name,
        description=req.description,
        category_id=req.category_id or 0,
        price=req.price,
        contact_method=req.contact_method,
        images=req.images,
        tags=req.tags,
    )
    return success_response(data=result)
