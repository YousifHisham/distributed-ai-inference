import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from common.models import RegisterRequest, RegisterResponse, HeartbeatPayload
from common.enums import WorkerStatus

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/workers/register", response_model=RegisterResponse)
async def register_worker(body: RegisterRequest, request: Request) -> RegisterResponse:
    if not body.worker_url:
        raise HTTPException(status_code=400, detail="worker_url is required")

    registry = request.app.state.registry
    node = registry.register(body.worker_url, body.gpu_total_vram_gb)
    return RegisterResponse(worker_id=node.worker_id)


@router.post("/workers/heartbeat")
async def worker_heartbeat(body: HeartbeatPayload, request: Request) -> dict:
    registry = request.app.state.registry
    node = registry.get(body.worker_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Worker not found")

    registry.update_heartbeat(body.worker_id, body)

    # Draining / recovery logic
    if body.gpu_temp_c > 85 or body.ecc_errors > 0:
        registry.set_draining(body.worker_id)
    elif node.status == WorkerStatus.DRAINING and body.gpu_temp_c <= 80 and body.ecc_errors == 0:
        registry.set_healthy(body.worker_id)
    elif node.status == WorkerStatus.UNHEALTHY and body.gpu_temp_c <= 80 and body.ecc_errors == 0:
        # Worker is still sending heartbeats — it's alive, recover it
        registry.set_healthy(body.worker_id)
        logger.info("Worker %s recovered from UNHEALTHY (heartbeat still arriving)", body.worker_id)

    # Update Prometheus per-worker gauges (US5)
    metrics = getattr(request.app.state, "worker_metrics", None)
    if metrics:
        wid = body.worker_id
        metrics["gpu_util"].labels(worker_id=wid).set(body.gpu_util_pct)
        metrics["vram_used"].labels(worker_id=wid).set(body.vram_used_gb)
        metrics["gpu_temp"].labels(worker_id=wid).set(body.gpu_temp_c)
        metrics["active_req"].labels(worker_id=wid).set(body.active_requests)
        status_value = {"HEALTHY": 1.0, "DRAINING": 0.5, "UNHEALTHY": 0.0}.get(
            registry.get(body.worker_id).status.value, 0.0
        )
        metrics["status"].labels(worker_id=wid).set(status_value)

    return {"status": "ok"}
