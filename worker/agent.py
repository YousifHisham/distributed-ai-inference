from __future__ import annotations
import asyncio
import socket
import time
import uuid
import httpx
from common.logging_config import setup_logging

logger = setup_logging("worker.agent")

_RETRY_DELAYS = [1, 2, 4, 8, 16, 30]


def _detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class WorkerAgent:
    def __init__(
        self,
        master_http_url: str,
        ollama_client,
        metrics_collector,
        model_name: str,
        heartbeat_interval: float,
        worker_http_port: int = 8001,
        advertise_host: str | None = None,
    ):
        self.master_http_url = master_http_url.rstrip("/")
        self.ollama = ollama_client
        self.collector = metrics_collector
        self.model_name = model_name
        self.heartbeat_interval = heartbeat_interval
        self.worker_http_port = worker_http_port
        self._client: httpx.AsyncClient | None = None

        hostname = socket.gethostname()
        self.node_id = f"{hostname}-{uuid.uuid4().hex[:8]}"
        self.ip_address = advertise_host or _detect_lan_ip()

        self._total_completed = 0
        self._total_failed = 0
        self._latency_samples: list[float] = []
        self._active_requests = 0

    def _avg_latency(self) -> float:
        if not self._latency_samples:
            return 0.0
        return sum(self._latency_samples[-50:]) / len(self._latency_samples[-50:])

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10)
        return self._client

    def _url(self, path: str) -> str:
        return f"{self.master_http_url}{path}"

    async def _post(self, endpoint: str, payload: dict):
        client = await self._get_client()
        return await client.post(self._url(endpoint), json=payload)

    async def _reset_client(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def register_with_master(self):
        import psutil
        cpu_count = psutil.cpu_count(logical=True) or 1
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        ollama_healthy = await self.ollama.health_check()

        reg = {
            "node_id": self.node_id,
            "hostname": socket.gethostname(),
            "ip_address": self.ip_address,
            "port": self.worker_http_port,
            "model_name": self.model_name,
            "cpu_count": cpu_count,
            "ram_gb": ram_gb,
            "gpu_available": self.collector.get_gpu_pct() >= 0,
            "gpu_name": "",
            "ollama_healthy": ollama_healthy,
        }

        for attempt, delay in enumerate(_RETRY_DELAYS, 1):
            try:
                resp = await self._post("/workers/register", reg)
                resp.raise_for_status()
                data = resp.json()
                logger.info(f"Registered as {self.node_id} (status={data.get('status')})")
                return
            except Exception as e:
                logger.warning(f"Registration attempt {attempt} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                await self._reset_client()
        logger.error("Failed to register with master after all retries")

    async def heartbeat_loop(self):
        logger.info(f"Heartbeat loop started (interval={self.heartbeat_interval}s)")
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                ollama_healthy = await self.ollama.health_check()
                hb = {
                    "node_id": self.node_id,
                    "timestamp": time.time(),
                    "status": "healthy" if ollama_healthy else "unhealthy",
                    "active_requests": self._active_requests,
                    "queue_size": 0,
                    "cpu_pct": self.collector.get_cpu_pct(),
                    "ram_pct": self.collector.get_ram_pct(),
                    "gpu_pct": self.collector.get_gpu_pct(),
                    "ollama_healthy": ollama_healthy,
                    "avg_latency": self._avg_latency(),
                }
                resp = await self._post("/workers/heartbeat", hb)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "re_register":
                    logger.warning("Master requested re-registration")
                    await self.register_with_master()
            except asyncio.CancelledError:
                logger.info("Heartbeat loop stopped")
                break
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                await self._reset_client()

    async def deregister(self):
        try:
            resp = await self._post("/workers/deregister", {"node_id": self.node_id})
            resp.raise_for_status()
            logger.info(f"Deregistered {self.node_id}")
        except Exception as e:
            logger.warning(f"Deregister failed (proceeding anyway): {e}")
        finally:
            await self._reset_client()

    async def infer(self, request_id: str, query: str, timeout: float):
        self._active_requests += 1
        start = time.time()
        try:
            result = await asyncio.wait_for(
                self.ollama.generate(query, self.model_name, timeout),
                timeout=timeout,
            )
            latency = time.time() - start
            self.record_inference(latency, success=True)
            return {
                "request_id": request_id,
                "result": result,
                "inference_time": latency,
                "worker_id": self.node_id,
                "error": "",
            }
        except asyncio.TimeoutError:
            self.record_inference(time.time() - start, success=False)
            return {
                "request_id": request_id,
                "error": "inference_timeout",
                "worker_id": self.node_id,
            }
        except Exception as e:
            self.record_inference(time.time() - start, success=False)
            logger.error(f"Ollama error for request {request_id}: {e}")
            return {
                "request_id": request_id,
                "error": "ollama_error",
                "worker_id": self.node_id,
            }
        finally:
            self._active_requests -= 1

    def record_inference(self, latency: float, success: bool):
        if success:
            self._total_completed += 1
            self._latency_samples.append(latency)
        else:
            self._total_failed += 1
