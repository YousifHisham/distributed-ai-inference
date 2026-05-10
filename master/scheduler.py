from __future__ import annotations
import asyncio
import time
import httpx
from common.enums import TaskStatus
from common.logging_config import setup_logging

logger = setup_logging("master.scheduler")

_STRATEGY_MAP = {
    "round_robin": "master.strategies.round_robin.RoundRobinStrategy",
    "least_active": "master.strategies.least_active.LeastActiveRequestsStrategy",
    "load_aware": "master.strategies.load_aware.LoadAwareRoutingStrategy",
    "lowest_latency": "master.strategies.lowest_latency.LowestAverageLatencyStrategy",
}


def _load_strategy(name: str):
    path = _STRATEGY_MAP.get(name)
    if not path:
        raise ValueError(f"Unknown strategy: {name}")
    module_path, class_name = path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


class Scheduler:
    def __init__(self, registry, task_queue, strategy_name: str, max_retries: int, task_timeout: float):
        self.registry = registry
        self.task_queue = task_queue
        self.strategy_name = strategy_name
        self._strategy = _load_strategy(strategy_name)
        self.max_retries = max_retries
        self.task_timeout = task_timeout
        self._worker_clients: dict[str, httpx.AsyncClient] = {}

    def set_strategy(self, name: str):
        self._strategy = _load_strategy(name)
        self.strategy_name = name
        logger.info(f"Scheduling strategy changed to: {name}")

    def _get_worker_client(self, address: str) -> httpx.AsyncClient:
        if address not in self._worker_clients:
            self._worker_clients[address] = httpx.AsyncClient(base_url=address)
        return self._worker_clients[address]

    async def dispatch_loop(self):
        logger.info("Dispatch loop started")
        while True:
            try:
                task = await self.task_queue.dequeue()
                asyncio.create_task(self._dispatch(task))
            except asyncio.CancelledError:
                logger.info("Dispatch loop stopped")
                break
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}")

    async def _dispatch(self, task):
        if task.status == TaskStatus.failed:
            return

        workers = self.registry.get_schedulable_workers()
        worker = self._strategy.select_worker(workers)

        if not worker:
            logger.warning(
                f"Task {task.request_id} has no available worker"
                f" (retry {task.retry_count}/{self.max_retries})"
            )
            await asyncio.sleep(1)
            if task.retry_count < self.max_retries:
                await self.task_queue.requeue(task.request_id)
            else:
                self.task_queue.fail(task.request_id, "no_workers_available")
            return

        logger.info(
            f"Task {task.request_id} → {worker.node_id}"
            f" strategy={self.strategy_name}"
        )
        task.status = TaskStatus.assigned
        task.assigned_worker_id = worker.node_id
        task.updated_at = time.time()
        if task.queue_wait_time is None:
            task.queue_wait_time = time.time() - task.created_at

        await self.registry.increment_active(worker.node_id)

        try:
            client = self._get_worker_client(worker.address)
            response = await client.post(
                "/infer",
                json={
                    "request_id": task.request_id,
                    "query": task.query,
                    "timeout": self.task_timeout,
                },
                timeout=self.task_timeout + 5,
            )
            latency = time.time() - task.created_at
            await self.registry.decrement_active(worker.node_id)

            if response.status_code != 200:
                error = response.text or "worker_error"
                await self.registry.record_completion(worker.node_id, latency, success=False)
                if task.retry_count < self.max_retries:
                    await self.task_queue.requeue(task.request_id)
                else:
                    self.task_queue.fail(task.request_id, error)
            else:
                payload = response.json()
                if payload.get("error"):
                    await self.registry.record_completion(worker.node_id, latency, success=False)
                    if task.retry_count < self.max_retries:
                        await self.task_queue.requeue(task.request_id)
                    else:
                        self.task_queue.fail(task.request_id, payload.get("error"))
                else:
                    await self.registry.record_completion(worker.node_id, latency, success=True)
                    logger.info(
                        f"Task {task.request_id} completed"
                        f" worker={worker.node_id} latency={latency:.2f}s"
                    )
                    self.task_queue.complete(
                        task.request_id,
                        payload.get("result"),
                        worker.node_id,
                        latency,
                    )

        except asyncio.TimeoutError:
            await self.registry.decrement_active(worker.node_id)
            logger.warning(f"Task {task.request_id} timed out on worker {worker.node_id}")
            if task.retry_count < self.max_retries:
                await self.task_queue.requeue(task.request_id)
            else:
                self.task_queue.fail(task.request_id, "timeout_exceeded")

        except Exception as e:
            await self.registry.decrement_active(worker.node_id)
            logger.error(f"Dispatch error for task {task.request_id}: {e}")
            if task.retry_count < self.max_retries:
                await self.task_queue.requeue(task.request_id)
            else:
                self.task_queue.fail(task.request_id, f"dispatch_error: {e}")
