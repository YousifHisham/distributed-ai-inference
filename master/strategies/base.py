from __future__ import annotations
from abc import ABC, abstractmethod
from common.models import WorkerRecord


class SchedulingStrategy(ABC):
    @abstractmethod
    def select_worker(self, workers: list[WorkerRecord]) -> WorkerRecord | None:
        """Select the best worker from the list of schedulable workers."""
