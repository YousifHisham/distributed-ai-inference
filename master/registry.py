import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from common.enums import WorkerStatus
from common.models import HeartbeatPayload

logger = logging.getLogger(__name__)

_EMA_ALPHA = 0.2


@dataclass
class WorkerNode:
    worker_id: str
    url: str
    status: WorkerStatus = WorkerStatus.HEALTHY
    gpu_util_pct: float = 0.0
    vram_used_gb: float = 0.0
    vram_total_gb: float = 0.0
    gpu_temp_c: float = 0.0
    ecc_errors: int = 0
    active_requests: int = 0
    max_slots: int = 1
    avg_latency_ms: float = 0.0
    last_heartbeat: Optional[datetime] = field(default=None)
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def free_slots(self) -> int:
        return max(0, self.max_slots - self.active_requests)


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[str, WorkerNode] = {}

    def register(self, url: str, vram_total_gb: float, max_slots: int = 1) -> WorkerNode:
        worker_id = str(uuid.uuid4())
        node = WorkerNode(
            worker_id=worker_id,
            url=url,
            vram_total_gb=vram_total_gb,
            max_slots=max_slots,
            last_heartbeat=datetime.now(timezone.utc),
        )
        self._workers[worker_id] = node
        logger.info("Registered worker %s at %s (max_slots=%d)", worker_id, url, max_slots)
        return node

    def update_heartbeat(self, worker_id: str, payload: HeartbeatPayload) -> WorkerNode:
        node = self._workers[worker_id]
        node.gpu_util_pct = payload.gpu_util_pct
        node.vram_used_gb = payload.vram_used_gb
        node.vram_total_gb = payload.vram_total_gb
        node.gpu_temp_c = payload.gpu_temp_c
        node.ecc_errors = payload.ecc_errors
        node.active_requests = payload.active_requests
        node.last_heartbeat = datetime.now(timezone.utc)
        return node

    def get_healthy_workers(self) -> list[WorkerNode]:
        return [w for w in self._workers.values() if w.status == WorkerStatus.HEALTHY]

    def get_schedulable_workers(self) -> list[WorkerNode]:
        return [w for w in self._workers.values() if w.status == WorkerStatus.HEALTHY]

    def mark_unhealthy(self, worker_id: str) -> None:
        if worker_id in self._workers:
            self._workers[worker_id].status = WorkerStatus.UNHEALTHY
            logger.warning("Marked worker %s UNHEALTHY", worker_id)

    def set_draining(self, worker_id: str) -> None:
        if worker_id in self._workers:
            w = self._workers[worker_id]
            if w.status == WorkerStatus.HEALTHY:
                w.status = WorkerStatus.DRAINING
                logger.warning("Worker %s → DRAINING (gpu_temp=%.1f, ecc=%d)", worker_id, w.gpu_temp_c, w.ecc_errors)

    def set_healthy(self, worker_id: str) -> None:
        if worker_id in self._workers:
            self._workers[worker_id].status = WorkerStatus.HEALTHY
            logger.info("Worker %s → HEALTHY (recovered)", worker_id)

    def update_avg_latency(self, worker_id: str, sample_ms: float) -> None:
        if worker_id in self._workers:
            node = self._workers[worker_id]
            if node.avg_latency_ms == 0.0:
                node.avg_latency_ms = sample_ms
            else:
                node.avg_latency_ms = _EMA_ALPHA * sample_ms + (1 - _EMA_ALPHA) * node.avg_latency_ms

    def get(self, worker_id: str) -> Optional[WorkerNode]:
        return self._workers.get(worker_id)

    def all_workers(self) -> list[WorkerNode]:
        return list(self._workers.values())
