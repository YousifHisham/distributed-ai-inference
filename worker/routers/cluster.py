from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from worker.main import app_state
from common.logging_config import setup_logging

logger = setup_logging("worker.cluster")
router = APIRouter(tags=["worker"])


class InferRequest(BaseModel):
    request_id: str
    query: str
    timeout: float = 120.0


@router.post("/infer")
async def infer(request: InferRequest):
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=503, detail="Worker not ready")
    logger.info(f"[{request.request_id}] Inference started: query={request.query[:80]!r}")
    result = await agent.infer(request.request_id, request.query, request.timeout)
    if result.get("error"):
        logger.warning(f"[{request.request_id}] Inference failed: {result['error']}")
    else:
        logger.info(
            f"[{request.request_id}] Inference done"
            f" in {result.get('inference_time', 0):.2f}s"
        )
    return result
