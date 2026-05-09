from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from master.main import app_state

router = APIRouter(tags=["config"])

VALID_STRATEGIES = {"round_robin", "least_active", "load_aware", "lowest_latency"}


class StrategyRequest(BaseModel):
    strategy: str


@router.post("/config/strategy")
async def set_strategy(body: StrategyRequest):
    if body.strategy not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Choose from: {sorted(VALID_STRATEGIES)}",
        )
    scheduler = app_state.get("scheduler")
    if scheduler:
        scheduler.set_strategy(body.strategy)
    app_state["strategy"] = body.strategy
    return {"status": "ok", "strategy": body.strategy}


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
