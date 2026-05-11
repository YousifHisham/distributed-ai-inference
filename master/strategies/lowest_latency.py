from master.strategies.base import BaseStrategy
from master.registry import WorkerNode


class LowestLatencyStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "lowest_latency"

    def select_worker(self, workers: list[WorkerNode]) -> WorkerNode:
        if not workers:
            raise ValueError("No healthy workers")
        return min(workers, key=lambda w: w.avg_latency_ms if w.avg_latency_ms > 0 else float("inf"))
