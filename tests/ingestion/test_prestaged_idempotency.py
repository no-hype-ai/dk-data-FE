"""Idempotency + audit-row tests for 005-prestaged-hydration (US5).

Stage 5 (T074, T075). Validates SC-006 (rerun-is-noop) and SC-007
(exactly one terminal row per source) at the unit level — mocks the DB
connection + writer so tests run without a live Postgres.

A heavier integration test exists at
``tests/load/test_prestaged_e2e.py`` but is gated behind
``@pytest.mark.integration`` and requires ``cnpg_conn`` + a real
``pg_restore`` binary; the unit tests here run on every CI build.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


from dk_data.ingestion.prestaged import run_step
from dk_data.ingestion.prestaged_types import LoadStep, PrestagedArtifact


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _artifact(schema: str, table: str, *, sha: str) -> PrestagedArtifact:
    return PrestagedArtifact(
        path=Path(f"/tmp/{schema}__{table}.dump"),
        target_schema=schema,
        target_table=table,
        tier="raw",
        chunk_index="",
        size_bytes=42,
        sha256=sha,
        magic_ok=True,
    )


def _step_with_artifact() -> LoadStep:
    return LoadStep(
        source_id="mol_raw.chembl",
        target_schema="mol_raw",
        target_table="chembl",
        tier="raw",
        kind="pg_dump",
        artifacts=[_artifact("mol_raw", "chembl", sha="a" * 64)],
    )


# ---------------------------------------------------------------------------
# T074 — SC-006: rerun-is-noop (idempotency guard skips dispatch)
# ---------------------------------------------------------------------------


def test_run_step_skips_dispatch_when_writer_reports_completed() -> None:
    """When writer.is_completed returns True for (run_label, schema, table),
    run_step short-circuits to RunStepOutcome(status='completed') without
    spawning a single pg_restore subprocess. This is SC-006 in unit form."""
    writer = MagicMock()
    writer.is_completed.return_value = True

    conn = MagicMock()
    step = _step_with_artifact()

    with patch("dk_data.ingestion.prestaged.dispatch_pg_restore") as mock_dispatch:
        outcome = run_step(conn, step, run_label="abc123", writer=writer)

    assert outcome.status == "completed"
    assert outcome.row_count == 0  # signals "skipped, prior row carries the count"
    assert outcome.error_detail is None

    # The skip predicate fired; dispatch was NEVER called
    mock_dispatch.assert_not_called()
    writer.is_completed.assert_called_once_with("abc123", "mol_raw", "chembl")
    # No new INSERT either — the existing completed row IS the audit
    writer.record.assert_not_called()


def test_repeated_run_step_with_completed_status_invokes_zero_subprocess() -> None:
    """Two back-to-back run_step calls with the same run_label spawn
    zero pg_restore invocations total, validating SC-006's "<5s rerun
    with zero subprocess calls" guarantee at unit scope."""
    writer = MagicMock()
    writer.is_completed.return_value = True
    conn = MagicMock()
    step = _step_with_artifact()

    with patch("dk_data.ingestion.prestaged.dispatch_pg_restore") as mock_dispatch:
        run_step(conn, step, run_label="run1", writer=writer)
        run_step(conn, step, run_label="run1", writer=writer)
        run_step(conn, step, run_label="run1", writer=writer)

    assert mock_dispatch.call_count == 0
    assert writer.is_completed.call_count == 3


# ---------------------------------------------------------------------------
# T075 — SC-007: exactly one terminal row per source per run
# ---------------------------------------------------------------------------


def test_successful_run_step_writes_exactly_one_terminal_row() -> None:
    """A successful run_step (one chunk, view-safe target) issues
    exactly one writer.record call and that row carries
    status='completed' (per SC-007)."""
    writer = MagicMock()
    writer.is_completed.return_value = False

    # Cursor returning a row count of 42
    cur = MagicMock()
    cur.fetchone.return_value = (42,)
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = None

    conn = MagicMock()
    conn.cursor.return_value = cur

    step = _step_with_artifact()

    with (
        patch("dk_data.ingestion.prestaged.dispatch_pg_restore", return_value=0),
        patch("dk_data.ingestion.prestaged.is_restorable_target", return_value=True),
    ):
        outcome = run_step(conn, step, run_label="run1", writer=writer)

    assert outcome.status == "completed"
    assert outcome.row_count == 42

    # SC-007: exactly one terminal row written
    assert writer.record.call_count == 1
    kwargs = writer.record.call_args.kwargs
    assert kwargs["status"] == "completed"
    assert kwargs["rows_processed"] == 42
    assert kwargs["schema"] == "mol_raw"
    assert kwargs["table"] == "chembl"
    assert kwargs["artifact_sha256"] == "a" * 64


def test_failed_chunk_writes_exactly_one_failed_row() -> None:
    """A pg_restore non-zero exit produces exactly one terminal row
    with status='failed' — not two (no spurious 'completed' shadow)."""
    writer = MagicMock()
    writer.is_completed.return_value = False

    conn = MagicMock()
    step = _step_with_artifact()

    with (
        patch("dk_data.ingestion.prestaged.dispatch_pg_restore", return_value=2),
        patch("dk_data.ingestion.prestaged.is_restorable_target", return_value=True),
    ):
        outcome = run_step(conn, step, run_label="run1", writer=writer)

    assert outcome.status == "failed"
    assert writer.record.call_count == 1
    assert writer.record.call_args.kwargs["status"] == "failed"


def test_view_target_writes_exactly_one_skipped_view_row() -> None:
    """When is_restorable_target returns False (target is a view),
    run_step writes exactly one row with status='skipped_view' and
    never invokes dispatch."""
    writer = MagicMock()
    writer.is_completed.return_value = False

    conn = MagicMock()
    step = _step_with_artifact()

    with (
        patch("dk_data.ingestion.prestaged.is_restorable_target", return_value=False),
        patch("dk_data.ingestion.prestaged.dispatch_pg_restore") as mock_dispatch,
    ):
        outcome = run_step(conn, step, run_label="run1", writer=writer)

    assert outcome.status == "skipped_view"
    mock_dispatch.assert_not_called()
    assert writer.record.call_count == 1
    assert writer.record.call_args.kwargs["status"] == "skipped_view"


# ---------------------------------------------------------------------------
# Bonus: OTLP shim is non-fatal even when opentelemetry is unavailable
# ---------------------------------------------------------------------------


def test_emit_otlp_silently_swallows_when_otel_missing() -> None:
    """T073 contract: _emit_otlp must never raise, even when the
    opentelemetry package isn't importable at runtime."""
    from dk_data.ingestion.prestaged import _emit_otlp
    step = _step_with_artifact()

    # Force the lazy import to fail by stubbing opentelemetry → ImportError
    with patch.dict(sys.modules, {"opentelemetry": None}):
        # Should NOT raise
        _emit_otlp(step, run_label="abc", status="completed", row_count=42)
