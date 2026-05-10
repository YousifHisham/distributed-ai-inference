import time
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from master.main import app_state

router = APIRouter(tags=["monitoring"])


@router.get("/workers")
async def list_workers():
    registry = app_state.get("registry")
    if not registry:
        return {"workers": []}
    workers = registry.get_all()
    return {
        "workers": [
            {
                "node_id": w.node_id,
                "hostname": w.hostname,
                "address": w.address,
                "status": w.status,
                "model_name": w.model_name,
                "active_requests": w.active_requests,
                "total_completed": w.total_completed,
                "total_failed": w.total_failed,
                "avg_latency": round(w.average_latency, 3),
                "cpu_pct": w.cpu_pct,
                "ram_pct": w.ram_pct,
                "gpu_pct": w.gpu_pct,
                "ollama_healthy": w.ollama_healthy,
                "seconds_since_heartbeat": round(time.time() - w.last_heartbeat, 1),
                "registered_at": w.registered_at,
            }
            for w in workers
        ]
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from master.metrics import update_cluster_metrics
        registry = app_state.get("registry")
        task_queue = app_state.get("task_queue")
        scheduler = app_state.get("scheduler")
        if registry and task_queue:
            update_cluster_metrics(registry, task_queue, scheduler)
        return PlainTextResponse(
            generate_latest().decode("utf-8"),
            media_type="text/plain; version=0.0.4",
        )
    except Exception:
        return PlainTextResponse("# metrics unavailable\n")
