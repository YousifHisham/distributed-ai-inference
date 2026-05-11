import logging
import os

from common.models import GPUMetrics

logger = logging.getLogger(__name__)

_nvml_initialized = False


def _try_init_nvml() -> bool:
    global _nvml_initialized
    if _nvml_initialized:
        return True
    try:
        import pynvml
        pynvml.nvmlInit()
        _nvml_initialized = True
        return True
    except Exception as exc:
        logger.warning("pynvml init failed: %s", exc)
        return False


def collect_gpu_metrics() -> GPUMetrics:
    if os.getenv("MOCK_GPU", "").lower() in ("1", "true", "yes"):
        logger.debug("MOCK_GPU enabled — returning zero GPU metrics")
        return GPUMetrics()

    if not _try_init_nvml():
        return GPUMetrics()

    try:
        import pynvml
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        try:
            ecc = pynvml.nvmlDeviceGetTotalEccErrors(
                handle,
                pynvml.NVML_MEMORY_ERROR_TYPE_UNCORRECTED,
                pynvml.NVML_VOLATILE_ECC,
            )
        except Exception:
            ecc = 0

        return GPUMetrics(
            gpu_util_pct=float(util.gpu),
            vram_used_gb=mem.used / 1024**3,
            vram_total_gb=mem.total / 1024**3,
            gpu_temp_c=float(temp),
            ecc_errors=int(ecc),
        )
    except Exception as exc:
        logger.error("Failed to collect GPU metrics: %s", exc)
        return GPUMetrics()
