"""Agent gateway routes — LangChain Agent execution endpoints."""

from __future__ import annotations

import structlog
from pydantic import BaseModel
from typing import Any

from fastapi import APIRouter, HTTPException

from app.common.utils.response import error_response, success_response
from app.gateway.agents.registry import registry, register_all_agents

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/admin/agents", tags=["agents"])


# ──────────────────────────────────────────
# Request models
# ──────────────────────────────────────────


class AgentRunRequest(BaseModel):
    content: str
    target_id: str = "test"
    context: dict[str, Any] = {}
    config: dict[str, Any] = {}
    target_type: str | None = None


class AgentTestRequest(BaseModel):
    content: str
    context: dict[str, Any] = {}


# ──────────────────────────────────────────
# Routes
# ──────────────────────────────────────────


@router.get("")
async def list_agents():
    """List all registered agents."""
    return success_response(data={"agents": registry.list_agents()})


@router.get("/{agent_key}/stats")
async def agent_stats(agent_key: str):
    """Get agent statistics."""
    try:
        registry.get(agent_key)
    except KeyError:
        return error_response("AGENT_NOT_FOUND", f"Agent '{agent_key}' not found", 404)

    # Query stats from DB
    import sqlite3
    from app.config import settings

    conn = sqlite3.connect(settings.store_database_path)
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN response_decision = 'approve' THEN 1 ELSE 0 END) as approved, "
            "SUM(CASE WHEN response_decision = 'reject' THEN 1 ELSE 0 END) as rejected, "
            "SUM(CASE WHEN response_decision = 'manual_review' THEN 1 ELSE 0 END) as manual, "
            "AVG(response_confidence) as avg_confidence "
            "FROM ai_review_logs WHERE product_id IN (SELECT id FROM shop_products WHERE category_id IS NOT NULL) LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
    except Exception:
        row = None
        conn.close()

    return success_response(
        data={
            "agent_key": agent_key,
            "status": "active",
            "stats": {
                "total_runs": row[0] if row else 0,
                "approved": row[1] if row else 0,
                "rejected": row[2] if row else 0,
                "manual_review": row[3] if row else 0,
                "avg_confidence": row[4] if row else 0,
            },
        }
    )


@router.post("/{agent_key}/run")
async def agent_run(agent_key: str, req: AgentRunRequest):
    """Execute an agent in production mode."""
    try:
        agent = registry.get(agent_key)
    except KeyError:
        return error_response("AGENT_NOT_FOUND", f"Agent '{agent_key}' not found", 404)

    try:
        result = await agent.run(
            content=req.content,
            target_id=req.target_id,
            context=req.context,
            config=req.config,
        )
        return success_response(data=result)
    except Exception as e:
        logger.error("agent_run_failed", agent_key=agent_key, error=str(e))
        return error_response("AGENT_RUN_FAILED", str(e), 500)


@router.post("/{agent_key}/test")
async def agent_test(agent_key: str, req: AgentTestRequest):
    """Test an agent with sample content."""
    try:
        agent = registry.get(agent_key)
    except KeyError:
        return error_response("AGENT_NOT_FOUND", f"Agent '{agent_key}' not found", 404)

    try:
        result = await agent.run(
            content=req.content,
            target_id="test_001",
            context=req.context,
        )
        return success_response(
            data={
                "test_mode": True,
                "agent_key": agent_key,
                **result,
            }
        )
    except Exception as e:
        return error_response("AGENT_TEST_FAILED", str(e), 500)


@router.get("/{agent_key}/runs")
async def agent_runs(agent_key: str, limit: int = 50, offset: int = 0):
    """List recent agent runs."""
    try:
        registry.get(agent_key)
    except KeyError:
        return error_response("AGENT_NOT_FOUND", f"Agent '{agent_key}' not found", 404)

    # For now, return placeholder
    return success_response(
        data={"runs": [], "total": 0, "limit": limit, "offset": offset}
    )


@router.get("/{agent_key}/control-config")
async def get_control_config(agent_key: str):
    """Get agent control config (thresholds, mode, etc.)."""
    return success_response(
        data={
            "agent_key": agent_key,
            "mode": "production",
            "auto_approve_threshold": 0.85,
            "auto_reject_threshold": 0.85,
            "is_enabled": True,
        }
    )


@router.put("/{agent_key}/control-config")
async def update_control_config(agent_key: str):
    """Update agent control config."""
    return success_response(data={"message": "Config updated (stub)"})


# ──────────────────────────────────────────
# Startup: register all agents
# ──────────────────────────────────────────


def init_agents() -> None:
    """Register all agents. Call this at app startup."""
    try:
        register_all_agents()
        logger.info("agents_initialized", count=len(registry.list_agents()))
    except Exception as e:
        logger.warning("agent_registration_failed", error=str(e))
