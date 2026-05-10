from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from master.main import app_state
from common.logging_config import setup_logging

logger = setup_logging("master.client")
router = APIRouter(tags=["inference"])


class InferRequestBody(BaseModel):
    query: str


@router.post("/infer")
async def infer(body: InferRequestBody):
    task_queue = app_state.get("task_queue")
    if not task_queue:
        raise HTTPException(status_code=503, detail="Service not ready")

    prompt = body.query
    rag_sources: list[str] = []
    rag_enabled = bool(app_state.get("rag_enabled", False))
    retriever = app_state.get("rag_retriever")
    if rag_enabled and retriever:
        chunks = retriever.retrieve(body.query, top_k=int(app_state.get("rag_top_k", 3)))
        prompt = retriever.build_prompt(body.query, chunks)
        rag_sources = [chunk.source for chunk in chunks]

    logger.info(f"Incoming request: query={body.query[:80]!r} rag={rag_enabled} sources={rag_sources}")
    task = await task_queue.enqueue(
        prompt,
        original_query=body.query,
        rag_sources=rag_sources,
        rag_enabled=rag_enabled,
    )
    # Wait for completion via asyncio.Event
    import asyncio
    event = asyncio.Event()
    task_queue.register_waiter(task.request_id, event)
    try:
        await asyncio.wait_for(event.wait(), timeout=float(app_state.get("task_timeout", 130)))
    except asyncio.TimeoutError:
        pass
    refreshed = task_queue.get(task.request_id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="Task lost")
    if refreshed.error:
        logger.warning(
            f"Request {refreshed.request_id} FAILED"
            f" error={refreshed.error} retries={refreshed.retry_count}"
        )
        return {
            "request_id": refreshed.request_id,
            "error": refreshed.error,
            "retry_count": refreshed.retry_count,
            "rag_sources": refreshed.rag_sources,
        }
    latency = round(refreshed.updated_at - refreshed.created_at, 3)
    logger.info(
        f"Request {refreshed.request_id} OK"
        f" worker={refreshed.assigned_worker_id}"
        f" latency={latency}s retries={refreshed.retry_count}"
    )
    return {
        "request_id": refreshed.request_id,
        "result": refreshed.result,
        "latency": latency,
        "worker_id": refreshed.assigned_worker_id,
        "retry_count": refreshed.retry_count,
        "rag_sources": refreshed.rag_sources,
    }


@router.get("/tasks/{request_id}")
async def get_task(request_id: str):
    task_queue = app_state.get("task_queue")
    if not task_queue:
        raise HTTPException(status_code=503, detail="Service not ready")
    task = task_queue.get(request_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
