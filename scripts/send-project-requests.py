#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier
from threading import Lock


DEFAULT_QUERIES = [
    "Explain load balancing in this distributed LLM system.",
    "How does worker failure detection work in this project?",
    "What is retrieval-augmented generation?",
    "How does the master scheduler choose a worker?",
    "Explain how GPU worker nodes are used with Ollama.",
]


@dataclass
class Result:
    level: int
    index: int
    status: str
    latency: float
    request_id: str = ""
    worker_id: str = ""
    retry_count: int = 0
    rag_sources: str = ""
    error: str = ""


def load_queries(path: str | None) -> list[str]:
    if not path:
        return DEFAULT_QUERIES
    query_path = Path(path)
    if not query_path.exists():
        return DEFAULT_QUERIES
    queries = [line.strip() for line in query_path.read_text().splitlines() if line.strip()]
    return queries or DEFAULT_QUERIES


def post_infer(master_url: str, query: str, timeout: float) -> tuple[int, dict]:
    payload = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        f"{master_url.rstrip('/')}/infer",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)


def send_one(
    master_url: str,
    query: str,
    level: int,
    index: int,
    timeout: float,
    barrier: Barrier | None,
    delay: float,
) -> Result:
    if delay > 0:
        time.sleep(delay)
    if barrier:
        barrier.wait()

    started = time.time()
    try:
        http_status, data = post_infer(master_url, query, timeout)
        latency = time.time() - started
        if http_status == 200 and data.get("result"):
            return Result(
                level=level,
                index=index,
                status="completed",
                latency=latency,
                request_id=data.get("request_id", ""),
                worker_id=data.get("worker_id", ""),
                retry_count=int(data.get("retry_count", 0)),
                rag_sources="|".join(data.get("rag_sources", [])),
            )
        return Result(
            level=level,
            index=index,
            status="failed",
            latency=latency,
            request_id=data.get("request_id", ""),
            retry_count=int(data.get("retry_count", 0)),
            rag_sources="|".join(data.get("rag_sources", [])),
            error=data.get("error") or data.get("detail") or f"HTTP {http_status}",
        )
    except urllib.error.HTTPError as exc:
        latency = time.time() - started
        return Result(level, index, "failed", latency, error=f"HTTP {exc.code}: {exc.reason}")
    except Exception as exc:
        latency = time.time() - started
        return Result(level, index, "error", latency, error=str(exc))


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * percent))
    return ordered[idx]


def print_summary(level: int, results: list[Result], elapsed: float) -> None:
    completed = [item for item in results if item.status == "completed"]
    failed = [item for item in results if item.status != "completed"]
    latencies = [item.latency for item in completed]
    workers: dict[str, int] = {}
    rag_sources: set[str] = set()

    for item in completed:
        workers[item.worker_id or "unknown"] = workers.get(item.worker_id or "unknown", 0) + 1
        for source in item.rag_sources.split("|"):
            if source:
                rag_sources.add(source)

    print()
    print("=" * 72)
    print(f"PDF LOAD LEVEL: {level} concurrent users")
    print("=" * 72)
    print(f"Total requests: {len(results)}")
    print(f"Completed:      {len(completed)}")
    print(f"Failed/Error:   {len(failed)}")
    print(f"Success rate:   {len(completed) / max(len(results), 1) * 100:.1f}%")
    print(f"Total time:     {elapsed:.2f}s")
    print(f"Throughput:     {len(completed) / max(elapsed, 0.001):.2f} req/s")

    if latencies:
        print(f"Avg latency:    {statistics.mean(latencies):.2f}s")
        print(f"P95 latency:    {percentile(latencies, 0.95):.2f}s")
        print(f"Max latency:    {max(latencies):.2f}s")

    if workers:
        print("Worker distribution:")
        for worker_id, count in sorted(workers.items(), key=lambda item: item[0]):
            print(f"  {worker_id}: {count}")

    if rag_sources:
        print("RAG sources used:")
        for source in sorted(rag_sources):
            print(f"  {source}")

    if failed:
        print("Top errors:")
        counts: dict[str, int] = {}
        for item in failed:
            key = item.error[:100] if item.error else item.status
            counts[key] = counts.get(key, 0) + 1
        for error, count in sorted(counts.items(), key=lambda item: -item[1])[:5]:
            print(f"  [{count}x] {error}")


def print_result(item: Result, lock: Lock) -> None:
    with lock:
        if item.status == "completed":
            print(
                f"[{item.level:>4} users] "
                f"request #{item.index + 1:<4} "
                f"OK      "
                f"worker={item.worker_id or 'unknown':<24} "
                f"latency={item.latency:>7.2f}s "
                f"retries={item.retry_count:<2} "
                f"rag={item.rag_sources or '-'}"
            )
        else:
            print(
                f"[{item.level:>4} users] "
                f"request #{item.index + 1:<4} "
                f"{item.status.upper():<7} "
                f"latency={item.latency:>7.2f}s "
                f"error={item.error[:120]}"
            )


def run_level(
    master_url: str,
    level: int,
    queries: list[str],
    timeout: float,
    burst: bool,
    ramp_seconds: float,
) -> list[Result]:
    print(f"\nStarting level {level} against {master_url}")
    print(f"Mode: {'burst' if burst else 'ramp' if ramp_seconds > 0 else 'batched'}")

    barrier = Barrier(level) if burst else None
    started = time.time()
    results: list[Result] = []
    print_lock = Lock()

    with ThreadPoolExecutor(max_workers=level) as executor:
        futures = []
        for index in range(level):
            query = queries[index % len(queries)]
            delay = (ramp_seconds / max(level, 1)) * index if ramp_seconds > 0 and not burst else 0.0
            futures.append(
                executor.submit(
                    send_one,
                    master_url,
                    query,
                    level,
                    index,
                    timeout,
                    barrier,
                    delay,
                )
            )

        for future in as_completed(futures):
            item = future.result()
            results.append(item)
            print_result(item, print_lock)

    elapsed = time.time() - started
    print_summary(level, results, elapsed)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PDF-style distributed LLM request load levels."
    )
    parser.add_argument("--master", default="http://localhost:8000", help="Master URL")
    parser.add_argument(
        "--levels",
        nargs="+",
        type=int,
        default=[100, 500, 1000],
        help="Concurrent user levels required by the project PDF",
    )
    parser.add_argument("--query-file", default="client/queries.txt")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--ramp", type=float, default=0.0, help="Ramp each level over N seconds")
    parser.add_argument("--burst", action="store_true", help="Fire each level simultaneously")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queries = load_queries(args.query_file)
    all_results: list[Result] = []

    print("Project PDF load demo")
    print(f"Master: {args.master}")
    print(f"Levels: {', '.join(str(level) for level in args.levels)}")
    print(f"Queries: {len(queries)}")

    for level in args.levels:
        all_results.extend(
            run_level(
                master_url=args.master,
                level=level,
                queries=queries,
                timeout=args.timeout,
                burst=args.burst,
                ramp_seconds=args.ramp,
            )
        )

    print()
    print("=" * 72)
    print("OVERALL SUMMARY")
    print("=" * 72)
    total = len(all_results)
    completed = [item for item in all_results if item.status == "completed"]
    failed = [item for item in all_results if item.status != "completed"]
    latencies = [item.latency for item in completed]
    print(f"Total requests: {total}")
    print(f"Completed:      {len(completed)}")
    print(f"Failed/Error:   {len(failed)}")
    print(f"Success rate:   {len(completed) / max(total, 1) * 100:.1f}%")
    if latencies:
        print(f"Avg latency:    {statistics.mean(latencies):.2f}s")
        print(f"P95 latency:    {percentile(latencies, 0.95):.2f}s")
        print(f"Max latency:    {max(latencies):.2f}s")

    failed = [item for item in all_results if item.status != "completed"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
