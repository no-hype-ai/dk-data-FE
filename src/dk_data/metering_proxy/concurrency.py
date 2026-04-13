"""Per-consumer concurrency guard for the metering proxy.

Feature: 002-external-integration-foundation (perf pass)

Why this exists: rate-limiting by RPM alone does NOT protect the
Postgres connection pool. A consumer with `rpm_limit=500` running
5 replicas × 10 concurrent requests each can legitimately keep
50 PostgREST connections busy on slow queries — enough to stall
the whole pool (`PGRST_DB_POOL=30` per replica). The guard here
caps simultaneous in-flight requests per consumer, which is the
metric that actually correlates with pool pressure.

On a saturated consumer, new requests return **503** with a
`Retry-After` header instead of queueing. 503 is a load-shedding
signal the client understands: it triggers the client's own
single-flight coalescing (drop duplicate work) and avoids queuing
requests inside the proxy (which would convert a fast 503 into a
slow 504 and make the problem worse).

Implementation note — counter not semaphore:
The previous implementation used `asyncio.wait_for(sem.acquire(), timeout=0.001)`.
This was functionally correct but added 1 ms of artificial latency per
caller (N callers × 1 ms = real hot-path overhead). asyncio.Semaphore
has no true non-blocking try-acquire API.

This version uses a plain integer counter.  In asyncio all coroutines
run on a single OS thread; context switches only happen at `await`
points.  Because there is no `await` between the counter read and the
counter increment below, no other coroutine can interleave — the check
and the increment are effectively atomic.  This gives us O(1) non-
blocking acquire with zero async overhead and correct isolation between
consumers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator


class ConsumerConcurrencyGuard:
    """Tracks per-consumer in-flight request counts.

    Usage:

        async with guard.acquire(consumer_alias, max_in_flight) as ok:
            if not ok:
                return 503_response()
            # ...do work...

    `acquire` returns immediately — it does NOT queue. This is
    deliberate load-shedding: a saturated proxy should fail fast
    so the client can back off, not pile up requests internally.
    """

    def __init__(self) -> None:
        # Plain int counter per consumer.  See module docstring for why
        # a counter is correct and faster than asyncio.Semaphore here.
        self._active: dict[str, int] = {}

    @asynccontextmanager
    async def acquire(
        self, consumer: str, max_in_flight: int
    ) -> AsyncIterator[bool]:
        """Try to reserve one slot. Yields True on success, False if saturated.

        Fail-fast — does not block. The yielded bool is the signal
        to the caller that the request should be rejected with 503.
        """
        current = self._active.get(consumer, 0)
        if current >= max_in_flight:
            yield False
            return

        # Claim the slot — no await between check and increment so this
        # is race-free within the single-threaded asyncio event loop.
        self._active[consumer] = current + 1
        try:
            yield True
        finally:
            self._active[consumer] = max(0, self._active.get(consumer, 0) - 1)

    def active_count(self, consumer: str) -> int:
        """Current in-flight request count for a consumer."""
        return self._active.get(consumer, 0)

    def all_active_counts(self) -> dict[str, int]:
        """Snapshot of every consumer's active count. Used by /metrics."""
        return dict(self._active)
