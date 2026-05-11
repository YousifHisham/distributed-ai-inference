from master.strategies.base import BaseStrategy
from master.registry import WorkerNode


class LoadAwareStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "load_aware"

    def select_worker(self, workers: list[WorkerNode]) -> WorkerNode:
        if not workers:
            raise ValueError("No workers available")
        if len(workers) == 1:
            return workers[0]

        max_active = max(w.active_requests for w in workers) or 1
        max_latency = max(w.avg_latency_ms for w in workers) or 1

        def score(w: WorkerNode) -> float:
            active_norm = w.active_requests / max_active
            latency_norm = w.avg_latency_ms / max_latency
            return 0.7 * active_norm + 0.3 * latency_norm

        return min(workers, key=score)
