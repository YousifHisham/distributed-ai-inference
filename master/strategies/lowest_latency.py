from master.strategies.base import BaseStrategy
from master.registry import WorkerNode


class LowestLatencyStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "lowest_latency"

    def select_worker(self, workers: list[WorkerNode]) -> WorkerNode:
        available = [w for w in workers if w.free_slots > 0]
        if not available:
            raise ValueError("No workers with free slots")
        return min(available, key=lambda w: w.avg_latency_ms if w.avg_latency_ms > 0 else float("inf"))
