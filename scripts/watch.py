#!/usr/bin/env python3
from __future__ import annotations
"""
Live cluster dashboard. Polls /workers every 0.5s and prints a refreshing view.

Usage:
  python3 scripts/watch.py [master_url]

Example:
  python3 scripts/watch.py https://yeast-spokesman-taekwondo.ngrok-free.app
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

import httpx

MASTER_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
REFRESH = 0.5

# ANSI colors
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

STATUS_COLOR = {
    "HEALTHY":   GREEN,
    "DRAINING":  YELLOW,
    "UNHEALTHY": RED,
}

BAR_WIDTH = 20


def bar(value: float, max_val: float = 100.0, width: int = BAR_WIDTH) -> str:
    filled = int(min(value / max_val, 1.0) * width)
    pct = value / max_val if max_val else 0
    color = GREEN if pct < 0.6 else YELLOW if pct < 0.85 else RED
    return color + "█" * filled + DIM + "░" * (width - filled) + RESET


def since(dt_str: str | None) -> str:
    if not dt_str:
        return "never"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        secs = (datetime.now(timezone.utc) - dt).total_seconds()
        return f"{secs:.1f}s ago"
    except Exception:
        return "?"


async def fetch(client: httpx.AsyncClient) -> dict | None:
    try:
        r = await client.get(f"{MASTER_URL}/workers", timeout=4)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def render(data: dict, tick: int) -> str:
    lines = []
    now = datetime.now().strftime("%H:%M:%S")
    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[tick % 10]

    if "error" in data:
        lines.append(f"{RED}{BOLD}  Cannot reach master: {data['error']}{RESET}")
        lines.append(f"  {DIM}Retrying...{RESET}")
        return "\n".join(lines)

    workers   = data.get("workers", [])
    strategy  = data.get("active_strategy", "?")
    queue     = data.get("queue_depth", 0)
    healthy   = data.get("healthy_count", 0)
    draining  = data.get("draining_count", 0)
    unhealthy = data.get("unhealthy_count", 0)

    total_active = sum(w.get("active_requests", 0) for w in workers)

    lines.append(f"{BOLD}  {spinner} Distributed Inference Cluster{RESET}  {DIM}{now}{RESET}")
    lines.append(f"  Strategy: {CYAN}{BOLD}{strategy}{RESET}   "
                 f"Queue: {YELLOW if queue > 0 else ''}{BOLD}{queue}{RESET}   "
                 f"Workers: {GREEN}{healthy}✓{RESET} "
                 f"{YELLOW}{draining}⚠{RESET} "
                 f"{RED}{unhealthy}✗{RESET}   "
                 f"In-flight: {BOLD}{total_active}{RESET}")
    lines.append(f"  {'─'*70}")

    if not workers:
        lines.append(f"  {YELLOW}No workers registered yet.{RESET}")
        return "\n".join(lines)

    for w in workers:
        wid      = w["worker_id"][:8]
        url      = w["url"]
        status   = w["status"]
        active   = w["active_requests"]
        gpu_pct  = w["gpu_util_pct"]
        vram_u   = w["vram_used_gb"]
        vram_t   = w["vram_total_gb"]
        temp     = w["gpu_temp_c"]
        avg_lat  = w["avg_latency_ms"]
        hb       = since(w.get("last_heartbeat"))
        col      = STATUS_COLOR.get(status, DIM)

        lines.append(
            f"  {col}{BOLD}[{status:8s}]{RESET}  {BOLD}{wid}{RESET}  {DIM}{url}{RESET}"
        )
        lines.append(
            f"            active={BOLD}{active:3d}{RESET}  "
            f"gpu={bar(gpu_pct)} {gpu_pct:4.0f}%  "
            f"vram={vram_u:.1f}/{vram_t:.0f}GB  "
            f"temp={temp:.0f}°C  "
            f"avg_lat={avg_lat:.0f}ms  "
            f"hb={DIM}{hb}{RESET}"
        )

    lines.append(f"  {'─'*70}")
    lines.append(f"  {DIM}Ctrl+C to exit  ·  refresh {REFRESH}s  ·  {MASTER_URL}{RESET}")
    return "\n".join(lines)


async def main() -> None:
    tick = 0
    async with httpx.AsyncClient() as client:
        while True:
            data = await fetch(client)
            output = render(data, tick)
            # clear screen and move cursor to top
            print("\033[H\033[J", end="")
            print(output)
            tick += 1
            await asyncio.sleep(REFRESH)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n")
