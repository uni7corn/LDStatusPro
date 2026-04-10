"""LD Store domain routes registration."""

from __future__ import annotations

from app.domains.store.routes import (
    shop_routes,
    shop_agent_routes,
    shop_ai_review_routes,
    image_ai_config_routes,
    internal_runtime_routes,
    schedule_routes,
    buy_sessions_routes,
    order_detail_routes,
    cdk_routes,
    message_routes,
    shop_admin_extra,
    products,  # Refactored Product Service Layer
)


def include_store_routers(app):
    """Register all LD Store domain routers."""
    # Core Store Routes (Legacy/Backfill)
    app.include_router(shop_routes.router)

    # Refactored Modules (Overrides for Products)
    app.include_router(products.router)

    # Agent & AI
    app.include_router(shop_agent_routes.router)
    app.include_router(shop_ai_review_routes.router)
    app.include_router(image_ai_config_routes.router)
    app.include_router(internal_runtime_routes.router)
    app.include_router(schedule_routes.router)

    # Other Domains
    app.include_router(buy_sessions_routes.router)
    app.include_router(order_detail_routes.router)
    app.include_router(cdk_routes.router)
    app.include_router(message_routes.router)
    app.include_router(shop_admin_extra.router)
