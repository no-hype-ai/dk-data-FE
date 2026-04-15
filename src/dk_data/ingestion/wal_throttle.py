"""WAL-aware throttling for 005-prestaged-hydration (US3).

Reads the existing ``meta.wal_usage`` view (added in commit 3b1c1e7) to
keep PostgreSQL WAL pressure deterministic during multi-GB restores.
The 5 tables in :data:`load_order.WAL_MODE_TABLES` route through the
:class:`WalThrottle.maybe_pause` gate before each ``pg_restore`` so a
busy checkpointer cannot collide with a fresh 7 GB write.

Active tag: ``[WALBUD]``.

Public API:
  - :func:`wal_pressure` — one-shot percentage read.
  - :class:`WalThrottle` — stateful gate with chunk-size downshift after
    repeated pauses (FR-008).

The module deliberately does no I/O at import time and never calls
``time.sleep`` directly — the sleep function is injectable so tests
need not actually wait. See ``tests/ingestion/test_wal_throttle.py``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


# ---------------------------------------------------------------------------
# Defaults — overridable by env vars in the CLI (FR-007/FR-008)
# ---------------------------------------------------------------------------

DEFAULT_HIGH_PCT = 70.0
DEFAULT_LOW_PCT = 40.0
DEFAULT_DOWNSHIFT_THRESHOLD = 2
DEFAULT_BUDGET_SECONDS = 600
DEFAULT_POLL_INTERVAL_S = 30.0
DEFAULT_CHUNK_SIZE = 5000


class _LoggerLike(Protocol):
    def info(self, msg: str, *args: Any) -> None: ...
    def warning(self, msg: str, *args: Any) -> None: ...


# ---------------------------------------------------------------------------
# T050 — wal_pressure: single-row read of meta.wal_usage
# ---------------------------------------------------------------------------

def wal_pressure(conn: Any) -> float:
    """Return the most recent ``pct_used`` from ``meta.wal_usage``.

    Returns ``0.0`` when the view has no observations yet — this fail-open
    behavior matches the existing ``wal_budget.py:headroom_check`` pattern
    (no observation ⇒ assume safe to write). Callers that need stronger
    guarantees should query the view directly.

    Args:
        conn: a psycopg2 connection. Caller owns transaction state.

    Returns:
        Float percentage in ``[0.0, 100.0]``. Higher means more WAL
        consumed of the configured ``max_wal_size`` budget.
    """
    sql = """
        SELECT pct_used
          FROM meta.wal_usage
         ORDER BY observed_at DESC
         LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    if row is None or row[0] is None:
        return 0.0
    return float(row[0])


# ---------------------------------------------------------------------------
# T051 + T053 — WalThrottle: stateful gate with downshift
# ---------------------------------------------------------------------------

@dataclass
class WalThrottle:
    """Stateful WAL-pressure gate. One instance per hydration run.

    Usage::

        throttle = WalThrottle(conn=psycopg_conn)
        for step in plan.sources:
            if step.wal_mode:
                throttle.maybe_pause()
            ...

    The instance carries:
      - ``chunk_size``: starts at ``DEFAULT_CHUNK_SIZE`` (5_000); halves
        every time ``downshift_threshold`` consecutive pauses fire (FR-008).
        Floor of 250 to avoid degenerating to per-row commits.
      - ``consecutive_pauses``: count since the last call that did NOT pause.
      - ``budget_remaining_s``: cumulative pause budget; once exhausted,
        :meth:`maybe_pause` logs a warning and returns immediately so the
        run does not deadlock waiting for a checkpointer that may have
        stalled.

    All non-trivial work happens in :meth:`maybe_pause`. The pure-read
    :func:`wal_pressure` is exposed separately for callers who want a
    one-shot snapshot without state mutation.
    """

    conn: Any
    high_pct: float = DEFAULT_HIGH_PCT
    low_pct: float = DEFAULT_LOW_PCT
    downshift_threshold: int = DEFAULT_DOWNSHIFT_THRESHOLD
    budget_s: int = DEFAULT_BUDGET_SECONDS
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S
    chunk_size: int = DEFAULT_CHUNK_SIZE
    consecutive_pauses: int = 0
    budget_remaining_s: float = field(init=False)

    # Injection points (defaulted for prod, overridden in tests)
    sleep_fn: Callable[[float], None] = field(default=time.sleep)
    pressure_fn: Callable[[Any], float] = field(default=wal_pressure)
    logger: _LoggerLike | None = None

    # Floor so chunk_size cannot collapse to nothing.
    chunk_size_floor: int = 250

    def __post_init__(self) -> None:
        self.budget_remaining_s = float(self.budget_s)
        if self.logger is None:
            from loguru import logger as _l
            self.logger = _l

    # ------------------------------------------------------------------
    def maybe_pause(self) -> bool:
        """Block until WAL pressure drops below :attr:`low_pct`, or until
        the run-level pause budget is exhausted.

        Returns:
            True when the call actually paused (pressure was above
            :attr:`high_pct` on entry); False when no wait was needed.

        Side effects:
          - ``consecutive_pauses`` increments on a True return; resets
            to 0 on False.
          - ``chunk_size`` halves (floored at :attr:`chunk_size_floor`)
            once ``consecutive_pauses`` reaches ``downshift_threshold``;
            the counter then resets to 0 so the next downshift requires
            another full sequence.
          - ``budget_remaining_s`` decreases by every actual sleep.
        """
        assert self.logger is not None  # __post_init__ sets it
        log = self.logger

        pressure = self.pressure_fn(self.conn)
        if pressure < self.high_pct:
            self.consecutive_pauses = 0
            return False

        log.warning(
            f"WAL pressure {pressure:.1f}% >= high_pct={self.high_pct:.1f}% "
            f"— pausing until <{self.low_pct:.1f}%"
        )

        # Poll until pressure drops below low_pct or budget runs out.
        while pressure >= self.low_pct:
            if self.budget_remaining_s <= 0:
                log.warning(
                    f"WAL pause budget exhausted (last pressure={pressure:.1f}%) "
                    f"— proceeding without further wait"
                )
                break
            wait = min(self.poll_interval_s, self.budget_remaining_s)
            self.sleep_fn(wait)
            self.budget_remaining_s -= wait
            pressure = self.pressure_fn(self.conn)
            log.info(
                f"WAL pressure now {pressure:.1f}% "
                f"(budget left {self.budget_remaining_s:.0f}s)"
            )

        self.consecutive_pauses += 1
        if self.consecutive_pauses >= self.downshift_threshold:
            old = self.chunk_size
            self.chunk_size = max(self.chunk_size_floor, self.chunk_size // 2)
            log.warning(
                f"Two consecutive WAL pauses — halving chunk_size {old} -> {self.chunk_size}"
            )
            self.consecutive_pauses = 0
        return True
