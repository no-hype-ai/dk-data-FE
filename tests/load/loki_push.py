"""T004c — Loki push rate limit test.

Feature: 002-external-integration-foundation (US-17, US-1)

Hammers the Loki HTTP push endpoint with a configurable burst
rate (default 500 events/sec) and measures:

  - Accept rate (Loki returns 204 on success)
  - 429 rate (rate limited — indicates we need batching or
    client-side throttling in dk-data-client)
  - 5xx rate (Loki or ingress is struggling)

If we cannot sustain 5,000 events/sec (5 consumers × 1,000 events/sec
headroom), the adapter v1.1 roadmap MUST include an ndjson batching
step; record the finding in `docs/reports/loki-push-capacity.md`.

## Usage

    export LOKI_PUSH_URL=https://loki.behaviorlabs.ai/loki/api/v1/push
    python -m tests.load.loki_push --eps 500 --duration 120

Exit codes:
    0  everything within tolerance
    1  sustained 429s (need batching)
    2  sustained 5xx (Loki infrastructure issue)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    print("httpx required — run inside the feature 002 venv")
    sys.exit(2)


def build_payload(i: int) -> dict[str, Any]:
    ts_ns = str(int(time.time() * 1_000_000_000))
    return {
        "streams": [
            {
                "stream": {
                    "app": "adapter-telemetry",
                    "client": "load-test",
                    "method": "molecules.get",
                    "outcome": "miss",
                },
                "values": [
                    [
                        ts_ns,
                        json.dumps(
                            {
                                "ts": int(time.time()),
                                "args_hash": f"sha256:loadtest{i:08d}",
                                "latency_ms": 42,
                                "cache_tier": "none",
                            }
                        ),
                    ]
                ],
            }
        ]
    }


async def pusher(
    client: httpx.AsyncClient,
    url: str,
    stop_at: float,
    events_per_sec: float,
    tally: dict[str, int],
) -> None:
    interval = 1.0 / events_per_sec
    i = 0
    while time.monotonic() < stop_at:
        tick = time.monotonic()
        try:
            resp = await client.post(
                url,
                json=build_payload(i),
                headers={"Content-Type": "application/json"},
            )
            sc = resp.status_code
            if 200 <= sc < 300:
                tally["success"] += 1
            elif sc == 429:
                tally["rate_limited"] += 1
            elif sc >= 500:
                tally["server_error"] += 1
            else:
                tally["other"] += 1
        except httpx.HTTPError:
            tally["transport_error"] += 1
        i += 1
        sleep_for = interval - (time.monotonic() - tick)
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)


async def run(url: str, eps: int, duration: int, concurrency: int) -> dict[str, Any]:
    tally = {
        "success": 0,
        "rate_limited": 0,
        "server_error": 0,
        "transport_error": 0,
        "other": 0,
    }
    stop_at = time.monotonic() + duration
    per_worker = eps / concurrency
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=5.0, limits=limits) as client:
        workers = [
            asyncio.create_task(pusher(client, url, stop_at, per_worker, tally))
            for _ in range(concurrency)
        ]
        await asyncio.gather(*workers, return_exceptions=True)
    total = sum(tally.values())
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "target_eps": eps,
        "duration_seconds": duration,
        "concurrency": concurrency,
        "total_pushes": total,
        **tally,
        "success_rate": tally["success"] / max(total, 1),
        "rate_limited_rate": tally["rate_limited"] / max(total, 1),
        "server_error_rate": tally["server_error"] / max(total, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Loki push rate limit driver")
    parser.add_argument("--url", default=os.environ.get("LOKI_PUSH_URL", ""))
    parser.add_argument("--eps", type=int, default=500, help="target events/sec")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()
    if not args.url:
        print("LOKI_PUSH_URL is required", file=sys.stderr)
        return 2

    summary = asyncio.run(
        run(args.url, args.eps, args.duration, args.concurrency)
    )
    os.makedirs("docs/reports", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = f"docs/reports/loki-push-{ts}.json"
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"wrote {report_path}")
    print(
        f"total={summary['total_pushes']}  "
        f"success={summary['success_rate']:.2%}  "
        f"429={summary['rate_limited_rate']:.2%}  "
        f"5xx={summary['server_error_rate']:.2%}"
    )
    if summary["server_error_rate"] > 0.01:
        return 2
    if summary["rate_limited_rate"] > 0.05:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
