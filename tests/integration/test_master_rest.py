import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport, Response
import json

from master.main import app
from master.registry import WorkerRegistry
from master.scheduler import Scheduler
import httpx as _httpx


def make_app_state():
    """Initialize app state without running the full lifespan."""
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
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_infer_503_when_no_workers(client):
    resp = await client.post("/infer", json={"query": "What is distributed computing?"})
    assert resp.status_code == 503


@pytest.mark.anyio
async def test_infer_validates_empty_query(client):
    resp = await client.post("/infer", json={"query": ""})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_worker_returns_worker_id(client):
    resp = await client.post("/workers/register", json={
        "worker_url": "http://worker1:8001",
        "gpu_total_vram_gb": 16.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "worker_id" in data
    assert data["heartbeat_interval_s"] == 2


@pytest.mark.anyio
async def test_workers_list_shows_registered(client):
    await client.post("/workers/register", json={
        "worker_url": "http://w-list:8001",
        "gpu_total_vram_gb": 8.0,
    })
    resp = await client.get("/workers")
    assert resp.status_code == 200
    data = resp.json()
    assert "workers" in data
    assert "active_strategy" in data


@pytest.mark.anyio
async def test_infer_success_with_mock_worker(client):
    reg_resp = await client.post("/workers/register", json={
        "worker_url": "http://mock-worker:8001",
        "gpu_total_vram_gb": 24.0,
    })
    assert reg_resp.status_code == 200
    worker_id = reg_resp.json()["worker_id"]

    mock_body = json.dumps({
        "result": "Distributed computing splits work across machines.",
        "latency_ms": 120.0,
        "rag_sources": ["distributed_systems_0"],
        "gpu_util_pct": 30.0,
        "worker_id": worker_id,
    }).encode()

    with patch.object(app.state.http_client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200,
            content=mock_body,
            headers={"content-type": "application/json"},
            request=MagicMock(),
        )
        resp = await client.post("/infer", json={"query": "Explain distributed computing"})

    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "worker_id" in data
    assert "latency_ms" in data
    assert "rag_sources" in data
