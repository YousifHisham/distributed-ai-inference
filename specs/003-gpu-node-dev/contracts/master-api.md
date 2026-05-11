# Master Node API Contract

**Service**: Master Node (FastAPI)  
**Runs on**: Developer laptop via Docker Compose  
**Exposed via**: NGINX reverse proxy on port 80; ngrok tunnel for worker access  
**Phase 1 output for**: `003-gpu-node-dev`

---

## Client Endpoints

### POST /infer

Submit an inference request. The master routes it to a healthy worker using the active strategy, enriches the query with context, runs inference, and returns the result.

**Request**:
```json
{
  "query": "string (1–4096 chars, required)"
}
```

**Response 200**:
```json
{
  "request_id": "uuid",
  "result": "string",
  "worker_id": "uuid",
  "latency_ms": 342.1,
  "rag_sources": ["chunk_id_1", "chunk_id_2"],
  "retry_count": 0,
  "strategy": "round_robin"
}
```

**Error responses**:
| Code | Condition |
|---|---|
| 400 | Query is empty or exceeds 4096 characters |
| 503 | No healthy workers available |
| 503 | Queue full (load shedding active) |
| 504 | All retries exhausted (worker timeouts) |

---

## Worker Management Endpoints

### POST /workers/register

Called by a worker agent on startup. Assigns a UUID to the worker and adds it to the healthy pool.

**Request**:
```json
{
  "worker_url": "https://worker-host:8001",
  "gpu_total_vram_gb": 24.0
}
```

**Response 200**:
```json
{
  "worker_id": "uuid",
  "heartbeat_interval_s": 2
}
```

**Error responses**:
| Code | Condition |
|---|---|
| 400 | `worker_url` is missing or malformed |

---

### POST /workers/heartbeat

Called by a worker every 2 seconds. Updates GPU metrics and active request count in the registry. Triggers draining state if health thresholds are breached.

**Request**:
```json
{
  "worker_id": "uuid",
  "gpu_util_pct": 78.5,
  "vram_used_gb": 18.2,
  "vram_total_gb": 24.0,
  "gpu_temp_c": 72.0,
  "ecc_errors": 0,
  "active_requests": 3,
  "timestamp": "2026-05-11T14:30:00Z"
}
```

**Response 200**:
```json
{
  "status": "ok"
}
```

**Error responses**:
| Code | Condition |
|---|---|
| 404 | `worker_id` not found in registry |

**Side effects**:
- Updates `WorkerNode` fields in registry
- If `gpu_temp_c > 85` or `ecc_errors > 0` → transitions worker to `DRAINING`
- If worker was `DRAINING` and `gpu_temp_c ≤ 80` and `ecc_errors == 0` and `active_requests == 0` → transitions to `HEALTHY`

---

## Configuration Endpoints

### POST /config/strategy

Switches the active scheduling strategy. Takes effect immediately for new requests; in-flight requests are not affected.

**Request**:
```json
{
  "strategy": "gpu_aware"
}
```

Valid values: `round_robin`, `least_active`, `load_aware`, `lowest_latency`, `gpu_aware`

**Response 200**:
```json
{
  "strategy": "gpu_aware",
  "applied_at": "2026-05-11T14:31:00Z"
}
```

**Error responses**:
| Code | Condition |
|---|---|
| 400 | Unknown strategy name |

---

## Monitoring Endpoints

### GET /workers

Returns current state of all registered workers.

**Response 200**:
```json
{
  "workers": [
    {
      "worker_id": "uuid",
      "url": "https://...",
      "status": "HEALTHY",
      "gpu_util_pct": 55.0,
      "vram_used_gb": 12.0,
      "vram_total_gb": 24.0,
      "gpu_temp_c": 68.0,
      "ecc_errors": 0,
      "active_requests": 2,
      "avg_latency_ms": 420.0,
      "last_heartbeat": "2026-05-11T14:30:59Z"
    }
  ],
  "active_strategy": "round_robin",
  "healthy_count": 3,
  "draining_count": 0,
  "unhealthy_count": 0
}
```

---

### GET /health

Liveness probe for Docker / NGINX health checks.

**Response 200**:
```json
{
  "status": "ok",
  "healthy_workers": 3
}
```

---

### GET /metrics

Prometheus text-format metrics endpoint. Scraped by Prometheus every 5 seconds.

**Response 200** (Content-Type: `text/plain; version=0.0.4`):
```
# HELP inference_requests_total Total inference requests
# TYPE inference_requests_total counter
inference_requests_total{strategy="round_robin",worker_id="...",status="success"} 142

# HELP inference_latency_seconds End-to-end latency
# TYPE inference_latency_seconds histogram
inference_latency_seconds_bucket{strategy="round_robin",worker_id="...",le="0.5"} 38
...

# HELP worker_gpu_util_pct GPU utilization %
# TYPE worker_gpu_util_pct gauge
worker_gpu_util_pct{worker_id="..."} 55.0

# HELP worker_vram_used_gb VRAM used GB
# TYPE worker_vram_used_gb gauge
worker_vram_used_gb{worker_id="..."} 12.0

# HELP worker_gpu_temp_c GPU temperature Celsius
# TYPE worker_gpu_temp_c gauge
worker_gpu_temp_c{worker_id="..."} 68.0

# HELP worker_active_requests Active in-flight requests
# TYPE worker_active_requests gauge
worker_active_requests{worker_id="..."} 2

# HELP worker_status Worker health (1=HEALTHY 0.5=DRAINING 0=UNHEALTHY)
# TYPE worker_status gauge
worker_status{worker_id="..."} 1
```
