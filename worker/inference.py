import logging
import os

import httpx

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def run_inference(prompt: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = os.getenv("WORKER_MODEL", "llama3.2:1b")
    url = f"{ollama_url}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    client = get_client()
    response = await client.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]
