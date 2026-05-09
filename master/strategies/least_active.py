from __future__ import annotations
from common.models import WorkerRecord
from master.strategies.base import SchedulingStrategy


class LeastActiveRequestsStrategy(SchedulingStrategy):
    def select_worker(self, workers: list[WorkerRecord]) -> WorkerRecord | None:
        if not workers:
            return None
        return min(workers, key=lambda w: w.active_requests)
