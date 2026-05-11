import pytest
from datetime import datetime, timezone

from master.registry import WorkerRegistry
from common.enums import WorkerStatus
from common.models import HeartbeatPayload


def make_heartbeat(worker_id: str, **kwargs) -> HeartbeatPayload:
    defaults = dict(
        worker_id=worker_id,
        gpu_util_pct=50.0,
        vram_used_gb=8.0,
        vram_total_gb=24.0,
        gpu_temp_c=65.0,
        ecc_errors=0,
        active_requests=2,
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return HeartbeatPayload(**defaults)


def test_register_creates_healthy_worker():
    reg = WorkerRegistry()
    node = reg.register("http://worker1:8001", 24.0)
    assert node.status == WorkerStatus.HEALTHY
    assert node.url == "http://worker1:8001"
    assert node.vram_total_gb == 24.0


def test_update_heartbeat_updates_fields():
    reg = WorkerRegistry()
    node = reg.register("http://worker1:8001", 24.0)
    hb = make_heartbeat(node.worker_id, gpu_util_pct=80.0, active_requests=5)
    reg.update_heartbeat(node.worker_id, hb)
    updated = reg.get(node.worker_id)
    assert updated.gpu_util_pct == 80.0
    assert updated.active_requests == 5


def test_get_healthy_workers_filters_by_status():
    reg = WorkerRegistry()
    n1 = reg.register("http://w1:8001", 24.0)
    n2 = reg.register("http://w2:8001", 24.0)
    reg.mark_unhealthy(n1.worker_id)
    healthy = reg.get_healthy_workers()
    assert len(healthy) == 1
    assert healthy[0].worker_id == n2.worker_id


def test_mark_unhealthy_changes_status():
    reg = WorkerRegistry()
    node = reg.register("http://w1:8001", 24.0)
    reg.mark_unhealthy(node.worker_id)
    assert reg.get(node.worker_id).status == WorkerStatus.UNHEALTHY


def test_ema_latency_update():
    reg = WorkerRegistry()
    node = reg.register("http://w1:8001", 24.0)
    reg.update_avg_latency(node.worker_id, 100.0)
    assert reg.get(node.worker_id).avg_latency_ms == 100.0
    reg.update_avg_latency(node.worker_id, 200.0)
    expected = 0.2 * 200.0 + 0.8 * 100.0
    assert abs(reg.get(node.worker_id).avg_latency_ms - expected) < 0.001


def test_set_draining_only_from_healthy():
    reg = WorkerRegistry()
    node = reg.register("http://w1:8001", 24.0)
    reg.set_draining(node.worker_id)
    assert reg.get(node.worker_id).status == WorkerStatus.DRAINING


def test_set_healthy_recovers_worker():
    reg = WorkerRegistry()
    node = reg.register("http://w1:8001", 24.0)
    reg.set_draining(node.worker_id)
    reg.set_healthy(node.worker_id)
    assert reg.get(node.worker_id).status == WorkerStatus.HEALTHY


def test_get_schedulable_workers_excludes_draining_and_unhealthy():
    reg = WorkerRegistry()
    n1 = reg.register("http://w1:8001", 24.0)
    n2 = reg.register("http://w2:8001", 24.0)
    n3 = reg.register("http://w3:8001", 24.0)
    reg.set_draining(n2.worker_id)
    reg.mark_unhealthy(n3.worker_id)
    schedulable = reg.get_schedulable_workers()
    assert len(schedulable) == 1
    assert schedulable[0].worker_id == n1.worker_id
