"""Per-consumer concurrency guard for the metering proxy.

Feature: 002-external-integration-foundation (perf pass)

Why this exists: rate-limiting by RPM alone does NOT protect the
Postgres connection pool. A consumer with `rpm_limit=500` running
5 replicas × 10 concurrent requests each can legitimately keep
50 PostgREST connections busy on slow queries — enough to stall
the whole pool (`PGRST_DB_POOL=30` per replica). The semaphore
here caps simultaneous in-flight requests per consumer, which is
the metric that actually correlates with pool pressure.

On a saturated consumer, new requests return **503** with a
`Retry-After` header instead of queueing. 503 is a load-shedding
signal the client understands: it triggers the client's own
single-flight coalescing (drop duplicate work) and avoids queuing
requests inside the proxy (which would convert a fast 503 into a
slow 504 and make the problem worse).

Thread-safe via asyncio.Semaphore. One semaphore per consumer
alias, lazily created.
"""

from __future__ import annotations

import asyncio
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
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._active_counts: dict[str, int] = {}

    def _get_semaphore(self, consumer: str, max_in_flight: int) -> asyncio.Semaphore:
        if consumer not in self._semaphores:
            self._semaphores[consumer] = asyncio.Semaphore(max_in_flight)
            self._active_counts[consumer] = 0
        return self._semaphores[consumer]

    @asynccontextmanager
    async def acquire(
        self, consumer: str, max_in_flight: int
    ) -> AsyncIterator[bool]:
        """Try to reserve one slot. Yields True on success, False if saturated.

        Fail-fast — does not block. The yielded bool is the signal
        to the caller that the request should be rejected with 503.
        """
        sem = self._get_semaphore(consumer, max_in_flight)
        acquired = False
        try:
            # Non-blocking acquire via locked() check. If the semaphore
            # has a free slot, we grab it; otherwise we fail-fast with
            # acquired=False so the caller can return 503 immediately.
            try:
                # asyncio.Semaphore doesn't have a true "try_acquire",
                # but wait_for with timeout=0 is equivalent and portable.
                await asyncio.wait_for(sem.acquire(), timeout=0.001)
                acquired = True
                self._active_counts[consumer] = (
                    self._active_counts.get(consumer, 0) + 1
                )
            except asyncio.TimeoutError:
                acquired = False
            yield acquired
        finally:
            if acquired:
                sem.release()
                self._active_counts[consumer] = max(
                    0, self._active_counts.get(consumer, 0) - 1
                )

    def active_count(self, consumer: str) -> int:
        """Current in-flight request count for a consumer."""
        return self._active_counts.get(consumer, 0)

    def all_active_counts(self) -> dict[str, int]:
        """Snapshot of every consumer's active count. Used by /metrics."""
        return dict(self._active_counts)
