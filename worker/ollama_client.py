import httpx
from common.logging_config import setup_logging

logger = setup_logging("worker.ollama")


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=None)

    async def generate(self, query: str, model: str, timeout: float) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {"model": model, "prompt": query, "stream": False}
        response = await self._client.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "")

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(self.base_url, timeout=3.0)
            return response.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self._client.aclose()
