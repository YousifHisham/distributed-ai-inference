from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from master.registry import WorkerNode


class BaseStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def select_worker(self, workers: list["WorkerNode"]) -> "WorkerNode": ...
