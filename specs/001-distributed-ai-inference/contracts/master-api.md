# Master Interfaces

The Master exposes three interfaces:

1. **REST API** (port 8000, FastAPI) — client-facing; load generator and operators call this
2. **gRPC server** (port 50051) — internal; Worker Agents call this to register, heartbeat, deregister. Defined in [`inference.proto`](inference.proto) under `MasterService`
3. **HTTP `/metrics`** (port 8000) — Prometheus scrape endpoint, Prometheus text format

## REST API

**Base URL**: `http://<master-ip>:8000`  
**Protocol**: HTTP/1.1, JSON bodies, UTF-8

---

## Client-Facing Endpoints

### POST /infer
Submit an AI inference request.

**Request body**:
```json
{
  "query": "What is the capital of France?"
}
```

**Response 200** (synchronous — waits for result):
```json
{
  "request_id": "uuid4",
  "result": "The capital of France is Paris.",
  "latency": 2.34,
  "worker_id": "worker-abc123",
  "retry_count": 0
}
```

**Response 503** (no healthy workers):
```json
{
  "error": "no_workers_available",
  "request_id": "uuid4"
}
```

**Response 504** (task timed out and exceeded retries):
```json
{
  "error": "max_retries_exceeded",
  "request_id": "uuid4",
  "retry_count": 3
}
```

---

### GET /tasks/{request_id}
Poll task status (for async/long-running variant).

**Response 200**:
```json
{
  "request_id": "uuid4",
  "status": "processing",
  "assigned_worker_id": "worker-abc123",
  "retry_count": 0,
  "created_at": 1746791234.5,
  "updated_at": 1746791236.1
}
```

---

> **Note**: Worker registration, heartbeat, and deregistration are handled via **gRPC** (`MasterService` in `inference.proto`), not REST. See [`inference.proto`](inference.proto).

---

## Monitoring Endpoints

### GET /metrics
Prometheus text format — scraped by Prometheus every 5s. Key metrics:

```
# Cluster-level
master_queue_size 12
master_active_tasks 8
master_completed_total 423
master_failed_total 2
master_healthy_workers 3
master_unhealthy_workers 0
master_requests_per_second 4.7
master_request_duration_seconds_bucket{le="1.0"} 210
master_request_duration_seconds_bucket{le="5.0"} 410
master_request_duration_seconds_count 423
master_request_duration_seconds_sum 901.2
master_retry_total 5
master_heartbeat_misses_total{worker_id="..."} 2
```

---

### GET /workers
Returns worker registry.

**Response 200**:
```json
{
  "workers": [
    {
      "node_id": "laptop-abc-a1b2c3d4",
      "hostname": "Ahmeds-MacBook",
      "address": "http://192.168.1.42:8001",
      "status": "healthy",
      "model_name": "llama3.2:1b",
      "max_concurrent": 4,
      "active_requests": 2,
      "total_completed": 141,
      "total_failed": 0,
      "avg_latency": 2.1,
      "ollama_healthy": true,
      "registered_at": 1746790000.0
    }
  ]
}
```

---

### POST /config/strategy
Change the active scheduling strategy without restart.

**Request body**:
```json
{
  "strategy": "round_robin"
}
```
Valid values: `round_robin`, `least_active`, `load_aware`, `lowest_latency`

**Response 200**:
```json
{
  "status": "ok",
  "strategy": "round_robin"
}
```

---

## GET /health
Basic liveness check.

**Response 200**:
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```
