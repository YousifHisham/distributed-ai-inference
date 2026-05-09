from __future__ import annotations
import threading
from common.models import WorkerRecord
from master.strategies.base import SchedulingStrategy


class RoundRobinStrategy(SchedulingStrategy):
    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()

    def select_worker(self, workers: list[WorkerRecord]) -> WorkerRecord | None:
        if not workers:
            return None
        with self._lock:
            worker = workers[self._index % len(workers)]
            self._index = (self._index + 1) % len(workers)
        return worker
