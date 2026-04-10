"""LLM gateway routes backed by database AI gateway config."""

from fastapi import APIRouter

from app.common.utils.response import success_response, error_response
from app.gateway.config_loader import build_llm_runtime_config

router = APIRouter(prefix="/api/gateway/llm", tags=["llm"])


@router.get("/models")
async def list_models():
    try:
        runtime = build_llm_runtime_config()
        models = []
        primary = runtime.get("primary")
        fallback = runtime.get("fallback")
        if primary:
            models.append(
                {
                    "id": primary.get("model"),
                    "provider": primary.get("name") or "primary",
                    "status": "primary",
                    "config_id": primary.get("id"),
                    "base_url": primary.get("base_url"),
                }
            )
        if fallback:
            models.append(
                {
                    "id": fallback.get("model"),
                    "provider": fallback.get("name") or "fallback",
                    "status": "fallback",
                    "config_id": fallback.get("id"),
                    "base_url": fallback.get("base_url"),
                }
            )
        return success_response(
            data={"models": models, "review_config": runtime.get("review_config")}
        )
    except Exception as e:
        return error_response("QUERY_FAILED", str(e), 500)
