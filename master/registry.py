from __future__ import annotations
import asyncio
import json
import os
import time
from typing import Optional
from common.models import WorkerRecord, WorkerRegistration, Heartbeat
from common.enums import WorkerStatus
from common.logging_config import setup_logging

logger = setup_logging("master.registry")

_TARGETS_FILE = os.getenv("PROMETHEUS_TARGETS_FILE", "/monitoring/targets.json")


def _write_prometheus_targets(workers: dict[str, WorkerRecord]):
    targets = []
    for w in workers.values():
        if w.status not in (WorkerStatus.offline,):
            ip = w.address.replace("http://", "").split(":")[0]
            worker_http_port = os.getenv("WORKER_HTTP_PORT", "8001")
            targets.append({
                "targets": [f"{ip}:{worker_http_port}"],
                "labels": {"worker_id": w.node_id, "hostname": w.hostname},
            })
    try:
        os.makedirs(os.path.dirname(_TARGETS_FILE), exist_ok=True)
        with open(_TARGETS_FILE, "w") as f:
            json.dump(targets, f)
    except Exception as e:
        logger.warning(f"Could not write Prometheus targets: {e}")


class WorkerRegistry:
    def __init__(self):
        self._workers: dict[str, WorkerRecord] = {}
        self._lock = asyncio.Lock()

    async def register(self, reg: WorkerRegistration) -> WorkerRecord:
        async with self._lock:
            address = f"http://{reg.ip_address}:{reg.port}"
            existing = self._workers.get(reg.node_id)
            if existing:
                existing.hostname = reg.hostname
                existing.address = address
                existing.model_name = reg.model_name
                existing.ollama_healthy = reg.ollama_healthy
                existing.last_heartbeat = time.time()
                existing.status = WorkerStatus.healthy if reg.ollama_healthy else WorkerStatus.unhealthy
                logger.info(f"Worker re-registered: {reg.node_id}")
                return existing

            record = WorkerRecord(
                node_id=reg.node_id,
                hostname=reg.hostname,
                address=address,
                status=WorkerStatus.healthy if reg.ollama_healthy else WorkerStatus.unhealthy,
                last_heartbeat=time.time(),
                model_name=reg.model_name,
                ollama_healthy=reg.ollama_healthy,
                gpu_available=reg.gpu_available,
                gpu_name=reg.gpu_name if reg.gpu_name else None,
                registered_at=time.time(),
            )
            self._workers[reg.node_id] = record
            logger.info(f"Worker registered: {reg.node_id} at {address}")
            _write_prometheus_targets(self._workers)
            return record

    async def update_heartbeat(self, hb: Heartbeat) -> Optional[WorkerRecord]:
        async with self._lock:
            worker = self._workers.get(hb.node_id)
            if not worker:
                return None
            worker.last_heartbeat = time.time()
            worker.active_requests = hb.active_requests
            worker.cpu_pct = hb.cpu_pct
            worker.ram_pct = hb.ram_pct
            worker.gpu_pct = hb.gpu_pct
            worker.ollama_healthy = hb.ollama_healthy
            if hb.avg_latency > 0:
                worker.average_latency = hb.avg_latency

            # Update load score for load-aware routing
            gpu_load = 0.0 if hb.gpu_pct < 0 else hb.gpu_pct / 100.0
            worker.current_load = (
                min(hb.active_requests / 10.0, 1.0) * 0.35
                + (hb.cpu_pct / 100.0) * 0.2
                + (hb.ram_pct / 100.0) * 0.2
                + gpu_load * 0.15
                + min(hb.avg_latency / 30.0, 1.0) * 0.1
            )

            # Status transitions based on load and Ollama health
            if not hb.ollama_healthy:
                worker.status = WorkerStatus.unhealthy
            elif worker.status not in (WorkerStatus.draining, WorkerStatus.unhealthy, WorkerStatus.offline):
                worker.status = WorkerStatus.busy if worker.current_load >= 0.9 else WorkerStatus.healthy
            return worker

    async def deregister(self, node_id: str) -> Optional[WorkerRecord]:
        async with self._lock:
            worker = self._workers.get(node_id)
            if worker:
                worker.status = WorkerStatus.draining
                logger.info(f"Worker draining: {node_id}")
                _write_prometheus_targets(self._workers)
            return worker

    async def mark_unhealthy(self, node_id: str) -> Optional[WorkerRecord]:
        async with self._lock:
            worker = self._workers.get(node_id)
            if worker and worker.status not in (WorkerStatus.offline, WorkerStatus.draining):
                worker.status = WorkerStatus.unhealthy
                logger.warning(f"Worker marked unhealthy: {node_id}")
                _write_prometheus_targets(self._workers)
            return worker

    async def mark_offline(self, node_id: str):
        async with self._lock:
            worker = self._workers.get(node_id)
            if worker:
                worker.status = WorkerStatus.offline
                logger.warning(f"Worker marked offline: {node_id}")

    def get_schedulable_workers(self) -> list[WorkerRecord]:
        return [
            w for w in self._workers.values()
            if w.is_schedulable()
        ]

    def get_all(self) -> list[WorkerRecord]:
        return list(self._workers.values())

    def get(self, node_id: str) -> Optional[WorkerRecord]:
        return self._workers.get(node_id)

    async def increment_active(self, node_id: str):
        async with self._lock:
            w = self._workers.get(node_id)
            if w:
                w.active_requests += 1

    async def decrement_active(self, node_id: str):
        async with self._lock:
            w = self._workers.get(node_id)
            if w and w.active_requests > 0:
                w.active_requests -= 1

    async def record_completion(self, node_id: str, latency: float, success: bool):
        async with self._lock:
            w = self._workers.get(node_id)
            if not w:
                return
            if success:
                w.total_completed += 1
                # Rolling average latency (exponential moving average)
                alpha = 0.1
                w.average_latency = alpha * latency + (1 - alpha) * w.average_latency
            else:
                w.total_failed += 1
