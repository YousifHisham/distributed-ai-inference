#!/usr/bin/env python3
"""Load generator: ramp and burst modes for the distributed inference cluster."""

import asyncio
import argparse
import random
import statistics
import time
from pathlib import Path

import httpx


async def send_request(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    semaphore: asyncio.Semaphore,
    results: list,
) -> None:
    async with semaphore:
        start = time.monotonic()
        try:
            resp = await client.post(f"{url}/infer", json={"query": query}, timeout=60.0)
            elapsed_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                results.append({
                    "status": "success",
                    "worker_id": data.get("worker_id", "?"),
                    "latency_ms": elapsed_ms,
                    "retry_count": data.get("retry_count", 0),
                })
                print(
                    f"OK  worker={data.get('worker_id', '?')[:8]}  "
                    f"latency={elapsed_ms:.0f}ms  retries={data.get('retry_count', 0)}"
                )
            else:
                results.append({"status": "error", "code": resp.status_code, "latency_ms": elapsed_ms})
                print(f"ERR status={resp.status_code}  latency={elapsed_ms:.0f}ms")
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            results.append({"status": "error", "exc": str(exc), "latency_ms": elapsed_ms})
            print(f"FAIL {exc}")


def load_queries(queries_file: str) -> list[str]:
    path = Path(queries_file)
    if path.exists():
        return [line.strip() for line in path.read_text().splitlines() if line.strip()]
    return ["What is distributed computing?", "Explain fault tolerance.", "What is load balancing?"]


def print_summary(results: list, total_time_s: float, label: str = "") -> None:
    if label:
        print(f"\n{'='*50}")
        print(f"  Summary: {label}")
        print(f"{'='*50}")
    successes = [r for r in results if r["status"] == "success"]
    errors = [r for r in results if r["status"] != "success"]
    latencies = [r["latency_ms"] for r in results if "latency_ms" in r]
    total = len(results)
    success_rate = len(successes) / total * 100 if total else 0
    throughput = total / total_time_s if total_time_s > 0 else 0

    print(f"Total requests : {total}")
    print(f"Successes      : {len(successes)} ({success_rate:.1f}%)")
    print(f"Errors         : {len(errors)}")
    print(f"Throughput     : {throughput:.1f} req/s")

    if latencies:
        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        print(f"Latency p50    : {p50:.0f}ms")
        print(f"Latency p95    : {p95:.0f}ms")
        print(f"Latency p99    : {p99:.0f}ms")


async def ramp_mode(url: str, queries: list[str], levels: list[int], step_duration: float) -> None:
    print(f"\nRAMP MODE: levels={levels}, {step_duration}s each")
    all_results = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for level in levels:
            print(f"\n--- Ramp level: {level} concurrent users ---")
            semaphore = asyncio.Semaphore(level)
            results: list = []
            start = time.monotonic()

            tasks = []
            # Send requests for step_duration seconds at this concurrency level
            deadline = start + step_duration
            while time.monotonic() < deadline:
                query = random.choice(queries)
                task = asyncio.create_task(
                    send_request(client, url, query, semaphore, results)
                )
                tasks.append(task)
                await asyncio.sleep(0.01)

            await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.monotonic() - start
            print_summary(results, elapsed, f"Level {level}")
            all_results.extend(results)

    print_summary(all_results, len(levels) * step_duration, "OVERALL")


async def burst_mode(url: str, queries: list[str], concurrency: int) -> None:
    print(f"\nBURST MODE: {concurrency} simultaneous requests")
    semaphore = asyncio.Semaphore(concurrency)
    results: list = []
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [
            asyncio.create_task(
                send_request(client, url, random.choice(queries), semaphore, results)
            )
            for _ in range(concurrency)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.monotonic() - start
    print_summary(results, elapsed, f"Burst {concurrency}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Distributed inference load generator")
    parser.add_argument("--url", default="http://localhost:8000", help="Master URL")
    parser.add_argument("--queries", default="client/queries.txt", help="Queries file")
    parser.add_argument(
        "--mode", choices=["ramp", "burst"], default="ramp", help="Load mode"
    )
    parser.add_argument(
        "--levels", nargs="+", type=int, default=[100, 500, 1000],
        help="Concurrency levels for ramp mode"
    )
    parser.add_argument(
        "--step", type=float, default=30.0, help="Seconds per ramp step"
    )
    parser.add_argument(
        "--burst", type=int, default=500, help="Concurrency for burst mode"
    )
    args = parser.parse_args()

    queries = load_queries(args.queries)
    print(f"Loaded {len(queries)} queries | Target: {args.url}")

    if args.mode == "ramp":
        asyncio.run(ramp_mode(args.url, queries, args.levels, args.step))
    else:
        asyncio.run(burst_mode(args.url, queries, args.burst))


if __name__ == "__main__":
    main()
