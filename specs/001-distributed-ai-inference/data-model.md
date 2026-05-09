# Data Model: Distributed AI Inference Orchestration Platform

**Branch**: `001-distributed-ai-inference` | **Date**: 2026-05-09

All state is held in-memory on the Master process. No persistent database is required.

---

## Entities

### InferenceRequest

Represents one client-submitted AI inference task throughout its lifecycle.

| Field | Type | Description |
|-------|------|-------------|
| request_id | str (UUID4) | Unique task identifier |
| query | str | The prompt/question to send to the LLM |
| status | TaskStatus | Current lifecycle state |
| assigned_worker_id | str \| None | node_id of the worker handling this task |
| retry_count | int | Number of times this task has been retried (starts at 0) |
| created_at | float | Unix timestamp when request was received |
| updated_at | float | Unix timestamp of last status change |
| timeout_at | float | Unix timestamp after which task is considered timed out |
| result | str \| None | The LLM response (set on completion) |
| error | str \| None | Error message (set on failure) |
| queue_wait_time | float \| None | Seconds spent in queue before first assignment |

**TaskStatus enum**:
```
queued      → task received, waiting in queue
assigned    → dispatched to a worker, awaiting acknowledgement
processing  → worker has confirmed receipt and is running Ollama
completed   → worker returned a result
failed      → exceeded max_retries or unrecoverable error
retrying    → returned to queue after worker failure or timeout
```

**State transitions**:
```
queued → assigned → processing → completed
                              ↘ retrying → assigned (retry loop)
                                         ↘ failed (max retries exceeded)
queued → failed (queue full / no workers)
```

---

### WorkerRecord

Registry entry maintained by the Master for each connected Worker Agent.

| Field | Type | Description |
|-------|------|-------------|
| node_id | str | Unique worker identifier (hostname + random suffix) |
| hostname | str | Laptop hostname |
| address | str | `http://<ip>:<port>` of the Worker Agent |
| status | WorkerStatus | Current health state |
| last_heartbeat | float | Unix timestamp of most recent heartbeat received |
| active_requests | int | Number of tasks currently in-flight on this worker |
| total_completed | int | Cumulative completed tasks since registration |
| total_failed | int | Cumulative failed tasks since registration |
| average_latency | float | Rolling average inference latency in seconds |
| current_load | float | Composite load score (0.0–1.0) used by LoadAware strategy |
| cpu_pct | float | Last reported CPU usage percentage |
| ram_pct | float | Last reported RAM usage percentage |
| gpu_pct | float \| None | Last reported GPU usage (None if no GPU) |
| gpu_name | str \| None | GPU model name if available |
| max_concurrent | int | Worker's declared concurrency limit |
| model_name | str | Ollama model loaded on this worker |
| ollama_healthy | bool | Whether local Ollama is reachable |
| registered_at | float | Unix timestamp of registration |

**WorkerStatus enum**:
```
healthy     → accepting new tasks (active_requests < max_concurrent * 0.8)
busy        → near capacity but still eligible (active_requests < max_concurrent)
draining    → graceful shutdown in progress, no new tasks
unhealthy   → heartbeat missed or Ollama down, no new tasks
offline     → removed from registry after timeout
```

**Scheduler eligibility**: Only `healthy` and `busy` workers receive new tasks.

---

### Heartbeat

Periodic status report sent by Worker Agent to Master.

| Field | Type | Description |
|-------|------|-------------|
| node_id | str | Identifies the sending worker |
| timestamp | float | Unix timestamp when heartbeat was generated |
| status | WorkerStatus | Worker's self-reported status |
| active_requests | int | Current in-flight count |
| queue_size | int | Requests waiting in local worker queue |
| cpu_pct | float | CPU usage % |
| ram_pct | float | RAM usage % |
| gpu_pct | float \| None | GPU usage % (None if unavailable) |
| ollama_healthy | bool | Result of Ollama health check |
| avg_latency | float | Rolling average latency of recent completions |

---

### WorkerRegistration

Payload sent by Worker Agent during startup registration.

| Field | Type | Description |
|-------|------|-------------|
| node_id | str | Auto-generated: `<hostname>-<8-char-uuid>` |
| hostname | str | System hostname |
| ip_address | str | LAN IP address (auto-detected) |
| port | int | Worker Agent HTTP port (default: 8001) |
| model_name | str | Ollama model name (e.g., `llama3.2:1b`) |
| max_concurrent | int | Max simultaneous Ollama generations (default: 4) |
| cpu_count | int | Number of CPU cores |
| ram_gb | float | Total RAM in GB |
| gpu_available | bool | Whether a GPU was detected |
| gpu_name | str \| None | GPU model name |
| ollama_healthy | bool | Whether Ollama responded to health check |

---

### MetricsSnapshot

Point-in-time aggregation of cluster metrics, returned by `/metrics` endpoint and streamed via SSE.

| Field | Type | Description |
|-------|------|-------------|
| timestamp | float | When snapshot was taken |
| total_workers | int | Total registered workers |
| healthy_workers | int | Workers with status healthy or busy |
| unhealthy_workers | int | Workers with status unhealthy or offline |
| draining_workers | int | Workers in draining state |
| queue_size | int | Tasks currently in the Master queue |
| active_tasks | int | Tasks with status assigned or processing |
| completed_total | int | All-time completed tasks |
| failed_total | int | All-time failed tasks |
| requests_per_sec | float | Throughput over last 10 seconds |
| avg_latency | float | Average end-to-end latency over last 60 seconds |
| p95_latency | float | 95th percentile latency over last 60 seconds |
| current_strategy | str | Active scheduling strategy name |
| workers | list[WorkerMetric] | Per-worker breakdown |

**WorkerMetric** (nested):

| Field | Type | Description |
|-------|------|-------------|
| node_id | str | Worker identifier |
| status | WorkerStatus | Current status |
| active_requests | int | In-flight count |
| total_completed | int | Cumulative completions |
| avg_latency | float | Rolling average latency |
| cpu_pct | float | CPU usage |
| ram_pct | float | RAM usage |
| gpu_pct | float \| None | GPU usage |
| seconds_since_heartbeat | float | Time since last heartbeat |

---

### TaskRecord (benchmark output)

Per-request record collected by the load generator and benchmark tool.

| Field | Type | Description |
|-------|------|-------------|
| request_id | str | Task identifier |
| submitted_at | float | Client submission timestamp |
| completed_at | float \| None | Completion timestamp |
| total_latency | float \| None | End-to-end time in seconds |
| queue_wait | float \| None | Time in Master queue |
| inference_time | float \| None | Time Ollama spent generating |
| assigned_worker | str \| None | Worker that completed the task |
| status | str | completed / failed / timeout |
| retry_count | int | Number of retries |

---

## Validation Rules

- `query` must be non-empty string, max 4096 characters
- `max_concurrent` must be between 1 and 32
- `TASK_TIMEOUT` must be > 0; default 120 seconds
- `HEARTBEAT_TIMEOUT` = 3 × `HEARTBEAT_INTERVAL`; default 15 seconds
- `retry_count` must not exceed `MAX_RETRIES` (default 3) before task is marked failed
- Workers with `ollama_healthy=false` must not receive inference tasks even if status is healthy
- `active_requests` on WorkerRecord must never exceed `max_concurrent`

---

## In-Memory Collections (Master)

```
worker_registry: dict[node_id, WorkerRecord]
task_registry:   dict[request_id, InferenceRequest]
task_queue:      asyncio.Queue[InferenceRequest]
latency_window:  deque[float] (last 1000 completed latencies, for p95 calc)
event_log:       deque[ClusterEvent] (last 500 events for dashboard SSE)
```
