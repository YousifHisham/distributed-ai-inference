"""
Integration test for fault tolerance: worker failure detection and task retry.
Uses in-process Master components with mock workers.
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from common.models import WorkerRegistration, WorkerRecord
from common.enums import TaskStatus, WorkerStatus
from master.registry import WorkerRegistry
from master.task_queue import TaskQueue
from master.health_monitor import run_health_monitor, _recover_inflight_tasks


@pytest.fixture
def registry():
    return WorkerRegistry()


@pytest.fixture
def task_queue():
    return TaskQueue(max_size=100, task_timeout=30)


@pytest.fixture
def sample_reg():
    return WorkerRegistration(
        node_id="worker-test-001",
        hostname="test-host",
        ip_address="127.0.0.1",
        port=50052,
        model_name="llama3.2:1b",
        max_concurrent=4,
        cpu_count=4,
        ram_gb=8.0,
        gpu_available=False,
        gpu_name="",
        ollama_healthy=True,
    )


async def test_worker_registers_and_appears_in_registry(registry, sample_reg):
    worker = await registry.register(sample_reg)
    assert worker.node_id == "worker-test-001"
    assert worker.status == WorkerStatus.healthy
    assert len(registry.get_all()) == 1
    assert len(registry.get_schedulable_workers()) == 1


async def test_worker_marked_unhealthy_on_heartbeat_timeout(registry, sample_reg, task_queue):
    await registry.register(sample_reg)

    # Backdate the heartbeat so it appears timed out
    worker = registry.get("worker-test-001")
    worker.last_heartbeat = time.time() - 30  # 30s ago, well past 15s timeout

    await registry.mark_unhealthy("worker-test-001")
    assert registry.get("worker-test-001").status == WorkerStatus.unhealthy
    assert registry.get_schedulable_workers() == []


async def test_inflight_tasks_requeued_on_worker_failure(registry, sample_reg, task_queue):
    await registry.register(sample_reg)

    # Enqueue and mark tasks as assigned to this worker
    task1 = await task_queue.enqueue("query 1")
    task2 = await task_queue.enqueue("query 2")

    # Drain the queue and mark as assigned
    t1 = await task_queue.dequeue()
    t2 = await task_queue.dequeue()
    t1.status = TaskStatus.assigned
    t1.assigned_worker_id = "worker-test-001"
    t2.status = TaskStatus.processing
    t2.assigned_worker_id = "worker-test-001"

    initial_queue_size = task_queue.size()

    # Simulate worker failure recovery
    await _recover_inflight_tasks("worker-test-001", task_queue)

    # Both tasks should be back in queue
    assert task_queue.size() == initial_queue_size + 2
    assert t1.status == TaskStatus.retrying
    assert t2.status == TaskStatus.retrying
    assert t1.retry_count == 1
    assert t2.retry_count == 1


async def test_worker_reregistration_resets_status(registry, sample_reg):
    await registry.register(sample_reg)
    await registry.mark_unhealthy("worker-test-001")
    assert registry.get("worker-test-001").status == WorkerStatus.unhealthy

    # Re-register (simulates worker coming back online)
    await registry.register(sample_reg)
    assert registry.get("worker-test-001").status == WorkerStatus.healthy
    assert len(registry.get_schedulable_workers()) == 1


async def test_draining_worker_excluded_from_scheduling(registry, sample_reg):
    await registry.register(sample_reg)
    assert len(registry.get_schedulable_workers()) == 1

    await registry.deregister("worker-test-001")
    assert registry.get("worker-test-001").status == WorkerStatus.draining
    assert registry.get_schedulable_workers() == []


async def test_task_fail_after_max_retries(task_queue):
    task = await task_queue.enqueue("test query")

    # Simulate exceeding max retries
    t = await task_queue.dequeue()
    t.retry_count = 3  # already at max
    task_queue.fail(t.request_id, "max_retries_exceeded")

    assert task_queue.get(t.request_id).status == TaskStatus.failed
    assert task_queue.get(t.request_id).error == "max_retries_exceeded"


async def test_multiple_workers_load_distributed(registry):
    for i in range(3):
        reg = WorkerRegistration(
            node_id=f"worker-{i:03d}",
            hostname=f"host-{i}",
            ip_address=f"192.168.1.{10+i}",
            port=50052,
            model_name="llama3.2:1b",
            max_concurrent=4,
            cpu_count=4,
            ram_gb=8.0,
            gpu_available=False,
            gpu_name="",
            ollama_healthy=True,
        )
        await registry.register(reg)

    schedulable = registry.get_schedulable_workers()
    assert len(schedulable) == 3

    # Kill one
    await registry.mark_unhealthy("worker-001")
    schedulable = registry.get_schedulable_workers()
    assert len(schedulable) == 2
