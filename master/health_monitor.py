import asyncio
import time
from common.logging_config import setup_logging

logger = setup_logging("master.health_monitor")


async def run_health_monitor(registry, task_queue, heartbeat_timeout: float):
    logger.info(f"Health monitor started (timeout={heartbeat_timeout}s)")
    while True:
        try:
            await asyncio.sleep(5)
            now = time.time()
            for worker in registry.get_all():
                if worker.status in ("draining", "offline"):
                    continue
                elapsed = now - worker.last_heartbeat
                if elapsed > heartbeat_timeout:
                    logger.warning(
                        f"Heartbeat timeout for {worker.node_id} "
                        f"(last seen {elapsed:.1f}s ago)"
                    )
                    await registry.mark_unhealthy(worker.node_id)
                    await _recover_inflight_tasks(worker.node_id, task_queue)
        except asyncio.CancelledError:
            logger.info("Health monitor stopped")
            break
        except Exception as e:
            logger.error(f"Health monitor error: {e}")


async def _recover_inflight_tasks(worker_id: str, task_queue):
    from common.enums import TaskStatus
    recovered = 0
    for task in list(task_queue.task_registry.values()):
        if (
            task.assigned_worker_id == worker_id
            and task.status in (TaskStatus.assigned, TaskStatus.processing)
        ):
            await task_queue.requeue(task.request_id)
            recovered += 1
    if recovered:
        logger.info(f"Recovered {recovered} in-flight tasks from failed worker {worker_id}")
