"""Unit tests for the WAL budget helpers.

Feature: 002-external-integration-foundation (perf pass, [WALMX])

These tests use a minimal fake connection/cursor because the helpers
only need: SHOW, SET LOCAL, INSERT INTO ... VALUES (...), COMMIT.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dk_data.ingestion.utils.wal_budget import (
    DEFAULT_CHUNK_SIZE,
    WAL_BUDGET_BYTES,
    bulk_load_session,
    chunked_insert,
    estimate_wal_per_row,
    max_chunk_size_for_row,
)


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.executemany_calls: list[tuple[str, list]] = []
        self._show_values: dict[str, str] = {
            "synchronous_commit": "on",
            "maintenance_work_mem": "64MB",
            "work_mem": "4MB",
        }

    def execute(self, sql: str, *args) -> None:
        self.executed.append(sql)

    def executemany(self, sql: str, rows) -> None:
        materialized = list(rows)
        self.executemany_calls.append((sql, materialized))

    def fetchone(self) -> tuple:
        # Parse the most recent SHOW back to its setting value
        last = self.executed[-1] if self.executed else ""
        if last.startswith("SHOW "):
            key = last[5:].strip()
            return (self._show_values.get(key, ""),)
        return ("",)

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self) -> None:
        self._cursor = FakeCursor()
        self.commits = 0

    def cursor(self) -> FakeCursor:
        # Each call returns a fresh cursor object but we keep the
        # same underlying executed list so tests can assert against it.
        return self._cursor

    def commit(self) -> None:
        self.commits += 1


class TestBulkLoadSession:
    def test_sets_synchronous_commit_off(self):
        conn = FakeConnection()
        with bulk_load_session(conn):
            pass
        executed = conn._cursor.executed
        # Expect SHOW for each setting then SET LOCAL, then restore.
        assert any(
            sql == "SET LOCAL synchronous_commit = 'off'" for sql in executed
        )
        assert any(
            sql == "SET LOCAL maintenance_work_mem = '256MB'" for sql in executed
        )
        assert any(
            sql == "SET LOCAL work_mem = '128MB'" for sql in executed
        )

    def test_restores_previous_on_exit(self):
        conn = FakeConnection()
        with bulk_load_session(conn):
            pass
        executed = conn._cursor.executed
        # Restore line should set back to the original 'on'
        assert any(
            sql == "SET LOCAL synchronous_commit = 'on'" for sql in executed
        )

    def test_restores_on_exception(self):
        conn = FakeConnection()
        with pytest.raises(ValueError):
            with bulk_load_session(conn):
                raise ValueError("boom")
        # Even on exception, the restore path must run
        executed = conn._cursor.executed
        assert any(
            sql == "SET LOCAL synchronous_commit = 'on'" for sql in executed
        )


class TestChunkedInsert:
    def test_empty_rows_is_no_op(self):
        conn = FakeConnection()
        total = chunked_insert(
            conn,
            table="mol_raw.test",
            columns=("a", "b"),
            rows=iter([]),
            chunk_size=10,
        )
        assert total == 0
        assert conn.commits == 0

    def test_one_chunk(self):
        conn = FakeConnection()
        rows = [(1, "a"), (2, "b"), (3, "c")]
        total = chunked_insert(
            conn,
            table="mol_raw.test",
            columns=("id", "name"),
            rows=iter(rows),
            chunk_size=10,
        )
        assert total == 3
        # Only one commit (the tail flush)
        assert conn.commits == 1
        # SQL should be parameterized INSERT
        sql, rows_sent = conn._cursor.executemany_calls[0]
        assert sql.startswith('INSERT INTO mol_raw.test ("id", "name") VALUES')
        assert rows_sent == rows

    def test_multiple_chunks_commit_separately(self):
        conn = FakeConnection()
        rows = list(range(25))
        row_tuples = [(r, f"name-{r}") for r in rows]
        total = chunked_insert(
            conn,
            table="mol_raw.test",
            columns=("id", "name"),
            rows=iter(row_tuples),
            chunk_size=10,
        )
        assert total == 25
        # 25 rows, chunk_size=10 → 2 full chunks + 1 partial = 3 commits
        assert conn.commits == 3

    def test_on_conflict_clause_appended(self):
        conn = FakeConnection()
        chunked_insert(
            conn,
            table="mol_raw.test",
            columns=("id",),
            rows=iter([(1,)]),
            chunk_size=10,
            on_conflict="(id) DO NOTHING",
        )
        sql, _ = conn._cursor.executemany_calls[0]
        assert "ON CONFLICT (id) DO NOTHING" in sql


class TestBudgetMath:
    def test_wal_budget_constant(self):
        assert WAL_BUDGET_BYTES == 2 * 1024 * 1024 * 1024

    def test_default_chunk_size_reasonable(self):
        assert 1_000 <= DEFAULT_CHUNK_SIZE <= 100_000

    def test_estimate_wal_per_row(self):
        # 200-byte row → ~400 bytes of WAL (2× raw for overhead)
        assert estimate_wal_per_row(200) == 400

    def test_max_chunk_size_for_small_row(self):
        # 100-byte row → ~200 bytes WAL → 100MB / 200 = 524288 rows,
        # but capped at 50_000 (DEFAULT_UPSERT_CHUNK_SIZE).
        assert max_chunk_size_for_row(100) == 50_000

    def test_max_chunk_size_for_large_row(self):
        # 10 KB row → ~20 KB WAL → 100MB / 20KB = ~5120 rows
        assert 4_000 <= max_chunk_size_for_row(10_000) <= 6_000
