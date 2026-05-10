import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from common.logging_config import setup_logging

logger = setup_logging("master")

# ── Config ────────────────────────────────────────────────────────────────────
MASTER_HTTP_PORT = int(os.getenv("MASTER_HTTP_PORT", "8000"))
SCHEDULING_STRATEGY = os.getenv("SCHEDULING_STRATEGY", "load_aware")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
TASK_TIMEOUT = float(os.getenv("TASK_TIMEOUT", "120"))
HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", "6"))
HEALTH_CHECK_INTERVAL = float(os.getenv("HEALTH_CHECK_INTERVAL", "1"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "5000"))
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_DOCS_DIR = os.getenv("RAG_DOCS_DIR", "rag/knowledge_base")
RAG_DB_DIR = os.getenv("RAG_DB_DIR", ".chroma")

# ── App state (populated in lifespan) ─────────────────────────────────────────
app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from master.registry import WorkerRegistry
    from master.task_queue import TaskQueue
    from master.health_monitor import run_health_monitor
    from master.scheduler import Scheduler
    from rag.retriever import ChromaRetriever

    registry = WorkerRegistry()
    task_queue = TaskQueue(max_size=MAX_QUEUE_SIZE, task_timeout=TASK_TIMEOUT)
    scheduler = Scheduler(
        registry=registry,
        task_queue=task_queue,
        strategy_name=SCHEDULING_STRATEGY,
        max_retries=MAX_RETRIES,
        task_timeout=TASK_TIMEOUT,
    )
    rag_retriever = ChromaRetriever(docs_dir=RAG_DOCS_DIR, db_dir=RAG_DB_DIR)
    if RAG_ENABLED:
        rag_retriever.initialize()

    app_state["registry"] = registry
    app_state["task_queue"] = task_queue
    app_state["scheduler"] = scheduler
    app_state["strategy"] = SCHEDULING_STRATEGY
    app_state["task_timeout"] = TASK_TIMEOUT
    app_state["rag_enabled"] = RAG_ENABLED
    app_state["rag_top_k"] = RAG_TOP_K
    app_state["rag_retriever"] = rag_retriever

    monitor_task = asyncio.create_task(
        run_health_monitor(registry, task_queue, HEARTBEAT_TIMEOUT, HEALTH_CHECK_INTERVAL)
    )
    dispatch_task = asyncio.create_task(scheduler.dispatch_loop())

    logger.info(f"Master started — HTTP:{MASTER_HTTP_PORT} strategy:{SCHEDULING_STRATEGY}")
    yield

    monitor_task.cancel()
    dispatch_task.cancel()
    await asyncio.gather(monitor_task, dispatch_task, return_exceptions=True)
    logger.info("Master shutdown complete")


app = FastAPI(title="Distributed AI Inference Master", lifespan=lifespan)

# ── Routers ───────────────────────────────────────────────────────────────────
from master.routers import client, monitoring, config, workers  # noqa: E402

app.include_router(client.router)
app.include_router(monitoring.router)
app.include_router(config.router)
app.include_router(workers.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("master.main:app", host="0.0.0.0", port=MASTER_HTTP_PORT, reload=False)
