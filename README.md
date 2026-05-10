# Distributed AI Inference Orchestration Platform

CSE354 Distributed Computing — Ain Shams University, Semester 2 2025/2026

A production-style distributed system that routes 1000+ concurrent LLM inference requests across multiple worker laptops on a LAN. Demonstrates distributed scheduling, fault tolerance, HTTP-based cluster communication, nginx reverse proxying, and Prometheus/Grafana observability.

## Architecture

```
Client Load Generator
        ↓  REST
          NGINX reverse proxy
        ↓  HTTP
   Master Gateway (FastAPI, port 8000)
        ↓  HTTP
Worker Agent laptops (FastAPI server, port 8001)
        ↓  HTTP localhost
    Ollama (native, port 11434)
        ↑
Prometheus → Grafana (docker-compose, ports 9090/3000)

RAG runs on the master before scheduling: the master retrieves context from ChromaDB, builds an enhanced prompt, and sends that prompt to the selected worker.
```

## Quick Start

### Prerequisites

Every laptop needs:
- **Docker** (Docker Desktop on Mac/Windows, Docker Engine on Linux)
- **Ollama** installed natively: https://ollama.com/download

### Step 1 — Pull the model on each worker laptop

```bash
ollama pull llama3.2:1b
ollama serve          # if not already running as a service
```

### Step 2 — Start the Master (one laptop)

```bash
./scripts/scenario.sh master
```

Verify: `curl http://localhost:8000/health` → `{"status": "ok"}`

### Step 3 — Join worker laptops

Put the Master's LAN IP in `.env`:

```env
MASTER_HTTP_URL=http://192.168.1.10:8000
```

Then start a worker:

```bash
./scripts/scenario.sh worker
```

You can still override the master for a one-off run: `./scripts/run-worker.sh 192.168.1.10`.

Verify: `curl http://192.168.1.10:8000/workers` — new worker appears.

### Step 4 — Check the cluster output

```bash
./scripts/scenario.sh status
```

Expected shape:

```text
Master health:
{"status":"ok"}

Registered workers:
{"workers":[...]}
```

### Step 5 — Send a RAG inference request

```bash
./scripts/scenario.sh rag
```

Expected shape:

```json
{
  "request_id": "...",
  "result": "...",
  "worker_id": "...",
  "retry_count": 0,
  "rag_sources": ["distributed_systems.txt", "..."]
}
```

### Optional — Configure `.env`

Docker Compose reads `.env` automatically. Copy the template once:

```bash
cp .env.example .env
```

For this one-master setup, set `MASTER_HTTP_URL` once in `.env`. Worker laptops read that value automatically, and the worker script auto-detects `WORKER_ADVERTISE_HOST`. You usually only edit the worker settings if you want a different model:

```bash
MASTER_HTTP_URL=http://192.168.1.10:8000
WORKER_MODEL=llama3.2:1b
```

### Step 6 — Open Grafana Dashboard

`http://192.168.1.10:3000` → Login: admin / admin → **Cluster Dashboard** auto-loads.

### Step 7 — Run Load Test

```bash
./scripts/scenario.sh load-pdf
```

This runs the project-PDF load levels: `100`, `500`, and `1000` concurrent users. It prints each completed request with the selected worker, latency, retries, and RAG sources, then prints total success rate, throughput, and latency summaries.

For a smaller rehearsal:

```bash
python3 scripts/send-project-requests.py --levels 10 25 50 --burst
```

Or use:

```bash
./scripts/scenario.sh load-small
```

## Fault Tolerance Demo

1. Start Master + 3 workers + load generator (`./scripts/scenario.sh fault-load`)
2. Watch cluster status: `./scripts/scenario.sh fault-watch`
3. While running, stop one worker laptop: `./scripts/scenario.sh fault-down 10`
4. Master detects failure in about 6-7s — in-flight tasks retry on healthy workers
5. Restart: `./scripts/scenario.sh start-worker` — worker re-registers, rejoins cluster
6. Watch all events live in Grafana

To stop and restart the worker automatically:

```bash
./scripts/scenario.sh fault-restart 10 15
```

## Scheduling Strategies

Switch strategy live (no restart needed):

```bash
curl -X POST http://master:8000/config/strategy \
  -H "Content-Type: application/json" \
  -d '{"strategy": "round_robin"}'
```

Strategies: `round_robin` · `least_active` · `load_aware` · `lowest_latency`

Script form:

```bash
./scripts/scenario.sh strategy round_robin
./scripts/scenario.sh strategies
```

## Environment Variables

| Variable | Default | Service |
|----------|---------|---------|
| `SCHEDULING_STRATEGY` | `load_aware` | Master |
| `MAX_RETRIES` | `3` | Master |
| `TASK_TIMEOUT` | `120` | Master |
| `HEARTBEAT_TIMEOUT` | `6` | Master |
| `HEALTH_CHECK_INTERVAL` | `1` | Master |
| `MAX_QUEUE_SIZE` | `5000` | Master |
| `RAG_ENABLED` | `true` | Master |
| `RAG_TOP_K` | `3` | Master |
| `RAG_DOCS_DIR` | `rag/knowledge_base` | Master |
| `RAG_DB_DIR` | `.chroma` | Master |
| `MASTER_HTTP_URL` | `http://localhost:8000` | Worker |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Worker |
| `WORKER_MODEL` | `llama3.2:1b` | Worker |
| `HEARTBEAT_INTERVAL` | `2` | Worker |

## Project Structure

```
master/          FastAPI REST gateway + HTTP scheduler + worker registration API
worker/          FastAPI worker HTTP server + Ollama client + heartbeat agent
common/          Shared Pydantic models, enums, logging utilities
rag/             ChromaDB-backed knowledge retrieval and seed documents
client/          Prompt/query set used by scenario scripts
monitoring/      Prometheus config + Grafana dashboard JSON
scripts/         One-command demo and scenario runners
```
