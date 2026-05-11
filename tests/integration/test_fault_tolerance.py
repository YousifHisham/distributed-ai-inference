import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
import httpx as _httpx

from master.main import app
from master.registry import WorkerRegistry
from master.scheduler import Scheduler
from common.enums import WorkerStatus


def make_app_state():
    http = _httpx.AsyncClient(timeout=35.0)
    registry = WorkerRegistry()
    scheduler = Scheduler(registry, http)
    app.state.registry = registry
    app.state.scheduler = scheduler
    app.state.http_client = http
    app.state.worker_metrics = None
    return http


@pytest_asyncio.fixture
async def client():
    http = make_app_state()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await http.aclose()


@pytest.mark.anyio
async def test_unhealthy_worker_not_routed(client):
    r1 = await client.post("/workers/register", json={
        "worker_url": "http://fault-w1:8001",
        "gpu_total_vram_gb": 24.0,
    })
    r2 = await client.post("/workers/register", json={
        "worker_url": "http://fault-w2:8001",
        "gpu_total_vram_gb": 24.0,
    })
    assert r1.status_code == 200
    assert r2.status_code == 200
    w1_id = r1.json()["worker_id"]

    registry = app.state.registry
    registry.mark_unhealthy(w1_id)

    assert registry.get(w1_id).status == WorkerStatus.UNHEALTHY
    schedulable = registry.get_schedulable_workers()
    assert all(w.worker_id != w1_id for w in schedulable)


@pytest.mark.anyio
async def test_worker_reregisters_as_healthy(client):
    registry = app.state.registry

    r1 = await client.post("/workers/register", json={
        "worker_url": "http://rereg-w1:8001",
        "gpu_total_vram_gb": 24.0,
    })
    w1_id = r1.json()["worker_id"]
    registry.mark_unhealthy(w1_id)
    assert registry.get(w1_id).status == WorkerStatus.UNHEALTHY

    r2 = await client.post("/workers/register", json={
        "worker_url": "http://rereg-w1:8001",
        "gpu_total_vram_gb": 24.0,
    })
    assert r2.status_code == 200
    w2_id = r2.json()["worker_id"]
    assert registry.get(w2_id).status == WorkerStatus.HEALTHY


@pytest.mark.anyio
async def test_draining_worker_excluded_from_routing(client):
    registry = app.state.registry

    r = await client.post("/workers/register", json={
        "worker_url": "http://drain-w1:8001",
        "gpu_total_vram_gb": 24.0,
    })
    wid = r.json()["worker_id"]
    registry.set_draining(wid)

    schedulable = registry.get_schedulable_workers()
    assert all(w.worker_id != wid for w in schedulable)


@pytest.mark.anyio
async def test_draining_recovers_on_heartbeat(client):
    registry = app.state.registry

    r = await client.post("/workers/register", json={
        "worker_url": "http://recover-w1:8001",
        "gpu_total_vram_gb": 24.0,
    })
    wid = r.json()["worker_id"]
    registry.set_draining(wid)
    assert registry.get(wid).status == WorkerStatus.DRAINING

    hb_resp = await client.post("/workers/heartbeat", json={
        "worker_id": wid,
        "gpu_util_pct": 20.0,
        "vram_used_gb": 4.0,
        "vram_total_gb": 24.0,
        "gpu_temp_c": 75.0,
        "ecc_errors": 0,
        "active_requests": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    assert hb_resp.status_code == 200
    assert registry.get(wid).status == WorkerStatus.HEALTHY
