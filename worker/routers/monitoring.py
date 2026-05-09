from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from worker.main import app_state

router = APIRouter(tags=["monitoring"])


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    try:
        from prometheus_client import generate_latest
        from worker.metrics import update_worker_metrics
        agent = app_state.get("agent")
        collector = app_state.get("collector")
        if agent and collector:
            update_worker_metrics(agent, collector)
        return PlainTextResponse(
            generate_latest().decode("utf-8"),
            media_type="text/plain; version=0.0.4",
        )
    except Exception:
        return PlainTextResponse("# metrics unavailable\n")


@router.get("/health")
async def health():
    agent = app_state.get("agent")
    ollama = app_state.get("ollama")
    ollama_healthy = False
    if ollama:
        ollama_healthy = await ollama.health_check()
    return {
        "status": "healthy" if ollama_healthy else "unhealthy",
        "node_id": agent.node_id if agent else "unknown",
        "ollama_healthy": ollama_healthy,
    }
