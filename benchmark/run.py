#!/usr/bin/env python3
"""
Benchmark tool — compares all scheduling strategies under identical load.

Usage:
    python3 benchmark/run.py --master http://192.168.1.10:8000 --users 50
    python3 benchmark/run.py --master http://localhost:8000 --users 100 --strategies round_robin least_active
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from client.load_generator import load_queries, run as run_load


STRATEGIES = ["round_robin", "least_active", "load_aware", "lowest_latency"]


@dataclass
class StrategyResult:
    strategy: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    throughput: float = 0.0
    avg_latency: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    min_latency: float = 0.0
    max_latency: float = 0.0
    elapsed: float = 0.0


async def set_strategy(master_url: str, strategy: str) -> bool:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{master_url}/config/strategy",
                json={"strategy": strategy},
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"  [warn] Could not set strategy {strategy}: {e}")
            return False


async def benchmark_strategy(
    master_url: str, strategy: str, num_users: int, queries: list[str], timeout: float
) -> StrategyResult:
    print(f"\n[benchmark] Running strategy: {strategy} ({num_users} users)...")
    ok = await set_strategy(master_url, strategy)
    if not ok:
        print(f"  [warn] Failed to set strategy — continuing anyway")

    await asyncio.sleep(1)  # let strategy propagate

    start = time.time()
    results = await run_load(master_url, num_users, queries, burst=True, ramp=0, request_timeout=timeout)
    elapsed = time.time() - start

    completed = [r for r in results if r.status == "completed"]
    failed = [r for r in results if r.status in ("failed", "error")]
    latencies = sorted([r.latency for r in completed if r.latency is not None])

    def percentile(data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        idx = int(len(data) * pct)
        return data[min(idx, len(data) - 1)]

    return StrategyResult(
        strategy=strategy,
        total=len(results),
        completed=len(completed),
        failed=len(failed),
        throughput=len(completed) / max(elapsed, 0.001),
        avg_latency=sum(latencies) / len(latencies) if latencies else 0.0,
        p50_latency=percentile(latencies, 0.50),
        p95_latency=percentile(latencies, 0.95),
        p99_latency=percentile(latencies, 0.99),
        min_latency=latencies[0] if latencies else 0.0,
        max_latency=latencies[-1] if latencies else 0.0,
        elapsed=elapsed,
    )


def save_csv(results: list[StrategyResult], output_dir: Path):
    path = output_dir / "summary.csv"
    fields = [
        "strategy", "total", "completed", "failed", "throughput",
        "avg_latency", "p50_latency", "p95_latency", "p99_latency",
        "min_latency", "max_latency", "elapsed",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow({k: getattr(r, k) for k in fields})
    print(f"[benchmark] CSV saved: {path}")


def save_charts(results: list[StrategyResult], output_dir: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[benchmark] matplotlib not installed — skipping charts")
        return

    strategies = [r.strategy for r in results]
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]

    # 1. Throughput bar chart
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(strategies, [r.throughput for r in results], color=colors)
    ax.set_title("Throughput by Scheduling Strategy")
    ax.set_ylabel("Requests / second")
    ax.set_xlabel("Strategy")
    for bar, r in zip(bars, results):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{r.throughput:.1f}", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig(output_dir / "throughput.png", dpi=150)
    plt.close()

    # 2. Latency comparison (avg + p95 grouped bars)
    x = range(len(strategies))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([i - width / 2 for i in x], [r.avg_latency for r in results], width, label="avg", color="#4C72B0")
    ax.bar([i + width / 2 for i in x], [r.p95_latency for r in results], width, label="p95", color="#DD8452")
    ax.set_title("Latency by Scheduling Strategy")
    ax.set_ylabel("Latency (seconds)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(strategies)
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "latency.png", dpi=150)
    plt.close()

    # 3. Success vs failure stacked bar
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(strategies, [r.completed for r in results], label="Completed", color="#55A868")
    ax.bar(strategies, [r.failed for r in results],
           bottom=[r.completed for r in results], label="Failed", color="#C44E52")
    ax.set_title("Completed vs Failed Requests")
    ax.set_ylabel("Request count")
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "success_rate.png", dpi=150)
    plt.close()

    print(f"[benchmark] Charts saved to {output_dir}/")


def print_table(results: list[StrategyResult]):
    print("\n" + "═" * 80)
    print(f"{'BENCHMARK RESULTS':^80}")
    print("═" * 80)
    header = f"{'Strategy':<18} {'Req/s':>7} {'Avg(s)':>7} {'p95(s)':>7} {'p99(s)':>7} {'Done':>6} {'Fail':>5}"
    print(header)
    print("─" * 80)
    for r in results:
        print(f"{r.strategy:<18} {r.throughput:>7.2f} {r.avg_latency:>7.2f} "
              f"{r.p95_latency:>7.2f} {r.p99_latency:>7.2f} {r.completed:>6} {r.failed:>5}")
    print("═" * 80)
    best_tp = max(results, key=lambda r: r.throughput)
    best_lat = min(results, key=lambda r: r.avg_latency)
    print(f"  Best throughput:  {best_tp.strategy} ({best_tp.throughput:.2f} req/s)")
    print(f"  Lowest avg latency: {best_lat.strategy} ({best_lat.avg_latency:.2f}s)")


async def main():
    parser = argparse.ArgumentParser(description="Scheduling Strategy Benchmark")
    parser.add_argument("--master", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--strategies", nargs="+", default=STRATEGIES,
                        choices=STRATEGIES, metavar="STRATEGY")
    parser.add_argument("--query-file", default="client/queries.txt")
    parser.add_argument("--output", default="benchmark/results")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    queries = load_queries(args.query_file)
    print(f"[benchmark] Master: {args.master} | Users: {args.users} | Strategies: {args.strategies}")

    all_results: list[StrategyResult] = []
    for strategy in args.strategies:
        result = await benchmark_strategy(args.master, strategy, args.users, queries, args.timeout)
        all_results.append(result)
        await asyncio.sleep(2)  # cooldown between runs

    print_table(all_results)
    save_csv(all_results, output_dir)
    save_charts(all_results, output_dir)


if __name__ == "__main__":
    asyncio.run(main())
