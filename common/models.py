from __future__ import annotations
import time
import uuid
from typing import Optional
from pydantic import BaseModel, Field
from common.enums import TaskStatus, WorkerStatus


class WorkerRegistration(BaseModel):
    node_id: str
    hostname: str
    ip_address: str
    port: int
    model_name: str
    max_concurrent: int = 4
    cpu_count: int = 1
    ram_gb: float = 8.0
    gpu_available: bool = False
    gpu_name: Optional[str] = None
    ollama_healthy: bool = False


class WorkerRecord(BaseModel):
    node_id: str
    hostname: str
    address: str
    status: WorkerStatus = WorkerStatus.healthy
    last_heartbeat: float = Field(default_factory=time.time)
    active_requests: int = 0
    total_completed: int = 0
    total_failed: int = 0
    average_latency: float = 0.0
    current_load: float = 0.0
    cpu_pct: float = 0.0
    ram_pct: float = 0.0
    gpu_pct: float = -1.0
    gpu_name: Optional[str] = None
    max_concurrent: int = 4
    model_name: str = ""
    ollama_healthy: bool = False
    registered_at: float = Field(default_factory=time.time)

    def is_schedulable(self) -> bool:
        return (
            self.status in (WorkerStatus.healthy, WorkerStatus.busy)
            and self.ollama_healthy
            and self.active_requests < self.max_concurrent
        )


class Heartbeat(BaseModel):
    node_id: str
    timestamp: float
    status: WorkerStatus
    active_requests: int
    queue_size: int
    cpu_pct: float
    ram_pct: float
    gpu_pct: float = -1.0
    ollama_healthy: bool
    avg_latency: float = 0.0


class InferenceRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    status: TaskStatus = TaskStatus.queued
    assigned_worker_id: Optional[str] = None
    retry_count: int = 0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    timeout_at: float = 0.0
    result: Optional[str] = None
    error: Optional[str] = None
    queue_wait_time: Optional[float] = None


class WorkerMetric(BaseModel):
    node_id: str
    status: WorkerStatus
    active_requests: int
    total_completed: int
    avg_latency: float
    cpu_pct: float
    ram_pct: float
    gpu_pct: float
    seconds_since_heartbeat: float


class MetricsSnapshot(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    total_workers: int = 0
    healthy_workers: int = 0
    unhealthy_workers: int = 0
    draining_workers: int = 0
    queue_size: int = 0
    active_tasks: int = 0
    completed_total: int = 0
    failed_total: int = 0
    requests_per_sec: float = 0.0
    avg_latency: float = 0.0
    p95_latency: float = 0.0
    current_strategy: str = "load_aware"
    workers: list[WorkerMetric] = []


class TaskRecord(BaseModel):
    request_id: str
    submitted_at: float
    completed_at: Optional[float] = None
    total_latency: Optional[float] = None
    queue_wait: Optional[float] = None
    inference_time: Optional[float] = None
    assigned_worker: Optional[str] = None
    status: str = "pending"
    retry_count: int = 0
