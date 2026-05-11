# Design: GPU Cluster Distributed AI Inference System

**Date**: 2026-05-11  
**Course**: CSE354 Distributed Computing — Ain Shams University, Semester 2 2025/2026  
**Branch**: `003-gpu-node-dev`  
**Status**: Approved

---

## Goal

Build a distributed LLM inference system that demonstrates core distributed computing concepts — load balancing, scheduling strategies, fault tolerance, and observability — using real GPU hardware. The primary output is a convincing demo and a written report. All components use real data: no simulated metrics, no stubbed inference.

---

## Architecture Overview

```
Load Generator (Python script)
        │ HTTP POST /infer  (100 → 1000 concurrent users, ramp mode)
        ▼
     NGINX
        │ reverse proxy, rate limiting, connection pooling
        ▼
┌─────────────────────────────────────────────────┐
│              MASTER NODE (your laptop)          │
│                                                 │
│  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Scheduler  │  │     Worker Registry     │  │
│  │  (strategy  │  │  tracks: status, GPU    │  │
│  │  switching) │  │  metrics, active reqs   │  │
│  └─────────────┘  └─────────────────────────┘  │
│  ┌──────────────────┐  ┌────────────────────┐  │
│  │  Health Monitor  │  │ Prometheus+Grafana  │  │
│  │  heartbeat +     │  │ GPU util, VRAM,     │  │
│  │  draining state  │  │ latency, throughput │  │
│  └──────────────────┘  └────────────────────┘  │
│                                                 │
│              ngrok tunnel                       │
└─────────────────┬───────────────────────────────┘
                  │ HTTPS (ngrok) — raw query dispatch
        ┌─────────┼─────────┐
        ▼         ▼         ▼
  ┌──────────┐ ┌──────────┐ ┌──────────┐
  │ Worker 1 │ │ Worker 2 │ │ Worker 3 │
  │ Thunder  │ │ Thunder  │ │ Thunder  │
  │ Compute  │ │ Compute  │ │ Compute  │
  │──────────│ │──────────│ │──────────│
  │ vLLM     │ │ vLLM     │ │ vLLM     │
  │ ChromaDB │ │ ChromaDB │ │ ChromaDB │
  │ pynvml   │ │ pynvml   │ │ pynvml   │
  └──────────┘ └──────────┘ └──────────┘
```

---

## Components

### Master Node (runs on developer's laptop)

**FastAPI REST gateway** — receives all client requests, orchestrates scheduling, manages the cluster.

Responsibilities:
- Accept inference requests from clients via NGINX
- Select a target worker using the active scheduling strategy
- Dispatch the raw query to the selected worker (worker handles RAG + inference)
- Track in-flight tasks and retry on worker failure
- Expose cluster status, strategy switching, and metrics endpoints
- Run Prometheus + Grafana for observability
- Expose itself to Thunder Compute workers via an ngrok tunnel

**Does not do**: RAG retrieval, LLM inference, GPU metric collection.

---

### GPU Worker Node (runs on Thunder Compute instances)

Each worker is a fully self-contained inference unit. Three workers planned for the demo (~$20 budget at ~$0.50–1.00/hr per instance).

**On each worker node:**

1. **vLLM inference server** — runs the LLM on the GPU. OpenAI-compatible API. Handles concurrent requests with continuous batching and PagedAttention. Default model: `meta-llama/Llama-3.2-1B` or equivalent small model that fits in VRAM.

2. **ChromaDB + knowledge base** — bundled into the worker Docker image. Performs vector similarity search on the incoming query to retrieve relevant context. No sync needed — knowledge base is static for the demo.

3. **Worker Agent (FastAPI)** — the wrapper service that:
   - Receives the raw query from master
   - Runs ChromaDB retrieval → builds enriched prompt
   - Calls vLLM for inference
   - Returns result + latency to master
   - Sends heartbeat to master every 2 seconds including GPU metrics
   - Self-registers with master on startup

4. **pynvml GPU metrics collector** — reads real hardware stats every heartbeat:
   - `gpu_util_pct` — current GPU compute utilization %
   - `vram_used_gb` / `vram_total_gb` — VRAM consumption
   - `gpu_temp_c` — GPU temperature
   - `ecc_errors` — ECC memory error count
   - `active_requests` — current in-flight vLLM requests

**Worker status states**: `HEALTHY` → `DRAINING` → `UNHEALTHY`

---

### NGINX

Reverse proxy sitting in front of the master. Handles:
- Connection pooling and keep-alive
- Rate limiting (prevents single clients from flooding)
- Load shedding when queue is full (returns 503 early)

Runs as a Docker container alongside the master on the developer's laptop.

---

### Scheduling Strategies

Five strategies, switchable live without restart via `POST /config/strategy`:

| Strategy | Logic |
|---|---|
| `round_robin` | Rotate through healthy workers in order |
| `least_active` | Pick worker with fewest active requests |
| `load_aware` | Weighted score of active requests + recent latency |
| `lowest_latency` | Pick worker with best average response time |
| `gpu_aware` | **New** — picks worker with most free VRAM and lowest GPU utilization |

The demo compares all five strategies under identical load to show measurable differences in GPU efficiency and latency.

---

### Fault Tolerance

**Reactive (heartbeat-based):**
- Workers send heartbeat every 2 seconds
- Master marks worker `UNHEALTHY` after 3 missed heartbeats (~6 seconds)
- In-flight tasks on a failed worker are retried on healthy workers (up to 3 retries)
- Recovered workers re-register automatically and re-enter the healthy pool

**Proactive (GPU health signals):**
- Workers include `gpu_temp_c` and `ecc_errors` in every heartbeat
- Master transitions worker to `DRAINING` when:
  - `gpu_temp_c > 85°C` (thermal throttling threshold)
  - `ecc_errors > 0` (memory integrity risk)
- `DRAINING` workers: accept no new tasks, complete active tasks, then return to `HEALTHY` once metrics normalise
- This prevents cascading failures from overheating nodes during heavy load

**Demo scenario**: Kill one Thunder Compute instance mid-load-test. Master detects within 6 seconds, retries tasks, cluster continues with 2 workers. Restart instance — it re-registers, rejoins pool.

---

### Observability

Prometheus scrapes metrics from master and all workers. Grafana dashboard shows:

- Per-worker GPU utilization % (real-time)
- Per-worker VRAM used / total
- Per-worker GPU temperature
- Cluster throughput (requests/sec)
- End-to-end latency (p50, p95, p99)
- Active requests per worker
- Worker health status (HEALTHY / DRAINING / UNHEALTHY)
- Strategy comparison panel (latency and GPU efficiency by strategy)

---

### Load Generator

Python script that simulates concurrent users sending inference requests:
- Ramp mode: 100 → 500 → 1000 concurrent users
- Burst mode: all users fire simultaneously
- Prints per-request: worker_id, latency, RAG sources, retry count
- Prints summary: success rate, throughput, p50/p95/p99 latency

---

## Worker Request Flow

```
1. Master receives query from client
2. Master selects worker via active strategy
3. Master POSTs raw query to worker /infer
4. Worker:
   a. ChromaDB similarity search → top-K context chunks
   b. Builds enriched prompt: [context] + [query]
   c. POSTs enriched prompt to local vLLM server
   d. vLLM runs GPU inference → token stream → response
   e. Worker returns: { result, latency_ms, rag_sources, gpu_util_pct, worker_id }
5. Master returns response to client
6. Parallel: worker sends heartbeat every 2s with GPU metrics
```

---

## Infrastructure

| Component | Where it runs | How |
|---|---|---|
| Master (FastAPI) | Developer laptop | `docker compose up` |
| NGINX | Developer laptop | `docker compose up` |
| Prometheus | Developer laptop | `docker compose up` |
| Grafana | Developer laptop | `docker compose up` |
| ngrok tunnel | Developer laptop | `ngrok http 8000` (one command) |
| Worker Agent | Thunder Compute instance | `docker run --gpus all ...` |
| vLLM server | Thunder Compute instance | `docker run --gpus all vllm/vllm-openai ...` |
| ChromaDB | Thunder Compute instance | embedded in worker Docker image |

---

## Project Structure (from scratch)

```
master/
  main.py              FastAPI app, routes
  scheduler.py         Strategy selection + task dispatch
  registry.py          Worker registration + state
  health_monitor.py    Heartbeat tracking + draining logic
  strategies/
    base.py
    round_robin.py
    least_active.py
    load_aware.py
    lowest_latency.py
    gpu_aware.py        ← new
  routers/
    client.py           POST /infer
    workers.py          POST /register, POST /heartbeat
    config.py           POST /config/strategy
    monitoring.py       GET /metrics, GET /workers, GET /health

worker/
  main.py              FastAPI app
  agent.py             Registration + heartbeat loop
  inference.py         vLLM client calls
  rag.py               ChromaDB retrieval + prompt building
  gpu_metrics.py       pynvml collection  ← new
  state.py             Worker state management

common/
  models.py            Shared Pydantic models
  enums.py             WorkerStatus, StrategyType

rag/
  knowledge_base/      .txt documents bundled into worker image

monitoring/
  prometheus.yml
  grafana/             Dashboard JSON

client/
  load_generator.py    Concurrent user simulation
  queries.txt          Sample queries

docker-compose.yml           master + nginx + prometheus + grafana
docker-compose.worker.yml    worker agent + vllm
scripts/
  scenario.sh          One-command demo runner
```

---

## What's Different from the Old System

| Aspect | Old system | New system |
|---|---|---|
| Workers | Student laptops on LAN | Thunder Compute GPU instances |
| Inference | Ollama (dev tool) | vLLM (production GPU server) |
| RAG | On master | On each worker |
| GPU metrics | None / simulated | Real (pynvml) |
| Fault tolerance | Heartbeat + retry | + Proactive draining on GPU health signals |
| Scheduling | 4 strategies | 5 strategies (+ gpu_aware) |
| Networking | LAN (same network) | Internet via ngrok tunnel |

---

## Demo Checklist

- [ ] `ngrok http 8000` running on laptop
- [ ] 3 Thunder Compute GPU instances started
- [ ] Workers registered: `GET /workers` shows 3 healthy nodes
- [ ] Grafana dashboard open: GPU util and VRAM panels live
- [ ] Run load test: `scenario.sh load-pdf` (100 → 500 → 1000 users)
- [ ] Switch strategies live: `scenario.sh strategy gpu_aware`
- [ ] Kill one worker mid-test — show recovery in Grafana
- [ ] Restart killed worker — show re-registration
- [ ] Show strategy comparison chart
