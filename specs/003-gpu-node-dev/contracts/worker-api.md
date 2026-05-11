# Worker Node API Contract

**Service**: Worker Agent (FastAPI)  
**Runs on**: Thunder Compute GPU instance  
**Exposed on**: Port 8001 (reachable from master via ngrok tunnel URL)  
**Phase 1 output for**: `003-gpu-node-dev`

---

## Inference Endpoint

### POST /infer

Called by the master to dispatch a raw query to this worker. The worker performs ChromaDB retrieval to enrich the query, calls the local vLLM server for inference, and returns the result.

**Request**:
```json
{
  "query": "string (1–4096 chars, required)",
  "request_id": "uuid"
}
```

**Response 200**:
```json
{
  "result": "string",
  "latency_ms": 312.5,
  "rag_sources": ["knowledge_base/chunk_42", "knowledge_base/chunk_17"],
  "gpu_util_pct": 82.0,
  "worker_id": "uuid"
}
```

**Error responses**:
| Code | Condition |
|---|---|
| 400 | Query is empty or malformed |
| 503 | Worker is in DRAINING state (master should not send here; included for safety) |
| 502 | Local vLLM server is unreachable |
| 504 | vLLM inference timed out (> 30 seconds) |

**Processing flow**:
1. Receive raw query from master
2. Embed query using sentence-transformers (`all-MiniLM-L6-v2`)
3. Query ChromaDB collection for top-3 most similar knowledge chunks
4. Build enriched prompt: `"Context:\n{chunks}\n\nQuestion: {query}\n\nAnswer:"`
5. POST enriched prompt to local vLLM at `http://localhost:9000/v1/chat/completions`
6. Record latency from step 1 to response
7. Return result + metadata to master

---

## Health Endpoint

### GET /health

Called by the master as a liveness check (separate from heartbeat mechanism).

**Response 200**:
```json
{
  "status": "ok",
  "worker_id": "uuid",
  "worker_status": "HEALTHY"
}
```

**Response 503** (if worker is UNHEALTHY):
```json
{
  "status": "unhealthy",
  "worker_id": "uuid",
  "worker_status": "UNHEALTHY"
}
```

---

## Worker Startup Behaviour (not an endpoint)

On startup, the worker agent performs the following sequence before accepting requests:

1. Initialize ChromaDB: load all `.txt` files from `rag/knowledge_base/`, chunk them, embed with `all-MiniLM-L6-v2`, upsert into ChromaDB collection `"knowledge"`
2. Initialize pynvml (or set `MOCK_GPU=true` fallback)
3. Wait for local vLLM server to become healthy (poll `http://localhost:9000/health` every 2s, timeout 120s)
4. POST to `{MASTER_URL}/workers/register` with `worker_url` and `gpu_total_vram_gb`
5. Store assigned `worker_id` from registration response
6. Start background heartbeat loop: every 2 seconds, collect GPU metrics and POST to `{MASTER_URL}/workers/heartbeat`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `MASTER_URL` | Yes | ngrok tunnel URL of the master (e.g., `https://abc123.ngrok-free.app`) |
| `WORKER_PORT` | No | Port for worker agent (default: `8001`) |
| `VLLM_URL` | No | URL of local vLLM server (default: `http://localhost:9000`) |
| `MOCK_GPU` | No | Set to `true` to skip pynvml (returns zero metrics); used for dev/testing |
| `HUGGING_FACE_HUB_TOKEN` | If model is gated | HF token for downloading gated models via vLLM |
