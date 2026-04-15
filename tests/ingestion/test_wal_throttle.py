"""Tests for src/dk_data/ingestion/wal_throttle.py.

Stage 4 (T054, T055) of 005-prestaged-hydration. Mocks the psycopg2
connection and time.sleep so tests are pure-CPU and deterministic.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from dk_data.ingestion.wal_throttle import (
    DEFAULT_CHUNK_SIZE,
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
# wal_pressure: simple SQL-result mapping
# ---------------------------------------------------------------------------


def test_wal_pressure_returns_pct_used_from_most_recent_row() -> None:
    """wal_pressure issues `SELECT pct_used … LIMIT 1` and returns it."""
    cur = MagicMock()
    cur.fetchone.return_value = (62.5,)
    cur.__enter__.return_value = cur

    conn = MagicMock()
    conn.cursor.return_value = cur

    assert wal_pressure(conn) == 62.5
    cur.execute.assert_called_once()
    sql = cur.execute.call_args.args[0]
    assert "meta.wal_usage" in sql and "ORDER BY observed_at DESC" in sql


def test_wal_pressure_returns_zero_when_view_empty() -> None:
    """No observations yet → fail-open with 0.0."""
    cur = MagicMock()
    cur.fetchone.return_value = None
    cur.__enter__.return_value = cur
    conn = MagicMock()
    conn.cursor.return_value = cur

    assert wal_pressure(conn) == 0.0


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
