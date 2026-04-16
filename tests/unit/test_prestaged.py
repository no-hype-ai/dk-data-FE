"""Unit tests for prestaged hydration row-count gate (PR-02, plan.md §B.3).

Scope: only the manifest row-count gate. Other prestaged behaviors are
covered by ``tests/ingestion/test_prestaged_*`` — this file focuses on
the new B.3 contract so the diff surface is auditable.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from dk_data.ingestion.prestaged import RunStepOutcome, run_step
from dk_data.ingestion.prestaged_types import LoadStep, PrestagedArtifact


def _artifact(dump_path: Path) -> PrestagedArtifact:
    return PrestagedArtifact(
        path=dump_path,
        target_schema="mol_raw",
        target_table="chembl",
        tier="raw",
        chunk_index="",
        size_bytes=dump_path.stat().st_size if dump_path.exists() else 42,
        sha256="a" * 64,
        magic_ok=True,
    )


def _step(dump_path: Path) -> LoadStep:
    return LoadStep(
        source_id="mol_raw.chembl",
        target_schema="mol_raw",
        target_table="chembl",
        tier="raw",
        kind="pg_dump",
        artifacts=[_artifact(dump_path)],
    )


def _write_manifest(dump_path: Path, expected_row_count: int) -> Path:
    """Write the companion manifest file alongside the dump."""
    manifest_path = dump_path.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(
            {
                "source": "mol_raw.chembl",
                "kind": "pg_dump",
                "target_schema": "mol_raw",
                "target_table": "chembl",
                "sha256": "a" * 64,
                "row_count": expected_row_count,
            }
        )
    )
    return manifest_path


def _mock_conn_returning_count(actual_row_count: int) -> MagicMock:
    """Build a mock conn whose cursor.fetchone yields (actual_row_count,)."""
    cur = MagicMock()
    cur.fetchone.return_value = (actual_row_count,)
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = None

    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ---------------------------------------------------------------------------
# B.3 primary contract: manifest says 1000, table has 500 → row_mismatch
# ---------------------------------------------------------------------------


def test_row_mismatch_when_actual_differs_from_manifest(tmp_path: Path) -> None:
    """Given a manifest with expected=1000 and a post-restore actual of 500,
    run_step returns status='row_mismatch' (not 'completed', not 'failed')
    and records it in meta.transform_runs with the mismatch detail.

    This is the load-bearing assertion for plan.md §B.3 — truncation that
    slips past pg_restore (session memory #2245) must be caught here."""
    dump_path = tmp_path / "chembl.dump"
    dump_path.write_bytes(b"PGDMP" + b"\x00" * 40)
    _write_manifest(dump_path, expected_row_count=1000)

    writer = MagicMock()
    writer.is_completed.return_value = False

    conn = _mock_conn_returning_count(500)
    step = _step(dump_path)

    with (
        patch("dk_data.ingestion.prestaged.dispatch_pg_restore", return_value=0),
        patch(
            "dk_data.ingestion.prestaged.is_restorable_target", return_value=True
        ),
    ):
        outcome = run_step(conn, step, run_label="run1", writer=writer)

    # Primary assertion
    assert outcome.status == "row_mismatch"
    assert outcome.row_count == 500
    assert outcome.error_detail is not None
    assert "expected=1000" in outcome.error_detail
    assert "actual=500" in outcome.error_detail

    # Exactly one terminal row, with status='row_mismatch'
    assert writer.record.call_count == 1
    kwargs = writer.record.call_args.kwargs
    assert kwargs["status"] == "row_mismatch"
    assert kwargs["rows_processed"] == 500
    assert kwargs["schema"] == "mol_raw"
    assert kwargs["table"] == "chembl"
    assert "row_mismatch" in kwargs["error_detail"]


# ---------------------------------------------------------------------------
# Negative cases the same gate must get right
# ---------------------------------------------------------------------------


def test_row_match_returns_completed(tmp_path: Path) -> None:
    """Manifest expected=1000, actual=1000 → status='completed'."""
    dump_path = tmp_path / "chembl.dump"
    dump_path.write_bytes(b"PGDMP" + b"\x00" * 40)
    _write_manifest(dump_path, expected_row_count=1000)

    writer = MagicMock()
    writer.is_completed.return_value = False

    conn = _mock_conn_returning_count(1000)
    step = _step(dump_path)

    with (
        patch("dk_data.ingestion.prestaged.dispatch_pg_restore", return_value=0),
        patch(
            "dk_data.ingestion.prestaged.is_restorable_target", return_value=True
        ),
    ):
        outcome = run_step(conn, step, run_label="run1", writer=writer)

    assert outcome.status == "completed"
    assert outcome.row_count == 1000
    assert writer.record.call_args.kwargs["status"] == "completed"


def test_absent_manifest_preserves_current_behavior(tmp_path: Path) -> None:
    """No manifest next to the dump → status='completed' (existing behavior)
    plus one increment of dk_hydration_manifest_missing_total.

    The B.3 contract explicitly requires "log and proceed" when a manifest
    is absent — we must NOT block hydration on a missing manifest, but we
    MUST emit the gap metric so the coverage hole is visible."""
    dump_path = tmp_path / "chembl.dump"
    dump_path.write_bytes(b"PGDMP" + b"\x00" * 40)
    # Intentionally no manifest file.

    writer = MagicMock()
    writer.is_completed.return_value = False

    conn = _mock_conn_returning_count(500)
    step = _step(dump_path)

    from dk_data.observability.metrics import (
        DK_HYDRATION_MANIFEST_MISSING_TOTAL,
    )

    missing_before = DK_HYDRATION_MANIFEST_MISSING_TOTAL.labels(
        source="mol_raw.chembl", schema="mol_raw", table="chembl",
    )._value.get()

    with (
        patch("dk_data.ingestion.prestaged.dispatch_pg_restore", return_value=0),
        patch(
            "dk_data.ingestion.prestaged.is_restorable_target", return_value=True
        ),
    ):
        outcome = run_step(conn, step, run_label="run1", writer=writer)

    assert outcome.status == "completed"  # no gate → current behavior preserved
    missing_after = DK_HYDRATION_MANIFEST_MISSING_TOTAL.labels(
        source="mol_raw.chembl", schema="mol_raw", table="chembl",
    )._value.get()
    assert missing_after == missing_before + 1


def test_row_mismatch_increments_counter(tmp_path: Path) -> None:
    """A detected mismatch must increment dk_hydration_row_mismatch_total,
    which is what the DkHydrationRowMismatch alert (plan.md §B.5) fires on."""
    dump_path = tmp_path / "chembl.dump"
    dump_path.write_bytes(b"PGDMP" + b"\x00" * 40)
    _write_manifest(dump_path, expected_row_count=1000)

    writer = MagicMock()
    writer.is_completed.return_value = False

    conn = _mock_conn_returning_count(500)
    step = _step(dump_path)

    from dk_data.observability.metrics import DK_HYDRATION_ROW_MISMATCH_TOTAL

    mismatch_before = DK_HYDRATION_ROW_MISMATCH_TOTAL.labels(
        source="mol_raw.chembl", schema="mol_raw", table="chembl",
    )._value.get()

    with (
        patch("dk_data.ingestion.prestaged.dispatch_pg_restore", return_value=0),
        patch(
            "dk_data.ingestion.prestaged.is_restorable_target", return_value=True
        ),
    ):
        run_step(conn, step, run_label="run1", writer=writer)

    mismatch_after = DK_HYDRATION_ROW_MISMATCH_TOTAL.labels(
        source="mol_raw.chembl", schema="mol_raw", table="chembl",
    )._value.get()
    assert mismatch_after == mismatch_before + 1
