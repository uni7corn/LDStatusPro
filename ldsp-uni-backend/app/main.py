"""FastAPI application entry point."""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.auth_middleware import AuthStateMiddleware
from app.core.logging import setup_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    setup_logging()
    logger.info("ldsp-uni-backend starting", env=settings.environment)

    Path("./data").mkdir(parents=True, exist_ok=True)

    from app.db.engine import init_databases

    await init_databases()
    logger.info("databases initialized")

    from app.domains.store.services.ai_capability_service import AICapabilityService

    AICapabilityService().ensure_ready()
    logger.info("store_ai_capabilities_initialized")

    # Register all LangChain agents
    from app.gateway.routes.agents import init_agents

    init_agents()
    logger.info("agents initialized")

    # Start APScheduler (22 jobs)
    from app.scheduler.scheduler import init_scheduler, trigger_startup_jobs

    scheduler = init_scheduler()
    scheduler.start()
    await trigger_startup_jobs()
    logger.info("scheduler_started", job_count=len(scheduler.get_jobs()))

    yield

    # Shutdown
    from app.scheduler.scheduler import shutdown_scheduler

    shutdown_scheduler()
    logger.info("ldsp-uni-backend shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="LDStatusPro Unified AI Backend",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthStateMiddleware)

    # LDStatusPro domain
    from app.domains.ldsp.routes.routes import include_ldsp_routers

    include_ldsp_routers(app)

    # LD Store domain
    from app.domains.store.routes.routes import include_store_routers

    include_store_routers(app)

    # AI Gateway
    from app.gateway.routes import agents, cost, llm, rag

    app.include_router(agents.router)
    app.include_router(cost.router)
    app.include_router(llm.router)
    app.include_router(rag.router)

    @app.get("/api/version")
    async def version():
        return {
            "name": "ldsp-uni-backend",
            "version": "0.1.0",
            "framework": "FastAPI",
            "python": True,
        }

    return app


app = create_app()
