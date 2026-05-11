import asyncio
import logging
import time
import uuid

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


class Scheduler:
    def __init__(self, registry: WorkerRegistry, http_client: httpx.AsyncClient) -> None:
        self._registry = registry
        self._http = http_client
        self._strategy: BaseStrategy = RoundRobinStrategy()
        self._lock = asyncio.Lock()

        # Prometheus metrics (set by main.py after creation)
        self.requests_total = None
        self.latency_histogram = None

    async def swap_strategy(self, strategy_type: StrategyType) -> None:
        async with self._lock:
            self._strategy = _STRATEGY_MAP[strategy_type]()
        logger.info("Strategy swapped to %s", strategy_type)

    @property
    def current_strategy_name(self) -> str:
        return self._strategy.name

    async def dispatch(self, query: str, request_id: str) -> InferenceResponse:
        start = time.monotonic()
        retry_count = 0
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            workers = self._registry.get_schedulable_workers()
            if not workers:
                raise NoHealthyWorkersError("No healthy workers available")

            worker = self._strategy.select_worker(workers)
            worker.active_requests += 1
            try:
                result = await self._call_worker(worker, query, request_id)
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

                return InferenceResponse(
                    request_id=request_id,
                    result=result.result,
                    worker_id=worker.worker_id,
                    latency_ms=elapsed_ms,
                    rag_sources=result.rag_sources,
                    retry_count=retry_count,
                    strategy=self._strategy.name,
                )
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

        raise AllRetriesExhaustedError(f"All {_MAX_RETRIES} retries failed: {last_exc}") from last_exc

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
