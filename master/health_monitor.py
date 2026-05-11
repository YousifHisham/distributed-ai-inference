import asyncio
import logging
import os
from datetime import datetime, timezone

from master.registry import WorkerRegistry
from common.enums import WorkerStatus

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        logger.info("HealthMonitor started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("HealthMonitor stopped")

    async def _run(self) -> None:
        interval = float(os.getenv("HEALTH_CHECK_INTERVAL", "2"))
        timeout = float(os.getenv("HEARTBEAT_TIMEOUT", "6"))

        while True:
            await asyncio.sleep(interval)
            now = datetime.now(timezone.utc)
            for worker in self._registry.all_workers():
                if worker.status == WorkerStatus.UNHEALTHY:
                    continue
                if worker.last_heartbeat is None:
                    continue
                elapsed = (now - worker.last_heartbeat).total_seconds()
                if elapsed > timeout:
                    logger.warning(
                        "Worker %s missed heartbeat for %.1fs — marking UNHEALTHY",
                        worker.worker_id,
                        elapsed,
                    )
                    self._registry.mark_unhealthy(worker.worker_id)
