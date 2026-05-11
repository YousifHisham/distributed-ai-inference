from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from common.enums import WorkerStatus
from common.models import ClusterStatusResponse, WorkerStatusResponse

router = APIRouter()


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/workers", response_model=ClusterStatusResponse)
async def list_workers(request: Request) -> ClusterStatusResponse:
    registry = request.app.state.registry
    scheduler = request.app.state.scheduler
    workers = registry.all_workers()

    worker_responses = [
        WorkerStatusResponse(
            worker_id=w.worker_id,
            url=w.url,
            status=w.status,
            gpu_util_pct=w.gpu_util_pct,
            vram_used_gb=w.vram_used_gb,
            vram_total_gb=w.vram_total_gb,
            gpu_temp_c=w.gpu_temp_c,
            ecc_errors=w.ecc_errors,
            active_requests=w.active_requests,
            avg_latency_ms=w.avg_latency_ms,
            last_heartbeat=w.last_heartbeat,
        )
        for w in workers
    ]

    return ClusterStatusResponse(
        workers=worker_responses,
        active_strategy=scheduler.current_strategy_name,
        healthy_count=sum(1 for w in workers if w.status == WorkerStatus.HEALTHY),
        draining_count=sum(1 for w in workers if w.status == WorkerStatus.DRAINING),
        unhealthy_count=sum(1 for w in workers if w.status == WorkerStatus.UNHEALTHY),
    )


@router.get("/health")
async def health(request: Request) -> dict:
    registry = request.app.state.registry
    return {
        "status": "ok",
        "healthy_workers": len(registry.get_healthy_workers()),
    }
