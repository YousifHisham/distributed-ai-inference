# Feature Specification: Distributed AI Inference Orchestration Platform

**Feature Branch**: `001-distributed-ai-inference`  
**Created**: 2026-05-09  
**Status**: Draft  

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit AI Requests Under Concurrent Load (Priority: P1)

A developer or tester submits hundreds to thousands of AI inference requests simultaneously through the system's public-facing gateway. The system accepts all requests, queues them, distributes them across available worker laptops on the LAN, and returns responses with measured latency — without losing any request or crashing.

**Why this priority**: This is the core value proposition of the system. Without functional concurrent request handling and distribution, no other feature has meaning.

**Independent Test**: Can be fully tested by running the load generator at 100, 500, and 1000 concurrent users against a live Master with at least 2 Worker Agents registered. Every submitted request must receive a response (success or controlled error), and no request should disappear silently.

**Acceptance Scenarios**:

1. **Given** the Master is running and 3 Worker Agents are registered, **When** 1000 concurrent requests are submitted via the load generator, **Then** all 1000 requests receive a response (result or failure notification) and the system does not crash
2. **Given** the system is processing requests, **When** the load generator measures latency and throughput, **Then** average latency and requests-per-second metrics are captured and displayed
3. **Given** no Worker Agents are available, **When** a request is submitted, **Then** the system returns a controlled error response (queue full or no workers available) rather than crashing

---

### User Story 2 - Worker Node Registers and Receives Tasks (Priority: P1)

A student starts the Worker Agent on their laptop. The agent detects the laptop's local IP, checks that Ollama is running, and automatically registers itself with the Master. From that point, the Master begins routing inference tasks to this worker without any manual configuration. The student's laptop immediately participates in the cluster.

**Why this priority**: Dynamic worker registration is the foundation of the distributed architecture. Without it, the system is not truly distributed.

**Independent Test**: Start the Master first, then start a Worker Agent on a second machine. Verify in the Master's registry that the worker appears as "healthy" and that subsequent requests are routed to it.

**Acceptance Scenarios**:

1. **Given** the Master is running, **When** a Worker Agent starts on a LAN laptop and Ollama is running locally, **Then** the worker appears in the Master's active registry within 5 seconds with status "healthy"
2. **Given** a worker is registered, **When** the load generator sends requests, **Then** the worker receives and processes tasks assigned by the scheduler
3. **Given** Ollama is not running on the worker laptop, **When** the Worker Agent starts, **Then** the worker still registers but reports an unhealthy Ollama status, and no inference tasks are routed to it

---

### User Story 3 - Fault Tolerance: Worker Failure and Recovery (Priority: P1)

While a load test is running, one of the worker laptops is closed or disconnected from Wi-Fi. The Master detects the missed heartbeats, marks the worker unhealthy, reassigns any in-flight tasks to remaining healthy workers, and continues serving requests without interruption. When the laptop reconnects and restarts the Worker Agent, it re-registers and begins receiving tasks again.

**Why this priority**: Fault tolerance is an explicit grading requirement and a core distributed systems concept the project must demonstrate.

**Independent Test**: Run the demo scenario — start Master + 3 workers + load generator, kill one worker mid-run, observe that the Master continues operating, all in-flight tasks are retried, and traffic redistributes. Then restart the killed worker and observe re-registration.

**Acceptance Scenarios**:

1. **Given** a worker is processing tasks, **When** its process is killed or the laptop closes, **Then** the Master detects the failure within the configured heartbeat timeout and marks the worker unhealthy
2. **Given** a worker is marked unhealthy, **When** tasks were in-flight on that worker, **Then** those tasks are retried on healthy workers and no request is silently lost
3. **Given** a previously failed worker restarts and re-registers, **When** it passes the health check, **Then** the Master adds it back to the scheduling pool and begins routing tasks to it again
4. **Given** a worker sends a graceful shutdown signal, **When** it is marked draining, **Then** no new tasks are routed to it and in-flight tasks finish or are reassigned before the worker is removed

---

### User Story 4 - Load Balancing Strategy Selection (Priority: P2)

An operator configures the Master to use a specific scheduling strategy (Round Robin, Least Active Requests, Load-Aware Routing, or Lowest Average Latency). The chosen strategy determines how tasks are distributed across workers. The operator can benchmark different strategies and compare throughput, latency, and worker utilization.

**Why this priority**: Demonstrates the pluggable scheduling architecture and enables the benchmarking comparison required by the project.

**Independent Test**: Configure the system with each of the 4 strategies in turn, run the same load test scenario, capture metrics, and verify that the distribution behavior differs meaningfully between strategies.

**Acceptance Scenarios**:

1. **Given** Round Robin is configured, **When** 12 tasks are dispatched across 3 workers, **Then** each worker receives approximately 4 tasks in rotation
2. **Given** Least Active Requests is configured and one worker has 10 active tasks while another has 2, **When** a new task arrives, **Then** it is assigned to the worker with 2 active tasks
3. **Given** Load-Aware Routing is configured, **When** a worker's CPU or RAM exceeds the overload threshold, **Then** that worker does not receive new tasks until utilization drops

---

### User Story 5 - Live Monitoring Dashboard (Priority: P2)

A system administrator opens the monitoring dashboard and sees a real-time view of the cluster: which workers are connected, their health status, current active request counts, queue sizes, throughput, average latency, and failed request counts. When a worker joins or leaves, the dashboard updates within seconds.

**Why this priority**: Observability is required by the project spec and essential for demonstrating system behavior during demos.

**Independent Test**: Open the dashboard, run a load test, kill a worker, and restart it. Verify all events (worker join, worker failure, worker recovery, metric updates) are visible in the dashboard without manual refresh.

**Acceptance Scenarios**:

1. **Given** the dashboard is open, **When** a new worker registers, **Then** it appears in the dashboard within 3 seconds with its health status and hardware stats
2. **Given** a load test is running, **When** the dashboard is viewed, **Then** it shows live requests/sec, average latency, queue sizes, and per-worker utilization
3. **Given** a worker fails, **When** the Master marks it unhealthy, **Then** the dashboard shows the failure event and the worker's status changes from healthy to unhealthy/offline

---

### User Story 6 - Benchmarking and Strategy Comparison (Priority: P3)

A researcher runs the benchmark tool to compare scheduling strategies across multiple test configurations. The tool produces a structured report with throughput, latency, queue wait times, worker utilization, and failure recovery times for each strategy. Results are visualized for easy comparison in the project report.

**Why this priority**: Required by the project spec but dependent on all other components being functional first.

**Independent Test**: Run the benchmark tool with at least 2 strategies and verify it produces a complete comparison report with charts or tables.

**Acceptance Scenarios**:

1. **Given** all strategies are implemented, **When** the benchmark tool runs each strategy under identical load conditions, **Then** it outputs a structured comparison of throughput, latency, and utilization per strategy
2. **Given** benchmark results are collected, **When** visualization is requested, **Then** charts or plots are generated showing performance differences between strategies

---

### Edge Cases

- What happens when all workers are unhealthy/offline and a request arrives? The system must queue or reject gracefully with a controlled error response.
- What happens when a task exceeds its retry limit? It must be marked failed and the client must receive a controlled error — not a timeout or silent drop.
- What happens when the queue grows larger than its capacity? Requests beyond capacity should receive a queue-full error immediately.
- What happens when a worker registers with a model name that no current request requires? The scheduler must still be able to route compatible requests.
- What happens when a worker's heartbeat arrives but Ollama is down? The worker must report unhealthy Ollama status and the Master must stop routing inference tasks to it.
- What happens when a worker reconnects after failure with a different IP? Re-registration flow must handle updated address correctly.
- What happens when two workers register with the same node_id? The second registration should update the existing record or be rejected with a conflict error.

---

## Requirements *(mandatory)*

### Functional Requirements

**Master Gateway / Scheduler**

- **FR-001**: The Master MUST accept incoming AI inference requests concurrently and maintain them in an internal task queue
- **FR-002**: The Master MUST maintain a worker registry tracking each worker's node_id, address, status, heartbeat timestamp, active requests, completed/failed counts, average latency, hardware stats, and supported models
- **FR-003**: The Master MUST implement four pluggable scheduling strategies: Round Robin, Least Active Requests, Load-Aware Routing, and Lowest Average Latency — selectable without restart
- **FR-004**: The Master MUST dispatch tasks asynchronously to Worker Agents and not block on individual task completion
- **FR-005**: The Master MUST retry failed or timed-out tasks on healthy workers up to a configurable maximum retry count
- **FR-006**: The Master MUST track each task's full lifecycle: queued → assigned → processing → completed/failed/retrying, with request_id, assigned_worker_id, retry_count, created_at, updated_at, and timeout_at
- **FR-007**: The Master MUST expose a Prometheus-compatible metrics endpoint so Prometheus can scrape cluster-wide counters and gauges (queue size, throughput, latency histograms, worker counts, failure counts)
- **FR-008**: The Master MUST detect worker failure by tracking heartbeat timestamps and marking workers unhealthy when heartbeats are missed beyond a configurable timeout
- **FR-009**: The Master MUST NOT communicate directly with Ollama — all inference must go through Worker Agents; internal Master↔Worker communication (task dispatch, registration, heartbeats) MUST use gRPC
- **FR-010**: The Master MUST continue operating without restart when workers join or leave the cluster

**Worker Node Agent**

- **FR-011**: Each Worker Agent MUST automatically register with the Master on startup via gRPC, providing node_id, hostname, IP address, model name, max concurrent requests, CPU info, RAM capacity, GPU availability, GPU name, and Ollama status
- **FR-012**: Each Worker Agent MUST send heartbeats to the Master via gRPC at a fixed interval (default: every 5 seconds), including current status, active_requests, queue_size, CPU/RAM/GPU usage, and Ollama health
- **FR-013**: Each Worker Agent MUST enforce a configurable limit on the number of concurrent inference generations
- **FR-014**: Each Worker Agent MUST check local Ollama health and report unhealthy status when Ollama is unavailable
- **FR-015**: Each Worker Agent MUST gracefully deregister from the Master when intentionally stopped, triggering the draining state

**Scheduling Behavior**

- **FR-017**: The scheduler MUST only route tasks to workers with status "healthy" (or "busy" below overload threshold)
- **FR-018**: The scheduler MUST NOT route tasks to workers with status unhealthy, offline, or draining
- **FR-019**: Load-Aware Routing MUST consider active_requests, queue_length, CPU usage, RAM usage, GPU usage, average latency, and worker health when selecting a worker
- **FR-020**: When a new worker joins, it MUST become immediately eligible for scheduling without Master restart
- **FR-021**: When a worker leaves, the scheduler MUST redistribute workload to remaining healthy workers automatically

**Fault Tolerance**

- **FR-022**: The system MUST identify all in-flight tasks on a failed worker and return them to the task queue for reassignment
- **FR-023**: The retry policy MUST be configurable: maximum retries, task timeout, retry delay, and optional exponential backoff
- **FR-024**: Tasks that exceed maximum retries MUST be marked failed and return a controlled error response to the requester — no request may disappear silently
- **FR-025**: Each inference task MUST have a timeout; timed-out tasks MUST be retried on a different healthy worker
- **FR-026**: A failed worker that re-registers MUST only receive tasks after a successful health check

**Client Load Generator**

- **FR-027**: The load generator MUST support configurable concurrent user counts: 100, 500, and 1000+
- **FR-028**: The load generator MUST support burst traffic patterns and randomized request sizes
- **FR-029**: The load generator MUST capture and report latency per request and aggregate throughput

**Monitoring & Observability**

- **FR-030**: Both Master and Worker Agents MUST expose Prometheus-compatible metrics endpoints; a Prometheus instance MUST scrape them and a Grafana instance MUST provide a pre-configured live dashboard showing active workers, worker health, queue sizes, throughput (req/sec), average latency, failed requests, active tasks, per-worker utilization, and load distribution
- **FR-031**: The Grafana dashboard MUST show worker lifecycle events (joins, failures, recoveries) and time-series graphs of all key metrics, updating in real time

**Benchmarking**

- **FR-032**: The benchmark tool MUST compare all four scheduling strategies under identical load conditions and report throughput, latency, queue wait times, worker utilization, and failure recovery time
- **FR-033**: Benchmark results MUST be exportable and visualizable (charts or structured tables)

### Key Entities

- **InferenceRequest**: Represents a single AI inference task. Attributes: request_id, query, status, assigned_worker_id, retry_count, created_at, updated_at, timeout_at, result, error
- **WorkerRecord**: Registry entry for a connected worker node. Attributes: node_id, hostname, address (IP:port), status, last_heartbeat, active_requests, total_completed, total_failed, average_latency, current_load, hardware_stats, supported_models
- **Heartbeat**: Periodic health report from a worker. Attributes: node_id, timestamp, status, active_requests, queue_size, cpu_pct, ram_pct, gpu_pct, ollama_healthy
- **SchedulingStrategy**: A pluggable algorithm for selecting a target worker. Variants: RoundRobin, LeastActiveRequests, LoadAwareRouting, LowestAverageLatency
- **TaskQueue**: The Master's internal queue holding pending and retrying inference tasks
- **MetricsSnapshot**: Aggregated cluster metrics at a point in time. Attributes: timestamp, total_requests, completed, failed, avg_latency, req_per_sec, per_worker_stats

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The system accepts and processes 1000 concurrent requests without crashing, losing any request silently, or requiring manual intervention
- **SC-002**: Worker failure is detected within 3× the configured heartbeat interval (default: within 15 seconds of a missed heartbeat)
- **SC-003**: In-flight tasks from a failed worker are reassigned and complete on healthy workers — zero requests are silently dropped due to node failure
- **SC-004**: A new worker laptop can join the cluster while a load test is running and begin receiving tasks within 10 seconds of registration
- **SC-005**: The monitoring dashboard reflects worker status changes (join, failure, recovery) within 5 seconds of the event occurring
- **SC-006**: All four scheduling strategies produce measurably different load distributions across workers in benchmark results
- **SC-007**: The benchmark tool produces a complete comparison report for all four strategies covering throughput, latency, and worker utilization
- **SC-008**: The system runs entirely on a local LAN with no cloud dependencies, no paid services, and no internet connectivity required
- **SC-009**: The fault tolerance demo scenario (start → load → kill worker → recover → rejoin) can be executed end-to-end and all events are visible in logs and dashboard

---

## Assumptions

- Worker laptops are on the same LAN and can reach the Master's IP and port directly (no NAT traversal needed)
- Python 3.9+ is available on all laptops (Master and Worker nodes)
- Ollama is pre-installed on worker laptops before the Worker Agent starts; the Worker Agent does not install Ollama
- The system does not require authentication — it is designed for a controlled academic demo environment, not public internet exposure
- A single Master node is sufficient for this project; Master high-availability is out of scope
- GPU support is a bonus when available; the system works on CPU-only laptops as long as Ollama can run the chosen model
- The model loaded in Ollama on each worker laptop is the same (or compatible) model; multi-model routing per request is out of scope for v1
- The monitoring dashboard is Grafana (open-source, no paid tier needed) with a pre-configured dashboard JSON checked into the repo; no custom frontend code is required
- Worker node_ids are generated automatically from hostname + a unique suffix if not provided by the operator
- Maximum queue size and overload thresholds are configurable via environment variables or a config file loaded at startup
- The benchmarking tool is run separately from the main system and reads collected metrics to produce reports
- Network partitions are treated as worker failures (the same heartbeat timeout mechanism handles both)
