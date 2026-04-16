"""Tests for src/dk_data/ingestion/wal_throttle.py.

Stage 4 (T054, T055) of 005-prestaged-hydration — original tests kept.
Horizon 2 / plan §C.2 — new tests for the meta.wal_pressure query path,
hysteresis edge behaviour, and per-source pause budget.

Mocks the psycopg2 connection and time.sleep so tests are pure-CPU and
deterministic.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

import dk_data.ingestion.wal_throttle as wal_throttle_module
from dk_data.ingestion.wal_throttle import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_PER_SOURCE_BUDGET_SECONDS,
    WalThrottle,
    wal_pressure,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakePressureFn:
    """Returns successive values from a queue. Pads with the last value
    once the queue is exhausted so tests need not over-specify."""

    def __init__(self, values: list[float]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self, _conn: Any) -> float:
        self.calls += 1
        if not self.values:
            return 0.0
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


class _FakeSleep:
    def __init__(self) -> None:
        self.total = 0.0
        self.calls: list[float] = []

    def __call__(self, secs: float) -> None:
        self.calls.append(secs)
        self.total += secs


def _make_throttle(
    pressures: list[float],
    *,
    high_pct: float = 70.0,
    low_pct: float = 40.0,
    downshift_threshold: int = 2,
    budget_s: int = 600,
    poll_interval_s: float = 30.0,
) -> tuple[WalThrottle, _FakeSleep, _FakePressureFn]:
    sleep = _FakeSleep()
    pressure = _FakePressureFn(pressures)
    t = WalThrottle(
        conn=MagicMock(),
        high_pct=high_pct,
        low_pct=low_pct,
        downshift_threshold=downshift_threshold,
        budget_s=budget_s,
        poll_interval_s=poll_interval_s,
        sleep_fn=sleep,
        pressure_fn=pressure,
        logger=logging.getLogger("test"),
    )
    return t, sleep, pressure


# ---------------------------------------------------------------------------
# wal_pressure: reads meta.wal_pressure view (plan §C.2 / FR-007)
# ---------------------------------------------------------------------------


def _make_conn_returning(row: Any) -> MagicMock:
    """Build a MagicMock psycopg2-style conn whose cursor().fetchone()
    returns ``row``. Context-manager compatible.
    """
    cur = MagicMock()
    cur.fetchone.return_value = row
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


@pytest.fixture(autouse=True)
def _reset_view_missing_flag() -> None:
    """Clear the once-per-process "view missing" sentinel so each test
    gets a fresh state. Tests that exercise the DEBUG log path rely on
    this."""
    wal_throttle_module._VIEW_MISSING_LOGGED = False
    yield
    wal_throttle_module._VIEW_MISSING_LOGGED = False


def test_wal_pressure_happy_path_returns_view_value() -> None:
    """View returns (55.0,) → wal_pressure returns 55.0 as float."""
    conn = _make_conn_returning((55.0,))
    assert wal_pressure(conn) == 55.0
    # Confirm the query actually hit meta.wal_pressure
    conn.cursor.assert_called_once()
    cur = conn.cursor.return_value
    called_sql = cur.execute.call_args.args[0]
    assert "meta.wal_pressure" in called_sql
    assert "pct_used" in called_sql


def test_wal_pressure_returns_zero_when_view_empty() -> None:
    """No observations yet (fetchone → None) → fail-open with 0.0."""
    conn = _make_conn_returning(None)
    assert wal_pressure(conn) == 0.0


def test_wal_pressure_returns_zero_on_db_error() -> None:
    """Any DB error (missing view, connection drop, etc.) → 0.0.

    The throttle must never leak exceptions back to callers; the worst
    case is a no-op gate. Rollback is best-effort so the caller's
    transaction state isn't left aborted.
    """
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("relation \"meta.wal_pressure\" does not exist")
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cur

    assert wal_pressure(conn) == 0.0
    # Best-effort rollback should have been attempted.
    conn.rollback.assert_called_once()


def test_wal_pressure_casts_numeric_to_float() -> None:
    """View returns a Decimal (psycopg2 default for NUMERIC) → float."""
    from decimal import Decimal
    conn = _make_conn_returning((Decimal("72.50"),))
    assert wal_pressure(conn) == 72.5


# ---------------------------------------------------------------------------
# T054: injected 80% WAL → maybe_pause waits until simulated drop below 40%
# ---------------------------------------------------------------------------


def test_maybe_pause_blocks_until_pressure_drops_below_low_pct() -> None:
    """Sequence: 80% (above high) → 65% (above low, keep waiting)
    → 35% (below low, exit). Expect 2 sleep calls and a True return."""
    t, sleep, pressure = _make_throttle(
        pressures=[80.0, 65.0, 35.0],
        poll_interval_s=10.0,
    )

    paused = t.maybe_pause()

    assert paused is True
    # wal_pressure called: 1 entry check (80%) + N polls (65%, 35%)
    assert pressure.calls == 3
    # Two sleeps because pressure didn't drop below 40 until the third read
    assert len(sleep.calls) == 2
    assert sleep.total == 20.0
    assert t.budget_remaining_s == pytest.approx(580.0)
    assert t.consecutive_pauses == 1


def test_maybe_pause_no_op_when_pressure_below_high_pct() -> None:
    """50% < high_pct(70) ⇒ return False, no sleep, reset
    consecutive_pauses."""
    t, sleep, pressure = _make_throttle(pressures=[50.0])

    # Prime the counter to confirm reset behavior.
    t.consecutive_pauses = 1

    paused = t.maybe_pause()
    assert paused is False
    assert sleep.calls == []
    assert pressure.calls == 1
    assert t.consecutive_pauses == 0


def test_maybe_pause_respects_budget_exhaustion() -> None:
    """When pressure stays high forever, budget caps the wait and we
    proceed (logged warning) without deadlocking."""
    # Pressure never drops; pad with the last value
    t, sleep, _ = _make_throttle(
        pressures=[90.0],
        budget_s=25,
        poll_interval_s=10.0,
    )

    paused = t.maybe_pause()
    assert paused is True
    # 10 + 10 + 5 = 25 (last sleep clipped to remaining budget)
    assert sleep.total == 25.0
    assert t.budget_remaining_s == 0


# ---------------------------------------------------------------------------
# T055: two consecutive pauses → chunk_size halves
# ---------------------------------------------------------------------------


def test_two_consecutive_pauses_halve_chunk_size() -> None:
    """downshift_threshold=2; first pause leaves chunk_size unchanged,
    second pause halves it and resets the counter."""
    t, _, _ = _make_throttle(
        pressures=[80.0, 35.0],  # one pause cycle's worth of readings
        downshift_threshold=2,
        poll_interval_s=10.0,
    )

    assert t.chunk_size == DEFAULT_CHUNK_SIZE  # 5000

    t.maybe_pause()
    assert t.chunk_size == DEFAULT_CHUNK_SIZE
    assert t.consecutive_pauses == 1

    # Reset the pressure_fn to give it another high→low sequence
    t.pressure_fn = _FakePressureFn([80.0, 35.0])

    t.maybe_pause()
    assert t.chunk_size == DEFAULT_CHUNK_SIZE // 2  # 2500
    # Counter resets after the downshift fires
    assert t.consecutive_pauses == 0


def test_chunk_size_floor_prevents_underflow() -> None:
    """Repeated halving floors at chunk_size_floor (default 250)."""
    t, _, _ = _make_throttle(pressures=[80.0, 35.0], downshift_threshold=1)
    t.chunk_size = 300

    # First pause: 300 // 2 = 150, but floor is 250
    t.maybe_pause()
    assert t.chunk_size == 250

    # Already at floor; another pause keeps it at 250
    t.pressure_fn = _FakePressureFn([80.0, 35.0])
    t.maybe_pause()
    assert t.chunk_size == 250


def test_no_pause_then_pause_resets_counter_correctly() -> None:
    """A no-pause call between two pauses must reset the counter so the
    halving requires a fresh consecutive sequence."""
    t, _, _ = _make_throttle(
        pressures=[80.0, 35.0],
        downshift_threshold=2,
    )

    # Pause #1 (counter -> 1)
    t.maybe_pause()
    assert t.consecutive_pauses == 1

    # No-pause call (counter -> 0)
    t.pressure_fn = _FakePressureFn([50.0])
    t.maybe_pause()
    assert t.consecutive_pauses == 0
    assert t.chunk_size == DEFAULT_CHUNK_SIZE

    # Pause #2 (counter -> 1, no halving)
    t.pressure_fn = _FakePressureFn([80.0, 35.0])
    t.maybe_pause()
    assert t.consecutive_pauses == 1
    assert t.chunk_size == DEFAULT_CHUNK_SIZE


# ---------------------------------------------------------------------------
# plan §C.2 — hysteresis transitions (70/40 edge behaviour)
# ---------------------------------------------------------------------------


def test_hysteresis_60_pct_does_not_pause() -> None:
    """Pressure at 60% is below high_pct(70) — no pause."""
    t, sleep, _ = _make_throttle(pressures=[60.0])
    assert t.maybe_pause() is False
    assert sleep.calls == []


def test_hysteresis_72_pct_triggers_pause() -> None:
    """Crossing the 70% high-water mark triggers a pause that runs
    until pressure falls below the 40% low-water mark."""
    # 72 → 68 (still above low) → 38 (below low, exit).
    t, sleep, pressure = _make_throttle(
        pressures=[72.0, 68.0, 38.0],
        poll_interval_s=10.0,
    )
    assert t.maybe_pause() is True
    assert pressure.calls == 3
    # Slept twice (for the two readings still above low_pct)
    assert len(sleep.calls) == 2


def test_hysteresis_stays_paused_at_68_then_resumes_at_38() -> None:
    """Between low(40) and high(70), an already-paused throttle keeps
    waiting — 68 is >= low_pct so we do not exit the wait loop. 38 is
    below low_pct so the loop exits and subsequent calls resume."""
    # First call: enter at 72, poll 68 (still waiting), poll 38 (exit).
    t, sleep, _ = _make_throttle(
        pressures=[72.0, 68.0, 38.0],
        poll_interval_s=10.0,
    )
    assert t.maybe_pause() is True
    assert len(sleep.calls) == 2  # two polls before 38 cleared

    # Second call: pressure is now stable at 38 (below high), no pause.
    t.pressure_fn = _FakePressureFn([38.0])
    assert t.maybe_pause() is False


def test_hysteresis_transition_logging_fires_once_per_edge(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Paused ↔ running transitions must log at INFO exactly once per
    edge (plan §C.2 requirement).
    """
    caplog.set_level(logging.INFO, logger="test")
    t, _, _ = _make_throttle(
        pressures=[80.0, 35.0],
        poll_interval_s=5.0,
    )

    # First call: no prior state → records state but does not log a
    # transition. After the pause, final pressure is 35 → running.
    t.maybe_pause()
    t.pressure_fn = _FakePressureFn([35.0])
    # Second call: running → running (no transition, no log).
    t.maybe_pause()
    # Third call: running → paused (1 transition log).
    t.pressure_fn = _FakePressureFn([80.0, 35.0])
    t.maybe_pause()

    transition_logs = [
        r for r in caplog.records
        if "WAL throttle transition" in r.getMessage()
    ]
    # We expect at least one transition in this sequence — exiting the
    # first pause (paused → running) and re-entering (running → paused).
    assert len(transition_logs) >= 1


# ---------------------------------------------------------------------------
# plan §C.2 — per-source pause budget
# ---------------------------------------------------------------------------


def test_per_source_budget_default_is_180s() -> None:
    """Regression guard — the plan pins the default at 180s."""
    assert DEFAULT_PER_SOURCE_BUDGET_SECONDS == 180


def test_per_source_budget_exhaustion_stops_pausing_for_that_source() -> None:
    """After a source has consumed its per-source budget, subsequent
    maybe_pause(source_id=that) calls must not pause — even if pressure
    is high — while a different source_id continues to pause normally.
    """
    # Per-source budget = 100s, global budget = 10000s (effectively
    # unbounded), poll_interval = 50s. First source burns 100s across
    # two polls; second source still has its own full budget.
    t, sleep, _ = _make_throttle(
        pressures=[80.0, 75.0, 70.0, 65.0, 35.0],
        budget_s=10_000,
        poll_interval_s=50.0,
    )
    t.per_source_budget_s = 100

    # Call #1: source_a at 80% → pauses. Budget caps at 100s → two
    # 50s polls, then the per-source cap triggers and the loop exits.
    paused = t.maybe_pause(source_id="source_a")
    assert paused is True
    # Per-source consumption should be at cap.
    assert t._per_source_consumed_s["source_a"] >= 100
    # Budget-exhausted counter fires exactly once for this source.
    assert "source_a" in t._budget_exhausted_sources

    # Call #2: source_a again at high pressure → NO pause (budget used).
    sleep.calls.clear()
    t.pressure_fn = _FakePressureFn([90.0])
    paused = t.maybe_pause(source_id="source_a")
    assert paused is False
    assert sleep.calls == []

    # Call #3: source_b at high pressure → still pauses (own budget).
    t.pressure_fn = _FakePressureFn([80.0, 35.0])
    paused = t.maybe_pause(source_id="source_b")
    assert paused is True
    assert t._per_source_consumed_s.get("source_b", 0.0) > 0
    # source_b did NOT hit its cap in this single pause.
    assert "source_b" not in t._budget_exhausted_sources


def test_per_source_budget_at_181s_stops_pausing() -> None:
    """Per the plan's example: after 181s pause for one source, the
    next call does not pause for that source but still pauses for a
    different one.
    """
    # Preload consumption above the default 180s cap for source_a.
    t, sleep, _ = _make_throttle(pressures=[90.0])
    t._per_source_consumed_s["source_a"] = 181.0

    # source_a: over-budget → no pause, no sleep.
    paused = t.maybe_pause(source_id="source_a")
    assert paused is False
    assert sleep.calls == []

    # source_b: untouched budget → pauses as normal.
    t.pressure_fn = _FakePressureFn([80.0, 35.0])
    paused = t.maybe_pause(source_id="source_b")
    assert paused is True


def test_per_source_budget_untracked_when_source_id_absent() -> None:
    """Calling maybe_pause() without source_id preserves the pre-§C.2
    behaviour — only the global budget applies, per-source dict stays
    empty.
    """
    t, _, _ = _make_throttle(
        pressures=[80.0, 35.0],
        poll_interval_s=5.0,
    )
    t.maybe_pause()  # no source_id
    assert t._per_source_consumed_s == {}
    assert t._budget_exhausted_sources == set()
