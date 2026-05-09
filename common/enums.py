from enum import Enum


class TaskStatus(str, Enum):
    queued = "queued"
    assigned = "assigned"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"


class WorkerStatus(str, Enum):
    healthy = "healthy"
    busy = "busy"
    draining = "draining"
    unhealthy = "unhealthy"
    offline = "offline"
