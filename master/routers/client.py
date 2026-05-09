from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from master.main import app_state

router = APIRouter(tags=["inference"])


class InferRequestBody(BaseModel):
    query: str


@router.post("/infer")
async def infer(body: InferRequestBody):
    task_queue = app_state.get("task_queue")
    if not task_queue:
        raise HTTPException(status_code=503, detail="Service not ready")
    task = await task_queue.enqueue(body.query)
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
        return {
            "request_id": refreshed.request_id,
            "error": refreshed.error,
            "retry_count": refreshed.retry_count,
        }
    return {
        "request_id": refreshed.request_id,
        "result": refreshed.result,
        "latency": round((refreshed.updated_at - refreshed.created_at), 3),
        "worker_id": refreshed.assigned_worker_id,
        "retry_count": refreshed.retry_count,
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
