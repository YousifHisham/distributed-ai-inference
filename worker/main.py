import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from common.logging_config import setup_logging

logger = setup_logging("worker")

# ── Config ────────────────────────────────────────────────────────────────────
MASTER_GRPC_URL = os.getenv("MASTER_GRPC_URL", "localhost:50051")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
WORKER_MODEL = os.getenv("WORKER_MODEL", "llama3.2:1b")
WORKER_MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT", "4"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "5"))
WORKER_HTTP_PORT = int(os.getenv("WORKER_HTTP_PORT", "8001"))
WORKER_GRPC_PORT = int(os.getenv("WORKER_GRPC_PORT", "50052"))

app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from worker.ollama_client import OllamaClient
    from worker.metrics_collector import MetricsCollector
    from worker.agent import WorkerAgent
    from worker.grpc_server import start_grpc_server

    ollama = OllamaClient(base_url=OLLAMA_URL)
    collector = MetricsCollector()
    agent = WorkerAgent(
        master_grpc_url=MASTER_GRPC_URL,
        ollama_client=ollama,
        metrics_collector=collector,
        model_name=WORKER_MODEL,
        max_concurrent=WORKER_MAX_CONCURRENT,
        heartbeat_interval=HEARTBEAT_INTERVAL,
        grpc_port=WORKER_GRPC_PORT,
    )

    app_state["agent"] = agent
    app_state["ollama"] = ollama
    app_state["collector"] = collector

    await agent.register_with_master()

    grpc_task = asyncio.create_task(
        start_grpc_server(agent, ollama, collector, WORKER_MAX_CONCURRENT, WORKER_GRPC_PORT)
    )
    heartbeat_task = asyncio.create_task(agent.heartbeat_loop())

    logger.info(f"Worker started — gRPC:{WORKER_GRPC_PORT} Prometheus:{WORKER_HTTP_PORT} model:{WORKER_MODEL}")
    yield

    await agent.deregister()
    grpc_task.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(grpc_task, heartbeat_task, return_exceptions=True)
    logger.info("Worker shutdown complete")


app = FastAPI(title="Distributed AI Inference Worker", lifespan=lifespan)

from worker.routers import monitoring  # noqa: E402

app.include_router(monitoring.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("worker.main:app", host="0.0.0.0", port=WORKER_HTTP_PORT, reload=False)
