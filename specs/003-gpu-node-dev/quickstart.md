# Quickstart: GPU Cluster Distributed AI Inference System

**Branch**: `003-gpu-node-dev`  
**Date**: 2026-05-11

---

## Prerequisites

- Docker Desktop running on your laptop
- ngrok account (free tier is sufficient)
- 3 Thunder Compute GPU instances provisioned (CUDA 12+, ≥ 24GB VRAM recommended)
- Hugging Face account with access to `meta-llama/Llama-3.2-1B` (or set `MODEL=Qwen/Qwen2.5-0.5B` for ungated)
- Python 3.11+ on your laptop (for the load generator)

---

## Step 1 — Start the Master Stack (laptop)

```bash
# Clone and enter the repo on your laptop
cd project-3/

# Copy and edit env file
cp .env.example .env
# Edit .env: set GRAFANA_PASSWORD, HF_TOKEN if needed

# Start master + nginx + prometheus + grafana
docker compose up --build -d

# Verify master is healthy
curl http://localhost:8000/health
# Expected: {"status": "ok", "healthy_workers": 0}
```

Grafana is available at `http://localhost:3000` (admin / your GRAFANA_PASSWORD).

---

## Step 2 — Expose Master via ngrok

```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL (e.g., `https://abc123.ngrok-free.app`). You'll use this as `MASTER_URL` for all workers.

---

## Step 3 — Start Workers on Thunder Compute

SSH into each Thunder Compute instance and run:

```bash
# Pull the worker image (or build from Dockerfile)
docker pull your-registry/worker:latest

# Start vLLM server (runs in background)
docker run -d --gpus all --name vllm \
  -p 9000:8000 \
  -e HUGGING_FACE_HUB_TOKEN=$HF_TOKEN \
  vllm/vllm-openai:latest \
  --model meta-llama/Llama-3.2-1B \
  --port 8000

# Wait ~60 seconds for model to load, then start worker agent
docker run -d --gpus all --name worker \
  -p 8001:8001 \
  -e MASTER_URL=https://abc123.ngrok-free.app \
  -e WORKER_PORT=8001 \
  -e VLLM_URL=http://localhost:9000 \
  your-registry/worker:latest
```

Repeat on all 3 instances. Workers self-register with the master on startup.

---

## Step 4 — Verify Cluster

```bash
# From your laptop
curl http://localhost:8000/workers
# Expected: 3 workers with status "HEALTHY"
```

Open Grafana (`http://localhost:3000`) — GPU utilization and VRAM panels should show live data.

---

## Step 5 — Run the Demo

```bash
# Full demo sequence (ramp load + strategy comparison + fault demo)
bash scripts/scenario.sh full-demo

# Or individual steps:
bash scripts/scenario.sh load-ramp          # 100 → 500 → 1000 users
bash scripts/scenario.sh strategy gpu_aware # Switch to gpu_aware strategy
bash scripts/scenario.sh kill-worker 1      # Kill worker 1 to demo fault tolerance
bash scripts/scenario.sh restart-worker 1   # Restart and show re-registration
bash scripts/scenario.sh strategy-compare   # Run all 5 strategies and print comparison
```

The load generator prints per-request results and a summary table to stdout.

---

## Step 6 — Tear Down

```bash
# Stop master stack
docker compose down

# On each Thunder Compute instance:
docker stop worker vllm && docker rm worker vllm
```

---

## Development / Local Testing (no GPU)

```bash
# Run master only, with mock worker
MOCK_GPU=true python -m uvicorn master.main:app --reload --port 8000

# Run worker locally (no vLLM, no real GPU)
MOCK_GPU=true MASTER_URL=http://localhost:8000 \
  python -m uvicorn worker.main:app --reload --port 8001

# Run tests
pytest tests/ -v
```

---

## Key URLs (local)

| Service | URL |
|---|---|
| Master API | `http://localhost:8000` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |
| NGINX (entry) | `http://localhost:80` |
