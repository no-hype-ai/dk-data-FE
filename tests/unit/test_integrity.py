"""Unit tests for dk_data.ingestion.common.integrity.ArtifactProvenanceWriter.

Feature: Horizon 2 / plan §C.4 — download integrity pipeline.

Coverage (per plan §C.4 unit-test requirements):
  1. New download with no prior row → inserts row, size_match=True when bytes match
  2. Same URL re-downloaded with same sha256 → inserts new row, changed_from_prior=False
  3. Same URL re-downloaded with different sha256 → changed_from_prior=True, metric incremented
  4. Write failure is swallowed + counter incremented (record_swallow)
  5. None Content-Length is not a size-match failure

The DB is mocked end-to-end — these are pure unit tests. The real DB path is
exercised by the post-deploy smoke test on staging, outside this file.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# In-memory DB double — just enough to exercise the writer's SQL contract.
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Cursor that records SQL + args and plays back a scripted response."""

    def __init__(self, store: "_FakeStore", dict_cursor: bool = False) -> None:
        self._store = store
        self._dict_cursor = dict_cursor
        self._last_result: Optional[Any] = None
        # Track the last query kind to choose how to respond in fetchone().
        self._last_kind: Optional[str] = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self._store.executions.append((sql, params))
        stripped = sql.strip().upper()
        if stripped.startswith("SELECT"):
            self._last_kind = "select_prior"
            # find most recent row for (source_name, source_url)
            src, url = params
            matches = [
                r for r in self._store.rows
                if r["source_name"] == src and r["source_url"] == url
            ]
            self._last_result = matches[-1] if matches else None
        elif stripped.startswith("INSERT"):
            self._last_kind = "insert"
            # Column order matches ArtifactProvenanceWriter._insert_row:
            (
                source_name, source_url, local_path,
                content_length, etag, last_modified,
                sha256, bytes_written, size_match,
                prior_provenance_id, changed_from_prior,
            ) = params
            self._store.next_id += 1
            row = {
                "provenance_id": self._store.next_id,
                "source_name": source_name,
                "source_url": source_url,
                "local_path": local_path,
                "content_length": content_length,
                "etag": etag,
                "last_modified": last_modified,
                "sha256": sha256,
                "bytes_written": bytes_written,
                "size_match": size_match,
                "downloaded_at": f"2026-04-16T00:00:{self._store.next_id:02d}Z",
                "prior_provenance_id": prior_provenance_id,
                "changed_from_prior": changed_from_prior,
            }
            self._store.rows.append(row)
            self._last_result = row
        else:
            raise AssertionError(f"Unexpected SQL kind: {sql!r}")

    def fetchone(self):
        r = self._last_result
        if r is None:
            return None
        if self._last_kind == "select_prior":
            # Writer expects (provenance_id, sha256) tuple for the prior-lookup.
            return (r["provenance_id"], r["sha256"])
        # INSERT ... RETURNING — writer expects a dict-like row.
        return dict(r) if self._dict_cursor else r


class _FakeConn:
    def __init__(self, store: "_FakeStore") -> None:
        self._store = store
        self.autocommit = False
        self.closed = False

    def cursor(self, cursor_factory: Optional[Any] = None) -> _FakeCursor:
        # RealDictCursor → dict fetchone; default cursor → tuple fetchone.
        import psycopg2.extras
        dict_cursor = cursor_factory is psycopg2.extras.RealDictCursor
        return _FakeCursor(self._store, dict_cursor=dict_cursor)

    def close(self) -> None:
        self.closed = True


class _FakeStore:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []
        self.executions: List[Tuple[str, tuple]] = []
        self.next_id: int = 0


@pytest.fixture
def fake_conn() -> _FakeConn:
    return _FakeConn(_FakeStore())


@pytest.fixture
def writer(fake_conn: _FakeConn):
    # Import inside the fixture so the metrics registry is set up before any
    # .labels() calls, and so an import error is attributed to the fixture
    # (not an early module-level import).
    from dk_data.ingestion.common.integrity import ArtifactProvenanceWriter
    return ArtifactProvenanceWriter(conn=fake_conn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(
    *, content_length: Optional[int] = 1234, etag: str = '"abc"', last_modified: str = "Wed, 15 Apr 2026 00:00:00 GMT"
) -> Dict[str, str]:
    h: Dict[str, str] = {}
    if content_length is not None:
        h["Content-Length"] = str(content_length)
    if etag is not None:
        h["ETag"] = etag
    if last_modified is not None:
        h["Last-Modified"] = last_modified
    return h


def _metric_value(counter, *, source: str) -> float:
    # prometheus_client Counters expose ._value on the child sample.
    return counter.labels(source=source)._value.get()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestArtifactProvenanceWriter:
    def test_new_download_no_prior_inserts_row_with_size_match_true(self, writer, fake_conn):
        """Scenario 1: new (source, url) + matching bytes → one INSERT, size_match=True."""
        row = writer.record(
            source_name="cms_part_d_spending",
            source_url="https://example/part_d.csv",
            local_path="/tmp/part_d.csv",
            headers_dict=_headers(content_length=1234, etag='"v1"'),
            bytes_written=1234,
            sha256="a" * 64,
        )

        assert row["size_match"] is True
        assert row["prior_provenance_id"] is None
        assert row["changed_from_prior"] is False
        assert row["content_length"] == 1234
        assert row["etag"] == '"v1"'
        assert row["sha256"] == "a" * 64
        # One row in the store.
        assert len(fake_conn._store.rows) == 1
        # Two SQL calls: prior lookup (None) + INSERT.
        sql_kinds = [sql.strip().upper().split()[0] for sql, _ in fake_conn._store.executions]
        assert sql_kinds == ["SELECT", "INSERT"]

    def test_missing_content_length_counts_as_size_match(self, writer):
        """Scenario 5: None CL is not a failure — size_match stays True."""
        row = writer.record(
            source_name="s",
            source_url="u",
            local_path="/p",
            headers_dict=_headers(content_length=None),  # chunked transfer
            bytes_written=999,
            sha256="b" * 64,
        )
        assert row["content_length"] is None
        assert row["size_match"] is True

    def test_content_length_mismatch_marks_size_match_false(self, writer):
        """Header-vs-disk mismatch is recorded for later auditing, even though
        the caller (cms_downloader) has already retried/failed on this case."""
        row = writer.record(
            source_name="s",
            source_url="u",
            local_path="/p",
            headers_dict=_headers(content_length=1000),
            bytes_written=500,
            sha256="c" * 64,
        )
        assert row["size_match"] is False
        assert row["content_length"] == 1000
        assert row["bytes_written"] == 500

    def test_same_url_same_sha256_does_not_set_changed_flag(self, writer, fake_conn):
        """Scenario 2: re-download with same sha256 → new row, changed_from_prior=False."""
        kw = dict(
            source_name="cms_x",
            source_url="https://example/x.csv",
            local_path="/tmp/x.csv",
            headers_dict=_headers(),
            bytes_written=1234,
            sha256="d" * 64,
        )
        first = writer.record(**kw)
        second = writer.record(**kw)

        assert first["changed_from_prior"] is False
        assert first["prior_provenance_id"] is None
        assert second["changed_from_prior"] is False
        assert second["prior_provenance_id"] == first["provenance_id"]
        assert second["provenance_id"] != first["provenance_id"]
        assert len(fake_conn._store.rows) == 2

    def test_same_url_different_sha256_sets_changed_flag_and_increments_metric(self, writer):
        """Scenario 3: re-download with different sha256 → changed_from_prior=True, metric +1."""
        from dk_data.observability.metrics import DK_ARTIFACT_CHANGED_TOTAL

        source = "cms_changed_src"
        before = _metric_value(DK_ARTIFACT_CHANGED_TOTAL, source=source)

        kw = dict(
            source_name=source,
            source_url="https://example/y.csv",
            local_path="/tmp/y.csv",
            headers_dict=_headers(),
            bytes_written=1234,
        )
        first = writer.record(**kw, sha256="e" * 64)
        second = writer.record(**kw, sha256="f" * 64)

        assert first["changed_from_prior"] is False
        assert second["changed_from_prior"] is True
        assert second["prior_provenance_id"] == first["provenance_id"]

        after = _metric_value(DK_ARTIFACT_CHANGED_TOTAL, source=source)
        assert after - before == pytest.approx(1.0)

    def test_headers_lookup_is_case_insensitive(self, writer):
        """ETag / Last-Modified arrive in mixed casing from various HTTP libs."""
        row = writer.record(
            source_name="s",
            source_url="u",
            local_path="/p",
            headers_dict={
                "content-length": "42",     # lowercase
                "etag": '"lower"',           # lowercase
                "Last-Modified": "now",      # mixed
            },
            bytes_written=42,
            sha256="0" * 64,
        )
        assert row["content_length"] == 42
        assert row["etag"] == '"lower"'
        assert row["last_modified"] == "now"


class TestRecordSwallow:
    def test_db_failure_is_swallowed_and_counter_incremented(self):
        """Scenario 4: DB raises → record_swallow returns None + metric +1."""
        from dk_data.ingestion.common.integrity import ArtifactProvenanceWriter
        from dk_data.observability.metrics import (
            DK_ARTIFACT_PROVENANCE_WRITE_ERRORS_TOTAL,
        )

        broken_conn = MagicMock()
        # Any cursor access raises — simulates connection lost / permission denied.
        broken_conn.cursor.side_effect = RuntimeError("synthetic DB failure")

        writer = ArtifactProvenanceWriter(conn=broken_conn)

        source = "cms_broken_src"
        before = _metric_value(DK_ARTIFACT_PROVENANCE_WRITE_ERRORS_TOTAL, source=source)

        result = writer.record_swallow(
            source_name=source,
            source_url="https://example/z.csv",
            local_path="/tmp/z.csv",
            headers_dict=_headers(),
            bytes_written=1234,
            sha256="9" * 64,
        )

        assert result is None
        after = _metric_value(DK_ARTIFACT_PROVENANCE_WRITE_ERRORS_TOTAL, source=source)
        assert after - before == pytest.approx(1.0)

    def test_successful_record_swallow_returns_row(self, writer):
        """Happy-path record_swallow just delegates to record and returns the row."""
        row = writer.record_swallow(
            source_name="s2",
            source_url="u2",
            local_path="/p2",
            headers_dict=_headers(),
            bytes_written=1234,
            sha256="1" * 64,
        )
        assert row is not None
        assert row["source_name"] == "s2"


class TestBuildDsnGate:
    """FR-030: the default constructor must route through build_dsn()."""

    def test_default_constructor_calls_build_dsn(self):
        from dk_data.ingestion.common import integrity as integ

        with patch.object(integ, "build_dsn", return_value="postgresql://fake") as m_dsn, \
             patch.object(integ.psycopg2, "connect") as m_connect:
            fake = MagicMock()
            m_connect.return_value = fake
            integ.ArtifactProvenanceWriter()
            m_dsn.assert_called_once()
            m_connect.assert_called_once_with("postgresql://fake")
            # autocommit flipped on so individual INSERTs don't need txn management
            assert fake.autocommit is True
