from __future__ import annotations
from common.models import WorkerRecord
from master.strategies.base import SchedulingStrategy

_OVERLOAD_THRESHOLD = 0.9


class LoadAwareRoutingStrategy(SchedulingStrategy):
    def select_worker(self, workers: list[WorkerRecord]) -> WorkerRecord | None:
        eligible = [w for w in workers if w.current_load < _OVERLOAD_THRESHOLD]
        if not eligible:
            eligible = workers  # fall back to all if everything is overloaded
        if not eligible:
            return None
        return min(eligible, key=lambda w: w.current_load)
