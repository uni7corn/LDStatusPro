"""Agent Registry — centralized agent discovery and instantiation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.config import constants
from app.gateway.agents.base_agent import BaseAgent

if TYPE_CHECKING:
    from langgraph.graph import CompiledStateGraph

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """Central registry for all agents.

    Usage:
        # Register
        registry = AgentRegistry()
        registry.register("shop_product_review", product_review_agent)

        # Get
        agent = registry.get("shop_product_review")
        result = await agent.run(content="...", target_id="123")

        # List
        registry.list_agents()
    """

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._graphs: dict[str, CompiledStateGraph] = {}

    def register(self, agent_key: str, agent: BaseAgent) -> None:
        """Register an agent instance."""
        self._agents[agent_key] = agent
        self._graphs[agent_key] = agent._graph
        logger.info(
            "agent_registered", agent_key=agent_key, version=agent.agent_version
        )

    def get(self, agent_key: str) -> BaseAgent:
        """Get an agent by key."""
        if agent_key not in self._agents:
            known = ", ".join(self._agents.keys())
            raise KeyError(f"Agent '{agent_key}' not found. Known agents: {known}")
        return self._agents[agent_key]

    def list_agents(self) -> list[dict]:
        """List all registered agents."""
        return [
            {
                "agent_key": agent.agent_key,
                "agent_name": agent.agent_name,
                "agent_version": agent.agent_version,
                "target_type": agent.target_type,
                "description": agent.description,
                "auto_approve_threshold": agent.auto_approve_threshold,
                "auto_reject_threshold": agent.auto_reject_threshold,
            }
            for agent in self._agents.values()
        ]


# ──────────────────────────────────────────
# Global singleton
# ──────────────────────────────────────────

registry = AgentRegistry()


def register_all_agents() -> None:
    """Register all agents at application startup."""
    from app.gateway.agents.product_review import ProductReviewAgent
    from app.gateway.agents.comment_review import CommentReviewAgent

    registry.register(
        constants.AGENT_PRODUCT_REVIEW,
        ProductReviewAgent(),
    )
    registry.register(
        constants.AGENT_COMMENT_REVIEW,
        CommentReviewAgent(),
    )
    logger.info("all_agents_registered", count=len(registry.list_agents()))
