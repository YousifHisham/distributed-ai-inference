#!/usr/bin/env python3
"""
Test a single worker's parallel capacity directly (bypasses master).
Usage: python3 scripts/test-worker-capacity.py <worker_ip> [port]
"""
import asyncio
import httpx
import sys
import time


def get_worker_url() -> str:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/test-worker-capacity.py <worker_ip> [port]")
        print("Example: python3 scripts/test-worker-capacity.py 1.2.3.4 8001")
        sys.exit(1)
    ip = sys.argv[1]
    port = sys.argv[2] if len(sys.argv) > 2 else "8001"
    return f"http://{ip}:{port}"


async def send(client: httpx.AsyncClient, worker_url: str, i: int) -> dict:
    start = time.monotonic()
    try:
        r = await client.post(
            f"{worker_url}/infer",
            json={"query": f"In one sentence, what is distributed systems concept number {i}?", "request_id": f"cap-test-{i}"},
            timeout=120,
        )
        r.raise_for_status()
        latency = (time.monotonic() - start) * 1000
        return {"ok": True, "latency_ms": round(latency), "i": i}
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return {"ok": False, "error": str(e), "latency_ms": round(latency), "i": i}


async def test(worker_url: str, concurrency: int) -> None:
    print(f"\n{'─'*50}")
    print(f"  {concurrency} concurrent requests")
    print(f"{'─'*50}")

    async with httpx.AsyncClient() as client:
        start = time.monotonic()
        results = await asyncio.gather(*[send(client, worker_url, i) for i in range(concurrency)])
    elapsed = time.monotonic() - start

    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    latencies = sorted(r["latency_ms"] for r in ok)

    print(f"  Success:    {len(ok)}/{concurrency}")
    if fail:
        print(f"  Failed:     {len(fail)} — {fail[0]['error'][:60]}")
    if latencies:
        n = len(latencies)
        print(f"  Wall time:  {elapsed:.1f}s")
        print(f"  Throughput: {len(ok)/elapsed:.1f} req/s")
        print(f"  p50:        {latencies[n//2]}ms")
        print(f"  p95:        {latencies[int(n*0.95)]}ms")
        print(f"  p99:        {latencies[min(int(n*0.99), n-1)]}ms")
        print(f"  min/max:    {latencies[0]}ms / {latencies[-1]}ms")


async def main() -> None:
    worker_url = get_worker_url()

    print(f"Testing worker at {worker_url}")

    # verify worker is reachable
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{worker_url}/health", timeout=5)
            print(f"Worker health: {r.json()}")
    except Exception as e:
        print(f"Cannot reach worker: {e}")
        sys.exit(1)

    for concurrency in [1, 4, 8, 16, 32, 48, 64]:
        await test(worker_url, concurrency)
        await asyncio.sleep(3)  # let worker drain between tests

    print(f"\n{'─'*50}")
    print("Done. Throughput plateau = your real max_slots value.")
    print(f"{'─'*50}\n")


asyncio.run(main())
