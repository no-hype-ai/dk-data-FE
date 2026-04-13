"""WAL-aware bulk-insert helpers for dk-data ingestion.

Feature: 002-external-integration-foundation (perf pass, [WALMX])

## Why WAL size matters

Every INSERT/UPDATE/DELETE writes to the PostgreSQL Write-Ahead Log.
Postgres holds WAL segments on disk until:

  1. A checkpoint flushes all dirty pages to the base relation
  2. Every replica has replayed them
  3. Archival (if configured) has completed

A single bursty transaction (e.g. backfilling ChEMBL year 2023 in
one `INSERT ... SELECT`) generates 500MB+ of WAL in seconds. That
fills the WAL directory, triggers an IO-heavy checkpoint, and
stalls every concurrent reader on the same disk. Worse:

  - PgBouncer transaction mode means `SET synchronous_commit = off`
    doesn't persist across transactions, so bulk loads pay full
    fsync cost per transaction unless the loader explicitly sets
    it per operation.
  - Replicas fall behind, and if `max_wal_size` or `wal_keep_size`
    is exceeded, the primary starts rotating segments before
    replicas have read them → replication lag or full replica
    re-sync.

The `[WALMX]` tag in the project's tag system is the reminder to
keep per-transaction WAL under 2 GB. This module enforces it.

## Usage

    from dk_data.ingestion.utils.wal_budget import (
        chunked_insert,
        bulk_load_session,
    )

    # 1. Chunked insert — commits every CHUNK_SIZE rows so WAL
    #    doesn't balloon.
    with bulk_load_session(conn) as session:
        chunked_insert(
            session,
            table="mol_raw.chembl_activities",
            columns=("activity_id", "molecule_id", "target_id", "phase"),
            rows=iter_rows_from_fetch(),
            chunk_size=5_000,  # commits per chunk (reduced from 10k under infra freeze)
        )

## Rules

- Use `bulk_load_session` around any loader that writes > 100k rows
  in one call. It sets `synchronous_commit = off` (safe for
  idempotent loaders — a crash drops the last chunk, next tick
  resumes).
- Keep `chunk_size` × `row_size` under 100 MB to stay well within
  the 2 GB WAL budget with headroom for other writers.
- Every chunked insert commits explicitly. Never rely on the
  session's implicit transaction end.
- For UPSERT (INSERT ... ON CONFLICT DO UPDATE), the chunk size
  can be larger — ON CONFLICT doesn't generate extra WAL for
  no-op rows — but stay ≤ 50k rows per chunk to keep checkpoint
  pressure reasonable.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Sequence

logger = logging.getLogger("dk_data.ingestion.wal_budget")

# Per-transaction WAL budget — matches the [WALMX] tag constraint.
# Violating this can cause replication lag and checkpoint stalls
# on a shared cluster.
WAL_BUDGET_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

# Practical WAL ceiling under infra freeze (2026-04-13):
# The CNPG cluster's max_wal_size is still at the default 1 GB
# (the planned 8 GB bump is a Group B parameter — pending infra ticket).
# A checkpoint fires when WAL exceeds 1 GB, causing an IO spike that
# stalls every reader. Keep per-chunk WAL well under 500 MB so a
# checkpoint never fires mid-load. At ~1 KB/row × 2 (WAL overhead),
# 5k rows = ~10 MB/commit — 50× below the 500 MB practical ceiling.
WAL_INFRA_FREEZE_CEILING_BYTES = 500 * 1024 * 1024  # 500 MB

# Default chunk size for INSERT loaders. Reduced from 10k → 5k to
# lower checkpoint pressure under the current max_wal_size=1GB (default).
# Restore to 10k when the infra team applies max_wal_size=8GB.
# At ~1 KB/row, 5k rows produces ~10 MB of WAL per commit.
DEFAULT_CHUNK_SIZE = 5_000

# Upper bound for an UPSERT chunk. UPSERT no-ops don't write WAL so
# we can afford bigger chunks here, but cap at 25k (was 50k) for the
# same infra-freeze checkpoint-pressure reason.
DEFAULT_UPSERT_CHUNK_SIZE = 25_000


@contextmanager
def bulk_load_session(conn: Any) -> Iterator[Any]:
    """Configure a psycopg2/asyncpg connection for bulk-load mode.

    Sets:
      - `synchronous_commit = off` — disables fsync per commit;
        safe for idempotent loaders because a crash loses the
        last chunk and the next tick resumes from the checkpoint.
      - `maintenance_work_mem = 256MB` — helps batch indexing.
      - `work_mem = 128MB` — wider hash joins during loader queries.

    On exit, every setting is reset to the session default. If the
    caller's loader throws, settings are restored before the
    exception propagates.

    This context manager is idempotent per connection — nesting it
    inside another bulk_load_session is a no-op (settings already
    match).
    """
    cursor = conn.cursor()
    previous: dict[str, str] = {}
    settings = {
        "synchronous_commit": "off",
        "maintenance_work_mem": "256MB",
        "work_mem": "128MB",
    }
    try:
        for key, value in settings.items():
            cursor.execute(f"SHOW {key}")
            previous[key] = cursor.fetchone()[0]
            cursor.execute(f"SET LOCAL {key} = '{value}'")
        logger.debug(
            "bulk_load_session entered", extra={"settings": settings}
        )
        yield conn
    finally:
        # Restore previous values. `SET LOCAL` would auto-reset on
        # commit but we set them explicitly here so nested sessions
        # observe the reset even if commits are interleaved.
        for key, value in previous.items():
            try:
                cursor.execute(f"SET LOCAL {key} = '{value}'")
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "bulk_load_session restore failed",
                    extra={"key": key, "error": str(e)},
                )
        cursor.close()


def chunked_insert(
    conn: Any,
    *,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    on_conflict: str | None = None,
) -> int:
    """Insert rows in WAL-bounded chunks, committing after each chunk.

    Args:
        conn: an open psycopg2 connection (sync). For async paths,
              wrap with `asyncio.to_thread` at the call site.
        table: fully-qualified table name (e.g. `mol_raw.chembl_activities`).
        columns: column names matching the row tuples.
        rows: iterator yielding row tuples. Empty iterators are a no-op.
        chunk_size: rows per commit. Default 10k; max 50k for UPSERT.
        on_conflict: optional ON CONFLICT clause (e.g.
              `"(activity_id) DO NOTHING"`).

    Returns the total number of rows inserted (inclusive of no-op
    rows when ON CONFLICT DO NOTHING is in effect).
    """
    columns_sql = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    base_stmt = f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders})"
    if on_conflict:
        base_stmt += f" ON CONFLICT {on_conflict}"

    cursor = conn.cursor()
    total = 0
    chunk: list[Sequence[Any]] = []
    try:
        for row in rows:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                cursor.executemany(base_stmt, chunk)
                conn.commit()
                total += len(chunk)
                logger.debug(
                    "chunked_insert commit",
                    extra={"table": table, "rows": len(chunk), "total": total},
                )
                chunk = []

        # Flush the tail
        if chunk:
            cursor.executemany(base_stmt, chunk)
            conn.commit()
            total += len(chunk)
            logger.debug(
                "chunked_insert tail commit",
                extra={"table": table, "rows": len(chunk), "total": total},
            )
    finally:
        cursor.close()

    return total


def estimate_wal_per_row(row_size_bytes: int) -> int:
    """Rough estimate of WAL generated by an insert of `row_size` bytes.

    Postgres WAL records include the row data plus per-row overhead
    (xmin/xmax, tuple header, index pointers, etc.) which roughly
    doubles the raw row size. Used for loader sizing calculations.
    """
    return row_size_bytes * 2


def max_chunk_size_for_row(row_size_bytes: int) -> int:
    """Largest safe chunk_size for a given average row size.

    Enforces the 100 MB per-transaction soft limit (1/20th of the
    2 GiB hard budget).
    """
    wal_per_row = estimate_wal_per_row(row_size_bytes)
    max_rows = (100 * 1024 * 1024) // max(wal_per_row, 1)
    return min(max_rows, DEFAULT_UPSERT_CHUNK_SIZE)
