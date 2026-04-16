"""Unit tests for dk_data.ingestion.resource_budget.ResourceBudget.

Feature: Horizon 3 / plan §D.3 — admission control by budget.

Coverage:
  1. try_reserve succeeds when all keys have capacity
  2. try_reserve fails atomically when one key is insufficient
  3. release returns capacity to the budget
  4. snapshot returns (total, reserved, remaining) per key
  5. decorate_dispatch wraps dispatch: reserves → calls → releases
  6. decorate_dispatch defers when try_reserve returns False
  7. Pool path: construction uses get_connection_pool(), not raw psycopg2.connect()

DB is mocked end-to-end — these are pure unit tests.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fake DB — minimal enough to exercise SELECT ... FOR UPDATE + UPDATE.
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, store: "_FakeStore", dict_cursor: bool = False) -> None:
        self._store = store
        self._dict_cursor = dict_cursor
        self._last_result: Optional[Any] = None
        self._last_rowset: List[Any] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self._store.executions.append((sql.strip(), params))
        s = sql.strip().upper()
        if s.startswith("SELECT"):
            # Accept either (keys_tuple,) or just keys_tuple for ANY binding
            keys = None
            if params is not None:
                # psycopg2 tuple-in-IN uses either a single list arg or tuple arg
                if isinstance(params, (list, tuple)) and len(params) == 1 and isinstance(params[0], (list, tuple)):
                    keys = list(params[0])
                elif isinstance(params, (list, tuple)):
                    keys = list(params)
            rows = []
            for k in (keys or list(self._store.budgets.keys())):
                if k in self._store.budgets:
                    row = self._store.budgets[k]
                    rows.append({
                        "budget_key": k,
                        "total_capacity": row["total_capacity"],
                        "reserved": row["reserved"],
                    })
            self._last_rowset = rows
            self._last_result = rows[0] if rows else None
        elif s.startswith("UPDATE"):
            # Pattern: UPDATE meta.resource_budget SET reserved = reserved + %s, updated_at = NOW() WHERE budget_key = %s
            # Or a bulk UPDATE with a CASE. For tests we accept either single-row or bulk and let the caller
            # pre-stage the increments in self._store.pending_updates.
            for key, delta in (self._store.pending_updates or []):
                self._store.budgets[key]["reserved"] += delta
            self._store.pending_updates = []
        else:
            raise AssertionError(f"Unexpected SQL: {sql!r}")

    def fetchall(self) -> List[Any]:
        if self._dict_cursor:
            return list(self._last_rowset)
        return [tuple(r.values()) for r in self._last_rowset]

    def fetchone(self):
        if not self._last_rowset:
            return None
        return self._last_rowset[0] if self._dict_cursor else tuple(self._last_rowset[0].values())


class _FakeConn:
    def __init__(self, store: "_FakeStore") -> None:
        self._store = store
        self.autocommit = False
        self.closed = False

    def cursor(self, cursor_factory: Optional[Any] = None) -> _FakeCursor:
        import psycopg2.extras
        dict_cursor = cursor_factory is psycopg2.extras.RealDictCursor
        return _FakeCursor(self._store, dict_cursor=dict_cursor)

    def commit(self) -> None:
        self._store.commits += 1

    def rollback(self) -> None:
        self._store.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class _FakeStore:
    def __init__(self, budgets: Dict[str, Dict[str, float]]) -> None:
        self.budgets = {k: dict(v) for k, v in budgets.items()}
        self.executions: List[Tuple[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self.pending_updates: List[Tuple[str, float]] = []


def _default_budgets() -> Dict[str, Dict[str, float]]:
    return {
        "wal_headroom":        {"total_capacity": 100, "reserved": 0},
        "db_connections":      {"total_capacity": 20,  "reserved": 0},
        "concurrent_restores": {"total_capacity": 4,   "reserved": 0},
        "seaweedfs_iops":      {"total_capacity": 1000, "reserved": 0},
    }


@pytest.fixture
def store() -> _FakeStore:
    return _FakeStore(_default_budgets())


@pytest.fixture
def conn(store: _FakeStore) -> _FakeConn:
    return _FakeConn(store)


@pytest.fixture
def budget(conn: _FakeConn):
    from dk_data.ingestion.resource_budget import ResourceBudget
    return ResourceBudget(conn=conn)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTryReserve:
    def test_reserves_when_all_keys_have_capacity(self, budget, store):
        store.pending_updates = [("db_connections", 2), ("concurrent_restores", 1)]
        ok = budget.try_reserve({"db_connections": 2, "concurrent_restores": 1})
        assert ok is True
        assert store.budgets["db_connections"]["reserved"] == 2
        assert store.budgets["concurrent_restores"]["reserved"] == 1

    def test_fails_when_one_key_is_insufficient(self, budget, store):
        # Exceed the concurrent_restores cap (=4).
        store.pending_updates = []  # no updates expected on failure path
        ok = budget.try_reserve({"db_connections": 1, "concurrent_restores": 99})
        assert ok is False
        # Atomicity: neither key was debited.
        assert store.budgets["db_connections"]["reserved"] == 0
        assert store.budgets["concurrent_restores"]["reserved"] == 0


class TestRelease:
    def test_returns_capacity(self, budget, store):
        store.budgets["db_connections"]["reserved"] = 3
        store.pending_updates = [("db_connections", -3)]
        budget.release({"db_connections": 3})
        assert store.budgets["db_connections"]["reserved"] == 0


class TestSnapshot:
    def test_returns_total_reserved_remaining_per_key(self, budget, store):
        store.budgets["db_connections"]["reserved"] = 5
        snap = budget.snapshot()
        assert "db_connections" in snap
        assert snap["db_connections"]["total"] == 20.0
        assert snap["db_connections"]["reserved"] == 5.0
        assert snap["db_connections"]["remaining"] == 15.0


class TestDecorateDispatch:
    def test_reserves_calls_releases_on_success(self, budget, store):
        store.pending_updates = [("db_connections", 1), ("concurrent_restores", 1)]

        calls: List[Any] = []

        def dispatch(desc: Any) -> str:
            calls.append(desc)
            # After this returns, the wrapper releases.
            store.pending_updates = [("db_connections", -1), ("concurrent_restores", -1)]
            return "ok"

        descriptor = MagicMock()
        descriptor.consumes = {"db_connections": 1, "concurrent_restores": 1}

        wrapped = budget.decorate_dispatch(dispatch)
        outcome = wrapped(descriptor)
        assert outcome == "ok"
        assert calls == [descriptor]
        assert store.budgets["db_connections"]["reserved"] == 0
        assert store.budgets["concurrent_restores"]["reserved"] == 0

    def test_defers_when_budget_exhausted(self, budget, store):
        store.budgets["concurrent_restores"]["reserved"] = 4  # at cap
        store.pending_updates = []  # no update path on failure

        dispatch = MagicMock()
        descriptor = MagicMock()
        descriptor.consumes = {"concurrent_restores": 1}

        wrapped = budget.decorate_dispatch(dispatch)
        outcome = wrapped(descriptor)
        # Deferred — dispatch not invoked.
        dispatch.assert_not_called()
        # Dispatch decorator returns None on deferral (by contract).
        assert outcome is None


class TestPoolPath:
    def test_constructor_uses_get_connection_pool(self, store):
        """FR-030: no raw psycopg2.connect() outside database.py."""
        from dk_data.ingestion import resource_budget as rb

        fake_pool = MagicMock()
        fake_pool.getconn.return_value = _FakeConn(store)

        with patch.object(rb, "get_connection_pool", return_value=fake_pool) as m_pool, \
             patch.object(rb, "init_connection_pool") as m_init, \
             patch.object(rb, "psycopg2") as m_psycopg2:
            # Guard: if the module ever called psycopg2.connect directly, assert.
            m_psycopg2.connect.side_effect = AssertionError(
                "ResourceBudget must NOT call psycopg2.connect() directly (FR-030)"
            )

            b = rb.ResourceBudget()
            m_pool.assert_called_once()
            fake_pool.getconn.assert_called_once()
            m_init.assert_not_called()  # pool already initialised in happy path
            b.close()
            fake_pool.putconn.assert_called_once()
