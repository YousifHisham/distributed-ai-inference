# Tasks: GPU Cluster Distributed AI Inference System

**Input**: Design documents from `specs/003-gpu-node-dev/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on in-progress tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Finalize project configuration before any implementation begins.

- [X] T001 Populate master/requirements.txt with all master dependencies (fastapi, uvicorn, httpx, prometheus-client, pynvml stub)
- [X] T002 [P] Populate worker/requirements.txt with all worker dependencies (fastapi, uvicorn, httpx, chromadb, sentence-transformers, pynvml, vllm reference)
- [X] T003 [P] Write docker-compose.yml for master + nginx + prometheus + grafana services with correct ports, volumes, and env vars
- [X] T004 [P] Write docker-compose.worker.yml for worker agent container with `--gpus all` and MASTER_URL env var
- [X] T005 [P] Write nginx.conf: reverse proxy to master:8000, connection pooling, rate limiting (100 req/s per IP), 503 on queue full
- [X] T006 [P] Write monitoring/prometheus.yml: scrape master `/metrics` every 5s; use file_sd_configs pointing to monitoring/targets.json for dynamic worker targets
- [X] T007 [P] Create .env.example with all required variables: GRAFANA_PASSWORD, HUGGING_FACE_HUB_TOKEN, MOCK_GPU, MASTER_URL, VLLM_URL, WORKER_PORT
- [X] T008 [P] Populate rag/knowledge_base/ with meaningful .txt documents covering distributed systems concepts, LLM inference, and project context (the 3 existing files: distributed_systems.txt, llm_inference.txt, project_overview.txt)

**Checkpoint**: All config files present and valid — `docker compose config` should parse without errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data models and base classes required by BOTH master and worker before any user story work.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [X] T009 Implement common/enums.py: `WorkerStatus` (HEALTHY, DRAINING, UNHEALTHY) and `StrategyType` (round_robin, least_active, load_aware, lowest_latency, gpu_aware) as `str, Enum` subclasses
- [X] T010 [P] Implement common/models.py: all Pydantic v2 models — `RegisterRequest`, `RegisterResponse`, `HeartbeatPayload`, `GPUMetrics`, `ClientInferRequest`, `WorkerInferRequest`, `WorkerInferResponse`, `InferenceResponse`, `StrategyConfigRequest`, `WorkerStatusResponse`, `ClusterStatusResponse`
- [X] T011 [P] Implement master/strategies/base.py: abstract `BaseStrategy` class with `select_worker(workers: list[WorkerNode]) -> WorkerNode` interface and `name: str` property
- [X] T012 [P] Implement worker/state.py: `WorkerStateMachine` class tracking current `WorkerStatus`, with `transition(new_status)` method and guard logic (cannot transition UNHEALTHY → DRAINING directly)

**Checkpoint**: `python -c "from common.enums import WorkerStatus, StrategyType; from common.models import HeartbeatPayload"` should succeed.

---

## Phase 3: User Story 1 — Concurrent Inference Under Load (Priority: P1) 🎯 MVP

**Goal**: A load generator can send queries through NGINX → master → worker → vLLM + ChromaDB and receive context-enriched responses. End-to-end flow works for a single healthy worker.

**Independent Test**: `MOCK_GPU=true` run: start master + one worker locally, send `POST /infer` with a query, receive a response containing `result`, `worker_id`, `latency_ms`, and `rag_sources`.

- [X] T013 [P] [US1] Implement worker/gpu_metrics.py: `collect_gpu_metrics() -> GPUMetrics` using pynvml; if `MOCK_GPU=true` env var is set, return zero-filled `GPUMetrics` and log warning
- [X] T014 [P] [US1] Implement worker/rag.py: on module init, load all `.txt` files from `rag/knowledge_base/`, chunk at ~500 chars with 50-char overlap, embed with `SentenceTransformer("all-MiniLM-L6-v2")`, upsert into ChromaDB `"knowledge"` collection; expose `retrieve_context(query: str, n_results: int = 3) -> list[str]` and `build_prompt(query: str) -> tuple[str, list[str]]`
- [X] T015 [US1] Implement worker/inference.py: `async run_inference(prompt: str) -> str` — POST enriched prompt to `{VLLM_URL}/v1/chat/completions` using shared `httpx.AsyncClient`; timeout 30s; raise on HTTP error
- [X] T016 [US1] Implement worker/agent.py: on startup call `POST {MASTER_URL}/workers/register`, store returned `worker_id`; start `asyncio` background loop every 2s: collect GPU metrics + active_requests, POST to `{MASTER_URL}/workers/heartbeat`
- [X] T017 [US1] Implement worker/main.py: FastAPI app with lifespan — initialize ChromaDB (call rag.py init), init pynvml, wait for vLLM health, start agent; `POST /infer` endpoint calls `rag.build_prompt` then `inference.run_inference`, returns `WorkerInferResponse`; `GET /health` returns worker status
- [X] T018 [P] [US1] Implement master/registry.py: `WorkerRegistry` class with in-memory `dict[str, WorkerNode]`; methods: `register(url, vram) -> WorkerNode`, `update_heartbeat(worker_id, payload)`, `get_healthy_workers() -> list[WorkerNode]`, `mark_unhealthy(worker_id)`, `update_avg_latency(worker_id, sample_ms)` using EMA α=0.2
- [X] T019 [US1] Implement master/strategies/round_robin.py: `RoundRobinStrategy` — maintain an `asyncio.Lock`-protected index counter; `select_worker` returns `workers[index % len(workers)]` and increments index
- [X] T020 [US1] Implement master/scheduler.py: `Scheduler` class holding current strategy instance and shared `httpx.AsyncClient`; `async dispatch(query, request_id) -> InferenceResponse` — get healthy workers, select via strategy, POST to worker `/infer`, on failure (connection error / 5xx / timeout) retry on next healthy worker (max 3 retries), update registry latency on success
- [X] T021 [P] [US1] Implement master/routers/workers.py: `POST /workers/register` creates WorkerNode in registry; `POST /workers/heartbeat` updates metrics and last_heartbeat timestamp
- [X] T022 [US1] Implement master/routers/client.py: `POST /infer` validates request, calls `scheduler.dispatch()`, returns `InferenceResponse`; returns 503 if no healthy workers; returns 504 if all retries fail
- [X] T023 [US1] Implement master/main.py: FastAPI app with lifespan — create shared `httpx.AsyncClient`, instantiate `WorkerRegistry`, `Scheduler`, mount all routers; expose app
- [X] T024 [P] [US1] Write tests/unit/test_registry.py: test `register`, `update_heartbeat` updates fields, `get_healthy_workers` filters by status, `mark_unhealthy` changes status, EMA latency update formula
- [X] T025 [US1] Write tests/integration/test_master_rest.py: use `httpx.AsyncClient(app=app)` — test `POST /infer` with a mock worker responding 200, test 503 when registry empty, test response schema matches `InferenceResponse`

**Checkpoint**: `MOCK_GPU=true pytest tests/ -v` passes. `POST /infer` returns a valid response with rag_sources populated.

---

## Phase 4: User Story 2 — Live Strategy Switching (Priority: P2)

**Goal**: All five scheduling strategies are implemented. The operator can switch strategies via `POST /config/strategy` without restarting. New requests immediately use the new strategy.

**Independent Test**: Switch strategy to `gpu_aware` via `POST /config/strategy`, send several requests, verify `GET /workers` shows uneven load distribution matching the gpu_aware algorithm.

- [X] T026 [P] [US2] Implement master/strategies/least_active.py: `LeastActiveStrategy` — `select_worker` returns `min(workers, key=lambda w: w.active_requests)`
- [X] T027 [P] [US2] Implement master/strategies/load_aware.py: `LoadAwareStrategy` — normalize `active_requests` and `avg_latency_ms` across workers; score = `0.7 * active_norm + 0.3 * latency_norm`; select min score
- [X] T028 [P] [US2] Implement master/strategies/lowest_latency.py: `LowestLatencyStrategy` — `select_worker` returns `min(workers, key=lambda w: w.avg_latency_ms)`; treat workers with no latency history as 0 (best)
- [X] T029 [P] [US2] Implement master/strategies/gpu_aware.py: `GpuAwareStrategy` — score = `0.5 * (1 - gpu_util_pct/100) + 0.5 * (vram_free / vram_total)`; select max score; `vram_free = vram_total - vram_used`
- [X] T030 [US2] Update master/scheduler.py: add `async swap_strategy(strategy_type: StrategyType)` method using `asyncio.Lock` to atomically replace the current strategy instance; registry of strategy constructors keyed by `StrategyType`
- [X] T031 [US2] Implement master/routers/config.py: `POST /config/strategy` validates strategy name, calls `scheduler.swap_strategy()`, returns new strategy name and applied timestamp
- [X] T032 [US2] Write tests/unit/test_strategies.py: test all 5 strategies with mock worker lists — verify each returns the expected worker given known metric values; test swap_strategy atomicity with concurrent requests

**Checkpoint**: `POST /config/strategy {"strategy": "gpu_aware"}` returns 200; subsequent `POST /infer` requests are dispatched to the worker with the most free VRAM.

---

## Phase 5: User Story 3 — Fault Detection and Recovery (Priority: P2)

**Goal**: A worker that stops sending heartbeats is detected within 6 seconds and removed from routing. In-flight requests on the failed worker are retried. A restarted worker automatically rejoins.

**Independent Test**: Register 2 mock workers, stop one from sending heartbeats, wait 6s, send a request — it should always go to the remaining healthy worker. Restart the stopped worker — it re-registers and receives new requests.

- [X] T033 [US3] Implement master/health_monitor.py: `HealthMonitor` class with `async start()` — background `asyncio` task running every 2s; for each registered worker, if `now - last_heartbeat > 6s` and status is not already UNHEALTHY, mark UNHEALTHY; log state transition
- [X] T034 [US3] Update master/main.py lifespan to instantiate and start `HealthMonitor` on startup; cancel the background task on shutdown
- [X] T035 [US3] Update master/scheduler.py `dispatch()`: when a worker returns a connection error or 5xx, immediately call `registry.mark_unhealthy(worker_id)` and retry on the next available healthy worker (existing retry loop covers this — ensure registry is filtered before each retry attempt, not just at the start of dispatch)
- [X] T036 [US3] Write tests/integration/test_fault_tolerance.py: register 2 mock workers via `POST /workers/register`; stop heartbeats from worker 1; advance mock time or sleep 7s; send 10 requests; assert all go to worker 2; re-register worker 1; assert it receives subsequent requests

**Checkpoint**: Kill a worker process mid-test — master detects within 6s (verify via `GET /workers` showing UNHEALTHY), remaining workers continue serving traffic.

---

## Phase 6: User Story 4 — Proactive Hardware-Health Draining (Priority: P3)

**Goal**: A worker reporting high GPU temperature (>85°C) or ECC errors is transitioned to DRAINING state — it stops receiving new requests but completes active ones. It automatically returns to HEALTHY when health signals normalise.

**Independent Test**: Send a heartbeat with `gpu_temp_c=90`, verify worker moves to DRAINING via `GET /workers`. Send another request — it should not go to the draining worker. Send a recovery heartbeat (`gpu_temp_c=75`, `ecc_errors=0`, `active_requests=0`) — verify worker returns to HEALTHY.

- [X] T037 [US4] Update master/routers/workers.py heartbeat handler: after updating metrics, check thresholds — if `gpu_temp_c > 85` or `ecc_errors > 0`, call `registry.set_draining(worker_id)`; if status is DRAINING and `gpu_temp_c <= 80` and `ecc_errors == 0` and `active_requests == 0`, call `registry.set_healthy(worker_id)`
- [X] T038 [US4] Add `set_draining(worker_id)` and `set_healthy(worker_id)` methods to master/registry.py; add `get_schedulable_workers()` that returns only HEALTHY workers (both DRAINING and UNHEALTHY are excluded)
- [X] T039 [US4] Update master/scheduler.py to call `registry.get_schedulable_workers()` (not `get_healthy_workers()`) — this ensures both DRAINING and UNHEALTHY workers are excluded from new assignments
- [X] T040 [US4] Update worker/main.py `POST /infer` handler: if worker's own state is DRAINING, return HTTP 503 with `{"detail": "worker is draining"}` (safety check in case master sends a request during a race condition)

**Checkpoint**: `POST /workers/heartbeat {"gpu_temp_c": 90, ...}` → `GET /workers` shows status DRAINING → `POST /infer` does not route to that worker → recovery heartbeat → status back to HEALTHY.

---

## Phase 7: User Story 5 — Real-Time Monitoring (Priority: P3)

**Goal**: A Grafana dashboard shows live per-node GPU metrics, cluster throughput, latency percentiles, and worker health. Prometheus scrapes the master every 5 seconds.

**Independent Test**: Start master with 1 mock worker, send 20 requests, open `GET /metrics` — verify counter and histogram entries exist for the worker. Open Grafana and confirm GPU util, VRAM, and latency panels are populated.

- [X] T041 [US5] Add prometheus_client metric instances to master/main.py application state: `inference_requests_total` (Counter, labels: strategy/worker_id/status), `inference_latency_seconds` (Histogram, labels: strategy/worker_id), `worker_gpu_util_pct` / `worker_vram_used_gb` / `worker_gpu_temp_c` / `worker_active_requests` / `worker_status` (all Gauge, label: worker_id)
- [X] T042 [P] [US5] Implement master/routers/monitoring.py: `GET /metrics` returns `generate_latest()` with content-type `text/plain; version=0.0.4`; `GET /workers` returns `ClusterStatusResponse` with all worker states and active strategy; `GET /health` returns `{"status": "ok", "healthy_workers": N}`
- [X] T043 [US5] Update master/scheduler.py `dispatch()`: on success increment `inference_requests_total` (status=success), observe `inference_latency_seconds`; on failure increment `inference_requests_total` (status=error)
- [X] T044 [US5] Update master/routers/workers.py heartbeat handler: update all per-worker Gauge metrics (`worker_gpu_util_pct`, `worker_vram_used_gb`, `worker_gpu_temp_c`, `worker_active_requests`, `worker_status`) on every heartbeat
- [X] T045 [P] [US5] Configure monitoring/grafana/dashboards/cluster.json: panels for per-worker GPU util %, VRAM used/total, GPU temp, active requests, worker health status; cluster throughput req/s; p50/p95/p99 latency; strategy comparison panel
- [X] T046 [P] [US5] Configure monitoring/targets.json as an empty JSON array initially; update monitoring/prometheus.yml to reload targets from this file; document in quickstart how to add worker targets after registration

**Checkpoint**: `curl http://localhost:8000/metrics` shows Prometheus metrics. Grafana dashboard shows live panels during a 10-request load test.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Load generator, demo scripts, and final validation.

- [X] T047 [P] Implement client/load_generator.py: `asyncio` + `httpx.AsyncClient` with semaphore; ramp mode (100 → 500 → 1000 users, 30s each step); burst mode (all at once); print per-request: worker_id, latency_ms, retry_count; print summary: success_rate, req/s throughput, p50/p95/p99 latency
- [X] T048 [P] Populate client/queries.txt with 25+ diverse inference queries spanning the knowledge base topics
- [X] T049 Write scripts/scenario.sh with subcommands: `load-ramp` (ramp mode), `burst` (burst mode), `strategy <name>` (switch strategy), `kill-worker <n>` (SSH terminate), `restart-worker <n>` (SSH restart), `strategy-compare` (run all 5 strategies sequentially and print comparison table), `full-demo` (run complete demo sequence)
- [ ] T050 Smoke test: `MOCK_GPU=true docker compose up -d && MOCK_GPU=true docker compose -f docker-compose.worker.yml up -d` → send 5 requests via load generator → verify all succeed → `docker compose down`
- [X] T051 [P] Update README.md with project overview, demo prerequisites, quickstart reference, and architecture diagram (ASCII from design doc)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — all tasks can start immediately, most in parallel
- **Foundational (Phase 2)**: Depends on Phase 1 completion — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 — first priority, implements the full end-to-end path
- **US2 (Phase 4)**: Depends on Phase 2 + US1 (needs scheduler.py and registry.py from US1)
- **US3 (Phase 5)**: Depends on Phase 2 + US1 (needs registry.py and main.py lifespan from US1)
- **US4 (Phase 6)**: Depends on US3 (extends registry state machine and heartbeat handler)
- **US5 (Phase 7)**: Depends on US1 (needs scheduler dispatch path and routers to instrument)
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Requires only Foundational phase — no story dependencies
- **US2 (P2)**: Requires US1 (reuses scheduler.py, registry.py) — strategies can be written in parallel with US1
- **US3 (P2)**: Requires US1 (reuses registry.py, main.py lifespan) — can be written in parallel with US2
- **US4 (P3)**: Requires US3 (extends DRAINING state introduced in Phase 5)
- **US5 (P3)**: Requires US1 (instruments existing dispatch path) — can be written in parallel with US2/US3

### Within Each User Story

- Models (common/) before services
- Services before endpoints
- Endpoints before integration tests
- Worker components (T013–T017) before master dispatch (T018–T023) within US1

### Parallel Opportunities

- All Phase 1 config tasks (T002–T008): all in parallel
- T009, T010, T011, T012 (Phase 2): T010, T011, T012 in parallel after T009
- Worker-side tasks T013, T014 (US1): in parallel with each other and with T018, T019
- All strategy implementations T026–T029 (US2): all in parallel
- T033 health monitor and T034 main.py update (US3): T033 in parallel with US2 strategy work
- T045, T046 Grafana config (US5): in parallel with instrumentation tasks

---

## Parallel Example: User Story 1

```bash
# Parallel: worker infrastructure (no dependencies between these files)
Task: "T013 Implement worker/gpu_metrics.py"
Task: "T014 Implement worker/rag.py"
Task: "T018 Implement master/registry.py"

# Sequential after T013 + T014:
Task: "T015 Implement worker/inference.py"  # needs rag.py
Task: "T016 Implement worker/agent.py"       # needs gpu_metrics.py

# Sequential after T018 + T019:
Task: "T020 Implement master/scheduler.py"   # needs registry + strategy
Task: "T021 Implement master/routers/workers.py"

# Sequential after T017 + T020 + T021:
Task: "T022 Implement master/routers/client.py"
Task: "T023 Implement master/main.py"
```

## Parallel Example: User Story 2

```bash
# All 4 strategy files are fully independent:
Task: "T026 Implement master/strategies/least_active.py"
Task: "T027 Implement master/strategies/load_aware.py"
Task: "T028 Implement master/strategies/lowest_latency.py"
Task: "T029 Implement master/strategies/gpu_aware.py"

# After all 4 strategies:
Task: "T030 Update master/scheduler.py for live swap"
Task: "T031 Implement master/routers/config.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (config files)
2. Complete Phase 2: Foundational (common/models.py, enums.py, base.py, state.py)
3. Complete Phase 3: US1 — full end-to-end inference pipeline with round-robin
4. **STOP and VALIDATE**: `POST /infer` returns enriched response; `MOCK_GPU=true pytest tests/` passes
5. Demo: 3 workers, basic load test working

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 complete → full inference pipeline works (MVP — demo-able!)
3. US2 complete → strategy switching adds academic value
4. US3 + US4 complete → fault tolerance demonstrated end-to-end
5. US5 complete → Grafana dashboard makes everything visible
6. Polish → demo script makes it one-command runnable

### Parallel Team Strategy

With 2 developers after Foundational is done:
- **Dev A**: US1 (master side) + US2 strategies
- **Dev B**: US1 (worker side: rag.py, inference.py, agent.py) + US3 health_monitor.py

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks in the same phase
- `[Story]` label maps task to specific user story for traceability
- All stub files already exist — implementation tasks fill in the empty files
- Use `MOCK_GPU=true` for all local development and testing (no GPU required on laptop)
- `common/` must be on `PYTHONPATH` when running master or worker: `PYTHONPATH=. uvicorn master.main:app`
- Commit after each phase checkpoint
- T013 and T014 (worker/gpu_metrics.py and worker/rag.py) have no inter-dependencies — dispatch them in parallel
