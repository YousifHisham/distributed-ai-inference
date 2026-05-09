import asyncio
import time
import grpc
from common.generated import inference_pb2, inference_pb2_grpc
from common.models import WorkerRegistration, Heartbeat
from common.enums import WorkerStatus
from common.logging_config import setup_logging

logger = setup_logging("master.grpc")


class MasterServicer(inference_pb2_grpc.MasterServiceServicer):
    def __init__(self, registry, scheduler):
        self.registry = registry
        self.scheduler = scheduler

    async def Register(self, request, context):
        reg = WorkerRegistration(
            node_id=request.node_id,
            hostname=request.hostname,
            ip_address=request.ip_address,
            port=request.port,
            model_name=request.model_name,
            max_concurrent=request.max_concurrent,
            cpu_count=request.cpu_count,
            ram_gb=request.ram_gb,
            gpu_available=request.gpu_available,
            gpu_name=request.gpu_name,
            ollama_healthy=request.ollama_healthy,
        )
        existing = self.registry.get(request.node_id)
        worker = await self.registry.register(reg)
        status = "updated" if existing else "registered"
        strategy = getattr(self.scheduler, "strategy_name", "load_aware")
        return inference_pb2.RegisterResponse(
            status=status,
            node_id=worker.node_id,
            strategy=strategy,
        )

    async def SendHeartbeat(self, request, context):
        hb = Heartbeat(
            node_id=request.node_id,
            timestamp=request.timestamp,
            status=WorkerStatus(request.status) if request.status else WorkerStatus.healthy,
            active_requests=request.active_requests,
            queue_size=request.queue_size,
            cpu_pct=request.cpu_pct,
            ram_pct=request.ram_pct,
            gpu_pct=request.gpu_pct,
            ollama_healthy=request.ollama_healthy,
            avg_latency=request.avg_latency,
        )
        worker = await self.registry.update_heartbeat(hb)
        if worker is None:
            return inference_pb2.HeartbeatResponse(status="re_register", server_time=time.time())
        return inference_pb2.HeartbeatResponse(status="ok", server_time=time.time())

    async def Deregister(self, request, context):
        worker = await self.registry.deregister(request.node_id)
        logger.info(f"Worker deregistered: {request.node_id}")
        return inference_pb2.DeregisterResponse(status="draining", node_id=request.node_id)


async def start_grpc_server(registry, scheduler, port: int):
    server = grpc.aio.server()
    inference_pb2_grpc.add_MasterServiceServicer_to_server(
        MasterServicer(registry, scheduler), server
    )
    server.add_insecure_port(f"0.0.0.0:{port}")
    await server.start()
    logger.info(f"Master gRPC server listening on port {port}")
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await server.stop(grace=5)
        logger.info("Master gRPC server stopped")
