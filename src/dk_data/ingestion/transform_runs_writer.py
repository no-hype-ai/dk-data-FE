"""Writer for ``meta.transform_runs`` used by 005-prestaged-hydration.

Every hydration outcome becomes one INSERT (post-migration 229). No
``ON CONFLICT`` — each run-of-a-step is a fresh row; historical rows are
preserved for audit. Idempotency is enforced on the read side
(:meth:`TransformRunsWriter.is_completed`) before dispatch.

See contracts/meta-transform-runs.md for the full column/index contract.

Active tags: [AUDIT], [IDMPT].
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

from dk_data.ingestion.prestaged_types import RunStatus, SourceKind


class TransformRunsWriter:
    """Append-only writer against ``meta.transform_runs``.

    The caller owns connection + transaction boundaries. This class does
    not commit; it only issues INSERTs. Commit inside the same
    transaction the caller already owns.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    # -----------------------------------------------------------------
    # Idempotency
    # -----------------------------------------------------------------

    def is_completed(self, run_label: str, schema: str, table: str) -> bool:
        """Return True iff ``meta.transform_runs`` already has a
        ``status='completed'`` row for this ``(run_label, procedure_name)``.

        This is the FR-011 skip predicate. Hits the
        ``meta_transform_runs_run_label_idx`` expression index.
        """
        procedure_name = f"prestaged:{schema}.{table}"
        sql = """
            SELECT 1
              FROM meta.transform_runs
             WHERE details ->> 'run_label' = %s
               AND procedure_name = %s
               AND status = 'completed'
             LIMIT 1
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (run_label, procedure_name))
            return cur.fetchone() is not None

    # -----------------------------------------------------------------
    # Terminal-state write
    # -----------------------------------------------------------------

    def record(
        self,
        *,
        run_label: str,
        schema: str,
        table: str,
        chunk_position: str,
        source_kind: SourceKind,
        status: RunStatus,
        started_at: _dt.datetime,
        ended_at: _dt.datetime,
        rows_processed: int,
        wal_bytes: int = 0,
        artifact_sha256: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        """Insert one terminal-state row.

        The caller is responsible for sequencing ``started_at`` / ``ended_at``
        correctly. Both are UTC timestamptz. ``chunk_position`` is the
        file-prefix string from the artifact (``"1"``, ``"3"``,
        ``"retry"``) or ``"-"`` for single-chunk steps.

        ``rows_processed`` is the post-restore ``COUNT(*)``; pass 0 on
        failure. ``wal_bytes`` is the client-measured WAL delta; 0 when
        unmeasured.

        ``details`` is JSONB and always includes ``run_label``. Only
        ``artifact_sha256`` / ``error_detail`` are nullable.
        """
        details = {
            "run_label": run_label,
            "source_kind": source_kind,
            "target_schema": schema,
            "target_table": table,
        }
        if artifact_sha256 is not None:
            details["artifact_sha256"] = artifact_sha256
        if error_detail is not None:
            # Truncate per the contract (≤4 KB)
            details["error_detail"] = error_detail[:4096]

        sql = """
            INSERT INTO meta.transform_runs
              (procedure_name, chunk_position, started_at, ended_at,
               rows_processed, wal_bytes, status, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        params = (
            f"prestaged:{schema}.{table}",
            chunk_position,
            started_at,
            ended_at,
            rows_processed,
            wal_bytes,
            status,
            json.dumps(details),
        )
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
