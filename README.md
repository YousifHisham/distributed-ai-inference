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

# How to Run Our Project

## Quick Start

### Prerequisites

Every participating laptop in the cluster requires:
- **Docker** (Docker Desktop on Mac/Windows, Docker Engine on Linux)
- **Ollama** installed natively: https://ollama.com/download

### Step 1 — Pull the Model on Each Worker Laptop

```bash
ollama pull llama3.2:1b
ollama serve          # Run this if Ollama is not already running as a background service
```

### Step 2 — Start the Master Node (one laptop)

```bash
./scripts/scenario.sh master
```

Verify: `curl http://localhost:8000/health` and expect `{"status": "ok"}`

### Step 3 — Configure and Join Worker Laptops

Workers need to know where the Master is located on the LAN. On each worker laptop, configure the `.env` file with the Master's IP address:
```env
cp .env.example .env
```

```env
MASTER_HTTP_URL=http://192.168.1.10:8000
WORKER_MODEL=llama3.2:1b
```

Then start a worker node:

```bash
./scripts/scenario.sh worker
```

You can still override the master for a one-off run: `./scripts/run-worker.sh 192.168.1.10`.

Verify: Check the Master node by running `curl http://192.168.1.10:8000/workers` to ensure the new worker appears in the registry.

### Step 4 — Check the Cluster Output

Check the overarching health of the Master and registered workers:

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

### Step 5 — Send a RAG Inference Request

Test the Retrieval-Augmented Generation pipeline:

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

### Step 6 — Monitor via Grafana Dashboard

Navigate to `http://192.168.1.10:3000` on any browser in the network → Login: admin / admin → **Cluster Dashboard** will automatically load, displaying real-time metrics.

### Step 7 — Execute Load Tests

To evaluate system performance under concurrency, run the automated load testing script for 100, 500, and 1000 users:

```bash
./scripts/scenario.sh load-pdf
```

This runs the project-PDF load levels: `100`, `500`, and `1000` concurrent users. It prints each completed request with the selected worker, latency, retries, and RAG sources, then prints total success rate, throughput, and latency summaries.

For a smaller rehearsal (10, 25, 50 users):


```bash
./scripts/scenario.sh load-small
```
Or use the Python script directly:

```bash
python3 scripts/send-project-requests.py --levels 10 25 50 --burst
```


## Fault Tolerance Demo

To demonstrate the system's ability to recover from node failures:

1. Start Master + 3 workers + load generator (`./scripts/scenario.sh fault-load`)
2. Watch cluster status: `./scripts/scenario.sh fault-watch`
3. While running, stop one worker laptop: `./scripts/scenario.sh fault-down 10`
4. The Master will detect the failure in ~6 seconds and automatically requeue in-flight tasks to healthy workers
5. Restart the downed node: `./scripts/scenario.sh start-worker`. It will re-register and rejoin the cluster seamlessly.
6. Watch all events live in Grafana.

Automated restart script:

```bash
./scripts/scenario.sh fault-restart 10 15
```

## Scheduling Strategies

You can hot-swap the load balancing strategy dynamically without restarting the cluster:

```bash
curl -X POST http://master:8000/config/strategy \
  -H "Content-Type: application/json" \
  -d '{"strategy": "round_robin"}'
```

Available Strategies: `round_robin` · `least_active` · `load_aware` · `lowest_latency`

Using provided scripts:

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
