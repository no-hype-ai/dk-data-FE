"""Single-flight (thundering-herd) coalescing for dk-data-client.

Feature: 002-external-integration-foundation (perf pass)

When N coroutines concurrently miss the same cache key, only ONE of
them should actually call the server — the other N-1 should wait for
the first call to finish and reuse its result. This is the classic
"thundering herd" fix.

Why it matters: imagine 20 concurrent consumers asking for
`molecules.getProfile("CHEMBL25")` at T=0, with a cold cache. Without
single-flight: 20 HTTP requests → 20 PostgREST connections → 20
Postgres rows read. With single-flight: 1 HTTP request → 19 waiters
get the same result for free.

Under sustained load on a single hot key (admin-app dashboard with
100 browser tabs open), single-flight can cut effective server RPS
by 10-100×. This is the single biggest per-request optimization
available to the client.

Implementation detail: we use an asyncio.Task rather than a bare
Future because a Task naturally retrieves its own exception (which
avoids "Task exception was never retrieved" warnings for single
callers) and handles cancellation semantics correctly. The first
caller becomes the owner of the Task; any other caller with the
same key awaits the Task directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class SingleFlight:
    """Deduplicate concurrent calls for the same key.

    `do(key, fn)` invokes `fn()` exactly once per key at any given
    time. Subsequent callers with the same key while the first call
    is in flight await the first caller's result.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Task[Any]] = {}

    async def do(
        self,
        key: str,
        fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Call `fn()` if no other call for `key` is in flight, else wait.

        The first caller creates a Task that runs `fn()`. Every other
        caller arriving while the Task is pending awaits the same
        Task and gets the same result (or the same exception).
        """
        pending = self._pending.get(key)
        if pending is not None and not pending.done():
            # Another call is already in flight. Wait for it without
            # shielding — if the first caller is cancelled, waiters
            # propagate the cancellation (they can then retry if they
            # care).
            return await pending

        # First caller — schedule a task and register it.
        task: asyncio.Task[Any] = asyncio.create_task(fn())
        self._pending[key] = task
        try:
            return await task
        finally:
            # Clean up regardless of outcome so the next caller
            # starts a fresh attempt. The task's result/exception is
            # already observed by the `await task` above, so Python
            # does NOT emit a "Task exception was never retrieved"
            # warning even if fn() raised.
            self._pending.pop(key, None)

    def active_count(self) -> int:
        """Number of keys currently in flight. Used for metrics / debug."""
        return len([t for t in self._pending.values() if not t.done()])
