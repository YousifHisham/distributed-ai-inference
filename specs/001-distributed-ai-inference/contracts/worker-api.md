# Worker Agent Interfaces

The Worker Agent exposes two interfaces:

1. **gRPC server** (port 50052) — called by Master for inference dispatch and health checks. Defined in [`inference.proto`](inference.proto) under `WorkerService`.
2. **HTTP `/metrics`** (port 8001) — Prometheus scrape endpoint, Prometheus text format.

## gRPC: WorkerService

See `inference.proto` for full message definitions.

| Method | Request | Response | Description |
|--------|---------|----------|-------------|
| `Infer` | `InferRequest` | `InferResponse` | Master dispatches one inference task |
| `Health` | `HealthRequest` | `HealthResponse` | Master checks worker health before routing |
| `GetMetrics` | `MetricsRequest` | `WorkerMetricsResponse` | Master polls utilization stats |

**Error cases returned in `InferResponse.error`**:
- `at_capacity` — worker has reached max_concurrent, Master should not have sent this task
- `inference_timeout` — Ollama did not respond within the task timeout
- `ollama_error` — Ollama returned an error or connection refused

## HTTP: Prometheus Metrics Endpoint

`GET http://<worker-ip>:8001/metrics`

Returns Prometheus text format. Key metrics exposed:

```
# Worker identity label applied to all metrics: worker_id="laptop-abc-a1b2c3d4"

worker_active_requests{worker_id="..."} 2
worker_total_completed{worker_id="..."} 141
worker_total_failed{worker_id="..."} 1
worker_avg_latency_seconds{worker_id="..."} 2.14
worker_cpu_percent{worker_id="..."} 34.2
worker_ram_percent{worker_id="..."} 61.0
worker_gpu_percent{worker_id="..."} -1.0
worker_ollama_healthy{worker_id="..."} 1
worker_inference_duration_seconds_bucket{le="1.0",...} 12
worker_inference_duration_seconds_bucket{le="5.0",...} 38
worker_inference_duration_seconds_count{...} 141
worker_inference_duration_seconds_sum{...} 302.1
```
