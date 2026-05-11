import asyncio
from master.strategies.base import BaseStrategy
from master.registry import WorkerNode


class RoundRobinStrategy(BaseStrategy):
    def __init__(self) -> None:
        self._index = 0
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "round_robin"

    def select_worker(self, workers: list[WorkerNode]) -> WorkerNode:
        if not workers:
            raise ValueError("No workers available")
        worker = workers[self._index % len(workers)]
        self._index += 1
        return worker
