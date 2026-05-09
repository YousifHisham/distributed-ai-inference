# Research: Distributed AI Inference Orchestration Platform

**Branch**: `001-distributed-ai-inference` | **Date**: 2026-05-09

---

## Decision 1: HTTP Framework (Master & Worker Agent)

**Decision**: FastAPI (Python 3.11) for both Master and Worker Agent  
**Rationale**: Native async/await support handles high concurrency without threads. Auto-generates OpenAPI docs (useful for the project report). `uvicorn` ASGI server handles thousands of concurrent connections efficiently. Far simpler than gRPC for LAN communication and easier to debug with curl/browser.  
**Alternatives considered**:
- Flask: synchronous by default, would require threads or gevent for concurrency — eliminated
- aiohttp server: more low-level, no auto-routing or validation — eliminated
- gRPC: adds protobuf compilation complexity with no benefit on a LAN — eliminated

---

## Decision 2: Internal Communication Protocol (Master ↔ Worker)

**Decision**: gRPC for all internal Master↔Worker communication; REST (FastAPI) retained for the client-facing API only  
**Rationale**: gRPC gives strongly-typed contracts enforced at compile time via protobuf, HTTP/2 multiplexing handles many concurrent dispatch calls efficiently, and built-in bidirectional streaming is available if we extend to streaming heartbeats later. The proto file becomes the single source of truth for the internal API — no drift between client and server. On a LAN the latency difference vs REST is negligible, but the type safety and tooling (grpc_cli, reflection) are valuable for debugging during the demo.  
**Alternatives considered**:
- REST/JSON: easier to curl but no schema enforcement, higher serialization overhead — retained only for client-facing API
- ZeroMQ/NATS: adds broker infrastructure complexity — eliminated
- WebSockets: useful for streaming, overkill for periodic heartbeats — eliminated

**Communication architecture**:
```
Client          →  REST POST /infer              →  Master (FastAPI, port 8000)
Master          →  gRPC Infer()                  →  Worker Agent (gRPC server, port 50052)
Worker Agent    →  gRPC Register()               →  Master (gRPC server, port 50051)
Worker Agent    →  gRPC SendHeartbeat()          →  Master (gRPC server, port 50051)  (every 5s)
Worker Agent    →  gRPC Deregister()             →  Master (gRPC server, port 50051)
Worker Agent    →  HTTP GET localhost:11434/api/generate  →  Ollama
```

When Worker Agent runs in Docker: Ollama reached via `host.docker.internal:11434` (Mac/Windows) or `--network=host` + `localhost:11434` (Linux).

**Proto compilation**: `grpcio-tools` compiles `.proto` → Python stubs at build time (in Dockerfile). Stubs are generated into `common/generated/`.

---

## Decision 3: Task Queue Implementation

**Decision**: `asyncio.Queue` (in-process, Master-side)  
**Rationale**: For this project's scope (single Master, LAN cluster), an in-process async queue is sufficient. asyncio.Queue is thread-safe within the async event loop, supports priority queuing, and requires zero infrastructure. A background coroutine drains the queue and dispatches to workers.  
**Alternatives considered**:
- Redis Queue / Celery: adds external broker dependency, requires Redis running — over-engineered for scope, eliminated
- RabbitMQ: same issue — eliminated
- Persistent DB-backed queue: adds durability but not required for demo — deferred

---

## Decision 4: Containerization Strategy

**Decision**: Docker + Docker Compose for Master and Worker Agent; Ollama runs natively on the host  
**Rationale**: Ollama requires access to GPU/Metal acceleration which does not work inside Docker on macOS (Apple Silicon) and requires the NVIDIA Container Toolkit on Linux. Running Ollama natively avoids this entirely. The Worker Agent container reaches Ollama via:
- `host.docker.internal:11434` on macOS/Windows Docker Desktop
- `--network=host` + `localhost:11434` on Linux

This means joining the cluster on a new laptop is:
1. `ollama pull <model>` (one-time)
2. `docker run ... worker-agent` (single command, configured via env vars)

Master runs as a single container, accessible on a known LAN IP and port.  
**Alternatives considered**:
- Containerizing Ollama: GPU passthrough complexity on macOS eliminates this — eliminated
- No containerization: manual Python venv setup on every laptop is error-prone — eliminated
- Kubernetes: way over-scoped for a LAN university demo — eliminated

**Environment variables for Worker Agent container**:
```
MASTER_URL=http://<master-ip>:8000
OLLAMA_URL=http://host.docker.internal:11434   # macOS/Windows
OLLAMA_URL=http://localhost:11434              # Linux (--network=host)
WORKER_MAX_CONCURRENT=4
WORKER_MODEL=llama3.2:1b
HEARTBEAT_INTERVAL=5
```

---

## Decision 5: Scheduling Strategy Architecture

**Decision**: Strategy pattern — abstract base class + pluggable implementations, selected at Master startup via config  
**Rationale**: Clean separation allows strategies to be swapped without touching dispatch logic. Each strategy receives the current worker registry snapshot and returns a selected worker (or None if no eligible worker exists).

**Interface**:
```python
class SchedulingStrategy(ABC):
    def select_worker(self, workers: list[WorkerRecord]) -> WorkerRecord | None: ...
```

**Implementations**:
- `RoundRobinStrategy`: cycles through healthy workers by index
- `LeastActiveRequestsStrategy`: picks worker with fewest active_requests
- `LoadAwareRoutingStrategy`: weighted score from active_requests, CPU%, RAM%, GPU%, avg_latency; skips workers above overload thresholds
- `LowestAverageLatencyStrategy`: picks worker with lowest rolling average latency

Selected via `SCHEDULING_STRATEGY=round_robin|least_active|load_aware|lowest_latency` env var.

---

## Decision 6: Monitoring Dashboard

**Decision**: Prometheus + Grafana — both run as Docker containers in docker-compose alongside the Master  
**Rationale**: Prometheus scrapes `/metrics` (Prometheus text format) from Master and all Worker Agents at configurable intervals. Grafana connects to Prometheus as a data source and renders time-series panels. A pre-configured Grafana dashboard JSON is checked into the repo (`monitoring/grafana/dashboards/cluster.json`) so the full dashboard loads automatically on first startup with zero manual setup. This approach produces a significantly more impressive and professional demo than a custom TUI or SSE page, requires zero custom frontend code, and demonstrates real-world observability tooling.

**Dashboard panels** (pre-configured in Grafana):
- Cluster overview: total workers, healthy/unhealthy counts, queue depth
- Throughput: requests/sec over time (line graph)
- Latency: avg + p95 over time (line graph)
- Per-worker panels: active_requests, CPU%, RAM%, GPU%, completions (one row per worker)
- Failure tracking: failed requests, retries, missed heartbeats over time
- Scheduling distribution: requests per worker (bar chart)

**Prometheus scrape targets** (in `monitoring/prometheus.yml`):
- `master:8000/metrics` — cluster-level metrics
- Worker Agents: discovered dynamically via file-based service discovery (Master writes `monitoring/targets.json` when workers register/deregister)

**Python library**: `prometheus-client` — exposed via FastAPI middleware on `/metrics` endpoint of both Master and Worker Agent.

---

## Decision 7: Fault Tolerance — Heartbeat & Recovery

**Decision**: Master runs a background asyncio task (`health_monitor`) that checks all worker last_heartbeat timestamps every 5 seconds. Threshold: 3× heartbeat interval = 15 seconds default.

**Worker status transitions**:
```
(startup) → healthy
healthy   → busy        (active_requests >= max_concurrent * 0.8)
busy      → healthy     (load drops)
healthy   → draining    (graceful deregister received)
healthy   → unhealthy   (heartbeat timeout)
draining  → offline     (tasks drained + timeout)
unhealthy → offline     (after additional timeout)
offline   → healthy     (worker re-registers + health check passes)
```

**In-flight task recovery**: Master maintains a `task_registry` dict mapping `request_id → TaskRecord`. When a worker is marked unhealthy, all tasks with `assigned_worker_id == failed_worker.node_id` and status `assigned|processing` are atomically returned to the queue with `status=retrying, retry_count += 1`.

---

## Decision 8: Retry Policy

**Decision**: Configurable via env vars, defaults suitable for LAN inference:
```
MAX_RETRIES=3
TASK_TIMEOUT=120s       (Ollama inference can be slow)
RETRY_DELAY=1s
EXPONENTIAL_BACKOFF=false  (LAN failures are usually hard failures, not transient)
```

Tasks that exceed MAX_RETRIES are marked `failed` and return `{"error": "max_retries_exceeded", "request_id": "..."}` to the client.

---

## Decision 9: Benchmarking Tool

**Decision**: Standalone Python script (`benchmark/run.py`) that:
1. Starts a load test against a running cluster for each strategy (or accepts pre-collected metrics)
2. Switches strategy via Master API call between runs
3. Collects per-request latency, throughput, queue wait time, worker utilization
4. Outputs comparison table + matplotlib charts saved to `benchmark/results/`

**Visualization**: matplotlib (universally available, no JS bundling needed).

---

## Decision 10: Load Generator

**Decision**: `asyncio` + `httpx` (async HTTP client) for the load generator  
**Rationale**: Can fire 1000+ concurrent requests from a single machine without threads. `httpx` is async-native and handles connection pooling. Results are collected per-request (latency, status) and summarized at the end.

**Modes**:
- `--users 100|500|1000` — concurrent user count
- `--burst` — sends all requests simultaneously
- `--ramp 60` — ramps up over 60 seconds
- `--query-file queries.txt` — randomized queries from file

---

## Summary of Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11 |
| Client-facing API | FastAPI + uvicorn (REST, port 8000) |
| Internal cluster comms | gRPC (grpcio + grpcio-tools, port 50051/50052) |
| Async HTTP client (Ollama) | httpx (async) |
| Task queue | asyncio.Queue |
| System metrics collection | psutil |
| Metrics exposition | prometheus-client |
| Monitoring stack | Prometheus + Grafana (Docker Compose) |
| Visualization (benchmark) | matplotlib |
| Containerization | Docker + Docker Compose |
| Ollama integration | HTTP to localhost:11434 |
| Testing | pytest + pytest-asyncio + httpx |
