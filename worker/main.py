import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request

from common.models import WorkerInferRequest, WorkerInferResponse
from worker.rag import init_rag, build_prompt
from worker.gpu_metrics import collect_gpu_metrics
from worker import agent
from worker import inference as infer_mod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_active_requests = 0
_draining = False


def get_active_requests() -> int:
    return _active_requests


async def _wait_for_ollama() -> None:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    async with httpx.AsyncClient() as client:
        for _ in range(60):
            try:
                resp = await client.get(f"{ollama_url}/api/version", timeout=3.0)
                if resp.status_code == 200:
                    logger.info("Ollama is healthy")
                    return
            except Exception:
                pass
            await asyncio.sleep(2)
    logger.warning("Ollama did not become healthy within 120s — proceeding anyway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _state
    docs_dir = os.getenv("RAG_DOCS_DIR", "rag/knowledge_base")
    init_rag(docs_dir)

    await _wait_for_ollama()

    http_client = httpx.AsyncClient(timeout=35.0)
    app.state.http_client = http_client

    await agent.register(http_client)
    await agent.start_heartbeat(http_client)

    yield

    await agent.stop_heartbeat()
    await infer_mod.close_client()
    await http_client.aclose()


app = FastAPI(title="Worker Agent", lifespan=lifespan)


@app.post("/infer", response_model=WorkerInferResponse)
async def infer(body: WorkerInferRequest, request: Request) -> WorkerInferResponse:
    global _active_requests

    if _draining:
        raise HTTPException(status_code=503, detail="worker is draining")

    _active_requests += 1
    start = time.monotonic()
    try:
        prompt, rag_sources = build_prompt(body.query)
        result = await infer_mod.run_inference(prompt)
        latency_ms = (time.monotonic() - start) * 1000

        metrics = collect_gpu_metrics()
        worker_id = agent.get_worker_id() or "unknown"

        return WorkerInferResponse(
            result=result,
            latency_ms=latency_ms,
            rag_sources=rag_sources,
            gpu_util_pct=metrics.gpu_util_pct,
            worker_id=worker_id,
        )
    finally:
        _active_requests -= 1


@app.get("/health")
async def health() -> dict:
    worker_id = agent.get_worker_id() or "unknown"
    return {"status": "ok", "worker_id": worker_id, "active_requests": _active_requests}
