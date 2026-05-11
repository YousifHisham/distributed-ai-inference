import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from common.logging_config import setup_logging

logger = setup_logging("worker")

# ── Config ────────────────────────────────────────────────────────────────────
MASTER_HTTP_URL = os.getenv("MASTER_HTTP_URL", "http://localhost:8000")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
WORKER_MODEL = os.getenv("WORKER_MODEL", "llama3.2:1b")
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "2"))
WORKER_HTTP_PORT = int(os.getenv("WORKER_HTTP_PORT", "8001"))
WORKER_ADVERTISE_HOST = os.getenv("WORKER_ADVERTISE_HOST")

from worker.state import app_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    from worker.ollama_client import OllamaClient
    from worker.metrics_collector import MetricsCollector
    from worker.agent import WorkerAgent

    ollama = OllamaClient(base_url=OLLAMA_URL)
    collector = MetricsCollector()
    agent = WorkerAgent(
        master_http_url=MASTER_HTTP_URL,
        ollama_client=ollama,
        metrics_collector=collector,
        model_name=WORKER_MODEL,
        heartbeat_interval=HEARTBEAT_INTERVAL,
        worker_http_port=WORKER_HTTP_PORT,
        advertise_host=WORKER_ADVERTISE_HOST,
    )

    app_state["agent"] = agent
    app_state["ollama"] = ollama
    app_state["collector"] = collector

    await agent.register_with_master()

    heartbeat_task = asyncio.create_task(agent.heartbeat_loop())

    logger.info(f"Worker started — HTTP:{WORKER_HTTP_PORT} Prometheus:{WORKER_HTTP_PORT} model:{WORKER_MODEL}")
    yield

    await agent.deregister()
    heartbeat_task.cancel()
    await asyncio.gather(heartbeat_task, return_exceptions=True)
    logger.info("Worker shutdown complete")


app = FastAPI(title="Distributed AI Inference Worker", lifespan=lifespan)

from worker.routers import monitoring  # noqa: E402
from worker.routers.cluster import router as cluster_router  # noqa: E402

app.include_router(cluster_router)
app.include_router(monitoring.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("worker.main:app", host="0.0.0.0", port=WORKER_HTTP_PORT, reload=False)
