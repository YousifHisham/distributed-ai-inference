"""Unit tests for TaskQueue."""
from __future__ import annotations
import asyncio
import pytest
from common.enums import TaskStatus
from master.task_queue import TaskQueue


async def test_enqueue_adds_to_registry():
    q = TaskQueue(max_size=10, task_timeout=30)
    task = await q.enqueue("hello world")
    assert task.request_id in q.task_registry
    assert task.status == TaskStatus.queued
    assert q.size() == 1


async def test_dequeue_returns_task():
    q = TaskQueue(max_size=10, task_timeout=30)
    t = await q.enqueue("test")
    dequeued = await q.dequeue()
    assert dequeued.request_id == t.request_id


async def test_complete_sets_result():
    q = TaskQueue(max_size=10, task_timeout=30)
    t = await q.enqueue("test")
    await q.dequeue()
    q.complete(t.request_id, "the answer", "worker-001", 1.5)
    assert q.get(t.request_id).status == TaskStatus.completed
    assert q.get(t.request_id).result == "the answer"


async def test_fail_sets_error():
    q = TaskQueue(max_size=10, task_timeout=30)
    t = await q.enqueue("test")
    await q.dequeue()
    q.fail(t.request_id, "max_retries_exceeded")
    assert q.get(t.request_id).status == TaskStatus.failed
    assert q.get(t.request_id).error == "max_retries_exceeded"


async def test_requeue_increments_retry_count():
    q = TaskQueue(max_size=10, task_timeout=30)
    t = await q.enqueue("test")
    await q.dequeue()
    await q.requeue(t.request_id)
    assert q.get(t.request_id).status == TaskStatus.retrying
    assert q.get(t.request_id).retry_count == 1
    await q.requeue(t.request_id)
    assert q.get(t.request_id).retry_count == 2


async def test_queue_full_raises():
    q = TaskQueue(max_size=2, task_timeout=30)
    await q.enqueue("first")
    await q.enqueue("second")
    with pytest.raises(RuntimeError, match="Queue is full"):
        await q.enqueue("third")


async def test_waiter_notified_on_complete():
    q = TaskQueue(max_size=10, task_timeout=30)
    t = await q.enqueue("test")
    event = asyncio.Event()
    q.register_waiter(t.request_id, event)
    assert not event.is_set()
    q.complete(t.request_id, "done", "w001", 1.0)
    assert event.is_set()


async def test_waiter_notified_on_fail():
    q = TaskQueue(max_size=10, task_timeout=30)
    t = await q.enqueue("test")
    event = asyncio.Event()
    q.register_waiter(t.request_id, event)
    q.fail(t.request_id, "error")
    assert event.is_set()


async def test_active_count():
    q = TaskQueue(max_size=10, task_timeout=30)
    t1 = await q.enqueue("a")
    t2 = await q.enqueue("b")
    await q.dequeue()
    await q.dequeue()
    t1_task = q.get(t1.request_id)
    t1_task.status = TaskStatus.assigned
    assert q.active_count() == 1
