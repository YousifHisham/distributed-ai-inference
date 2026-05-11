#!/usr/bin/env python3
"""
End-to-end cluster test. Shows per-worker breakdown, latencies, and strategy behavior.

Usage:
  python3 scripts/cluster_test.py [master_url] [--concurrency N] [--total N] [--strategy NAME]

Examples:
  python3 scripts/cluster_test.py https://yeast-spokesman-taekwondo.ngrok-free.app
  python3 scripts/cluster_test.py http://localhost:8000 --concurrency 10 --total 30
  python3 scripts/cluster_test.py http://localhost:8000 --strategy round_robin
"""

import argparse
import asyncio
import statistics
import sys
import time
from collections import defaultdict

import httpx

QUERIES = [
    "What is distributed computing?",
    "Explain fault tolerance in systems.",
    "What is load balancing?",
    "How does consensus work in distributed systems?",
    "What is the CAP theorem?",
    "Explain horizontal vs vertical scaling.",
    "What is a message queue?",
    "How do distributed databases handle replication?",
]


async def show_cluster_status(client: httpx.AsyncClient, master_url: str) -> bool:
    try:
        r = await client.get(f"{master_url}/workers", timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[ERROR] Cannot reach master at {master_url}: {e}")
        return False

    workers = data["workers"]
    print(f"\n{'='*60}")
    print(f"  Cluster status — strategy: {data['active_strategy']}")
    print(f"  healthy={data['healthy_count']}  draining={data['draining_count']}  unhealthy={data['unhealthy_count']}")
    print(f"{'='*60}")
    if not workers:
        print("  [!] No workers registered.")
        return False
    for w in workers:
        wid = w["worker_id"][:8]
        print(
            f"  [{w['status']:8s}] {wid}  url={w['url']}  "
            f"slots={w['active_requests']}/{w['max_slots']}  "
            f"gpu={w['gpu_util_pct']:.0f}%  "
            f"avg_lat={w['avg_latency_ms']:.0f}ms"
        )
    print(f"{'='*60}\n")
    return True


async def send_one(client: httpx.AsyncClient, master_url: str, query: str, idx: int) -> dict:
    start = time.monotonic()
    try:
        r = await client.post(f"{master_url}/infer", json={"query": query}, timeout=60)
        elapsed = (time.monotonic() - start) * 1000
        if r.status_code == 200:
            d = r.json()
            wid = d.get("worker_id", "?")[:8]
            print(f"  [{idx:3d}] OK   worker={wid}  lat={elapsed:.0f}ms  retries={d.get('retry_count', 0)}")
            return {"ok": True, "worker_id": d.get("worker_id", "?"), "latency_ms": elapsed, "retry_count": d.get("retry_count", 0)}
        else:
            print(f"  [{idx:3d}] ERR  status={r.status_code}  lat={elapsed:.0f}ms")
            return {"ok": False, "latency_ms": elapsed, "status_code": r.status_code}
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        print(f"  [{idx:3d}] FAIL {e}")
        return {"ok": False, "latency_ms": elapsed, "exc": str(e)}


async def run_test(master_url: str, concurrency: int, total: int, strategy: str | None) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        reachable = await show_cluster_status(client, master_url)
        if not reachable:
            sys.exit(1)

        if strategy:
            r = await client.post(f"{master_url}/config/strategy", json={"strategy": strategy}, timeout=5)
            if r.status_code == 200:
                print(f"Strategy set to: {strategy}\n")
            else:
                print(f"[WARN] Could not set strategy: {r.text}\n")

        print(f"Sending {total} requests  concurrency={concurrency}")
        print(f"{'-'*60}")

        semaphore = asyncio.Semaphore(concurrency)
        results = []

        async def bounded(idx: int, query: str) -> None:
            async with semaphore:
                result = await send_one(client, master_url, query, idx)
                results.append(result)

        start = time.monotonic()
        await asyncio.gather(*[
            bounded(i + 1, QUERIES[i % len(QUERIES)])
            for i in range(total)
        ])
        wall = time.monotonic() - start

        print(f"\n{'='*60}")
        print("  Results")
        print(f"{'='*60}")

        ok = [r for r in results if r.get("ok")]
        fail = [r for r in results if not r.get("ok")]
        latencies = sorted(r["latency_ms"] for r in ok)

        print(f"  Total      : {total}")
        print(f"  Success    : {len(ok)}  ({len(ok)/total*100:.1f}%)")
        print(f"  Errors     : {len(fail)}")
        print(f"  Throughput : {total/wall:.2f} req/s")

        if latencies:
            p50 = statistics.median(latencies)
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[int(len(latencies) * 0.99)]
            print(f"  p50 lat    : {p50:.0f}ms")
            print(f"  p95 lat    : {p95:.0f}ms")
            print(f"  p99 lat    : {p99:.0f}ms")

        worker_counts: dict[str, int] = defaultdict(int)
        worker_lats: dict[str, list[float]] = defaultdict(list)
        for r in ok:
            wid = r["worker_id"][:8]
            worker_counts[wid] += 1
            worker_lats[wid].append(r["latency_ms"])

        if worker_counts:
            print(f"\n  Per-worker distribution:")
            for wid, count in sorted(worker_counts.items(), key=lambda x: -x[1]):
                avg = sum(worker_lats[wid]) / len(worker_lats[wid])
                print(f"    {wid}  requests={count}  avg_lat={avg:.0f}ms")

        print(f"{'='*60}")

        await show_cluster_status(client, master_url)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("master_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--total", type=int, default=15)
    parser.add_argument("--strategy", type=str, default=None,
                        choices=["round_robin", "least_active", "load_aware", "lowest_latency", "gpu_aware"])
    args = parser.parse_args()

    asyncio.run(run_test(args.master_url, args.concurrency, args.total, args.strategy))


if __name__ == "__main__":
    main()
