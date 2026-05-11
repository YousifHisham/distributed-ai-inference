from enum import Enum


class WorkerStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DRAINING = "DRAINING"
    UNHEALTHY = "UNHEALTHY"


class StrategyType(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_ACTIVE = "least_active"
    LOAD_AWARE = "load_aware"
    LOWEST_LATENCY = "lowest_latency"
    GPU_AWARE = "gpu_aware"
