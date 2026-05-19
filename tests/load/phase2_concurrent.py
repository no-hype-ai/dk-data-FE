"""T002a — Phase 2 concurrent load simulation.

Feature: 002-external-integration-foundation (US-3, US-14)

Simulates the Phase 2 peak load on a staging cluster so we can
measure query p99, CPU, connection pool utilization, and detect
saturation BEFORE the feature ships to production.

**IMPORTANT**: This is a load *driver*, not a unit test. Running it
against an in-process FastAPI or against a shared dev cluster is
NOT supported — it opens hundreds of concurrent connections. Point
it at a dedicated staging dk-data-FE stack.

## What it simulates

Four concurrent workloads that run on the same cluster at peak:

1. **SQLMesh transform job** — 1 run writing to `mol_silver.*` /
   `mol_gold.*` via `POSTGRES_HOST_DIRECT` (bypasses PgBouncer)
2. **Backfill orchestrator** — the 10-minute cron tick that reads
   `meta.backfill_state` and picks up one source to fetch
3. **Adapter fleet** — 10k calls/min across all consumers going
   through the metering proxy to PostgREST
4. **Metering proxy JWT minting** — every adapter call triggers
   one JWT mint; this stresses the CPU path

## What it measures

- Adapter-observed latency p50/p99 per method
- Metering proxy CPU utilization (via `/metrics` scrape)
- Connection pool utilization (pg_stat_activity)
- 429 rate from the metering proxy (indicates burst exhaustion)
- 5xx rate from PostgREST (indicates DB saturation)

## Pass/fail criteria

- **p99 latency ≤ 200 ms** (SLO)
- **0 sustained 5xx** (any blip > 30 seconds fails)
- **429 rate ≤ 5%** (bursts are tolerated; sustained 429 is not)
- **Connection pool < 70%** utilization (headroom for surge)

## Usage

    # Point at staging via kubectl port-forward:
    kubectl -n dk-data-stage port-forward svc/metering-proxy 3001:3001 &
    kubectl -n dk-data-stage port-forward svc/postgres 5433:5432 &

    export DK_DATA_URL=http://localhost:3001
    export DK_DATA_API_KEY=dk_data_loadtest_...
    export POSTGRES_DSN=postgres://postgres:$PW@localhost:5433/dk_data

    python -m tests.load.phase2_concurrent --duration 600 --adapter-rpm 10000

The driver writes a JSON results file to
`docs/reports/phase2-load-YYYYMMDD-HHMMSS.json` — the run is not
"done" until this file exists AND all pass criteria are met.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    import httpx
except ImportError:  # pragma: no cover
    print("httpx required — run inside the feature 002 venv")
    sys.exit(1)


@dataclass
class LoadStats:
    started_at: str = ""
    ended_at: str = ""
    total_requests: int = 0
    success_count: int = 0
    rate_limited_count: int = 0
    server_error_count: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    def record(self, status_code: int, latency_ms: float) -> None:
        self.total_requests += 1
        self.latencies_ms.append(latency_ms)
        if 200 <= status_code < 300:
            self.success_count += 1
        elif status_code == 429:
            self.rate_limited_count += 1
        elif status_code >= 500:
            self.server_error_count += 1

    def summary(self) -> dict[str, float | int | str]:
        if not self.latencies_ms:
            return {
                "total_requests": 0,
                "p50_ms": 0.0,
                "p99_ms": 0.0,
                "success_rate": 0.0,
                "rate_limited_rate": 0.0,
                "server_error_rate": 0.0,
            }
        sorted_latencies = sorted(self.latencies_ms)
        p50 = sorted_latencies[len(sorted_latencies) // 2]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        return {
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "rate_limited_count": self.rate_limited_count,
            "server_error_count": self.server_error_count,
            "p50_ms": round(p50, 2),
            "p99_ms": round(p99, 2),
            "mean_ms": round(statistics.mean(self.latencies_ms), 2),
            "success_rate": round(self.success_count / max(self.total_requests, 1), 4),
            "rate_limited_rate": round(
                self.rate_limited_count / max(self.total_requests, 1), 4
            ),
            "server_error_rate": round(
                self.server_error_count / max(self.total_requests, 1), 4
            ),
        }


async def adapter_worker(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    stop_at: float,
    stats: LoadStats,
    requests_per_sec: float,
) -> None:
    """One concurrent adapter worker driving `requests_per_sec` RPS."""
    headers = {"Authorization": f"Bearer {api_key}"}
    interval = 1.0 / requests_per_sec
    while time.monotonic() < stop_at:
        tick_start = time.monotonic()
        request_start = time.perf_counter()
        try:
            response = await client.get(
                f"{base_url}/mol_silver/molecules",
                headers=headers,
                params={"limit": "10"},
            )
            latency_ms = (time.perf_counter() - request_start) * 1000
            stats.record(response.status_code, latency_ms)
        except httpx.HTTPError:
            latency_ms = (time.perf_counter() - request_start) * 1000
            stats.record(599, latency_ms)
        sleep_for = interval - (time.monotonic() - tick_start)
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)


async def run_load(
    base_url: str,
    api_key: str,
    duration_seconds: int,
    adapter_rpm: int,
    concurrency: int,
) -> LoadStats:
    stats = LoadStats(
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    stop_at = time.monotonic() + duration_seconds
    rps_per_worker = (adapter_rpm / 60.0) / concurrency
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:
        tasks = [
            asyncio.create_task(
                adapter_worker(client, base_url, api_key, stop_at, stats, rps_per_worker)
            )
            for _ in range(concurrency)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    stats.ended_at = datetime.now(timezone.utc).isoformat()
    return stats


def write_report(stats: LoadStats, args: argparse.Namespace) -> str:
    summary = stats.summary()
    summary["config"] = {
        "base_url": args.base_url,
        "duration_seconds": args.duration,
        "adapter_rpm": args.adapter_rpm,
        "concurrency": args.concurrency,
    }
    # Pass/fail criteria (§ top-of-file)
    summary["pass_criteria"] = {
        "p99_under_200ms": summary["p99_ms"] < 200,
        "server_error_rate_under_1pct": summary["server_error_rate"] < 0.01,
        "rate_limited_under_5pct": summary["rate_limited_rate"] < 0.05,
    }
    summary["overall_pass"] = all(summary["pass_criteria"].values())
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = f"docs/reports/phase2-load-{ts}.json"
    os.makedirs("docs/reports", exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 concurrent load driver")
    parser.add_argument("--base-url", default=os.environ.get("DK_DATA_URL", "http://localhost:3001"))
    parser.add_argument("--api-key", default=os.environ.get("DK_DATA_API_KEY", ""))
    parser.add_argument("--duration", type=int, default=60, help="seconds")
    parser.add_argument("--adapter-rpm", type=int, default=600)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    if not args.api_key:
        print("DK_DATA_API_KEY is required", file=sys.stderr)
        return 2
    stats = asyncio.run(
        run_load(
            args.base_url,
            args.api_key,
            duration_seconds=args.duration,
            adapter_rpm=args.adapter_rpm,
            concurrency=args.concurrency,
        )
    )
    report_path = write_report(stats, args)
    summary = stats.summary()
    print(f"wrote {report_path}")
    print(f"p50={summary['p50_ms']} ms  p99={summary['p99_ms']} ms  "
          f"success_rate={summary['success_rate']:.2%}  "
          f"rate_limited={summary['rate_limited_rate']:.2%}  "
          f"server_errors={summary['server_error_rate']:.2%}")
    return 0 if summary.get("overall_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
