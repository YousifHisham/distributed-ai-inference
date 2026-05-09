import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from common.models import WorkerRecord, WorkerRegistration
from common.enums import WorkerStatus
import time


@pytest.fixture
def sample_registration():
    return WorkerRegistration(
        node_id="test-worker-001",
        hostname="test-laptop",
        ip_address="192.168.1.100",
        port=50052,
        model_name="llama3.2:1b",
        max_concurrent=4,
        cpu_count=8,
        ram_gb=16.0,
        gpu_available=False,
        gpu_name="",
        ollama_healthy=True,
    )


@pytest.fixture
def sample_worker_record():
    return WorkerRecord(
        node_id="test-worker-001",
        hostname="test-laptop",
        address="http://192.168.1.100:50052",
        status=WorkerStatus.healthy,
        last_heartbeat=time.time(),
        active_requests=0,
        total_completed=0,
        total_failed=0,
        average_latency=0.0,
        current_load=0.0,
        cpu_pct=10.0,
        ram_pct=30.0,
        gpu_pct=-1.0,
        gpu_name=None,
        max_concurrent=4,
        model_name="llama3.2:1b",
        ollama_healthy=True,
        registered_at=time.time(),
    )
