from __future__ import annotations
import asyncio
import time
from common.models import InferenceRequest
from common.enums import TaskStatus
from common.logging_config import setup_logging

logger = setup_logging("master.queue")


class TaskQueue:
    def __init__(self, max_size: int = 5000, task_timeout: float = 120):
        self._queue: asyncio.Queue[InferenceRequest] = asyncio.Queue(maxsize=max_size)
        self.task_registry: dict[str, InferenceRequest] = {}
        self._waiters: dict[str, asyncio.Event] = {}
        self.task_timeout = task_timeout
        self._completed_count = 0
        self._failed_count = 0

    def register_waiter(self, request_id: str, event: asyncio.Event):
        self._waiters[request_id] = event

    async def enqueue(self, query: str) -> InferenceRequest:
        if self._queue.full():
            raise RuntimeError("Queue is full — service at capacity")
        task = InferenceRequest(
            query=query,
            status=TaskStatus.queued,
            timeout_at=time.time() + self.task_timeout,
        )
        self.task_registry[task.request_id] = task
        await self._queue.put(task)
        logger.info(f"Task enqueued: {task.request_id} (queue_size={self._queue.qsize()})")
        return task

    async def dequeue(self) -> InferenceRequest:
        return await self._queue.get()

    def get(self, request_id: str) -> InferenceRequest | None:
        return self.task_registry.get(request_id)

    def complete(self, request_id: str, result: str, worker_id: str, latency: float):
        task = self.task_registry.get(request_id)
        if not task:
            return
        task.status = TaskStatus.completed
        task.result = result
        task.assigned_worker_id = worker_id
        task.updated_at = time.time()
        self._completed_count += 1
        self._notify(request_id)

    def fail(self, request_id: str, error: str):
        task = self.task_registry.get(request_id)
        if not task:
            return
        task.status = TaskStatus.failed
        task.error = error
        task.updated_at = time.time()
        self._failed_count += 1
        logger.warning(f"Task failed: {request_id} — {error}")
        self._notify(request_id)

    async def requeue(self, request_id: str):
        task = self.task_registry.get(request_id)
        if not task:
            return
        task.retry_count += 1
        task.status = TaskStatus.retrying
        task.assigned_worker_id = None
        task.updated_at = time.time()
        await self._queue.put(task)
        logger.info(f"Task requeued: {request_id} (retry {task.retry_count})")

    def size(self) -> int:
        return self._queue.qsize()

    def active_count(self) -> int:
        return sum(
            1 for t in self.task_registry.values()
            if t.status in (TaskStatus.assigned, TaskStatus.processing)
        )

    def _notify(self, request_id: str):
        event = self._waiters.pop(request_id, None)
        if event:
            event.set()
