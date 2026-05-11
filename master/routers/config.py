from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from common.models import StrategyConfigRequest
from common.enums import StrategyType

router = APIRouter()


@router.post("/config/strategy")
async def set_strategy(body: StrategyConfigRequest, request: Request) -> dict:
    scheduler = request.app.state.scheduler
    await scheduler.swap_strategy(body.strategy)
    return {
        "strategy": body.strategy.value,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
