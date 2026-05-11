# Implementation Plan: GPU Cluster Distributed AI Inference System

**Branch**: `003-gpu-node-dev` | **Date**: 2026-05-11 | **Spec**: `specs/003-gpu-node-dev/spec.md`
**Input**: Feature specification from `specs/003-gpu-node-dev/spec.md`

## Summary

Build a distributed LLM inference system with a FastAPI master node (runs locally via Docker Compose) dispatching requests to three GPU worker nodes on Thunder Compute instances. Workers run vLLM + ChromaDB + pynvml and report real GPU metrics every 2 seconds. The master implements five live-switchable scheduling strategies and proactive fault tolerance via draining states triggered by GPU health signals. All components are containerized; a Python load generator drives the demo.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI 0.111, uvicorn, httpx (async HTTP), vLLM 0.4+ (workers only), chromadb 0.5+, sentence-transformers (`all-MiniLM-L6-v2`), pynvml, prometheus-client  
**Storage**: ChromaDB embedded (per-worker, static knowledge base); in-memory worker registry on master (no persistence required)  
**Testing**: pytest 8, pytest-asyncio, httpx AsyncClient  
**Target Platform**: Linux Docker containers — master stack on macOS via Docker Desktop; workers on Thunder Compute Ubuntu 22.04 GPU instances (CUDA 12+)  
**Project Type**: distributed web-service (master-worker topology)  
**Performance Goals**: sustain 100–1,000 concurrent inference requests; record p50/p95/p99 latency per strategy; real-time GPU utilization visible in Grafana  
**Constraints**: fault detection ≤ 6 seconds; zero simulated GPU metrics (all via pynvml); cloud budget ~$20 (Thunder Compute ~$0.50–1.00/hr × 3 nodes)  
**Scale/Scope**: 3 GPU worker nodes, 1 master node, 1 static knowledge base

## Constitution Check

*The project constitution is a template with no ratified principles. No gates apply.*

**Gate status**: PASS (no active gates)

**Post-design re-check**: PASS — design does not introduce complexity that would require justification under any standard constitutional principle.

## Project Structure

### Documentation (this feature)

```text
specs/003-gpu-node-dev/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── master-api.md    # Phase 1 output
│   └── worker-api.md    # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
master/
├── main.py              FastAPI app, lifespan, route mounting
├── scheduler.py         Strategy selection + async dispatch + retry (up to 3)
├── registry.py          Worker registration, state machine, heartbeat tracking
├── health_monitor.py    Background task: heartbeat timeout detection, draining logic
├── requirements.txt
├── Dockerfile
├── strategies/
│   ├── base.py          Abstract base: select_worker(workers) -> WorkerNode
│   ├── round_robin.py
│   ├── least_active.py
│   ├── load_aware.py
│   ├── lowest_latency.py
│   └── gpu_aware.py
└── routers/
    ├── client.py        POST /infer
    ├── workers.py       POST /workers/register, POST /workers/heartbeat
    ├── config.py        POST /config/strategy
    └── monitoring.py    GET /metrics, GET /workers, GET /health

worker/
├── main.py              FastAPI app, lifespan
├── agent.py             Self-registration + async heartbeat loop (2s interval)
├── inference.py         httpx calls to local vLLM OpenAI-compatible endpoint
├── rag.py               ChromaDB similarity search + prompt enrichment
├── gpu_metrics.py       pynvml collection; falls back to zeros if MOCK_GPU=true
├── state.py             WorkerStatus state machine
├── requirements.txt
└── Dockerfile

common/
├── models.py            Pydantic v2 models shared by master and worker
└── enums.py             WorkerStatus, StrategyType

rag/
└── knowledge_base/      Static .txt documents bundled into worker Docker image

monitoring/
├── prometheus.yml       Scrape config (master + 3 workers)
└── grafana/             Dashboard JSON + provisioning

client/
├── load_generator.py    asyncio + httpx semaphore-based concurrency; ramp + burst modes
└── queries.txt          Sample inference queries

scripts/
└── scenario.sh          One-command demo runner

docker-compose.yml           master + nginx + prometheus + grafana
docker-compose.worker.yml    worker-agent (--gpus all)
nginx.conf

tests/
├── unit/
│   ├── test_strategies.py
│   └── test_registry.py
└── integration/
    ├── test_master_rest.py
    └── test_fault_tolerance.py
```

**Structure Decision**: Master-worker split. `common/` is shared via `PYTHONPATH`. Workers run on separate hosts; Docker Compose manages the master stack locally. No monorepo tooling needed.

## Complexity Tracking

> No constitution violations.
