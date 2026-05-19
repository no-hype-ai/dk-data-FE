"""Hydration dead-letter queue / source quarantine writer.

Feature: Horizon 2 / plan §C.3.

What this module does
---------------------
Tracks consecutive hydration failures per ``(source_id, schema, table)``
in ``meta.hydration_backlog`` (migration 231). After N consecutive
same-signature failures (``HYDRATION_DLQ_QUARANTINE_THRESHOLD``, default
5), the row is auto-quarantined — the dispatcher sees ``is_quarantined()``
return True and skips the source with outcome ``status='quarantined'``
until an operator calls ``unquarantine(...)``.

Exponential backoff (``next_retry_at``) applies even before quarantine
kicks in, so a transiently-failing source isn't hammered every run.

Typical usage
-------------
.. code-block:: python

    backlog = HydrationBacklogWriter()
    try:
        if backlog.is_quarantined(source_id, schema, table):
            # dispatcher skips, emits DK_HYDRATION_DLQ_SKIPPED_TOTAL
            return RunStepOutcome(status='quarantined', ...)

        # ... dispatch pg_restore ...
        if failed:
            backlog.record_failure(
                source_id=source_id,
                schema=schema,
                table=table,
                error_code='PG_RESTORE_FATAL',
                error_detail=stderr_hint,
            )
    finally:
        backlog.close()

FR-030 compliance
-----------------
The connection is obtained via the sanctioned pool helpers in
``dk_data.ingestion.utils.database`` (``get_connection_pool`` and
``init_connection_pool``). Mirrors the pattern in
``dk_data.ingestion.common.integrity``. Raw connection construction
outside ``database.py`` is a CI failure (FR-030 / T003 grep gate).

Failure-tolerance pattern
-------------------------
The ingestion pipeline must not fail because the backlog write failed.
Callers in ``prestaged.py`` wrap writes in ``try/except`` and swallow
``RuntimeError`` / ``psycopg2.Error`` — see the pattern used by
``ArtifactProvenanceWriter.record_swallow``. The constructor itself also
tolerates missing secrets (no POSTGRES_PASSWORD → writer effectively
no-ops).

Auto-quarantine signature logic
-------------------------------
"Same signature" means the new failure's ``error_code`` matches the row's
current ``last_error_code``. The upsert in ``record_failure`` increments
``consecutive_same_error_count`` when matched and resets it to 1 on
mismatch. Quarantine fires when ``failure_count >= threshold`` AND
``consecutive_same_error_count >= threshold`` — both conditions must hold
so a source that bounces between error signatures never quarantines
(that's usually upstream flapping, not a persistent bug).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from dk_data.ingestion.utils.database import (
    get_connection_pool,
    init_connection_pool,
)

logger = logging.getLogger(__name__)

DEFAULT_QUARANTINE_THRESHOLD = 5
# Cap the exponential backoff at 24h. pow(2, 10) * 60 = 61440s ≈ 17h; at
# failure_count=11 this would be ~34h, so we clamp. Same shape as the
# capped-retry pattern in downloaders/cms_downloader.py.
_BACKOFF_CAP_SECONDS = 86400  # 24h


def _quarantine_threshold() -> int:
    """Read ``HYDRATION_DLQ_QUARANTINE_THRESHOLD`` with a sane default."""
    raw = os.environ.get("HYDRATION_DLQ_QUARANTINE_THRESHOLD")
    if not raw:
        return DEFAULT_QUARANTINE_THRESHOLD
    try:
        val = int(raw)
        if val < 1:
            return DEFAULT_QUARANTINE_THRESHOLD
        return val
    except (TypeError, ValueError):
        return DEFAULT_QUARANTINE_THRESHOLD


class HydrationBacklogWriter:
    """DLQ writer for ``meta.hydration_backlog``.

    Holds one psycopg2 connection leased from the shared pool (FR-030) or
    an injected one for tests / orchestrators that already own a handle.
    Mirrors the lifecycle of
    :class:`dk_data.ingestion.common.integrity.ArtifactProvenanceWriter`.
    """

    def __init__(self, conn: Optional[psycopg2.extensions.connection] = None) -> None:
        """Initialise the writer.

        Args:
            conn: Optional pre-built connection (useful for tests that inject
                a mock, or orchestrators that already own a handle). When
                ``None`` (production path), a connection is leased from the
                shared pool via ``get_connection_pool()``. The pool is
                lazy-initialised on first use if needed.
        """
        self._owns_conn = False
        if conn is None:
            try:
                pool = get_connection_pool()
            except RuntimeError:
                init_connection_pool()
                pool = get_connection_pool()
            conn = pool.getconn()
            conn.autocommit = True
            self._owns_conn = True
        self._conn = conn

    @property
    def conn(self) -> psycopg2.extensions.connection:
        return self._conn

    def close(self) -> None:
        """Return the leased connection to the pool (if owned)."""
        if not self._owns_conn:
            return
        try:
            pool = get_connection_pool()
            pool.putconn(self._conn)
        except Exception:  # pragma: no cover — defensive
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def record_failure(
        self,
        *,
        source_id: str,
        schema: str,
        table: str,
        error_code: str,
        error_detail: str,
    ) -> Dict[str, Any]:
        """Upsert a failure row; auto-quarantine when signature repeats.

        The upsert is a single round-trip: it INSERTs a new row with
        ``failure_count=1, consecutive_same_error_count=1`` OR, if the
        row already exists, UPDATEs counters + computes the new
        ``next_retry_at`` with exponential backoff (capped at 24h).
        Signature match is done by comparing the NEW ``error_code`` against
        the EXISTING row's ``last_error_code`` via ``EXCLUDED``/``meta...``
        column references — see the ON CONFLICT block below.

        If after the upsert both ``failure_count >= threshold`` AND
        ``consecutive_same_error_count >= threshold``, a second UPDATE
        sets ``quarantined_by='auto', quarantined_at=NOW(),
        next_retry_at=NULL``. We keep this as a separate statement (not
        folded into the upsert) because threshold reads from env at each
        call — computing it server-side would require injecting it as a
        GUC or CTE param, which buys nothing at current volumes.

        Returns:
            The row as a dict after all updates.
        """
        threshold = _quarantine_threshold()
        detail = (error_detail or "")[:4096]

        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Single-statement upsert with exponential-backoff computation
            # done inside the ON CONFLICT clause. The CASE expression for
            # consecutive_same_error_count reads the existing row's
            # last_error_code (via the bare column ref in an UPDATE target
            # list — in ON CONFLICT, unqualified column refs resolve to
            # the pre-update row) against EXCLUDED.last_error_code (the
            # incoming value). If they match, increment; otherwise reset
            # to 1.
            #
            # next_retry_at: least(pow(2, least(new_failure_count, 10)) * 60, 86400)
            # seconds ahead of NOW(). Using `meta.hydration_backlog.failure_count + 1`
            # (the value after the +1) so backoff tracks the new state.
            cur.execute(
                """
                INSERT INTO meta.hydration_backlog (
                    source_id, schema_name, table_name,
                    last_failure_at, failure_count,
                    last_error_code, last_error_detail,
                    first_failure_at, next_retry_at,
                    consecutive_same_error_count
                )
                VALUES (
                    %(source_id)s, %(schema)s, %(table)s,
                    NOW(), 1,
                    %(error_code)s, %(error_detail)s,
                    NOW(),
                    NOW() + (LEAST(POW(2, 1) * 60, %(cap)s) || ' seconds')::interval,
                    1
                )
                ON CONFLICT (source_id, schema_name, table_name) DO UPDATE SET
                    last_failure_at   = NOW(),
                    failure_count     = meta.hydration_backlog.failure_count + 1,
                    last_error_code   = EXCLUDED.last_error_code,
                    last_error_detail = EXCLUDED.last_error_detail,
                    consecutive_same_error_count = CASE
                        WHEN meta.hydration_backlog.last_error_code IS NOT DISTINCT FROM EXCLUDED.last_error_code
                        THEN meta.hydration_backlog.consecutive_same_error_count + 1
                        ELSE 1
                    END,
                    next_retry_at = NOW() + (
                        LEAST(
                            POW(2, LEAST(meta.hydration_backlog.failure_count + 1, 10)) * 60,
                            %(cap)s
                        ) || ' seconds'
                    )::interval
                RETURNING
                    backlog_id, source_id, schema_name, table_name,
                    last_failure_at, failure_count, last_error_code,
                    last_error_detail, first_failure_at, next_retry_at,
                    quarantined_by, quarantined_at,
                    consecutive_same_error_count
                """,
                {
                    "source_id": source_id,
                    "schema": schema,
                    "table": table,
                    "error_code": error_code,
                    "error_detail": detail,
                    "cap": _BACKOFF_CAP_SECONDS,
                },
            )
            row = dict(cur.fetchone() or {})

        # Auto-quarantine trigger: both counters must meet threshold AND
        # the row must not already be quarantined (idempotent re-run safe).
        should_quarantine = (
            row.get("failure_count", 0) >= threshold
            and row.get("consecutive_same_error_count", 0) >= threshold
            and row.get("quarantined_by") is None
        )
        if should_quarantine:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE meta.hydration_backlog
                       SET quarantined_by = 'auto',
                           quarantined_at = NOW(),
                           next_retry_at  = NULL
                     WHERE source_id = %s AND schema_name = %s AND table_name = %s
                 RETURNING backlog_id, source_id, schema_name, table_name,
                           last_failure_at, failure_count, last_error_code,
                           last_error_detail, first_failure_at, next_retry_at,
                           quarantined_by, quarantined_at,
                           consecutive_same_error_count
                    """,
                    (source_id, schema, table),
                )
                updated = cur.fetchone()
                if updated is not None:
                    row = dict(updated)
            logger.warning(
                "Auto-quarantined %s (%s.%s) — failure_count=%d consecutive=%d error_code=%s",
                source_id, schema, table,
                row.get("failure_count"),
                row.get("consecutive_same_error_count"),
                error_code,
            )

        return row

    def is_quarantined(self, source_id: str, schema: str, table: str) -> bool:
        """Return True iff the row exists and has a non-NULL ``quarantined_by``."""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT quarantined_by
                  FROM meta.hydration_backlog
                 WHERE source_id = %s AND schema_name = %s AND table_name = %s
                """,
                (source_id, schema, table),
            )
            row = cur.fetchone()
        if row is None:
            return False
        return row[0] is not None

    def unquarantine(
        self,
        source_id: str,
        schema: str,
        table: str,
        reason: str,
        caller: Optional[str] = None,
    ) -> None:
        """Clear quarantine flags + write an audit row to ``meta.transform_runs``.

        Args:
            source_id: Canonical ``"{schema}.{table}"`` source id.
            schema: Target schema.
            table: Target table.
            reason: Free-text operator reason (stored in the audit row's
                ``details`` JSONB).
            caller: Optional operator identifier; falls back to the
                ``USER`` env var so manual ``dk`` CLI runs auto-populate.
        """
        actor = caller or os.environ.get("USER") or "unknown"
        with self._conn.cursor() as cur:
            # Clear quarantine + reset retry clock to NOW so the next
            # dispatch run picks the source back up.
            cur.execute(
                """
                UPDATE meta.hydration_backlog
                   SET quarantined_by = NULL,
                       quarantined_at = NULL,
                       next_retry_at  = NOW()
                 WHERE source_id = %s AND schema_name = %s AND table_name = %s
                """,
                (source_id, schema, table),
            )

            # Audit row in meta.transform_runs so the unquarantine action
            # is part of the platform's standard run history. procedure_name
            # uses the `dlq:unquarantine` prefix so it's easy to filter:
            #   SELECT * FROM meta.transform_runs
            #    WHERE procedure_name LIKE 'dlq:%' ORDER BY started_at DESC;
            import json as _json
            details = _json.dumps({
                "source_id": source_id,
                "target_schema": schema,
                "target_table": table,
                "reason": reason,
                "caller": actor,
            })
            cur.execute(
                """
                INSERT INTO meta.transform_runs
                  (procedure_name, chunk_position, started_at, ended_at,
                   rows_processed, wal_bytes, status, details)
                VALUES (%s, %s, NOW(), NOW(), %s, %s, %s, %s::jsonb)
                """,
                (
                    "dlq:unquarantine",
                    "-",
                    0,
                    0,
                    "completed",
                    details,
                ),
            )

        logger.info(
            "Unquarantined %s (%s.%s) — reason=%s caller=%s",
            source_id, schema, table, reason, actor,
        )

    def list_all(self) -> List[Dict[str, Any]]:
        """Return every backlog row as a list of dicts. Used by ``--list-backlog``."""
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT backlog_id, source_id, schema_name, table_name,
                       last_failure_at, failure_count, last_error_code,
                       last_error_detail, first_failure_at, next_retry_at,
                       quarantined_by, quarantined_at,
                       consecutive_same_error_count
                  FROM meta.hydration_backlog
                 ORDER BY last_failure_at DESC
                """
            )
            return [dict(r) for r in cur.fetchall()]


__all__ = [
    "HydrationBacklogWriter",
    "DEFAULT_QUARANTINE_THRESHOLD",
]
