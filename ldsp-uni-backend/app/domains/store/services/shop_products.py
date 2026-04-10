"""Async Product service for managing shop products."""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_store_session

logger = structlog.get_logger(__name__)


class ProductService:
    """Async Service for product-related database operations."""

    async def list_public_products(
        self,
        db: AsyncSession,
        category_id: int | None = None,
        status: str = "ai_approved",
        page: int = 1,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        search: str = "",
        price_min: float | None = None,
        price_max: float | None = None,
    ):
        """Public endpoint: list approved products."""
        where_clauses = ["p.status = :status"]
        params = {"status": status}

        if category_id:
            where_clauses.append("p.category_id = :category_id")
            params["category_id"] = category_id
        if search:
            where_clauses.append("(p.name LIKE :search OR p.description LIKE :search)")
            params["search"] = f"%{search}%"
        if price_min is not None:
            where_clauses.append("p.price >= :price_min")
            params["price_min"] = price_min
        if price_max is not None:
            where_clauses.append("p.price <= :price_max")
            params["price_max"] = price_max

        where_sql = " AND ".join(where_clauses)
        offset = (page - 1) * limit
        limit_val = limit

        # Select products with seller info
        query = text(f"""
            SELECT p.*, u.username as seller_username, u.avatar_url as seller_avatar,
                   c.name as category_name, c.icon as category_icon
            FROM shop_products p
            LEFT JOIN users u ON u.site = p.seller_site AND u.user_id = p.seller_user_id
            LEFT JOIN shop_categories c ON c.id = p.category_id
            WHERE {where_sql}
            ORDER BY p.{sort_by} {sort_order}
            LIMIT :limit OFFSET :offset
        """)

        count_query = text(f"SELECT COUNT(*) FROM shop_products p WHERE {where_sql}")

        result = await db.execute(query, dict(params, limit=limit_val, offset=offset))
        products = [dict(r._mapping) for r in result.fetchall()]  # Safe mapping access
        for item in products:
            price = float(item.get("price") or 0)
            discount = float(item.get("discount") or 1)
            if discount <= 0:
                discount = 1
            item["final_price"] = round(price * discount, 2)
            item["isFavorited"] = bool(item.get("is_favorited") or False)

        count_result = await db.execute(count_query, params)
        total = count_result.scalar_one()

        return {"products": products, "total": total}

    async def create_product(
        self,
        db: AsyncSession,
        user_id: str,
        product_type: str,
        name: str,
        description: str = "",
        category_id: int = 0,
        price: float = 0.0,
        contact_method: str = "",
        images: list | None = None,
        tags: list | None = None,
    ) -> dict:
        """Submit a new product."""
        import json
        import time

        now = str(int(round(time.time() * 1000)))
        query = text("""
            INSERT INTO shop_products 
                (seller_user_id, product_type, name, description, category_id, price, 
                 contact_method, images_json, tags_json, status, created_at, updated_at)
            VALUES 
                (:user_id, :product_type, :name, :description, :category_id, :price, 
                 :contact_method, :images, :tags, 'pending_ai', :now, :now)
        """)

        result = await db.execute(
            query,
            {
                "user_id": user_id,
                "product_type": product_type,
                "name": name,
                "description": description,
                "category_id": category_id,
                "price": price,
                "contact_method": contact_method,
                "images": json.dumps(images or []),
                "tags": json.dumps(tags or []),
                "now": now,
            },
        )
        await db.commit()
        return {"id": result.lastrowid, "message": "提交成功，正在进行 AI 审核"}

    async def get_product_detail(self, db: AsyncSession, product_id: int):
        """Get public product detail."""
        query = text("""
            SELECT p.*, u.username as seller_username, u.avatar_url as seller_avatar,
                   c.name as category_name, c.icon as category_icon
            FROM shop_products p
            LEFT JOIN users u ON u.site = p.seller_site AND u.user_id = p.seller_user_id
            LEFT JOIN shop_categories c ON c.id = p.category_id
            WHERE p.id = :product_id
        """)
        result = await db.execute(query, {"product_id": product_id})
        row = result.mappings().first()
        if not row:
            return None
        product = dict(row)
        price = float(product.get("price") or 0)
        discount = float(product.get("discount") or 1)
        if discount <= 0:
            discount = 1
        product["final_price"] = round(price * discount, 2)
        product["isFavorited"] = bool(product.get("is_favorited") or False)
        return product

    async def record_product_view(
        self,
        db: AsyncSession,
        product_id: int,
        viewer_ip: str,
        viewer_user_id: str | None = None,
    ) -> bool:
        """Increase product view count once per IP per hour."""
        import time

        if not viewer_ip:
            return False
        one_hour_ago = int(time.time() * 1000) - 3600000
        existing_query = text(
            """SELECT id FROM shop_product_views
               WHERE product_id = :product_id AND viewer_ip = :viewer_ip AND created_at > :since
               LIMIT 1"""
        )
        existing = await db.execute(
            existing_query,
            {"product_id": product_id, "viewer_ip": viewer_ip, "since": one_hour_ago},
        )
        if existing.first():
            return False

        now_ms = int(time.time() * 1000)
        await db.execute(
            text(
                "INSERT INTO shop_product_views (product_id, viewer_ip, viewer_user_id, created_at) VALUES (:product_id, :viewer_ip, :viewer_user_id, :created_at)"
            ),
            {
                "product_id": product_id,
                "viewer_ip": viewer_ip,
                "viewer_user_id": viewer_user_id,
                "created_at": now_ms,
            },
        )
        await db.execute(
            text(
                "UPDATE shop_products SET view_count = COALESCE(view_count, 0) + 1 WHERE id = :product_id"
            ),
            {"product_id": product_id},
        )
        await db.commit()
        return True
