"""Unit tests for dk_data.ingestion.hydration_backlog.HydrationBacklogWriter.

Feature: Horizon 2 / plan §C.3 — hydration DLQ / source quarantine.

Coverage:
  1. New failure inserts row with failure_count=1, consecutive_same_error_count=1
  2. Repeated same-signature failures increment, quarantine at threshold (default 5)
  3. Different-signature failures never quarantine
     (consecutive_same_error_count stays low even as failure_count climbs)
  4. is_quarantined reflects the column state
  5. unquarantine clears fields + writes transform_runs audit
  6. Connection pool path (FR-030): mock get_connection_pool, assert no
     direct psycopg2.connect

The DB is mocked end-to-end — these are pure unit tests (mirror
test_integrity.py). The real DB path is exercised by the post-deploy
smoke test on staging, outside this file.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# In-memory DB double — matches the shape of the backlog writer's SQL.
# ---------------------------------------------------------------------------
#
# The writer issues three distinct SQL shapes:
#   a. INSERT ... ON CONFLICT (source_id, schema_name, table_name) DO UPDATE
#      ... RETURNING ...          (record_failure upsert)
#   b. UPDATE meta.hydration_backlog SET quarantined_by='auto', ...
#      WHERE source_id = %s AND schema_name = %s AND table_name = %s
#      RETURNING ...              (record_failure quarantine second stmt)
#   c. SELECT quarantined_by FROM meta.hydration_backlog WHERE ... (is_quarantined)
#   d. SELECT * FROM meta.hydration_backlog ORDER BY last_failure_at DESC (list_all)
#   e. UPDATE meta.hydration_backlog SET quarantined_by=NULL ... (unquarantine)
#   f. INSERT INTO meta.transform_runs (procedure_name, ...) VALUES (...) (unquarantine audit)
#
# The fake classifies each execution by looking at the leading verb + a
# couple of distinguishing substrings, then mutates an in-memory dict
# keyed on the (source_id, schema_name, table_name) natural key.


class _FakeStore:
    def __init__(self) -> None:
        # Keyed by (source_id, schema_name, table_name) → row dict.
        self.rows: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        # Every executed (sql, params) tuple — for assertion introspection.
        self.executions: List[Tuple[str, Any]] = []
        # Every row written to meta.transform_runs by unquarantine().
        self.transform_runs: List[Dict[str, Any]] = []
        self._next_id = 0

    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id


class _FakeCursor:
    def __init__(self, store: _FakeStore, dict_cursor: bool = False) -> None:
        self._store = store
        self._dict_cursor = dict_cursor
        self._last_result: Optional[Any] = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    # ---- Dispatch ----------------------------------------------------
    def execute(self, sql: str, params: Any = ()) -> None:
        self._store.executions.append((sql, params))
        s = re.sub(r"\s+", " ", sql.strip().upper())
        if s.startswith("INSERT INTO META.HYDRATION_BACKLOG"):
            self._handle_upsert(params)
        elif s.startswith(
            "UPDATE META.HYDRATION_BACKLOG SET QUARANTINED_BY = 'AUTO'"
        ):
            self._handle_quarantine(params)
        elif s.startswith("UPDATE META.HYDRATION_BACKLOG SET QUARANTINED_BY = NULL"):
            self._handle_unquarantine(params)
        elif s.startswith("SELECT QUARANTINED_BY"):
            self._handle_is_quarantined(params)
        elif s.startswith("SELECT BACKLOG_ID"):
            self._handle_list_all(params)
        elif s.startswith("INSERT INTO META.TRANSFORM_RUNS"):
            self._handle_audit(params)
        else:  # pragma: no cover — any unknown SQL is a test defect
            raise AssertionError(f"Unexpected SQL in fake: {sql!r}")

    def fetchone(self) -> Any:
        return self._last_result

    def fetchall(self) -> Any:
        return self._last_result or []

    # ---- Handlers ----------------------------------------------------
    def _handle_upsert(self, params: Dict[str, Any]) -> None:
        key = (params["source_id"], params["schema"], params["table"])
        existing = self._store.rows.get(key)
        if existing is None:
            row = {
                "backlog_id": self._store.next_id(),
                "source_id": params["source_id"],
                "schema_name": params["schema"],
                "table_name": params["table"],
                "last_failure_at": "now",
                "failure_count": 1,
                "last_error_code": params["error_code"],
                "last_error_detail": params["error_detail"],
                "first_failure_at": "now",
                "next_retry_at": "now+backoff",
                "quarantined_by": None,
                "quarantined_at": None,
                "consecutive_same_error_count": 1,
            }
            self._store.rows[key] = row
        else:
            existing["failure_count"] += 1
            if existing["last_error_code"] == params["error_code"]:
                existing["consecutive_same_error_count"] += 1
            else:
                existing["consecutive_same_error_count"] = 1
            existing["last_error_code"] = params["error_code"]
            existing["last_error_detail"] = params["error_detail"]
            existing["last_failure_at"] = "now"
            existing["next_retry_at"] = "now+backoff"
        self._last_result = (
            dict(self._store.rows[key])
            if self._dict_cursor
            else self._store.rows[key]
        )

    def _handle_quarantine(self, params: Tuple[str, str, str]) -> None:
        key = params
        row = self._store.rows.get(key)
        if row is not None:
            row["quarantined_by"] = "auto"
            row["quarantined_at"] = "now"
            row["next_retry_at"] = None
            self._last_result = dict(row) if self._dict_cursor else row
        else:
            self._last_result = None

    def _handle_unquarantine(self, params: Tuple[str, str, str]) -> None:
        key = params
        row = self._store.rows.get(key)
        if row is not None:
            row["quarantined_by"] = None
            row["quarantined_at"] = None
            row["next_retry_at"] = "now"
        self._last_result = None  # UPDATE without RETURNING

    def _handle_is_quarantined(self, params: Tuple[str, str, str]) -> None:
        row = self._store.rows.get(params)
        if row is None:
            self._last_result = None
        else:
            # Non-dict cursor — is_quarantined uses tuple fetchone.
            self._last_result = (row["quarantined_by"],)

    def _handle_list_all(self, _params: Any) -> None:
        self._last_result = [dict(r) for r in self._store.rows.values()]

    def _handle_audit(self, params: Tuple[Any, ...]) -> None:
        (procedure_name, chunk_position, rows_processed, wal_bytes, status, details_json) = params
        self._store.transform_runs.append({
            "procedure_name": procedure_name,
            "chunk_position": chunk_position,
            "status": status,
            "details": details_json,
        })
        self._last_result = None


class _FakeConn:
    def __init__(self, store: _FakeStore) -> None:
        self._store = store
        self.autocommit = False
        self.closed = False

    def cursor(self, cursor_factory: Optional[Any] = None) -> _FakeCursor:
        import psycopg2.extras
        dict_cursor = cursor_factory is psycopg2.extras.RealDictCursor
        return _FakeCursor(self._store, dict_cursor=dict_cursor)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_store() -> _FakeStore:
    return _FakeStore()


@pytest.fixture
def fake_conn(fake_store: _FakeStore) -> _FakeConn:
    return _FakeConn(fake_store)


@pytest.fixture
def writer(fake_conn: _FakeConn):
    from dk_data.ingestion.hydration_backlog import HydrationBacklogWriter
    return HydrationBacklogWriter(conn=fake_conn)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecordFailure:
    def test_new_failure_inserts_row_with_failure_count_one(self, writer, fake_store):
        """Scenario 1: brand-new (source, schema, table) → failure_count=1."""
        row = writer.record_failure(
            source_id="mol_raw.chembl_molecules",
            schema="mol_raw",
            table="chembl_molecules",
            error_code="PG_RESTORE_FATAL",
            error_detail="pg_restore returned exit code 1",
        )
        assert row["failure_count"] == 1
        assert row["consecutive_same_error_count"] == 1
        assert row["last_error_code"] == "PG_RESTORE_FATAL"
        assert row["quarantined_by"] is None
        assert len(fake_store.rows) == 1

    def test_repeated_same_signature_quarantines_at_threshold(self, writer, fake_store, monkeypatch):
        """Scenario 2: default threshold=5 → the 5th same-signature failure
        tips the row into auto-quarantine."""
        monkeypatch.delenv("HYDRATION_DLQ_QUARANTINE_THRESHOLD", raising=False)

        kw = dict(
            source_id="mol_raw.chembl_molecules",
            schema="mol_raw",
            table="chembl_molecules",
            error_code="CONN_LOST",
            error_detail="psycopg2 InterfaceError: connection already closed",
        )
        # 4 failures — still not quarantined.
        for i in range(1, 5):
            row = writer.record_failure(**kw)
            assert row["failure_count"] == i
            assert row["quarantined_by"] is None
        # 5th failure crosses the threshold.
        row = writer.record_failure(**kw)
        assert row["failure_count"] == 5
        assert row["consecutive_same_error_count"] == 5
        assert row["quarantined_by"] == "auto"
        assert row["quarantined_at"] is not None
        assert row["next_retry_at"] is None

    def test_different_signatures_never_quarantine(self, writer, fake_store, monkeypatch):
        """Scenario 3: failure_count climbs, but error_code keeps changing, so
        consecutive_same_error_count oscillates between 1 and 2 — never
        reaches the threshold."""
        monkeypatch.delenv("HYDRATION_DLQ_QUARANTINE_THRESHOLD", raising=False)

        kw_base = dict(
            source_id="mol_raw.drugbank",
            schema="mol_raw",
            table="drugbank",
            error_detail="noise",
        )
        codes = ["A", "B", "A", "B", "A", "B", "A", "B", "A", "B"]
        for code in codes:
            row = writer.record_failure(**kw_base, error_code=code)

        assert row["failure_count"] == len(codes)
        # Signature kept alternating, so the consecutive-same counter never
        # climbed above 1 after the first row.
        assert row["consecutive_same_error_count"] == 1
        assert row["quarantined_by"] is None


class TestIsQuarantined:
    def test_reflects_column_state(self, writer, fake_store):
        """Scenario 4: is_quarantined returns False for unknown rows and
        returns True after the row is quarantined."""
        src = "mol_raw.chembl_molecules"
        sch, tbl = "mol_raw", "chembl_molecules"

        # No row yet → not quarantined.
        assert writer.is_quarantined(src, sch, tbl) is False

        # Record a failure but below threshold → still not quarantined.
        writer.record_failure(
            source_id=src, schema=sch, table=tbl,
            error_code="PG_RESTORE_FATAL",
            error_detail="rc=1",
        )
        assert writer.is_quarantined(src, sch, tbl) is False

        # Directly flip the fake-store row to quarantined and re-check.
        fake_store.rows[(src, sch, tbl)]["quarantined_by"] = "auto"
        assert writer.is_quarantined(src, sch, tbl) is True


class TestUnquarantine:
    def test_clears_fields_and_writes_transform_runs_audit(self, writer, fake_store):
        """Scenario 5: unquarantine clears quarantine flags and inserts a
        corresponding audit row into meta.transform_runs."""
        src = "mol_raw.chembl_molecules"
        sch, tbl = "mol_raw", "chembl_molecules"

        # Seed a quarantined row directly.
        fake_store.rows[(src, sch, tbl)] = {
            "backlog_id": 1,
            "source_id": src,
            "schema_name": sch,
            "table_name": tbl,
            "last_failure_at": "old",
            "failure_count": 7,
            "last_error_code": "PG_RESTORE_FATAL",
            "last_error_detail": "rc=1",
            "first_failure_at": "older",
            "next_retry_at": None,
            "quarantined_by": "auto",
            "quarantined_at": "old",
            "consecutive_same_error_count": 7,
        }

        writer.unquarantine(src, sch, tbl, reason="operator investigated; upstream fixed", caller="nick")

        row = fake_store.rows[(src, sch, tbl)]
        assert row["quarantined_by"] is None
        assert row["quarantined_at"] is None
        assert row["next_retry_at"] == "now"

        # One audit row in transform_runs.
        assert len(fake_store.transform_runs) == 1
        audit = fake_store.transform_runs[0]
        assert audit["procedure_name"] == "dlq:unquarantine"
        assert audit["status"] == "completed"
        # details is a JSON string — quick substring check so we don't have
        # to import json for a two-field assertion.
        assert "operator investigated" in audit["details"]
        assert "nick" in audit["details"]


class TestConnectionPoolPath:
    """FR-030: default constructor must route through the sanctioned pool,
    never raw psycopg2.connect()."""

    def test_default_constructor_leases_from_pool(self):
        from dk_data.ingestion import hydration_backlog as hb

        leased = MagicMock()
        leased.autocommit = False
        fake_pool = MagicMock()
        fake_pool.getconn.return_value = leased

        # Patch any direct-connect so a regression (using psycopg2.connect
        # directly) would be caught even if the pool-mock were silently
        # bypassed. Any call here is a test failure.
        with patch.object(hb, "get_connection_pool", return_value=fake_pool) as m_pool, \
             patch.object(hb, "init_connection_pool") as m_init, \
             patch("psycopg2.connect", side_effect=AssertionError("raw psycopg2.connect called — FR-030 violation")):
            writer = hb.HydrationBacklogWriter()

            m_pool.assert_called_once()
            fake_pool.getconn.assert_called_once()
            m_init.assert_not_called()
            assert leased.autocommit is True

            writer.close()
            fake_pool.putconn.assert_called_once_with(leased)
