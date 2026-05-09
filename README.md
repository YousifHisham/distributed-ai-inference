# Distributed AI Inference Orchestration Platform

CSE354 Distributed Computing — Ain Shams University, Semester 2 2025/2026

A production-style distributed system that routes 1000+ concurrent LLM inference requests across multiple worker laptops on a LAN. Demonstrates distributed scheduling, fault tolerance, gRPC cluster communication, and Prometheus/Grafana observability.

## Architecture

```
Client Load Generator
        ↓  REST
   Master Gateway (FastAPI + gRPC server, port 8000/50051)
        ↓  gRPC
Worker Agent laptops (gRPC server, port 50052)
        ↓  HTTP localhost
    Ollama (native, port 11434)
        ↑
Prometheus → Grafana (docker-compose, ports 9090/3000)
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
# Find your LAN IP
ipconfig getifaddr en0        # macOS
hostname -I | awk '{print $1}'  # Linux

# Start Master + Prometheus + Grafana
docker compose up --build
```

Verify: `curl http://localhost:8000/health` → `{"status": "ok"}`

### Step 3 — Join worker laptops

Replace `192.168.1.10` with your Master's LAN IP.

**macOS / Windows:**
```bash
docker run -d \
  -p 8001:8001 -p 50052:50052 \
  -e MASTER_GRPC_URL=192.168.1.10:50051 \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e WORKER_MODEL=llama3.2:1b \
  -e WORKER_MAX_CONCURRENT=4 \
  --name worker-agent \
  distributed-ai-worker
```

**Linux:**
```bash
docker run -d --network=host \
  -e MASTER_GRPC_URL=192.168.1.10:50051 \
  -e OLLAMA_URL=http://localhost:11434 \
  -e WORKER_MODEL=llama3.2:1b \
  -e WORKER_MAX_CONCURRENT=4 \
  --name worker-agent \
  distributed-ai-worker
```

Verify: `curl http://192.168.1.10:8000/workers` — new worker appears.

### Step 4 — Open Grafana Dashboard

`http://192.168.1.10:3000` → Login: admin / admin → **Cluster Dashboard** auto-loads.

### Step 5 — Run Load Test

```bash
pip3 install httpx
python3 client/load_generator.py --master http://192.168.1.10:8000 --users 100
python3 client/load_generator.py --master http://192.168.1.10:8000 --users 1000 --burst
```

## Fault Tolerance Demo

1. Start Master + 3 workers + load generator (`--users 500 --ramp 60`)
2. While running: `docker stop worker-agent` on one worker laptop
3. Master detects failure within 15s — in-flight tasks retry on healthy workers
4. Restart: `docker start worker-agent` — worker re-registers, rejoins cluster
5. Watch all events live in Grafana

## Scheduling Strategies

Switch strategy live (no restart needed):

```bash
curl -X POST http://master:8000/config/strategy \
  -H "Content-Type: application/json" \
  -d '{"strategy": "round_robin"}'
```

Strategies: `round_robin` · `least_active` · `load_aware` · `lowest_latency`

## Benchmarking

```bash
pip3 install matplotlib httpx
python3 benchmark/run.py \
  --master http://192.168.1.10:8000 \
  --users 50 \
  --strategies round_robin least_active load_aware lowest_latency \
  --output benchmark/results/
```

Produces `benchmark/results/throughput.png`, `latency.png`, `success_rate.png`, `summary.csv`.

## Running Tests

```bash
pip3 install -r master/requirements.txt
python3 -m pytest tests/ -v
```

**49 tests** — unit tests for registry, task queue, and all 4 strategies + integration tests for fault tolerance and REST API.

## Environment Variables

| Variable | Default | Service |
|----------|---------|---------|
| `SCHEDULING_STRATEGY` | `load_aware` | Master |
| `MAX_RETRIES` | `3` | Master |
| `TASK_TIMEOUT` | `120` | Master |
| `HEARTBEAT_TIMEOUT` | `15` | Master |
| `MAX_QUEUE_SIZE` | `5000` | Master |
| `MASTER_GRPC_URL` | `localhost:50051` | Worker |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Worker |
| `WORKER_MODEL` | `llama3.2:1b` | Worker |
| `WORKER_MAX_CONCURRENT` | `4` | Worker |

## Project Structure

```
master/          FastAPI REST gateway + gRPC Master server + scheduler
worker/          gRPC Worker server + Ollama client + heartbeat agent
common/          Shared Pydantic models, enums, logging, gRPC stubs
client/          Async load generator (100–1000+ concurrent users)
benchmark/       Strategy comparison tool with matplotlib charts
monitoring/      Prometheus config + Grafana dashboard JSON
tests/           49 unit + integration tests
proto/           inference.proto (gRPC service definitions)
```
