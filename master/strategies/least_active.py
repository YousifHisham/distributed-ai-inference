from master.strategies.base import BaseStrategy
from master.registry import WorkerNode


class LeastActiveStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "least_active"

    def select_worker(self, workers: list[WorkerNode]) -> WorkerNode:
        if not workers:
            raise ValueError("No workers available")
        return min(workers, key=lambda w: w.active_requests)
