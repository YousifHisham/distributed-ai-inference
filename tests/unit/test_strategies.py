import pytest
from master.registry import WorkerNode, WorkerRegistry
from master.strategies.round_robin import RoundRobinStrategy
from master.strategies.least_active import LeastActiveStrategy
from master.strategies.load_aware import LoadAwareStrategy
from master.strategies.lowest_latency import LowestLatencyStrategy
from master.strategies.gpu_aware import GpuAwareStrategy
from common.enums import WorkerStatus


def make_worker(worker_id: str = "w1", **kwargs) -> WorkerNode:
    defaults = dict(
        worker_id=worker_id,
        url=f"http://{worker_id}:8001",
        status=WorkerStatus.HEALTHY,
        gpu_util_pct=0.0,
        vram_used_gb=0.0,
        vram_total_gb=24.0,
        gpu_temp_c=65.0,
        ecc_errors=0,
        active_requests=0,
        avg_latency_ms=0.0,
    )
    defaults.update(kwargs)
    return WorkerNode(**defaults)


def test_round_robin_cycles():
    strategy = RoundRobinStrategy()
    workers = [make_worker("w1"), make_worker("w2"), make_worker("w3")]
    selected = [strategy.select_worker(workers).worker_id for _ in range(6)]
    assert selected == ["w1", "w2", "w3", "w1", "w2", "w3"]


def test_least_active_picks_min():
    strategy = LeastActiveStrategy()
    workers = [
        make_worker("w1", active_requests=5),
        make_worker("w2", active_requests=1),
        make_worker("w3", active_requests=3),
    ]
    assert strategy.select_worker(workers).worker_id == "w2"


def test_load_aware_picks_lowest_combined_score():
    strategy = LoadAwareStrategy()
    workers = [
        make_worker("w1", active_requests=10, avg_latency_ms=500.0),
        make_worker("w2", active_requests=2, avg_latency_ms=100.0),
        make_worker("w3", active_requests=5, avg_latency_ms=300.0),
    ]
    assert strategy.select_worker(workers).worker_id == "w2"


def test_lowest_latency_picks_min():
    strategy = LowestLatencyStrategy()
    workers = [
        make_worker("w1", avg_latency_ms=400.0),
        make_worker("w2", avg_latency_ms=100.0),
        make_worker("w3", avg_latency_ms=250.0),
    ]
    assert strategy.select_worker(workers).worker_id == "w2"


def test_gpu_aware_picks_most_free():
    strategy = GpuAwareStrategy()
    workers = [
        make_worker("w1", gpu_util_pct=80.0, vram_used_gb=20.0, vram_total_gb=24.0),
        make_worker("w2", gpu_util_pct=20.0, vram_used_gb=4.0, vram_total_gb=24.0),
        make_worker("w3", gpu_util_pct=50.0, vram_used_gb=12.0, vram_total_gb=24.0),
    ]
    assert strategy.select_worker(workers).worker_id == "w2"


def test_strategies_raise_on_empty():
    for strategy in [
        RoundRobinStrategy(),
        LeastActiveStrategy(),
        LoadAwareStrategy(),
        LowestLatencyStrategy(),
        GpuAwareStrategy(),
    ]:
        with pytest.raises((ValueError, Exception)):
            strategy.select_worker([])


@pytest.mark.asyncio
async def test_swap_strategy_atomicity():
    from master.scheduler import Scheduler
    from master.registry import WorkerRegistry
    import httpx
    from common.enums import StrategyType
    import asyncio

    reg = WorkerRegistry()
    async with httpx.AsyncClient() as client:
        scheduler = Scheduler(reg, client)
        await asyncio.gather(
            scheduler.swap_strategy(StrategyType.GPU_AWARE),
            scheduler.swap_strategy(StrategyType.LEAST_ACTIVE),
        )
        assert scheduler.current_strategy_name in ("gpu_aware", "least_active")
