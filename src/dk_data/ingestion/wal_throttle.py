"""WAL-aware throttling for 005-prestaged-hydration (US3).

Queries the ``meta.wal_pressure`` view (added by migration 231 —
Horizon 2 / plan §C.2) to keep PostgreSQL WAL pressure deterministic
during multi-GB restores. The 5 tables in
:data:`load_order.WAL_MODE_TABLES` route through the
:class:`WalThrottle.maybe_pause` gate before each ``pg_restore`` so a
busy checkpointer cannot collide with a fresh 7 GB write.

Active tag: ``[WALBUD]``.

Public API:
  - :func:`wal_pressure` — one-shot percentage read of
    ``meta.wal_pressure.pct_used``. Fails open (returns 0.0) if the
    view is missing or the query errors, so the throttle degrades to a
    no-op rather than blocking the run on an observability gap.
  - :class:`WalThrottle` — stateful gate with chunk-size downshift
    (FR-008), run-level pause budget, and per-source pause budget.

The module deliberately does no I/O at import time and never calls
``time.sleep`` directly — the sleep function is injectable so tests
need not actually wait. See ``tests/ingestion/test_wal_throttle.py``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

# Metric is defined in src/dk_data/observability/metrics.py (added for
# plan §C.2). Imported lazily inside the method that emits it so this
# module stays import-safe in contexts without prometheus_client.


# ---------------------------------------------------------------------------
# Defaults — overridable by env vars in the CLI (FR-007/FR-008)
# ---------------------------------------------------------------------------

DEFAULT_HIGH_PCT = 70.0
DEFAULT_LOW_PCT = 40.0
DEFAULT_DOWNSHIFT_THRESHOLD = 2
DEFAULT_BUDGET_SECONDS = 600
# Per-source cap — one bad source can't drain the whole run's budget.
# Default is half the typical p95 run-level pause so pathological
# pressure on one source leaves headroom for the rest of the run.
DEFAULT_PER_SOURCE_BUDGET_SECONDS = 180
DEFAULT_POLL_INTERVAL_S = 30.0
DEFAULT_CHUNK_SIZE = 5000


class _LoggerLike(Protocol):
    def info(self, msg: str, *args: Any) -> None: ...
    def warning(self, msg: str, *args: Any) -> None: ...
    def debug(self, msg: str, *args: Any) -> None: ...


# Sentinel so we only emit the view-missing DEBUG line once per process.
_VIEW_MISSING_LOGGED = False


# ---------------------------------------------------------------------------
# wal_pressure — single-row read of meta.wal_pressure (plan §C.2)
# ---------------------------------------------------------------------------

def wal_pressure(conn: Any) -> float:
    """Return live WAL pressure as a percentage in [0, 100].

    Reads one row from ``meta.wal_pressure`` (migration 231). The view
    computes ``100 * bytes_since_last_checkpoint / max_wal_size``, so a
    value of 70 means WAL has consumed 70% of the configured ceiling
    since the last checkpoint.

    Fail-open semantics (plan §C.2 hard constraint):
      * Missing view (``UndefinedTable`` / ``UndefinedObject``) — a
        DEBUG line is logged ONCE per process; subsequent calls return
        0.0 silently. This is the expected state on a DB that hasn't
        had migration 231 applied yet.
      * Empty result — return 0.0 (view should always return one row,
        but be defensive).
      * Any other DB error — return 0.0. We never let the throttle take
        down the hydration run; the worst case is a no-op gate, and
        that degrades to the pre-migration-231 behaviour.

    Args:
        conn: a psycopg2 connection. Caller owns transaction state.
            We use ``autocommit``-friendly read-only SELECTs with no
            side effects, and roll back on error to leave the caller's
            transaction in a clean state.

    Returns:
        The ``pct_used`` value from ``meta.wal_pressure``, or 0.0 on
        empty result / DB error / missing view.
    """
    global _VIEW_MISSING_LOGGED

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pct_used FROM meta.wal_pressure LIMIT 1")
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — fail-open by design
        # Try to leave the connection transaction state clean. psycopg2
        # leaves the connection in an aborted transaction after an
        # UndefinedTable error, and subsequent queries on the same
        # connection fail until a rollback.
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        _maybe_log_missing_view(exc)
        return 0.0

    if not row:
        return 0.0
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return 0.0


def _maybe_log_missing_view(exc: BaseException) -> None:
    """Log once per process when ``meta.wal_pressure`` isn't present.

    Broader DB errors also land here. We emit at DEBUG because the
    throttle's fail-open behaviour is intentional and not something
    operators should see in INFO logs every poll cycle.
    """
    global _VIEW_MISSING_LOGGED
    if _VIEW_MISSING_LOGGED:
        return
    _VIEW_MISSING_LOGGED = True
    try:
        from loguru import logger as _l
        _l.debug(
            "meta.wal_pressure query failed — throttle degrading to no-op "
            f"(err={type(exc).__name__}: {exc})"
        )
    except Exception:  # noqa: BLE001 — never crash on logger import
        pass


# ---------------------------------------------------------------------------
# WalThrottle: stateful gate with downshift + per-source budget (plan §C.2)
# ---------------------------------------------------------------------------

@dataclass
class WalThrottle:
    """Stateful WAL-pressure gate. One instance per hydration run.

    Usage::

        throttle = WalThrottle(conn=psycopg_conn)
        for step in plan.sources:
            if step.wal_mode:
                throttle.maybe_pause(source_id=step.source_id)
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
      - ``per_source_budget_s`` + ``_per_source_consumed_s``: per-source
        pause cap (plan §C.2). Once a single source has consumed its
        share, subsequent ``maybe_pause(source_id=that_source)`` calls
        skip the pause (return False) and increment
        ``dk_wal_source_budget_exhausted_total{source}``. Pauses for
        OTHER source_ids still honour the global budget.
      - ``_paused_state``: last recorded paused/running state for
        transition-based INFO logging (plan §C.2).

    All non-trivial work happens in :meth:`maybe_pause`. The pure-read
    :func:`wal_pressure` is exposed separately for callers who want a
    one-shot snapshot without state mutation.
    """

    conn: Any
    high_pct: float = DEFAULT_HIGH_PCT
    low_pct: float = DEFAULT_LOW_PCT
    downshift_threshold: int = DEFAULT_DOWNSHIFT_THRESHOLD
    budget_s: int = DEFAULT_BUDGET_SECONDS
    per_source_budget_s: int = DEFAULT_PER_SOURCE_BUDGET_SECONDS
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

    # Per-source cumulative pause tracking. Keyed by source_id; values
    # are seconds of pause consumed for that source across the run.
    _per_source_consumed_s: dict[str, float] = field(default_factory=dict)
    # Set of source_ids we've already emitted the budget-exhausted metric
    # for — prevents the counter from double-counting a single exhaustion
    # event across many subsequent calls for the same source.
    _budget_exhausted_sources: set[str] = field(default_factory=set)
    # Transition state for INFO logging. True = last observation was
    # "paused", False = "running", None = no prior observation.
    _last_paused_state: Optional[bool] = None

    def __post_init__(self) -> None:
        self.budget_remaining_s = float(self.budget_s)
        if self.logger is None:
            from loguru import logger as _l
            self.logger = _l

    # ------------------------------------------------------------------
    def maybe_pause(self, source_id: Optional[str] = None) -> bool:
        """Block until WAL pressure drops below :attr:`low_pct`, or until
        a pause budget is exhausted.

        Args:
            source_id: optional identifier of the source currently being
                restored. When provided, per-source pause consumption is
                tracked and capped by :attr:`per_source_budget_s`. When
                ``None``, only the global budget applies (preserves the
                pre-§C.2 calling convention).

        Returns:
            True when the call actually paused (pressure was above
            :attr:`high_pct` on entry and we slept at least once); False
            otherwise (no pressure, per-source budget already exhausted,
            etc.).

        Side effects:
          - ``consecutive_pauses`` increments on a True return; resets
            to 0 on False.
          - ``chunk_size`` halves (floored at :attr:`chunk_size_floor`)
            once ``consecutive_pauses`` reaches ``downshift_threshold``;
            the counter then resets to 0 so the next downshift requires
            another full sequence.
          - ``budget_remaining_s`` decreases by every actual sleep.
          - ``_per_source_consumed_s[source_id]`` increases by every
            actual sleep when ``source_id`` is provided.
          - On state transition (running → paused or paused → running)
            an INFO line records the observed pct_used (plan §C.2).
          - On first exhaustion of a source's budget, increments the
            ``dk_wal_source_budget_exhausted_total{source}`` counter.
        """
        assert self.logger is not None  # __post_init__ sets it
        log = self.logger

        pressure = self.pressure_fn(self.conn)

        # Per-source budget gate — if this source has already burned its
        # share, skip the pause entirely. Still record the transition
        # so observers see the source racing through.
        if (
            source_id is not None
            and self._per_source_consumed_s.get(source_id, 0.0)
            >= self.per_source_budget_s
        ):
            self._record_transition(running=True, pressure=pressure)
            self.consecutive_pauses = 0
            return False

        if pressure < self.high_pct:
            self._record_transition(running=True, pressure=pressure)
            self.consecutive_pauses = 0
            return False

        self._record_transition(running=False, pressure=pressure)
        log.warning(
            f"WAL pressure {pressure:.1f}% >= high_pct={self.high_pct:.1f}% "
            f"— pausing until <{self.low_pct:.1f}%"
            + (f" (source={source_id})" if source_id else "")
        )

        # Poll until pressure drops below low_pct or a budget runs out.
        while pressure >= self.low_pct:
            if self.budget_remaining_s <= 0:
                log.warning(
                    f"WAL pause budget exhausted (last pressure={pressure:.1f}%) "
                    f"— proceeding without further wait"
                )
                break
            # Per-source check — stop pausing for THIS source only.
            if (
                source_id is not None
                and self._per_source_consumed_s.get(source_id, 0.0)
                >= self.per_source_budget_s
            ):
                log.warning(
                    "WAL per-source pause budget exhausted "
                    f"(source={source_id}, consumed="
                    f"{self._per_source_consumed_s.get(source_id, 0.0):.0f}s, "
                    f"cap={self.per_source_budget_s}s) — proceeding without further wait"
                )
                self._mark_source_budget_exhausted(source_id)
                break

            # Wait is bounded by whichever budget is tighter.
            wait = min(self.poll_interval_s, self.budget_remaining_s)
            if source_id is not None:
                remaining_source = (
                    self.per_source_budget_s
                    - self._per_source_consumed_s.get(source_id, 0.0)
                )
                wait = min(wait, max(remaining_source, 0.0))
            if wait <= 0:
                # No budget left anywhere; the guards above should catch
                # this, but be defensive.
                break

            self.sleep_fn(wait)
            self.budget_remaining_s -= wait
            if source_id is not None:
                self._per_source_consumed_s[source_id] = (
                    self._per_source_consumed_s.get(source_id, 0.0) + wait
                )
            pressure = self.pressure_fn(self.conn)
            log.info(
                f"WAL pressure now {pressure:.1f}% "
                f"(budget left {self.budget_remaining_s:.0f}s)"
                + (
                    f" (source={source_id} consumed="
                    f"{self._per_source_consumed_s.get(source_id, 0.0):.0f}s)"
                    if source_id
                    else ""
                )
            )

        # On exit, update transition state based on final pressure.
        self._record_transition(running=pressure < self.high_pct, pressure=pressure)

        self.consecutive_pauses += 1
        if self.consecutive_pauses >= self.downshift_threshold:
            old = self.chunk_size
            self.chunk_size = max(self.chunk_size_floor, self.chunk_size // 2)
            log.warning(
                f"Two consecutive WAL pauses — halving chunk_size {old} -> {self.chunk_size}"
            )
            self.consecutive_pauses = 0
        return True

    # ------------------------------------------------------------------
    def _record_transition(self, *, running: bool, pressure: float) -> None:
        """Emit an INFO log line on every paused ↔ running transition.

        ``running=True`` means "below high_pct, throttle is not holding
        back the restore". ``running=False`` means "pressure observed
        at or above high_pct and we are about to / did pause".

        Called at the start of every ``maybe_pause`` so operators see
        each edge exactly once (plan §C.2 requirement: log every state
        transition at INFO).
        """
        assert self.logger is not None
        paused = not running
        if self._last_paused_state is None:
            # First observation — record the state but don't log; there
            # is nothing to transition from.
            self._last_paused_state = paused
            return
        if paused == self._last_paused_state:
            return
        self._last_paused_state = paused
        label = "paused" if paused else "running"
        self.logger.info(
            f"WAL throttle transition -> {label} (pct_used={pressure:.1f}%)"
        )

    # ------------------------------------------------------------------
    def _mark_source_budget_exhausted(self, source_id: str) -> None:
        """Increment the source-budget-exhausted counter exactly once
        per (run, source). Subsequent exhaustion events for the same
        source in this run are a no-op — the counter is a "did it
        happen" signal, not a pause-count signal.
        """
        if source_id in self._budget_exhausted_sources:
            return
        self._budget_exhausted_sources.add(source_id)
        try:
            from dk_data.observability.metrics import (
                DK_WAL_SOURCE_BUDGET_EXHAUSTED_TOTAL,
            )
            DK_WAL_SOURCE_BUDGET_EXHAUSTED_TOTAL.labels(source=source_id).inc()
        except Exception:  # noqa: BLE001 — never crash on metrics emission
            # In tests and environments without prometheus_client,
            # silently swallow. The log line above already records the
            # event; the counter is the machine-readable twin.
            pass
