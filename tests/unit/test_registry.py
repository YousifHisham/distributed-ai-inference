"""Unit tests for WorkerRegistry status transitions."""
from __future__ import annotations
import time
import pytest
from common.models import WorkerRegistration
from common.enums import WorkerStatus
from master.registry import WorkerRegistry


def make_reg(node_id: str = "w001", ollama_healthy: bool = True) -> WorkerRegistration:
    return WorkerRegistration(
        node_id=node_id, hostname="host", ip_address="127.0.0.1", port=8001,
        model_name="llama3.2:1b", max_concurrent=4, cpu_count=4, ram_gb=8.0,
        gpu_available=False, gpu_name="", ollama_healthy=ollama_healthy,
    )


async def test_register_new_worker():
    r = WorkerRegistry()
    w = await r.register(make_reg())
    assert w.node_id == "w001"
    assert w.status == WorkerStatus.healthy
    assert len(r.get_all()) == 1


async def test_register_unhealthy_ollama():
    r = WorkerRegistry()
    w = await r.register(make_reg(ollama_healthy=False))
    assert w.status == WorkerStatus.unhealthy
    assert r.get_schedulable_workers() == []


async def test_re_register_updates_existing():
    r = WorkerRegistry()
    await r.register(make_reg())
    await r.mark_unhealthy("w001")
    # Re-register heals the worker
    w = await r.register(make_reg())
    assert w.status == WorkerStatus.healthy
    assert len(r.get_all()) == 1


async def test_mark_unhealthy_removes_from_schedulable():
    r = WorkerRegistry()
    await r.register(make_reg())
    assert len(r.get_schedulable_workers()) == 1
    await r.mark_unhealthy("w001")
    assert r.get_schedulable_workers() == []


async def test_deregister_sets_draining():
    r = WorkerRegistry()
    await r.register(make_reg())
    await r.deregister("w001")
    assert r.get("w001").status == WorkerStatus.draining
    assert r.get_schedulable_workers() == []


async def test_get_all_returns_all():
    r = WorkerRegistry()
    for i in range(5):
        await r.register(make_reg(node_id=f"w{i:03d}"))
    assert len(r.get_all()) == 5


async def test_increment_decrement_active():
    r = WorkerRegistry()
    await r.register(make_reg())
    await r.increment_active("w001")
    await r.increment_active("w001")
    assert r.get("w001").active_requests == 2
    await r.decrement_active("w001")
    assert r.get("w001").active_requests == 1


async def test_record_completion_updates_latency():
    r = WorkerRegistry()
    await r.register(make_reg())
    await r.record_completion("w001", 2.0, success=True)
    await r.record_completion("w001", 3.0, success=True)
    assert r.get("w001").total_completed == 2
    assert r.get("w001").average_latency > 0


async def test_multiple_workers_only_healthy_schedulable():
    r = WorkerRegistry()
    for i in range(3):
        await r.register(make_reg(node_id=f"w{i:03d}"))
    await r.mark_unhealthy("w001")
    schedulable = r.get_schedulable_workers()
    assert len(schedulable) == 2
    assert all(w.node_id != "w001" for w in schedulable)
