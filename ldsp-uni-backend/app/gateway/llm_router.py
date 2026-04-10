"""LLM Router — multi-provider routing with fallback. Skeleton."""

from __future__ import annotations

from app.core.exceptions import AllProvidersFailedError


class LLMRouter:
    """Multi-model router with automatic fallback."""

    def __init__(self, config):
        self.providers = {}
        self.fallback_chain: list[str] = []

    async def invoke(self, prompt: str, **kwargs) -> dict:
        raise NotImplementedError("LLM routers need provider implementations")
