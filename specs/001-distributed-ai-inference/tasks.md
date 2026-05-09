# Tasks: Distributed AI Inference Orchestration Platform

**Input**: Design documents from `specs/001-distributed-ai-inference/`  
**Branch**: `001-distributed-ai-inference`

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- All file paths are relative to project root

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Create project skeleton, dependency manifests, configuration, and the proto contract that everything else depends on.

- [x] T001 Create full directory structure: `master/`, `master/strategies/`, `master/routers/`, `worker/`, `worker/routers/`, `common/`, `common/generated/`, `proto/`, `client/`, `benchmark/benchmark/results/`, `monitoring/grafana/provisioning/datasources/`, `monitoring/grafana/provisioning/dashboards/`, `monitoring/grafana/dashboards/`, `tests/unit/`, `tests/integration/`
- [x] T002 [P] Create `master/requirements.txt` with: fastapi, uvicorn[standard], grpcio, grpcio-tools, httpx, psutil, prometheus-client, pytest, pytest-asyncio
- [x] T003 [P] Create `worker/requirements.txt` with: fastapi, uvicorn[standard], grpcio, grpcio-tools, httpx, psutil, prometheus-client, pytest, pytest-asyncio
- [x] T004 [P] Create `.env.example` documenting all env vars: MASTER_HTTP_PORT, MASTER_GRPC_PORT, SCHEDULING_STRATEGY, MAX_RETRIES, TASK_TIMEOUT, HEARTBEAT_TIMEOUT, MAX_QUEUE_SIZE, MASTER_GRPC_URL, OLLAMA_URL, WORKER_MODEL, WORKER_MAX_CONCURRENT, HEARTBEAT_INTERVAL, WORKER_HTTP_PORT, WORKER_GRPC_PORT
- [x] T005 [P] Write `proto/inference.proto` — full MasterService (Register, SendHeartbeat, Deregister) and WorkerService (Infer, Health, GetMetrics) with all message types per `contracts/inference.proto` design
- [x] T006 [P] Create `tests/conftest.py` with shared pytest fixtures and `pytest.ini` with asyncio_mode = auto

**Checkpoint**: Directory structure and proto contract exist — proto compilation can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Compile gRPC stubs and implement shared models/enums that every service and user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Create `scripts/compile_proto.sh` that runs `python -m grpc_tools.protoc -I proto --python_out=common/generated --grpc_python_out=common/generated proto/inference.proto` and add `common/generated/__init__.py`; run it to produce `common/generated/inference_pb2.py` and `common/generated/inference_pb2_grpc.py`
- [x] T008 [P] Implement `common/enums.py` — TaskStatus enum (queued, assigned, processing, completed, failed, retrying) and WorkerStatus enum (healthy, busy, draining, unhealthy, offline)
- [x] T009 [P] Implement `common/models.py` — Pydantic models: WorkerRecord, WorkerRegistration, Heartbeat, InferenceRequest, MetricsSnapshot, WorkerMetric, TaskRecord (fields per data-model.md)
- [x] T010 Implement `master/main.py` — FastAPI app with lifespan context manager; loads env vars (MASTER_HTTP_PORT default 8000, MASTER_GRPC_PORT default 50051, SCHEDULING_STRATEGY, MAX_RETRIES, TASK_TIMEOUT, HEARTBEAT_TIMEOUT, MAX_QUEUE_SIZE); registers routers; lifespan starts background services (stubbed for now)
- [x] T011 [P] Implement `worker/main.py` — FastAPI app with lifespan context manager; loads env vars (MASTER_GRPC_URL, OLLAMA_URL, WORKER_MODEL, WORKER_MAX_CONCURRENT, HEARTBEAT_INTERVAL, WORKER_HTTP_PORT, WORKER_GRPC_PORT); registers routers; lifespan starts background services (stubbed for now)
- [x] T012 [P] Configure structured logging in `common/logging_config.py` using Python's logging module with JSON-formatted output including timestamp, level, service name, and message

**Checkpoint**: gRPC stubs compiled, models defined, both app skeletons boot — user stories can begin

---

## Phase 3: User Story 2 — Worker Node Registers and Receives Tasks (Priority: P1)

**Goal**: A worker laptop starts, self-registers with the Master via gRPC, sends heartbeats, and can receive and execute inference tasks forwarded by the Master.

**Independent Test**: Start Master, start Worker Agent pointing at it. `curl http://master:8000/workers` shows the worker as healthy. POST a test inference to Master — it dispatches via gRPC to the worker which calls Ollama and returns a result.

- [x] T013 [US2] Implement `master/registry.py` — WorkerRegistry class with: `register(WorkerRegistration) -> WorkerRecord`, `update_heartbeat(Heartbeat)`, `deregister(node_id)`, `mark_unhealthy(node_id)`, `get_schedulable_workers() -> list[WorkerRecord]`, `get_all() -> list[WorkerRecord]`, `get(node_id) -> WorkerRecord | None`; all status transitions per data-model.md; thread-safe via asyncio.Lock
- [x] T014 [US2] Implement `master/health_monitor.py` — async coroutine `run_health_monitor(registry, heartbeat_timeout)` that loops every 5s, checks `time.time() - worker.last_heartbeat > heartbeat_timeout` for each worker, calls `registry.mark_unhealthy(node_id)` on timeout; logs failure events
- [x] T015 [US2] Implement `master/grpc_server.py` — MasterServicer class implementing Register (calls registry.register, returns RegisterResponse), SendHeartbeat (calls registry.update_heartbeat, returns HeartbeatResponse with "ok" or "re_register" if worker not found), Deregister (calls registry.deregister, marks draining, returns DeregisterResponse); `start_grpc_server(registry, port)` async function using `grpc.aio.server()`
- [x] T016 [P] [US2] Implement `worker/ollama_client.py` — OllamaClient class with async `generate(query: str, timeout: float) -> str` (POST to `{OLLAMA_URL}/api/generate` with stream=false) and async `health_check() -> bool` (GET `{OLLAMA_URL}/`); uses httpx.AsyncClient
- [x] T017 [P] [US2] Implement `worker/metrics_collector.py` — MetricsCollector class with `get_cpu_pct() -> float`, `get_ram_pct() -> float`, `get_gpu_pct() -> float` (nvidia-smi subprocess, returns -1.0 if unavailable); uses psutil for CPU/RAM
- [x] T018 [US2] Implement `worker/agent.py` — WorkerAgent class: `detect_lan_ip() -> str` (socket trick), `build_registration() -> WorkerRegistration`, async `register_with_master()` (gRPC stub call to MasterService.Register with retry on failure), async `heartbeat_loop()` (every HEARTBEAT_INTERVAL seconds: collect metrics, call MasterService.SendHeartbeat; on "re_register" response: re-call register_with_master), async `deregister()` (gRPC Deregister on shutdown)
- [x] T019 [US2] Implement `worker/grpc_server.py` — WorkerServicer class: `Infer` handler (acquire asyncio.Semaphore(WORKER_MAX_CONCURRENT), call ollama_client.generate, release semaphore, return InferResponse; on capacity return error="at_capacity"; on timeout return error="inference_timeout"), `Health` handler (check ollama health, return HealthResponse), `GetMetrics` handler (return WorkerMetricsResponse from metrics_collector); `start_grpc_server(port)` async function
- [x] T020 [US2] Wire `master/main.py` lifespan: instantiate WorkerRegistry, start `run_health_monitor` as asyncio task, call `start_grpc_server(registry, MASTER_GRPC_PORT)` as asyncio task
- [x] T021 [US2] Wire `worker/main.py` lifespan: instantiate WorkerAgent + OllamaClient + MetricsCollector, call `agent.register_with_master()` on startup, start `agent.heartbeat_loop()` as asyncio task, start `start_grpc_server(WORKER_GRPC_PORT)` as asyncio task; call `agent.deregister()` on shutdown
- [x] T022 [P] [US2] Implement `master/routers/monitoring.py` GET /workers endpoint — returns JSON list of all WorkerRecord from registry; add router to master/main.py

**Checkpoint**: Worker self-registers → GET /workers shows it healthy → heartbeats keep it alive → Master detects failure after timeout

---

## Phase 4: User Story 1 — Submit AI Requests Under Concurrent Load (Priority: P1)

**Goal**: Client submits 1000 concurrent requests to Master. Master queues them, dispatches to workers via gRPC, and returns all results without crashing or silently dropping requests.

**Independent Test**: With Master + 2 workers running, run `python client/load_generator.py --users 100`. All 100 requests receive responses. No silent drops.

- [x] T023 [US1] Implement `master/task_queue.py` — TaskQueue class with: `asyncio.Queue` internal queue, `task_registry: dict[str, InferenceRequest]`, async `enqueue(query: str) -> InferenceRequest` (creates task, assigns UUID, sets status=queued, sets timeout_at, raises if queue full), async `dequeue() -> InferenceRequest`, `complete(request_id, result, latency)`, `fail(request_id, error)`, `requeue(request_id)` (status=retrying, retry_count+=1), `get(request_id) -> InferenceRequest | None`, `size() -> int`
- [x] T024 [P] [US1] Implement `master/strategies/base.py` — abstract SchedulingStrategy with `select_worker(workers: list[WorkerRecord]) -> WorkerRecord | None`
- [x] T025 [P] [US1] Implement `master/strategies/round_robin.py` — RoundRobinStrategy: maintains internal index, cycles through healthy workers; thread-safe index increment
- [x] T026 [P] [US1] Implement `master/strategies/least_active.py` — LeastActiveRequestsStrategy: returns worker with min(active_requests) from schedulable workers
- [x] T027 [P] [US1] Implement `master/strategies/load_aware.py` — LoadAwareRoutingStrategy: composite score = active_requests*0.4 + cpu_pct*0.2 + ram_pct*0.2 + avg_latency_normalized*0.2; skips workers where active_requests >= max_concurrent; returns worker with lowest score
- [x] T028 [P] [US1] Implement `master/strategies/lowest_latency.py` — LowestAverageLatencyStrategy: returns worker with min(avg_latency); falls back to least_active if all avg_latency == 0
- [x] T029 [US1] Implement `master/scheduler.py` — Scheduler class: holds TaskQueue + WorkerRegistry + active strategy; async `dispatch_loop()` coroutine: `task = await queue.dequeue()` → `worker = strategy.select_worker(registry.get_schedulable_workers())` → if no worker: sleep + requeue → else: `asyncio.wait_for(worker_grpc_stub.Infer(InferRequest(...)), timeout=TASK_TIMEOUT)` → on success: `queue.complete(...)` → on timeout/error: `queue.requeue(...)` if retry_count < MAX_RETRIES else `queue.fail(...)`; updates registry active_requests count; each dispatch runs as a new asyncio task (non-blocking loop)
- [x] T030 [US1] Implement `master/routers/client.py` — POST /infer: enqueues task, creates asyncio.Event keyed by request_id, awaits event (up to TASK_TIMEOUT + buffer), returns result or error JSON; GET /tasks/{request_id}: returns current InferenceRequest status from task_registry; add both to master/main.py
- [x] T031 [US1] Wire `master/main.py` lifespan: instantiate TaskQueue + Scheduler with configured strategy; start `scheduler.dispatch_loop()` as asyncio task
- [x] T032 [P] [US1] Create `client/queries.txt` with 60 sample queries of varying complexity (short factual questions, medium reasoning tasks, longer analytical queries)
- [x] T033 [US1] Implement `client/load_generator.py` — async main using httpx.AsyncClient: `--master URL`, `--users N` (default 100), `--burst` (all at once) / `--ramp SECONDS` (gradual), `--query-file PATH`; spawns N concurrent tasks each POSTing to /infer; collects per-request (request_id, submitted_at, completed_at, latency, status); prints summary table: total, completed, failed, avg_latency, p95_latency, throughput (req/s)

**Checkpoint**: `python client/load_generator.py --users 1000 --burst` completes — all requests receive responses — summary shows throughput and latency

---

## Phase 5: User Story 3 — Fault Tolerance: Worker Failure and Recovery (Priority: P1)

**Goal**: A worker disappears mid-run. Master detects it within 15s, retries in-flight tasks on healthy workers, continues serving requests. When worker returns it re-registers and resumes.

**Independent Test**: Run load generator (`--users 200 --ramp 30`), kill worker container at the 10s mark. Verify from logs: failure detected, tasks retried, load_generator summary shows zero silently lost requests. Restart worker and verify it re-registers.

- [x] T034 [US3] Enhance `master/health_monitor.py`: when marking a worker unhealthy, scan `task_queue.task_registry` for all tasks with `assigned_worker_id == node_id` and status in (assigned, processing) → call `queue.requeue(request_id)` for each; log count of recovered tasks
- [x] T035 [US3] Enhance `master/scheduler.py` dispatch loop: wrap worker gRPC call in try/except for `grpc.aio.AioRpcError` in addition to `asyncio.TimeoutError`; on any failure: call `queue.requeue(task.request_id)` if `task.retry_count < MAX_RETRIES` else `queue.fail(task.request_id, "max_retries_exceeded")`; notify waiting client asyncio.Event on failure so POST /infer returns controlled error immediately
- [x] T036 [US3] Implement graceful drain in `master/grpc_server.py` Deregister handler: set worker status to draining via `registry.deregister(node_id)`; update `master/registry.py` so draining workers are excluded from `get_schedulable_workers()`; start background task to remove worker after all its tasks complete or TASK_TIMEOUT elapses
- [x] T037 [US3] Implement worker recovery in `master/grpc_server.py` Register handler: if node_id already exists in registry (re-registration), call `WorkerService.Health` gRPC stub on the re-registering worker before changing status; only set status=healthy if health check returns `ollama_healthy=true`; log recovery event
- [x] T038 [US3] Implement `worker/agent.py` reconnect logic: if `register_with_master()` gRPC call fails (Master unreachable), retry with exponential backoff (1s, 2s, 4s, up to 30s); if heartbeat receives "re_register" response, immediately re-call `register_with_master()`
- [x] T039 [US3] Write `tests/integration/test_fault_tolerance.py` — integration test using pytest-asyncio: spin up in-process Master + 2 mock workers, submit 20 tasks, stop one worker mid-run (cancel its heartbeat + gRPC server), assert all 20 tasks complete (on surviving worker), assert failed worker's tasks appear in retrying state then complete

**Checkpoint**: Kill a worker container mid-load-test → all tasks resolve → restart worker → it rejoins cluster

---

## Phase 6: User Story 4 — Load Balancing Strategy Selection (Priority: P2)

**Goal**: Operator can switch between 4 scheduling strategies at runtime. Each strategy produces measurably different distribution.

**Independent Test**: POST `/config/strategy` with each strategy name, submit 20 tasks, check per-worker task counts differ between strategies.

- [ ] T040 [US4] Implement `master/routers/config.py` — POST /config/strategy: validates strategy name (round_robin, least_active, load_aware, lowest_latency), calls `scheduler.set_strategy(name)`, returns current strategy; GET /health: returns {"status": "ok"}; add both to master/main.py
- [ ] T041 [US4] Add `set_strategy(name: str)` method to `master/scheduler.py` Scheduler class: instantiates the correct strategy class from a registry dict and replaces the active strategy atomically (assign to instance variable — asyncio single-threaded, no lock needed)
- [ ] T042 [US4] Write `tests/unit/test_strategies.py` — unit tests for all 4 strategies: create mock WorkerRecord list with varying loads, assert each strategy selects the correct worker; test edge cases (no healthy workers returns None, single worker always selected, tie-breaking behavior)

**Checkpoint**: POST /config/strategy switches behavior live — unit tests confirm each strategy's selection logic

---

## Phase 7: User Story 5 — Monitoring Dashboard (Priority: P2)

**Goal**: Prometheus scrapes Master + Workers. Grafana shows a live cluster dashboard that auto-loads from the repo with zero manual configuration.

**Independent Test**: `docker compose up` → open Grafana at :3000 → cluster dashboard loads → run load test → all panels update live → kill worker → dashboard shows failure.

- [ ] T043 [US5] Implement `master/metrics.py` — define prometheus-client metrics: `master_queue_size` (Gauge), `master_active_tasks` (Gauge), `master_healthy_workers` (Gauge), `master_unhealthy_workers` (Gauge), `master_requests_total` (Counter, labels: status), `master_retries_total` (Counter), `master_heartbeat_misses_total` (Counter, labels: worker_id), `master_request_duration_seconds` (Histogram, buckets: .5,1,2,5,10,30,60,120); expose `update_cluster_metrics(registry, task_queue)` function called by health_monitor loop
- [ ] T044 [P] [US5] Implement `worker/metrics.py` — define prometheus-client metrics: `worker_active_requests` (Gauge, labels: worker_id), `worker_total_completed` (Counter, labels: worker_id), `worker_total_failed` (Counter, labels: worker_id), `worker_inference_duration_seconds` (Histogram, labels: worker_id), `worker_cpu_percent` (Gauge, labels: worker_id), `worker_ram_percent` (Gauge, labels: worker_id), `worker_gpu_percent` (Gauge, labels: worker_id), `worker_ollama_healthy` (Gauge, labels: worker_id); expose `record_inference(worker_id, duration, success)` and `update_system_metrics(worker_id, cpu, ram, gpu, ollama_healthy)` helpers
- [ ] T045 [US5] Add GET /metrics endpoint to `master/routers/monitoring.py` using `prometheus_client.generate_latest()` with `Content-Type: text/plain; version=0.0.4`; call `update_cluster_metrics()` before generating response
- [ ] T046 [P] [US5] Add GET /metrics endpoint to `worker/routers/monitoring.py` using `prometheus_client.generate_latest()`; add router to worker/main.py
- [ ] T047 [US5] Add Prometheus file SD support to `master/registry.py`: after any register/deregister/mark_unhealthy call, write `monitoring/targets.json` as a Prometheus file_sd_configs JSON array: `[{"targets": ["<worker-ip>:<WORKER_HTTP_PORT>"], "labels": {"worker_id": "<node_id>"}}]` for all non-offline workers
- [ ] T048 [P] [US5] Write `monitoring/prometheus.yml` — scrape config: job `master` scrapes `master:8000/metrics` every 5s; job `workers` uses `file_sd_configs` pointing to `/etc/prometheus/targets.json` every 5s
- [ ] T049 [P] [US5] Write `monitoring/grafana/provisioning/datasources/prometheus.yml` — auto-provisions Prometheus data source at `http://prometheus:9090`
- [ ] T050 [P] [US5] Write `monitoring/grafana/provisioning/dashboards/dashboard.yml` — auto-loads all dashboards from `/var/lib/grafana/dashboards/`
- [ ] T051 [US5] Create `monitoring/grafana/dashboards/cluster.json` — Grafana dashboard JSON with panels: (1) Cluster Overview stat panels (healthy workers, queue size, active tasks, total requests), (2) Throughput time-series (master_requests_total rate), (3) Latency time-series (avg + p95 from histogram), (4) Per-worker active requests (multi-series), (5) Per-worker CPU/RAM/GPU gauges, (6) Failed requests + retries over time, (7) Worker status table (health, last heartbeat, completions)
- [ ] T052 [US5] Update `docker-compose.yml` — add Prometheus service (image: prom/prometheus, port 9090, mounts prometheus.yml + targets.json volume), add Grafana service (image: grafana/grafana, port 3000, mounts provisioning/ + dashboards/ volumes, env: GF_AUTH_ANONYMOUS_ENABLED=true)

**Checkpoint**: `docker compose up` → Grafana :3000 → cluster dashboard auto-loads → all panels populate during load test

---

## Phase 8: User Story 6 — Benchmarking and Strategy Comparison (Priority: P3)

**Goal**: Benchmark tool runs all 4 strategies under identical load, produces a comparison report with charts.

**Independent Test**: `python benchmark/run.py --strategies all --users 50` completes and produces `benchmark/results/comparison.png` and `benchmark/results/results.csv`.

- [ ] T053 [US6] Implement `benchmark/run.py` — CLI tool: `--master URL`, `--users N` (default 100), `--strategies` (space-separated list, default: all 4), `--output DIR` (default benchmark/results/); for each strategy: POST /config/strategy, run load_generator as subprocess or inline async call, collect TaskRecord results; store per-strategy metrics: throughput, avg_latency, p95_latency, total_failed, total_retries
- [ ] T054 [US6] Add matplotlib chart generation to `benchmark/run.py`: (1) bar chart — throughput per strategy, (2) box plot — latency distribution per strategy, (3) line chart — requests/sec over time per strategy; save all to `--output` dir as PNG files
- [ ] T055 [P] [US6] Add CSV export to `benchmark/run.py`: write `results.csv` with columns: strategy, request_id, latency, status, retry_count, worker_id; write `summary.csv` with per-strategy aggregates

**Checkpoint**: `python benchmark/run.py` → benchmark/results/ contains PNG charts + CSV files comparing all 4 strategies

---

## Phase 9: Polish & Integration

**Purpose**: Containerization, full integration tests, demo validation.

- [ ] T056 [P] Write `master/Dockerfile` — multi-stage: stage 1 installs grpcio-tools and compiles proto (`python -m grpc_tools.protoc ...`); stage 2 copies compiled stubs + source, installs runtime requirements, sets CMD to `uvicorn master.main:app --host 0.0.0.0 --port $MASTER_HTTP_PORT`; also starts gRPC server via lifespan
- [ ] T057 [P] Write `worker/Dockerfile` — same multi-stage proto compilation pattern; CMD runs worker/main.py; exposes WORKER_HTTP_PORT and WORKER_GRPC_PORT
- [ ] T058 Finalize `docker-compose.yml` — Master service (builds master/, ports 8000+50051, env vars, depends_on: none); Prometheus (depends_on: master); Grafana (depends_on: prometheus); add volume for monitoring/targets.json shared between master and prometheus containers; document worker join command in comments
- [ ] T059 [P] Write `tests/unit/test_registry.py` — unit tests for WorkerRegistry: register, heartbeat update, status transitions (healthy→busy→draining→unhealthy→offline), get_schedulable_workers filters correctly
- [ ] T060 [P] Write `tests/unit/test_task_queue.py` — unit tests for TaskQueue: enqueue/dequeue ordering, retry_count increment on requeue, max_retries enforcement, queue size limit
- [ ] T061 [P] Write `tests/integration/test_master_rest.py` — FastAPI TestClient tests: POST /infer, GET /tasks/{id}, GET /workers, POST /config/strategy, GET /health, GET /metrics
- [ ] T062 Write `README.md` matching quickstart.md steps; include demo scenario script (start → load → kill worker → recover → rejoin)
- [ ] T063 Run full test suite `pytest tests/` and fix any failures
- [ ] T064 Execute quickstart.md demo scenario end-to-end on LAN with at least 2 worker laptops; verify Grafana dashboard shows all events

**Checkpoint**: All tests pass — demo scenario executes cleanly — Grafana shows fault tolerance events

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 — **blocks all user story phases**
- **Phase 3 (US2)**: Requires Phase 2 — must complete before Phase 4 (US1 needs workers to dispatch to)
- **Phase 4 (US1)**: Requires Phase 3 — dispatch engine needs a working worker agent
- **Phase 5 (US3)**: Requires Phase 4 — fault tolerance builds on top of working dispatch
- **Phase 6 (US4)**: Requires Phase 4 — strategy hot-swap needs scheduler running
- **Phase 7 (US5)**: Requires Phase 3 + Phase 4 — metrics need both Master and Worker running
- **Phase 8 (US6)**: Requires Phase 4 + Phase 6 — benchmarking needs all strategies + load generator
- **Phase 9 (Polish)**: Requires all user story phases complete

### User Story Dependencies

- **US2 (P1)**: Depends on Foundational only — first story to implement
- **US1 (P1)**: Depends on US2 (needs workers to dispatch to)
- **US3 (P1)**: Depends on US1 (enhances existing dispatch + health monitor)
- **US4 (P2)**: Depends on US1 (adds hot-swap to existing scheduler)
- **US5 (P2)**: Depends on US2 + US1 (scrapes metrics from both services)
- **US6 (P3)**: Depends on US1 + US4 (runs load generator per strategy)

### Within Each Phase — Task Order

- Models/enums before services
- Services before gRPC servers
- gRPC servers before agent startup
- Agent startup before integration tests

### Parallel Opportunities

- T002, T003, T004, T005, T006 — all Phase 1 tasks after T001 run in parallel
- T008, T009, T011, T012 — Phase 2 tasks after T007 (proto compiled)
- T016, T017 — Phase 3 worker components built in parallel with T013–T015
- T024, T025, T026, T027, T028 — all strategy implementations in parallel
- T043, T044 — master and worker metrics files in parallel
- T056, T057, T059, T060, T061 — Polish phase tasks mostly parallel

---

## Parallel Example: Phase 4 (US1)

```bash
# All strategies can be implemented simultaneously (different files):
Task T025: master/strategies/round_robin.py
Task T026: master/strategies/least_active.py
Task T027: master/strategies/load_aware.py
Task T028: master/strategies/lowest_latency.py

# Then sequentially:
Task T029: master/scheduler.py  (imports all strategies)
Task T030: master/routers/client.py  (uses scheduler)
```

---

## Implementation Strategy

### MVP (P1 Stories — US2 → US1 → US3)

1. Complete Phase 1 + Phase 2 (Setup + Foundational)
2. Complete Phase 3 (US2 — worker registration)
3. Complete Phase 4 (US1 — concurrent request handling + load generator)
4. **STOP and VALIDATE**: `python client/load_generator.py --users 100` — all requests answered
5. Complete Phase 5 (US3 — fault tolerance)
6. **DEMO**: fault tolerance scenario visible in logs

### Full System

7. Phase 6 (US4 — strategy hot-swap)
8. Phase 7 (US5 — Prometheus + Grafana)
9. Phase 8 (US6 — benchmarking)
10. Phase 9 (Polish + containerization)

### Parallel Team Strategy (5 students)

After Phases 1–2 complete:
- **Student A**: Phase 3 (US2 — worker agent + gRPC)
- **Student B**: Phase 4 (US1 — scheduler + strategies)
- **Student C**: Phase 5 (US3 — fault tolerance)
- **Student D**: Phase 7 (US5 — Prometheus + Grafana)
- **Student E**: Phase 8 (US6 — benchmarking) + Phase 9 (Polish)

---

## Notes

- [P] tasks operate on different files — safe to assign to different team members simultaneously
- Proto stubs in `common/generated/` must be committed or compiled before any service imports them
- Test the fault tolerance scenario (Phase 5) on real LAN hardware — in-process mocks may not catch network-level failures
- Grafana dashboard JSON (T051) can be built interactively in Grafana UI then exported as JSON
- GPU metrics (nvidia-smi) will show -1.0 on CPU-only laptops — this is expected and handled
