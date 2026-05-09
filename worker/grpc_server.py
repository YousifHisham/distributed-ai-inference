import asyncio
import time
import grpc
from common.generated import inference_pb2, inference_pb2_grpc
from common.logging_config import setup_logging

logger = setup_logging("worker.grpc")


class WorkerServicer(inference_pb2_grpc.WorkerServiceServicer):
    def __init__(self, agent, ollama_client, metrics_collector, max_concurrent: int):
        self.agent = agent
        self.ollama = ollama_client
        self.collector = metrics_collector
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def Infer(self, request, context):
        if self._semaphore.locked() and self.agent._active_requests >= self.agent.max_concurrent:
            return inference_pb2.InferResponse(
                request_id=request.request_id,
                error="at_capacity",
                worker_id=self.agent.node_id,
            )

        async with self._semaphore:
            self.agent._active_requests += 1
            start = time.time()
            try:
                result = await asyncio.wait_for(
                    self.ollama.generate(request.query, self.agent.model_name, request.timeout),
                    timeout=request.timeout,
                )
                latency = time.time() - start
                self.agent.record_inference(latency, success=True)
                return inference_pb2.InferResponse(
                    request_id=request.request_id,
                    result=result,
                    inference_time=latency,
                    worker_id=self.agent.node_id,
                    error="",
                )
            except asyncio.TimeoutError:
                self.agent.record_inference(time.time() - start, success=False)
                return inference_pb2.InferResponse(
                    request_id=request.request_id,
                    error="inference_timeout",
                    worker_id=self.agent.node_id,
                )
            except Exception as e:
                self.agent.record_inference(time.time() - start, success=False)
                logger.error(f"Ollama error for request {request.request_id}: {e}")
                return inference_pb2.InferResponse(
                    request_id=request.request_id,
                    error="ollama_error",
                    worker_id=self.agent.node_id,
                )
            finally:
                self.agent._active_requests -= 1

    async def Health(self, request, context):
        ollama_healthy = await self.ollama.health_check()
        status = "healthy" if ollama_healthy else "unhealthy"
        return inference_pb2.HealthResponse(
            status=status,
            node_id=self.agent.node_id,
            ollama_healthy=ollama_healthy,
            active_requests=self.agent._active_requests,
            model_name=self.agent.model_name,
        )

    async def GetMetrics(self, request, context):
        return inference_pb2.WorkerMetricsResponse(
            node_id=self.agent.node_id,
            active_requests=self.agent._active_requests,
            total_completed=self.agent._total_completed,
            total_failed=self.agent._total_failed,
            avg_latency=self.agent._avg_latency(),
            cpu_pct=self.collector.get_cpu_pct(),
            ram_pct=self.collector.get_ram_pct(),
            gpu_pct=self.collector.get_gpu_pct(),
            ollama_healthy=await self.ollama.health_check(),
        )


async def start_grpc_server(agent, ollama_client, metrics_collector, max_concurrent: int, port: int):
    server = grpc.aio.server()
    inference_pb2_grpc.add_WorkerServiceServicer_to_server(
        WorkerServicer(agent, ollama_client, metrics_collector, max_concurrent), server
    )
    server.add_insecure_port(f"0.0.0.0:{port}")
    await server.start()
    logger.info(f"Worker gRPC server listening on port {port}")
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await server.stop(grace=5)
        logger.info("Worker gRPC server stopped")
