import asyncio
import psutil
from common.logging_config import setup_logging

logger = setup_logging("worker.metrics")


class MetricsCollector:
    def get_cpu_pct(self) -> float:
        return psutil.cpu_percent(interval=None)

    def get_ram_pct(self) -> float:
        return psutil.virtual_memory().percent

    def get_gpu_pct(self) -> float:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return float(result.stdout.strip().split("\n")[0])
        except Exception:
            pass
        return -1.0
