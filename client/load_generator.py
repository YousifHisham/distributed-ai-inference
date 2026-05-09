#!/usr/bin/env python3
"""
Concurrent load generator for the Distributed AI Inference Platform.

Usage:
    python client/load_generator.py --master http://192.168.1.10:8000 --users 100
    python client/load_generator.py --master http://localhost:8000 --users 1000 --burst
    python client/load_generator.py --master http://localhost:8000 --users 500 --ramp 60
"""
import argparse
import asyncio
import time
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import httpx


@dataclass
class RequestResult:
    request_id: str
    submitted_at: float
    completed_at: Optional[float] = None
    latency: Optional[float] = None
    status: str = "pending"
    error: Optional[str] = None
    worker_id: Optional[str] = None
    retry_count: int = 0


def load_queries(query_file: str) -> list[str]:
    path = Path(query_file)
    if path.exists():
        queries = [l.strip() for l in path.read_text().splitlines() if l.strip()]
        if queries:
            return queries
    return [
        "What is distributed computing?",
        "Explain load balancing.",
        "What is fault tolerance?",
        "Describe a microservices architecture.",
        "What is gRPC?",
    ]


async def send_request(
    client: httpx.AsyncClient,
    master_url: str,
    query: str,
    user_id: int,
    results: list[RequestResult],
    timeout: float = 300.0,
):
    submitted_at = time.time()
    result = RequestResult(request_id=f"gen-{user_id}-{int(submitted_at*1000)}", submitted_at=submitted_at)
    results.append(result)
    try:
        resp = await client.post(
            f"{master_url}/infer",
            json={"query": query},
            timeout=timeout,
        )
        completed_at = time.time()
        result.completed_at = completed_at
        result.latency = completed_at - submitted_at
        data = resp.json()
        if resp.status_code == 200 and "result" in data:
            result.status = "completed"
            result.request_id = data.get("request_id", result.request_id)
            result.worker_id = data.get("worker_id")
            result.retry_count = data.get("retry_count", 0)
        else:
            result.status = "failed"
            result.error = data.get("error") or data.get("detail") or f"HTTP {resp.status_code}"
    except Exception as e:
        result.completed_at = time.time()
        result.latency = result.completed_at - submitted_at
        result.status = "error"
        result.error = str(e)


def print_summary(results: list[RequestResult], elapsed: float):
    completed = [r for r in results if r.status == "completed"]
    failed = [r for r in results if r.status in ("failed", "error")]
    latencies = [r.latency for r in completed if r.latency is not None]

    print("\n" + "═" * 60)
    print("  LOAD TEST SUMMARY")
    print("═" * 60)
    print(f"  Total requests:   {len(results)}")
    print(f"  Completed:        {len(completed)}")
    print(f"  Failed/Error:     {len(failed)}")
    print(f"  Success rate:     {len(completed)/max(len(results),1)*100:.1f}%")
    print(f"  Total time:       {elapsed:.1f}s")
    print(f"  Throughput:       {len(completed)/max(elapsed,0.001):.1f} req/s")

    if latencies:
        latencies.sort()
        avg = sum(latencies) / len(latencies)
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        print(f"\n  Latency (seconds):")
        print(f"    avg:  {avg:.2f}s")
        print(f"    p50:  {p50:.2f}s")
        print(f"    p95:  {p95:.2f}s")
        print(f"    p99:  {p99:.2f}s")
        print(f"    min:  {latencies[0]:.2f}s")
        print(f"    max:  {latencies[-1]:.2f}s")

    if failed:
        error_counts: dict[str, int] = {}
        for r in failed:
            key = r.error or "unknown"
            error_counts[key] = error_counts.get(key, 0) + 1
        print(f"\n  Errors:")
        for err, count in sorted(error_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"    [{count}x] {err[:60]}")
    print("═" * 60)


async def run(master_url: str, num_users: int, queries: list[str], burst: bool, ramp: float, request_timeout: float):
    results: list[RequestResult] = []
    limits = httpx.Limits(max_connections=num_users + 50, max_keepalive_connections=num_users)

    async with httpx.AsyncClient(limits=limits) as client:
        start = time.time()
        tasks = []

        if burst:
            print(f"[load-gen] Firing {num_users} requests simultaneously...")
            for i in range(num_users):
                query = random.choice(queries)
                tasks.append(asyncio.create_task(
                    send_request(client, master_url, query, i, results, request_timeout)
                ))
        elif ramp > 0:
            print(f"[load-gen] Ramping {num_users} users over {ramp}s...")
            delay = ramp / num_users
            for i in range(num_users):
                query = random.choice(queries)
                tasks.append(asyncio.create_task(
                    send_request(client, master_url, query, i, results, request_timeout)
                ))
                await asyncio.sleep(delay)
        else:
            print(f"[load-gen] Sending {num_users} requests with light concurrency stagger...")
            batch_size = min(50, num_users)
            for i in range(0, num_users, batch_size):
                batch = []
                for j in range(i, min(i + batch_size, num_users)):
                    query = random.choice(queries)
                    batch.append(asyncio.create_task(
                        send_request(client, master_url, query, j, results, request_timeout)
                    ))
                tasks.extend(batch)
                await asyncio.sleep(0.05)

        await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start

    print_summary(results, elapsed)
    return results


def main():
    parser = argparse.ArgumentParser(description="Distributed AI Inference Load Generator")
    parser.add_argument("--master", default="http://localhost:8000", help="Master URL")
    parser.add_argument("--users", type=int, default=100, help="Number of concurrent users")
    parser.add_argument("--burst", action="store_true", help="Fire all requests at once")
    parser.add_argument("--ramp", type=float, default=0, help="Ramp up over N seconds")
    parser.add_argument("--query-file", default="client/queries.txt", help="File with queries (one per line)")
    parser.add_argument("--timeout", type=float, default=300.0, help="Per-request timeout in seconds")
    args = parser.parse_args()

    queries = load_queries(args.query_file)
    print(f"[load-gen] Loaded {len(queries)} queries")
    print(f"[load-gen] Target: {args.master} | Users: {args.users} | Burst: {args.burst} | Ramp: {args.ramp}s")

    asyncio.run(run(args.master, args.users, queries, args.burst, args.ramp, args.timeout))


if __name__ == "__main__":
    main()
