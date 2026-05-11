# Data Model: GPU Cluster Distributed AI Inference System

**Phase 1 output for**: `003-gpu-node-dev`  
**Date**: 2026-05-11

---

## Entities

### WorkerNode

Represents a registered GPU compute instance in the cluster. Lives in the master's in-memory registry.

| Field | Type | Description |
|---|---|---|
| `worker_id` | `str` (UUID) | Unique identifier assigned by master on registration |
| `url` | `str` | Base URL of the worker agent (e.g., `https://thunder-1.internal:8001`) |
| `status` | `WorkerStatus` | Current health state (see state machine below) |
| `gpu_util_pct` | `float` | GPU compute utilization % (0–100), from last heartbeat |
| `vram_used_gb` | `float` | VRAM consumed in GB, from last heartbeat |
| `vram_total_gb` | `float` | Total VRAM available in GB, from last heartbeat |
| `gpu_temp_c` | `float` | GPU temperature in Celsius, from last heartbeat |
| `ecc_errors` | `int` | Cumulative uncorrected ECC memory errors, from last heartbeat |
| `active_requests` | `int` | Number of in-flight inference requests on this worker |
| `avg_latency_ms` | `float` | Exponential moving average of response latency (α=0.2) |
| `last_heartbeat` | `datetime` | UTC timestamp of last received heartbeat |
| `registered_at` | `datetime` | UTC timestamp of initial registration |

**Validation rules**:
- `gpu_util_pct` must be in [0, 100]
- `vram_used_gb` must be ≥ 0 and ≤ `vram_total_gb`
- `gpu_temp_c` must be > 0 (negative is invalid; 0 treated as unavailable)
- `active_requests` must be ≥ 0

**State machine** (`WorkerStatus`):

```
         register / recover
              │
              ▼
           HEALTHY  ──── temp > 85°C or ecc_errors > 0 ────► DRAINING
              ▲                                                    │
              │                                                    │ active_requests == 0
              │                                                    │ AND temp ≤ 80°C
              │                                                    │ AND ecc_errors == 0
              └──────────────────────────────────────────────────◄─┘
              │
              │  3 missed heartbeats (> 6s since last heartbeat)
              ▼
          UNHEALTHY ──── re-register ────► HEALTHY
```

- `HEALTHY`: eligible for new request assignment
- `DRAINING`: excluded from scheduling; completes active requests only
- `UNHEALTHY`: excluded from scheduling; in-flight retried on other workers

---

### InferenceRequest (in-flight tracking on master)

Tracks an active request from receipt to response.

| Field | Type | Description |
|---|---|---|
| `request_id` | `str` (UUID) | Unique request identifier |
| `query` | `str` | Raw user query |
| `strategy` | `StrategyType` | Strategy active at dispatch time |
| `worker_id` | `str` \| `None` | Assigned worker (None until dispatched) |
| `retry_count` | `int` | Number of retries attempted so far |
| `created_at` | `datetime` | UTC timestamp when request was received |
| `dispatched_at` | `datetime` \| `None` | UTC timestamp when sent to worker |

**Validation rules**:
- `query` must be non-empty and ≤ 4096 characters
- `retry_count` must be in [0, 3]

---

### HeartbeatPayload (worker → master)

Sent by each worker every 2 seconds.

| Field | Type | Description |
|---|---|---|
| `worker_id` | `str` | Worker's UUID (assigned at registration) |
| `gpu_util_pct` | `float` | Current GPU compute utilization % |
| `vram_used_gb` | `float` | Current VRAM consumed in GB |
| `vram_total_gb` | `float` | Total VRAM in GB |
| `gpu_temp_c` | `float` | Current GPU temperature in Celsius |
| `ecc_errors` | `int` | Cumulative uncorrected ECC errors |
| `active_requests` | `int` | Current in-flight requests on this worker |
| `timestamp` | `datetime` | UTC timestamp of measurement |

---

### RegisterRequest (worker → master on startup)

| Field | Type | Description |
|---|---|---|
| `worker_url` | `str` | Full URL where the worker's `/infer` endpoint is reachable |
| `gpu_total_vram_gb` | `float` | Total VRAM available on this worker's GPU |

**Response** from master:

| Field | Type | Description |
|---|---|---|
| `worker_id` | `str` | UUID assigned by master |
| `heartbeat_interval_s` | `int` | Requested heartbeat interval (always 2) |

---

### InferenceResponse (master → client)

| Field | Type | Description |
|---|---|---|
| `request_id` | `str` | Echo of request ID |
| `result` | `str` | Generated text response |
| `worker_id` | `str` | Worker that handled the request |
| `latency_ms` | `float` | End-to-end latency in milliseconds |
| `rag_sources` | `list[str]` | Knowledge base chunk identifiers used for context |
| `retry_count` | `int` | Number of retries before success |
| `strategy` | `str` | Strategy used for routing |

---

### WorkerInferResponse (worker → master)

| Field | Type | Description |
|---|---|---|
| `result` | `str` | Generated text from vLLM |
| `latency_ms` | `float` | Time from worker receipt to response in milliseconds |
| `rag_sources` | `list[str]` | IDs of knowledge chunks used |
| `gpu_util_pct` | `float` | GPU utilization at time of inference |
| `worker_id` | `str` | Worker's own ID |

---

### GPUMetrics (embedded, used in heartbeat and worker response)

| Field | Type | Description |
|---|---|---|
| `gpu_util_pct` | `float` | GPU compute utilization % |
| `vram_used_gb` | `float` | VRAM consumed in GB |
| `vram_total_gb` | `float` | Total VRAM in GB |
| `gpu_temp_c` | `float` | GPU temperature in Celsius |
| `ecc_errors` | `int` | Cumulative uncorrected ECC errors |

---

## Enumerations

### WorkerStatus

```python
class WorkerStatus(str, Enum):
    HEALTHY   = "HEALTHY"
    DRAINING  = "DRAINING"
    UNHEALTHY = "UNHEALTHY"
```

### StrategyType

```python
class StrategyType(str, Enum):
    ROUND_ROBIN    = "round_robin"
    LEAST_ACTIVE   = "least_active"
    LOAD_AWARE     = "load_aware"
    LOWEST_LATENCY = "lowest_latency"
    GPU_AWARE      = "gpu_aware"
```

---

## Relationships

```
WorkerNode (1) ──── receives ────► (many) InferenceRequest
WorkerNode (1) ──── sends ──────► (many) HeartbeatPayload
InferenceRequest (1) ──── routed by ────► (1) StrategyType
InferenceRequest (1) ──── produces ────► (1) InferenceResponse
```

---

## Notes

- All entities are in-memory on the master; no database persistence is needed for the demo.
- `avg_latency_ms` on `WorkerNode` is updated on each successful inference response using exponential moving average: `new = α * sample + (1-α) * old` where α = 0.2.
- `common/models.py` contains the Pydantic v2 definitions for all request/response bodies shared between master and worker.
- `common/enums.py` contains `WorkerStatus` and `StrategyType`.
