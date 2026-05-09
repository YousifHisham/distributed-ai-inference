from __future__ import annotations
import asyncio
import socket
import time
import uuid
import grpc
from common.generated import inference_pb2, inference_pb2_grpc
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
        master_grpc_url: str,
        ollama_client,
        metrics_collector,
        model_name: str,
        max_concurrent: int,
        heartbeat_interval: float,
        grpc_port: int,
    ):
        self.master_grpc_url = master_grpc_url
        self.ollama = ollama_client
        self.collector = metrics_collector
        self.model_name = model_name
        self.max_concurrent = max_concurrent
        self.heartbeat_interval = heartbeat_interval
        self.grpc_port = grpc_port

        hostname = socket.gethostname()
        self.node_id = f"{hostname}-{uuid.uuid4().hex[:8]}"
        self.ip_address = _detect_lan_ip()

        self._channel: grpc.aio.Channel | None = None
        self._stub: inference_pb2_grpc.MasterServiceStub | None = None
        self._total_completed = 0
        self._total_failed = 0
        self._latency_samples: list[float] = []
        self._active_requests = 0

    def _avg_latency(self) -> float:
        if not self._latency_samples:
            return 0.0
        return sum(self._latency_samples[-50:]) / len(self._latency_samples[-50:])

    def _get_stub(self) -> inference_pb2_grpc.MasterServiceStub:
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.master_grpc_url)
            self._stub = inference_pb2_grpc.MasterServiceStub(self._channel)
        return self._stub

    async def register_with_master(self):
        import psutil
        cpu_count = psutil.cpu_count(logical=True) or 1
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        ollama_healthy = await self.ollama.health_check()

        reg = inference_pb2.WorkerRegistration(
            node_id=self.node_id,
            hostname=socket.gethostname(),
            ip_address=self.ip_address,
            port=self.grpc_port,
            model_name=self.model_name,
            max_concurrent=self.max_concurrent,
            cpu_count=cpu_count,
            ram_gb=ram_gb,
            gpu_available=self.collector.get_gpu_pct() >= 0,
            gpu_name="",
            ollama_healthy=ollama_healthy,
        )

        for attempt, delay in enumerate(_RETRY_DELAYS, 1):
            try:
                stub = self._get_stub()
                resp = await stub.Register(reg, timeout=10)
                logger.info(f"Registered as {self.node_id} (status={resp.status} strategy={resp.strategy})")
                return
            except Exception as e:
                logger.warning(f"Registration attempt {attempt} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
        logger.error("Failed to register with master after all retries")

    async def heartbeat_loop(self):
        logger.info(f"Heartbeat loop started (interval={self.heartbeat_interval}s)")
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                ollama_healthy = await self.ollama.health_check()
                hb = inference_pb2.Heartbeat(
                    node_id=self.node_id,
                    timestamp=time.time(),
                    status="healthy" if ollama_healthy else "unhealthy",
                    active_requests=self._active_requests,
                    queue_size=0,
                    cpu_pct=self.collector.get_cpu_pct(),
                    ram_pct=self.collector.get_ram_pct(),
                    gpu_pct=self.collector.get_gpu_pct(),
                    ollama_healthy=ollama_healthy,
                    avg_latency=self._avg_latency(),
                )
                stub = self._get_stub()
                resp = await stub.SendHeartbeat(hb, timeout=5)
                if resp.status == "re_register":
                    logger.warning("Master requested re-registration")
                    await self.register_with_master()
            except asyncio.CancelledError:
                logger.info("Heartbeat loop stopped")
                break
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                # Reset channel on connection failure
                if self._channel:
                    await self._channel.close()
                    self._channel = None
                    self._stub = None

    async def deregister(self):
        try:
            stub = self._get_stub()
            await stub.Deregister(
                inference_pb2.DeregisterRequest(node_id=self.node_id), timeout=5
            )
            logger.info(f"Deregistered {self.node_id}")
        except Exception as e:
            logger.warning(f"Deregister failed (proceeding anyway): {e}")
        finally:
            if self._channel:
                await self._channel.close()

    def record_inference(self, latency: float, success: bool):
        if success:
            self._total_completed += 1
            self._latency_samples.append(latency)
        else:
            self._total_failed += 1
