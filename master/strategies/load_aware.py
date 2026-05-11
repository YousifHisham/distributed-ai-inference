from master.strategies.base import BaseStrategy
from master.registry import WorkerNode


class LoadAwareStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "load_aware"

    def select_worker(self, workers: list[WorkerNode]) -> WorkerNode:
        available = [w for w in workers if w.free_slots > 0]
        if not available:
            raise ValueError("No workers with free slots")
        if len(available) == 1:
            return available[0]

        max_active = max(w.active_requests for w in available) or 1
        max_latency = max(w.avg_latency_ms for w in available) or 1

        def score(w: WorkerNode) -> float:
            active_norm = w.active_requests / max_active
            latency_norm = w.avg_latency_ms / max_latency
            return 0.7 * active_norm + 0.3 * latency_norm

        return min(available, key=score)
