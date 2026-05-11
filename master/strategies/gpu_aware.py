from master.strategies.base import BaseStrategy
from master.registry import WorkerNode


class GpuAwareStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "gpu_aware"

    def select_worker(self, workers: list[WorkerNode]) -> WorkerNode:
        if not workers:
            raise ValueError("No healthy workers")

        def score(w: WorkerNode) -> float:
            gpu_free = 1.0 - (w.gpu_util_pct / 100.0)
            vram_free = (w.vram_total_gb - w.vram_used_gb) / w.vram_total_gb if w.vram_total_gb > 0 else 0.5
            return 0.5 * gpu_free + 0.5 * vram_free

        return max(workers, key=score)
