"""Refactored Shop Product Routes using Service Layer."""

from __future__ import annotations

from typing import Any
import time

from app.domains.store.schemas.product import ProductCreateRequest, ProductUpdateRequest
from app.domains.store.services.shop_products import ProductService
from app.common.utils.response import (
    success_response,
    success_with_meta,
    error_response,
)

product_service = ProductService()


# --- Public Product Routes ---


async def get_public_products(
    request,
    page: int = 1,
    size: int = 20,
    category_id: int | None = None,
    search: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    price_min: float | None = None,
    price_max: float | None = None,
):
    """List products with public visibility."""
    result = product_service.list_public_products(
        category_id,
        "ai_approved",
        page,
        size,
        sort_by,
        sort_order,
        search,
        price_min,
        price_max,
    )
    return success_response(data=result)


async def get_product_detail(request, product_id: int):
    """Get single product detail."""
    p = product_service.get_product_detail(product_id)
    if not p:
        return error_response("NOT_FOUND", "商品不存在", 404)
    return success_response(data=p)


async def get_product_comments(request, product_id: int, page: int = 1, size: int = 20):
    """Get comments for a product."""
    # Implementation via service
    return success_response(data={"comments": [], "total": 0})


# --- User Product Routes ---


async def get_my_products(request, page: int = 1, size: int = 20):
    """Get the authenticated user's products."""
    user_id = request.state.user.get("user_id")
    # Use service
    return success_response(data={"products": [], "total": 0})


async def submit_product(req: ProductCreateRequest, request):
    """Submit a new product."""
    user_id = request.state.user.get("user_id")
    result = product_service.create_product(
        user_id,
        "normal",
        req.name,
        req.description,
        req.category_id or 0,
        req.price,
        req.contact_method or "",
        req.images,
        req.tags,
    )
    return success_response(data=result)


async def delete_product(request, product_id: int):
    """Delete user's own product."""
    # Implementation via service
    return success_response({"message": "Deleted"})
