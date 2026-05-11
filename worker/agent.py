import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

from common.models import RegisterRequest, HeartbeatPayload
from worker.gpu_metrics import collect_gpu_metrics

logger = logging.getLogger(__name__)

_worker_id: str | None = None
_heartbeat_task: asyncio.Task | None = None


def get_worker_id() -> str | None:
    return _worker_id


async def register(http_client: httpx.AsyncClient) -> str:
    global _worker_id
    master_url = os.getenv("MASTER_HTTP_URL", "http://localhost:8000")
    advertise_host = os.getenv("WORKER_ADVERTISE_HOST", "")
    port = int(os.getenv("WORKER_HTTP_PORT", "8001"))

    if advertise_host:
        worker_url = f"http://{advertise_host}:{port}"
    else:
        worker_url = f"http://host.docker.internal:{port}"

    metrics = collect_gpu_metrics()
    payload = RegisterRequest(
        worker_url=worker_url,
        gpu_total_vram_gb=metrics.vram_total_gb,
    )

    for attempt in range(1, 11):
        try:
            resp = await http_client.post(
                f"{master_url}/workers/register",
                json=payload.model_dump(),
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            _worker_id = data["worker_id"]
            logger.info("Registered with master — worker_id=%s url=%s", _worker_id, worker_url)
            return _worker_id
        except Exception as exc:
            logger.warning("Registration attempt %d/10 failed: %s — retrying in 5s", attempt, exc)
            await asyncio.sleep(5)

    raise RuntimeError(f"Could not register with master at {master_url} after 10 attempts")


async def _heartbeat_loop(http_client: httpx.AsyncClient) -> None:
    master_url = os.getenv("MASTER_HTTP_URL", "http://localhost:8000")
    interval = float(os.getenv("HEARTBEAT_INTERVAL", "0.25"))

    while True:
        await asyncio.sleep(interval)
        if _worker_id is None:
            continue
        try:
            from worker.main import get_active_requests
            metrics = collect_gpu_metrics()
            payload = HeartbeatPayload(
                worker_id=_worker_id,
                gpu_util_pct=metrics.gpu_util_pct,
                vram_used_gb=metrics.vram_used_gb,
                vram_total_gb=metrics.vram_total_gb,
                gpu_temp_c=metrics.gpu_temp_c,
                ecc_errors=metrics.ecc_errors,
                active_requests=get_active_requests(),
                timestamp=datetime.now(timezone.utc),
            )
            await http_client.post(
                f"{master_url}/workers/heartbeat",
                json=payload.model_dump(mode="json"),
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)


async def start_heartbeat(http_client: httpx.AsyncClient) -> None:
    global _heartbeat_task
    _heartbeat_task = asyncio.create_task(_heartbeat_loop(http_client))


async def stop_heartbeat() -> None:
    global _heartbeat_task
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
        _heartbeat_task = None
