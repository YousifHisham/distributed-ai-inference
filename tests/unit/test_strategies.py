"""Unit tests for all 4 scheduling strategies."""
import time
import pytest
from common.models import WorkerRecord
from common.enums import WorkerStatus
from master.strategies.round_robin import RoundRobinStrategy
from master.strategies.least_active import LeastActiveRequestsStrategy
from master.strategies.load_aware import LoadAwareRoutingStrategy
from master.strategies.lowest_latency import LowestAverageLatencyStrategy


def make_worker(node_id: str, active: int = 0, cpu: float = 10.0, ram: float = 30.0,
                avg_latency: float = 0.0, load: float = 0.0, max_concurrent: int = 4) -> WorkerRecord:
    return WorkerRecord(
        node_id=node_id,
        hostname=f"host-{node_id}",
        address=f"http://192.168.1.1:50052",
        status=WorkerStatus.healthy,
        last_heartbeat=time.time(),
        active_requests=active,
        max_concurrent=max_concurrent,
        cpu_pct=cpu,
        ram_pct=ram,
        average_latency=avg_latency,
        current_load=load,
        ollama_healthy=True,
    )


# ── Round Robin ───────────────────────────────────────────────────────────────

def test_round_robin_cycles_through_workers():
    strategy = RoundRobinStrategy()
    workers = [make_worker(f"w{i}") for i in range(3)]
    selected = [strategy.select_worker(workers).node_id for _ in range(6)]
    assert selected == ["w0", "w1", "w2", "w0", "w1", "w2"]


def test_round_robin_single_worker_always_selected():
    strategy = RoundRobinStrategy()
    workers = [make_worker("solo")]
    for _ in range(5):
        assert strategy.select_worker(workers).node_id == "solo"


def test_round_robin_empty_returns_none():
    assert RoundRobinStrategy().select_worker([]) is None


def test_round_robin_distributes_evenly():
    strategy = RoundRobinStrategy()
    workers = [make_worker(f"w{i}") for i in range(4)]
    counts = {w.node_id: 0 for w in workers}
    for _ in range(100):
        w = strategy.select_worker(workers)
        counts[w.node_id] += 1
    for count in counts.values():
        assert count == 25


# ── Least Active ──────────────────────────────────────────────────────────────

def test_least_active_picks_least_loaded():
    strategy = LeastActiveRequestsStrategy()
    workers = [make_worker("busy", active=3), make_worker("idle", active=0)]
    assert strategy.select_worker(workers).node_id == "idle"


def test_least_active_tie_returns_any():
    strategy = LeastActiveRequestsStrategy()
    workers = [make_worker("a", active=2), make_worker("b", active=2)]
    result = strategy.select_worker(workers)
    assert result.node_id in ("a", "b")


def test_least_active_empty_returns_none():
    assert LeastActiveRequestsStrategy().select_worker([]) is None


def test_least_active_single_worker():
    strategy = LeastActiveRequestsStrategy()
    assert strategy.select_worker([make_worker("only", active=3)]).node_id == "only"


# ── Load Aware ────────────────────────────────────────────────────────────────

def test_load_aware_picks_lowest_load():
    strategy = LoadAwareRoutingStrategy()
    workers = [make_worker("heavy", load=0.8), make_worker("light", load=0.1)]
    assert strategy.select_worker(workers).node_id == "light"


def test_load_aware_skips_overloaded_falls_back():
    strategy = LoadAwareRoutingStrategy()
    # All workers overloaded — should fall back and return the least loaded
    workers = [make_worker("a", load=0.95), make_worker("b", load=0.92)]
    result = strategy.select_worker(workers)
    assert result.node_id == "b"  # lowest load even above threshold


def test_load_aware_empty_returns_none():
    assert LoadAwareRoutingStrategy().select_worker([]) is None


def test_load_aware_prefers_under_threshold():
    strategy = LoadAwareRoutingStrategy()
    workers = [
        make_worker("over", load=0.95),
        make_worker("under", load=0.3),
    ]
    assert strategy.select_worker(workers).node_id == "under"


# ── Lowest Latency ────────────────────────────────────────────────────────────

def test_lowest_latency_picks_fastest():
    strategy = LowestAverageLatencyStrategy()
    workers = [make_worker("slow", avg_latency=3.0), make_worker("fast", avg_latency=0.5)]
    assert strategy.select_worker(workers).node_id == "fast"


def test_lowest_latency_zero_latency_prioritized():
    strategy = LowestAverageLatencyStrategy()
    workers = [make_worker("experienced", avg_latency=1.5), make_worker("new", avg_latency=0.0)]
    assert strategy.select_worker(workers).node_id == "new"


def test_lowest_latency_empty_returns_none():
    assert LowestAverageLatencyStrategy().select_worker([]) is None


def test_lowest_latency_single_worker():
    strategy = LowestAverageLatencyStrategy()
    result = strategy.select_worker([make_worker("only", avg_latency=5.0)])
    assert result.node_id == "only"


# ── Strategy hot-swap (via Scheduler.set_strategy) ────────────────────────────

def test_scheduler_set_strategy_changes_behavior():
    from master.scheduler import Scheduler
    from master.task_queue import TaskQueue
    from master.registry import WorkerRegistry

    registry = WorkerRegistry()
    queue = TaskQueue()
    scheduler = Scheduler(
        registry=registry, task_queue=queue,
        strategy_name="round_robin", max_retries=3, task_timeout=30
    )
    assert scheduler.strategy_name == "round_robin"

    scheduler.set_strategy("least_active")
    assert scheduler.strategy_name == "least_active"
    assert isinstance(scheduler._strategy, LeastActiveRequestsStrategy)

    scheduler.set_strategy("load_aware")
    assert scheduler.strategy_name == "load_aware"
    assert isinstance(scheduler._strategy, LoadAwareRoutingStrategy)
