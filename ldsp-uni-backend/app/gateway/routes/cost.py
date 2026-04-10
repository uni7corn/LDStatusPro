"""Agent cost tracking routes — placeholder."""

from fastapi import APIRouter

from app.common.utils.response import success_response

router = APIRouter(prefix="/api/gateway/cost", tags=["cost"])


@router.get("")
async def cost_dashboard():
    return success_response(
        data={
            "daily_token_used": 0,
            "daily_cost": 0.0,
            "total_requests": 0,
            "daily_budget": 50.0,
        }
    )
