from __future__ import annotations
from prometheus_client import Counter, Gauge, Histogram

QUEUE_SIZE = Gauge("master_queue_size", "Current task queue depth")
ACTIVE_TASKS = Gauge("master_active_tasks", "Tasks currently assigned or processing")
HEALTHY_WORKERS = Gauge("master_healthy_workers", "Workers with healthy/busy status")
UNHEALTHY_WORKERS = Gauge("master_unhealthy_workers", "Workers with unhealthy/offline status")

REQUESTS_TOTAL = Counter("master_requests_total", "Total inference requests", ["status"])
RETRIES_TOTAL = Counter("master_retries_total", "Total task retries")

REQUEST_DURATION = Histogram(
    "master_request_duration_seconds",
    "End-to-end request latency",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)


def update_cluster_metrics(registry, task_queue, scheduler=None):
    from common.enums import WorkerStatus

    workers = registry.get_all()
    healthy = sum(1 for w in workers if w.status in (WorkerStatus.healthy, WorkerStatus.busy))
    unhealthy = sum(1 for w in workers if w.status in (WorkerStatus.unhealthy, WorkerStatus.offline))

    HEALTHY_WORKERS.set(healthy)
    UNHEALTHY_WORKERS.set(unhealthy)
    QUEUE_SIZE.set(task_queue.size())
    ACTIVE_TASKS.set(task_queue.active_count())


def record_request_completed(latency: float):
    REQUESTS_TOTAL.labels(status="completed").inc()
    REQUEST_DURATION.observe(latency)


def record_request_failed():
    REQUESTS_TOTAL.labels(status="failed").inc()


def record_retry():
    RETRIES_TOTAL.inc()
