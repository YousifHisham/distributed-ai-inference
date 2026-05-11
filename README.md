# Distributed AI Inference Orchestration Platform

CSE354 Distributed Computing — Ain Shams University, Semester 2 2025/2026

A distributed system that routes LLM inference requests across multiple GPU worker nodes. The master node runs locally on your Mac via Docker and dispatches requests to GPU workers on Thunder Compute instances. Includes 5 live-switchable scheduling strategies, RAG-augmented inference, fault tolerance, and Prometheus/Grafana monitoring.

## Architecture

```
Client / Load Generator
        ↓
   NGINX (port 8000, Docker on Mac)
        ↓
  Master Node (FastAPI, Docker on Mac)
        ↓  HTTP via ngrok tunnel
  Worker Nodes (FastAPI on Thunder Compute GPU instances)
        ↓  localhost
    Ollama :11434 (llama3.2:1b)

Prometheus → Grafana (Docker on Mac, ports 9090/3000)
```

---

## Prerequisites

- **Mac**: Docker Desktop running
- **Mac**: ngrok installed (`pip3 install ngrok` or download from ngrok.com)
- **Mac**: Python 3.11+
- **Thunder Compute account**: thundercompute.com
- **Thunder Compute CLI**: `pip3 install thundercompute` then `tnr login`

---

## Part 1 — Start the Master Stack (Mac)

```bash
cd "path/to/project-3"

# Copy env file (only needed once)
cp .env.example .env

# Start master + nginx + prometheus + grafana
docker compose up --build -d

# Verify master is healthy
curl http://localhost:8000/health
# Expected: {"status": "ok", "healthy_workers": 0}
```

Grafana: `http://localhost:3000` (admin / admin)
Prometheus: `http://localhost:9090`

---

## Part 2 — Expose Master via ngrok

In a separate terminal, keep this running the entire time:

```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL, e.g.:
```
https://yeast-spokesman-taekwondo.ngrok-free.dev
```

You will use this as `MASTER_HTTP_URL` for all workers.

---

## Part 3 — Create GPU Instances on Thunder Compute

Go to console.thundercompute.com → **+ Create** (repeat 3 times):

| Setting | Value |
|---|---|
| GPU Type | RTX A6000 |
| Count | 1 GPU |
| CPU | 4 vCPUs / 32GB RAM |
| Storage | 100GB |
| Mode | Prototyping ($0.35/hr) |

Wait for all 3 to show **Running** in `tnr status`.

---

## Part 4 — Set Up Each GPU Instance

Open **3 terminal tabs** on your Mac. In each tab connect to one instance:

```bash
tnr connect 0   # Tab 1
tnr connect 1   # Tab 2
tnr connect 2   # Tab 3
```

Run these commands **inside each instance**:

### 4a — Install Ollama and pull model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2:1b
```

Verify Ollama is running:
```bash
curl http://localhost:11434/api/version
# Expected: {"version":"..."}
```

### 4b — Clone the repo and install dependencies

```bash
git clone -b 003-gpu-node-dev https://github.com/YousifHisham/distributed-ai-inference.git project3
cd project3
pip install -r worker/requirements.txt
```

### 4c — Start the worker

Replace the ngrok URL with your actual URL:

```bash
INSTANCE_IP=$(curl -s ifconfig.me)

MASTER_HTTP_URL=https://YOUR-NGROK-URL.ngrok-free.dev \
WORKER_ADVERTISE_HOST=$INSTANCE_IP \
WORKER_HTTP_PORT=8001 \
OLLAMA_URL=http://localhost:11434 \
WORKER_MODEL=llama3.2:1b \
HEARTBEAT_INTERVAL=2 \
python3 -m uvicorn worker.main:app --host 0.0.0.0 --port 8001
```

You should see:
```
Registered with master — worker_id=...
HTTP Request: POST https://YOUR-NGROK-URL.../workers/heartbeat "HTTP/1.1 200 OK"
```

---

## Part 5 — Verify the Cluster

On your Mac:

```bash
curl http://localhost:8000/workers | python3 -m json.tool
```

Expected: 3 workers with `"status": "HEALTHY"`.

---

## Part 6 — Run Inference

```bash
# Single request
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"query": "What is a distributed system?"}'
```

---

## Part 7 — Switch Scheduling Strategy

```bash
curl -X POST http://localhost:8000/config/strategy \
  -H "Content-Type: application/json" \
  -d '{"strategy": "round_robin"}'
```

Available strategies: `round_robin` · `least_active` · `load_aware` · `lowest_latency` · `gpu_aware`

---

## Part 8 — Run the Demo Scenarios

```bash
# Check cluster status
./scripts/scenario.sh status

# Send a RAG inference request
./scripts/scenario.sh rag

# Load test (small)
./scripts/scenario.sh load-small

# Load test (PDF levels: 100, 500, 1000 users)
./scripts/scenario.sh load-pdf

# Compare all strategies
./scripts/scenario.sh strategies

# Fault tolerance demo
./scripts/scenario.sh fault-watch   # watch health in one terminal
./scripts/scenario.sh fault-down 10 # kill worker after 10s in another
```

---

## Part 9 — Tear Down

**Stop instances when done — they cost $0.35/hr each.**

```bash
# On each Thunder Compute instance: Ctrl+C to stop the worker

# Stop master stack on Mac
docker compose down

# Stop ngrok: Ctrl+C in its terminal

# Stop Thunder Compute instances from the console or:
tnr status   # find instance IDs, then stop from console
```

---

## Local Development (no GPU, no Thunder Compute)

Run everything on your Mac with `MOCK_GPU=true`:

```bash
# Terminal 1: start Ollama
ollama serve

# Terminal 2: start master
docker compose up --build -d

# Terminal 3: start a local worker
MOCK_GPU=true \
MASTER_HTTP_URL=http://localhost:8000 \
WORKER_ADVERTISE_HOST=127.0.0.1 \
WORKER_HTTP_PORT=8001 \
OLLAMA_URL=http://localhost:11434 \
WORKER_MODEL=llama3.2:1b \
HEARTBEAT_INTERVAL=2 \
python3 -m uvicorn worker.main:app --host 0.0.0.0 --port 8001
```

Run tests:
```bash
pip install pytest pytest-asyncio httpx
pytest tests/unit/ -v
pytest tests/integration/ -v   # requires master running
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MASTER_HTTP_URL` | `http://localhost:8000` | Worker → Master URL (use ngrok URL for remote workers) |
| `WORKER_ADVERTISE_HOST` | *(auto)* | IP master uses to reach back to this worker |
| `WORKER_HTTP_PORT` | `8001` | Worker listen port |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint on worker machine |
| `WORKER_MODEL` | `llama3.2:1b` | Model name to use for inference |
| `HEARTBEAT_INTERVAL` | `2` | Seconds between worker heartbeats |
| `HEARTBEAT_TIMEOUT` | `6` | Seconds before master marks worker unhealthy |
| `SCHEDULING_STRATEGY` | `load_aware` | Initial strategy on master startup |
| `MAX_RETRIES` | `3` | Retry attempts per request |
| `MOCK_GPU` | `false` | Set `true` to skip pynvml GPU collection |

---

## Project Structure

```
master/          FastAPI gateway, scheduler, worker registry, health monitor
worker/          FastAPI worker server, Ollama client, RAG, GPU metrics, heartbeat
common/          Shared Pydantic models and enums
rag/             Knowledge base documents + ChromaDB initialization
client/          Load generator
monitoring/      Prometheus config + Grafana dashboard JSON
scripts/         Demo and scenario runner scripts
docker-compose.yml          Master stack (Mac)
docker-compose.worker.yml   Worker container (GPU instances)
```
