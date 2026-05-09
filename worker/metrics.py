from __future__ import annotations
from prometheus_client import Counter, Gauge, Histogram

ACTIVE_REQUESTS = Gauge("worker_active_requests", "In-flight inference requests", ["worker_id"])
TOTAL_COMPLETED = Counter("worker_total_completed", "Completed inferences", ["worker_id"])
TOTAL_FAILED = Counter("worker_total_failed", "Failed inferences", ["worker_id"])
INFERENCE_DURATION = Histogram(
    "worker_inference_duration_seconds",
    "Ollama inference time",
    ["worker_id"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)
CPU_PERCENT = Gauge("worker_cpu_percent", "CPU usage %", ["worker_id"])
RAM_PERCENT = Gauge("worker_ram_percent", "RAM usage %", ["worker_id"])
GPU_PERCENT = Gauge("worker_gpu_percent", "GPU usage % (-1 if N/A)", ["worker_id"])
OLLAMA_HEALTHY = Gauge("worker_ollama_healthy", "1 if Ollama is healthy", ["worker_id"])


def record_inference(worker_id: str, duration: float, success: bool):
    if success:
        TOTAL_COMPLETED.labels(worker_id=worker_id).inc()
        INFERENCE_DURATION.labels(worker_id=worker_id).observe(duration)
    else:
        TOTAL_FAILED.labels(worker_id=worker_id).inc()


def update_worker_metrics(agent, collector):
    wid = agent.node_id
    ACTIVE_REQUESTS.labels(worker_id=wid).set(agent._active_requests)
    CPU_PERCENT.labels(worker_id=wid).set(collector.get_cpu_pct())
    RAM_PERCENT.labels(worker_id=wid).set(collector.get_ram_pct())
    GPU_PERCENT.labels(worker_id=wid).set(collector.get_gpu_pct())
