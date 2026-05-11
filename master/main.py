import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_client import Counter, Histogram, Gauge

from master.registry import WorkerRegistry
from master.scheduler import Scheduler
from master.health_monitor import HealthMonitor
from master.routers import client, workers, config, monitoring
from common.enums import StrategyType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    http_client = httpx.AsyncClient(timeout=35.0)
    registry = WorkerRegistry()
    scheduler = Scheduler(registry, http_client)
    health_monitor = HealthMonitor(registry)

    # Prometheus metrics
    requests_total = Counter(
        "inference_requests_total",
        "Total inference requests",
        ["strategy", "worker_id", "status"],
    )
    latency_histogram = Histogram(
        "inference_latency_seconds",
        "End-to-end inference latency",
        ["strategy", "worker_id"],
    )
    worker_metrics = {
        "gpu_util": Gauge("worker_gpu_util_pct", "GPU utilization %", ["worker_id"]),
        "vram_used": Gauge("worker_vram_used_gb", "VRAM used GB", ["worker_id"]),
        "gpu_temp": Gauge("worker_gpu_temp_c", "GPU temperature Celsius", ["worker_id"]),
        "active_req": Gauge("worker_active_requests", "Active in-flight requests", ["worker_id"]),
        "status": Gauge("worker_status", "Worker health (1=HEALTHY 0.5=DRAINING 0=UNHEALTHY)", ["worker_id"]),
    }

    scheduler.requests_total = requests_total
    scheduler.latency_histogram = latency_histogram

    app.state.registry = registry
    app.state.scheduler = scheduler
    app.state.http_client = http_client
    app.state.worker_metrics = worker_metrics

    # Apply initial strategy from env
    initial_strategy = os.getenv("SCHEDULING_STRATEGY", "load_aware")
    try:
        await scheduler.swap_strategy(StrategyType(initial_strategy))
    except Exception:
        logger.warning("Unknown SCHEDULING_STRATEGY=%s — using load_aware", initial_strategy)

    await health_monitor.start()
    await scheduler.start()

    yield

    await scheduler.stop()
    await health_monitor.stop()
    await http_client.aclose()


app = FastAPI(title="Master Node", lifespan=lifespan)

app.include_router(client.router)
app.include_router(workers.router)
app.include_router(config.router)
app.include_router(monitoring.router)
