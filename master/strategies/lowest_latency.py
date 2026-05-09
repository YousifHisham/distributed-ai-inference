from common.models import WorkerRecord
from master.strategies.base import SchedulingStrategy


class LowestAverageLatencyStrategy(SchedulingStrategy):
    def select_worker(self, workers: list[WorkerRecord]) -> WorkerRecord | None:
        if not workers:
            return None
        # Workers with no latency data yet get priority (0.0 sorts first)
        return min(workers, key=lambda w: w.average_latency)
