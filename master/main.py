import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from common.logging_config import setup_logging

logger = setup_logging("master")

# ── Config ────────────────────────────────────────────────────────────────────
MASTER_HTTP_PORT = int(os.getenv("MASTER_HTTP_PORT", "8000"))
MASTER_GRPC_PORT = int(os.getenv("MASTER_GRPC_PORT", "50051"))
SCHEDULING_STRATEGY = os.getenv("SCHEDULING_STRATEGY", "load_aware")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
TASK_TIMEOUT = float(os.getenv("TASK_TIMEOUT", "120"))
HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", "15"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "5000"))

# ── App state (populated in lifespan) ─────────────────────────────────────────
app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from master.registry import WorkerRegistry
    from master.task_queue import TaskQueue
    from master.health_monitor import run_health_monitor
    from master.grpc_server import start_grpc_server
    from master.scheduler import Scheduler

    registry = WorkerRegistry()
    task_queue = TaskQueue(max_size=MAX_QUEUE_SIZE, task_timeout=TASK_TIMEOUT)
    scheduler = Scheduler(
        registry=registry,
        task_queue=task_queue,
        strategy_name=SCHEDULING_STRATEGY,
        max_retries=MAX_RETRIES,
        task_timeout=TASK_TIMEOUT,
    )

    app_state["registry"] = registry
    app_state["task_queue"] = task_queue
    app_state["scheduler"] = scheduler
    app_state["strategy"] = SCHEDULING_STRATEGY

    grpc_task = asyncio.create_task(
        start_grpc_server(registry, scheduler, MASTER_GRPC_PORT)
    )
    monitor_task = asyncio.create_task(
        run_health_monitor(registry, task_queue, HEARTBEAT_TIMEOUT)
    )
    dispatch_task = asyncio.create_task(scheduler.dispatch_loop())

    logger.info(f"Master started — HTTP:{MASTER_HTTP_PORT} gRPC:{MASTER_GRPC_PORT} strategy:{SCHEDULING_STRATEGY}")
    yield

    grpc_task.cancel()
    monitor_task.cancel()
    dispatch_task.cancel()
    await asyncio.gather(grpc_task, monitor_task, dispatch_task, return_exceptions=True)
    logger.info("Master shutdown complete")


app = FastAPI(title="Distributed AI Inference Master", lifespan=lifespan)

# ── Routers ───────────────────────────────────────────────────────────────────
from master.routers import client, monitoring, config  # noqa: E402

app.include_router(client.router)
app.include_router(monitoring.router)
app.include_router(config.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("master.main:app", host="0.0.0.0", port=MASTER_HTTP_PORT, reload=False)
