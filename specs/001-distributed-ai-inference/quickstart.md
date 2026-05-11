# Quickstart: Distributed AI Inference Platform

## Prerequisites

**All laptops:**
- Docker Desktop (Mac/Windows) or Docker Engine (Linux)
- Ollama installed natively: https://ollama.com/download
- Same LAN (Wi-Fi or Ethernet)

**One laptop (Master):**
- Know its LAN IP (e.g., `192.168.1.10`) — run `ipconfig getifaddr en0` on Mac

---

## Step 1: Start Ollama on each Worker laptop

```bash
# Pull the model (one-time, ~1GB)
ollama pull llama3.2:1b

# Start Ollama (if not already running as a service)
ollama serve
```

Verify: `curl http://localhost:11434/` should return `Ollama is running`.

---

## Step 2: Start the Master

On the designated Master laptop:

```bash
docker compose up master
```

Or without compose:

```bash
docker run -d \
  -p 8000:8000 \
  -e SCHEDULING_STRATEGY=load_aware \
  -e MAX_RETRIES=3 \
  -e TASK_TIMEOUT=120 \
  -e HEARTBEAT_TIMEOUT=15 \
  --name master \
  distributed-ai-master
```

Verify: `curl http://localhost:8000/health` → `{"status": "ok"}`

---

## Step 3: Start a Worker Agent on each laptop

On each worker laptop (replace `192.168.1.10` with actual Master LAN IP):

**macOS / Windows (Docker Desktop):**
```bash
docker run -d \
  -p 8001:8001 \
  -e MASTER_HTTP_URL=http://192.168.1.10:8000 \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -e WORKER_MODEL=llama3.2:1b \
  -e WORKER_MAX_CONCURRENT=4 \
  --name worker-agent \
  distributed-ai-worker
```

**Linux:**
```bash
docker run -d \
  --network=host \
  -e MASTER_HTTP_URL=http://192.168.1.10:8000 \
  -e OLLAMA_URL=http://localhost:11434 \
  -e WORKER_MODEL=llama3.2:1b \
  -e WORKER_MAX_CONCURRENT=4 \
  --name worker-agent \
  distributed-ai-worker
```

The Worker Agent automatically registers with the Master on startup.

Verify on Master: `curl http://192.168.1.10:8000/workers` — new worker appears.

---

## Step 4: Open the Grafana Dashboard

Grafana starts automatically with the Master via docker-compose.

Open `http://192.168.1.10:3000` in any browser on the LAN.
- Default login: `admin` / `admin`
- The **Cluster Dashboard** loads automatically — no setup needed.

Prometheus is available at `http://192.168.1.10:9090` for raw metric queries.

---

## Step 5: Run the Load Generator

```bash
pip install httpx
python client/load_generator.py \
  --master http://192.168.1.10:8000 \
  --users 100 \
  --query-file client/queries.txt
```

Scale up:
```bash
python client/load_generator.py --master http://192.168.1.10:8000 --users 1000 --burst
```

---

## Step 6: Fault Tolerance Demo

1. Run load generator: `--users 500 --ramp 60`
2. While running, close Docker on one worker laptop (or `docker stop worker-agent`)
3. Watch dashboard: worker turns unhealthy, tasks retry on remaining workers
4. Restart worker agent on that laptop — it re-registers, turns healthy, receives new tasks

---

## Step 7: Benchmarking

```bash
python benchmark/run.py \
  --master http://192.168.1.10:8000 \
  --users 200 \
  --strategies round_robin least_active load_aware lowest_latency \
  --output benchmark/results/
```

Produces comparison charts in `benchmark/results/`.

---

## Environment Variable Reference

### Master
| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULING_STRATEGY` | `load_aware` | `round_robin`, `least_active`, `load_aware`, `lowest_latency` |
| `MAX_RETRIES` | `3` | Max task retry attempts |
| `TASK_TIMEOUT` | `120` | Seconds before a task times out |
| `HEARTBEAT_TIMEOUT` | `15` | Seconds of missed heartbeat before marking unhealthy |
| `MASTER_HTTP_PORT` | `8000` | REST API port |
| `MAX_QUEUE_SIZE` | `5000` | Max tasks in queue before rejecting new requests |

### Worker Agent
| Variable | Default | Description |
|----------|---------|-------------|
| `MASTER_HTTP_URL` | required | Master HTTP address (e.g., `http://192.168.1.10:8000`) |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Local Ollama URL |
| `WORKER_MODEL` | `llama3.2:1b` | Model name to use for inference |
| `WORKER_MAX_CONCURRENT` | `4` | Max simultaneous Ollama generations |
| `HEARTBEAT_INTERVAL` | `5` | Seconds between heartbeats |
| `WORKER_HTTP_PORT` | `8001` | Prometheus metrics and inference HTTP port |
