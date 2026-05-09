"""
Integration tests for Master REST API endpoints.
Uses FastAPI TestClient (synchronous ASGI test runner).
"""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from master.main import app, app_state
from common.enums import WorkerStatus, TaskStatus
from common.models import WorkerRecord
import time


@pytest.fixture(autouse=True)
def setup_app_state():
    """Inject mock app_state so routes work without running lifespan."""
    from master.registry import WorkerRegistry
    from master.task_queue import TaskQueue

    registry = WorkerRegistry()
    task_queue = TaskQueue(max_size=100, task_timeout=30)

    mock_scheduler = MagicMock()
    mock_scheduler.strategy_name = "load_aware"
    mock_scheduler.set_strategy = MagicMock()

    app_state["registry"] = registry
    app_state["task_queue"] = task_queue
    app_state["scheduler"] = mock_scheduler
    app_state["strategy"] = "load_aware"
    app_state["task_timeout"] = 30
    yield
    app_state.clear()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_workers_empty(client):
    resp = client.get("/workers")
    assert resp.status_code == 200
    assert resp.json()["workers"] == []


def test_list_workers_with_registered_worker(client):
    import asyncio
    from common.models import WorkerRegistration
    reg = WorkerRegistration(
        node_id="w001", hostname="host", ip_address="127.0.0.1", port=50052,
        model_name="llama3.2:1b", max_concurrent=4, cpu_count=4, ram_gb=8.0,
        gpu_available=False, gpu_name="", ollama_healthy=True,
    )
    asyncio.get_event_loop().run_until_complete(app_state["registry"].register(reg))

    resp = client.get("/workers")
    assert resp.status_code == 200
    workers = resp.json()["workers"]
    assert len(workers) == 1
    assert workers[0]["node_id"] == "w001"
    assert workers[0]["status"] == "healthy"


def test_set_strategy_valid(client):
    resp = client.post("/config/strategy", json={"strategy": "round_robin"})
    assert resp.status_code == 200
    assert resp.json()["strategy"] == "round_robin"
    app_state["scheduler"].set_strategy.assert_called_once_with("round_robin")


def test_set_strategy_invalid(client):
    resp = client.post("/config/strategy", json={"strategy": "banana"})
    assert resp.status_code == 400


def test_get_task_not_found(client):
    resp = client.get("/tasks/nonexistent-id")
    assert resp.status_code == 404


def test_metrics_endpoint_returns_prometheus_format(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "master_" in resp.text or "# " in resp.text
