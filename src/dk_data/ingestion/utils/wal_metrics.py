"""WAL consumption measurement utilities.

Feature: 001-silver-medallion-rebuild / T226
Provides measure_wal() — a context manager that reads pg_current_wal_lsn()
before and after a block, computes WAL bytes consumed, and writes the result
to meta.wal_usage.

FR-021: Max 2 GiB WAL per transform chunk. Exceeding this limit logs a
WARNING and sets exceeded_limit=true in meta.wal_usage (picked up by the
dk-data-wal alert rule from T098).
"""

import logging
import os
import time
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# FR-021: 2 GiB ceiling per transform chunk
WAL_LIMIT_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GiB

_POD_NAME = os.environ.get("HOSTNAME", "")


class WALCircuitBreakerOpen(Exception):
    """Raised when pre-flight WAL/archiver checks fail.

    Callers should catch this and exit cleanly (exit 0) so the CronJob
    doesn't count as a failure — the next scheduled tick will re-check.
    """


def check_wal_circuit_breaker(
    conn,
    *,
    max_wal_pct: float = 0.75,
    archiver_fail_window_minutes: int = 30,
    caller: str = "unknown",
) -> None:
    """Pre-flight check: abort if WAL is dangerously accumulated.

    Mirrors the circuit breakers in meta.backfill_orchestrator_pick()
    (migration 165) but runs in Python so every transform entry point
    can call it before doing any work.

    Checks (in order):
      1. WAL archiver health — if pg_stat_archiver shows recent failures,
         WAL cannot be recycled and will grow regardless of batch size.
      2. WAL directory size — if pg_ls_waldir() exceeds max_wal_pct of
         max_wal_size, we're already in danger territory.

    Args:
        conn: Open psycopg2 connection (autocommit=True recommended).
        max_wal_pct: Fraction of max_wal_size that triggers the breaker.
        archiver_fail_window_minutes: Only consider archiver failures
            within this many minutes as "recent".
        caller: Name of the calling transform (for log messages).

    Raises:
        WALCircuitBreakerOpen: If any check fails.
    """
    with conn.cursor() as cur:
        # Check 1: WAL archiver health
        cur.execute(
            "SELECT failed_count, last_failed_time FROM pg_stat_archiver"
        )
        row = cur.fetchone()
        if row and row[0] and row[0] > 0 and row[1] is not None:
            cur.execute(
                "SELECT last_failed_time > NOW() - INTERVAL '%s minutes' "
                "FROM pg_stat_archiver",
                (archiver_fail_window_minutes,),
            )
            recent = cur.fetchone()[0]
            if recent:
                msg = (
                    f"WAL circuit breaker OPEN ({caller}): "
                    f"archiver has {row[0]} failures, last within "
                    f"{archiver_fail_window_minutes}min — skipping transform"
                )
                logger.warning(msg)
                raise WALCircuitBreakerOpen(msg)

        # Check 2: WAL directory size vs max_wal_size
        cur.execute(
            "SELECT COALESCE(SUM(size), 0) / 1024.0 / 1024.0 FROM pg_ls_waldir()"
        )
        wal_dir_mb = float(cur.fetchone()[0] or 0)

        cur.execute(
            "SELECT setting::numeric FROM pg_settings WHERE name = 'max_wal_size'"
        )
        max_wal_mb = float(cur.fetchone()[0] or 4096)

        if wal_dir_mb > max_wal_mb * max_wal_pct:
            msg = (
                f"WAL circuit breaker OPEN ({caller}): "
                f"WAL dir {wal_dir_mb:.0f} MB > {max_wal_pct*100:.0f}% of "
                f"max_wal_size {max_wal_mb:.0f} MB — skipping transform"
            )
            logger.warning(msg)
            raise WALCircuitBreakerOpen(msg)

    logger.info(
        "WAL circuit breaker OK (%s): wal_dir=%.0f MB, max_wal=%.0f MB, archiver_ok",
        caller, wal_dir_mb, max_wal_mb,
    )


@contextmanager
def measure_wal(
    procedure_name: str,
    chunk_index: int = 0,
    conn=None,
) -> Generator[None, None, None]:
    """Measure WAL bytes consumed within a block.

    Reads pg_current_wal_lsn() before and after the block via *conn*
    (or skips measurement if conn is None), then writes a row to
    meta.wal_usage.  Emits a WARNING when the chunk exceeds FR-021's
    2 GiB ceiling.

    Usage::

        with measure_wal("mol_bronze.refresh_chembl_activities_via_tray",
                         chunk_index=1, conn=conn):
            cur.execute("CALL mol_bronze.refresh_chembl_activities_via_tray()")

    Args:
        procedure_name: Name of the procedure / transform being measured.
        chunk_index: Chunk number within the procedure (0 = full run).
        conn: An open psycopg2 connection used for LSN queries and logging.
              If None, measurement is skipped (block still executes normally).
    """
    if conn is None:
        yield
        return

    lsn_before: Optional[str] = None
    start = time.monotonic()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_current_wal_lsn()")
            lsn_before = cur.fetchone()[0]
    except Exception as exc:
        logger.debug("Could not read pre-block WAL LSN: %s", exc)

    try:
        yield
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        wal_bytes: Optional[int] = None

        if lsn_before is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), %s::pg_lsn)",
                        (lsn_before,),
                    )
                    wal_bytes = cur.fetchone()[0] or 0
            except Exception as exc:
                logger.debug("Could not compute WAL diff: %s", exc)

        exceeded = (wal_bytes is not None and wal_bytes > WAL_LIMIT_BYTES)

        if exceeded:
            logger.warning(
                "FR-021 WAL ceiling exceeded: procedure=%s chunk=%d wal_bytes=%d (limit=%d)",
                procedure_name, chunk_index, wal_bytes, WAL_LIMIT_BYTES,
            )

        if wal_bytes is not None:
            _write_wal_usage(
                conn=conn,
                procedure_name=procedure_name,
                chunk_index=chunk_index,
                wal_bytes=wal_bytes,
                duration_ms=duration_ms,
                exceeded_limit=exceeded,
            )


def _write_wal_usage(
    conn,
    procedure_name: str,
    chunk_index: int,
    wal_bytes: int,
    duration_ms: float,
    exceeded_limit: bool,
    rows_processed: Optional[int] = None,
) -> None:
    """Insert a row into meta.wal_usage. Best-effort — never raises."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.wal_usage
                    (procedure_name, chunk_index, wal_bytes, rows_processed,
                     duration_ms, pod_name, exceeded_limit)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    procedure_name,
                    chunk_index,
                    wal_bytes,
                    rows_processed,
                    round(duration_ms, 3),
                    _POD_NAME,
                    exceeded_limit,
                ),
            )
        conn.commit()
    except Exception as exc:
        logger.debug("Failed to write meta.wal_usage: %s", exc)
