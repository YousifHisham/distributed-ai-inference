import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

import httpx

from common.enums import StrategyType
from common.models import WorkerInferRequest, InferenceResponse
from master.registry import WorkerRegistry, WorkerNode
from master.strategies.base import BaseStrategy
from master.strategies.round_robin import RoundRobinStrategy
from master.strategies.least_active import LeastActiveStrategy
from master.strategies.load_aware import LoadAwareStrategy
from master.strategies.lowest_latency import LowestLatencyStrategy
from master.strategies.gpu_aware import GpuAwareStrategy

logger = logging.getLogger(__name__)

_STRATEGY_MAP: dict[StrategyType, type[BaseStrategy]] = {
    StrategyType.ROUND_ROBIN: RoundRobinStrategy,
    StrategyType.LEAST_ACTIVE: LeastActiveStrategy,
    StrategyType.LOAD_AWARE: LoadAwareStrategy,
    StrategyType.LOWEST_LATENCY: LowestLatencyStrategy,
    StrategyType.GPU_AWARE: GpuAwareStrategy,
}

_MAX_RETRIES = 3
_DISPATCHER_POLL_INTERVAL = 0.05  # 50ms — how often dispatcher checks for free slots


@dataclass
class _PendingJob:
    query: str
    request_id: str
    future: asyncio.Future
    enqueued_at: float


class Scheduler:
    def __init__(self, registry: WorkerRegistry, http_client: httpx.AsyncClient) -> None:
        self._registry = registry
        self._http = http_client
        self._strategy: BaseStrategy = RoundRobinStrategy()
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[_PendingJob] = asyncio.Queue()
        self._dispatcher_task: asyncio.Task | None = None

        self.requests_total = None
        self.latency_histogram = None

    async def start(self) -> None:
        self._dispatcher_task = asyncio.create_task(self._dispatcher_loop())

    async def stop(self) -> None:
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass

    async def swap_strategy(self, strategy_type: StrategyType) -> None:
        async with self._lock:
            self._strategy = _STRATEGY_MAP[strategy_type]()
        logger.info("Strategy swapped to %s", strategy_type)

    @property
    def current_strategy_name(self) -> str:
        return self._strategy.name

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    async def dispatch(self, query: str, request_id: str) -> InferenceResponse:
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        job = _PendingJob(
            query=query,
            request_id=request_id,
            future=future,
            enqueued_at=time.monotonic(),
        )
        await self._queue.put(job)
        return await future

    async def _dispatcher_loop(self) -> None:
        while True:
            job = await self._queue.get()

            worker = None
            while worker is None:
                async with self._lock:
                    workers = self._registry.get_healthy_workers()
                    if workers:
                        try:
                            worker = self._strategy.select_worker(workers)
                            worker.active_requests += 1
                        except ValueError:
                            worker = None
                if worker is None:
                    await asyncio.sleep(_DISPATCHER_POLL_INTERVAL)

            asyncio.create_task(self._execute_job(job, worker))

    async def _execute_job(self, job: _PendingJob, worker: WorkerNode) -> None:
        start = time.monotonic()
        retry_count = 0
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                # retry: pick a new worker
                async with self._lock:
                    workers = self._registry.get_healthy_workers()
                    if not workers:
                        break
                    try:
                        worker = self._strategy.select_worker(workers)
                        worker.active_requests += 1
                    except ValueError:
                        break

            try:
                result = await self._call_worker(worker, job.query, job.request_id)
                elapsed_ms = (time.monotonic() - start) * 1000
                self._registry.update_avg_latency(worker.worker_id, elapsed_ms)

                if self.requests_total:
                    self.requests_total.labels(
                        strategy=self._strategy.name,
                        worker_id=worker.worker_id,
                        status="success",
                    ).inc()
                if self.latency_histogram:
                    self.latency_histogram.labels(
                        strategy=self._strategy.name,
                        worker_id=worker.worker_id,
                    ).observe(elapsed_ms / 1000)

                response = InferenceResponse(
                    request_id=job.request_id,
                    result=result.result,
                    worker_id=worker.worker_id,
                    latency_ms=elapsed_ms,
                    rag_sources=result.rag_sources,
                    retry_count=retry_count,
                    strategy=self._strategy.name,
                )
                if not job.future.done():
                    job.future.set_result(response)
                return

            except Exception as exc:
                last_exc = exc
                retry_count += 1
                self._registry.mark_unhealthy(worker.worker_id)
                logger.warning(
                    "Worker %s failed on attempt %d: %s — marking UNHEALTHY",
                    worker.worker_id,
                    attempt + 1,
                    exc,
                )
            finally:
                worker.active_requests = max(0, worker.active_requests - 1)

        if self.requests_total:
            self.requests_total.labels(
                strategy=self._strategy.name,
                worker_id="unknown",
                status="error",
            ).inc()

        if not job.future.done():
            job.future.set_exception(
                AllRetriesExhaustedError(f"All {_MAX_RETRIES} retries failed: {last_exc}")
            )

    async def _call_worker(self, worker: WorkerNode, query: str, request_id: str):
        from common.models import WorkerInferResponse
        payload = WorkerInferRequest(query=query, request_id=request_id)
        resp = await self._http.post(
            f"{worker.url}/infer",
            json=payload.model_dump(),
            timeout=35.0,
        )
        resp.raise_for_status()
        return WorkerInferResponse.model_validate(resp.json())


class NoHealthyWorkersError(Exception):
    pass


class AllRetriesExhaustedError(Exception):
    pass
