from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from common.enums import WorkerStatus, StrategyType


class GPUMetrics(BaseModel):
    gpu_util_pct: float = 0.0
    vram_used_gb: float = 0.0
    vram_total_gb: float = 0.0
    gpu_temp_c: float = 0.0
    ecc_errors: int = 0


class RegisterRequest(BaseModel):
    worker_url: str
    gpu_total_vram_gb: float


class RegisterResponse(BaseModel):
    worker_id: str


class HeartbeatPayload(BaseModel):
    worker_id: str
    gpu_util_pct: float
    vram_used_gb: float
    vram_total_gb: float
    gpu_temp_c: float
    ecc_errors: int
    active_requests: int
    timestamp: datetime


class ClientInferRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)


class WorkerInferRequest(BaseModel):
    query: str
    request_id: str


class WorkerInferResponse(BaseModel):
    result: str
    latency_ms: float
    rag_sources: list[str]
    gpu_util_pct: float
    worker_id: str


class InferenceResponse(BaseModel):
    request_id: str
    result: str
    worker_id: str
    latency_ms: float
    rag_sources: list[str]
    retry_count: int
    strategy: str


class StrategyConfigRequest(BaseModel):
    strategy: StrategyType


class WorkerStatusResponse(BaseModel):
    worker_id: str
    url: str
    status: WorkerStatus
    gpu_util_pct: float
    vram_used_gb: float
    vram_total_gb: float
    gpu_temp_c: float
    ecc_errors: int
    active_requests: int
    avg_latency_ms: float
    last_heartbeat: Optional[datetime]


class ClusterStatusResponse(BaseModel):
    workers: list[WorkerStatusResponse]
    active_strategy: str
    queue_depth: int
    healthy_count: int
    draining_count: int
    unhealthy_count: int
