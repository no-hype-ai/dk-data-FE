"""Application-side query timing utilities.

Feature: 001-silver-medallion-rebuild / T224
Provides timed_query() — a context manager that measures wall-clock duration
of a database operation and logs slow queries to meta.slow_query_log when the
duration exceeds SLOW_QUERY_THRESHOLD_MS.
"""

import hashlib
import logging
import os
import time
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Log to meta.slow_query_log when a query exceeds this threshold
SLOW_QUERY_THRESHOLD_MS: float = float(
    os.environ.get("SLOW_QUERY_THRESHOLD_MS", "5000")
)

_POD_NAME = os.environ.get("HOSTNAME", "")
_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "dk-data")


@contextmanager
def timed_query(
    query: str,
    schema_name: Optional[str] = None,
    table_name: Optional[str] = None,
    operation: Optional[str] = None,
    conn=None,
) -> Generator[None, None, None]:
    """Context manager that measures query wall-clock time.

    Logs slow queries to meta.slow_query_log when duration exceeds
    SLOW_QUERY_THRESHOLD_MS (default 5000 ms).

    Usage::

        with timed_query("INSERT INTO mol_bronze.chembl_activities ...",
                         schema_name="mol_bronze",
                         table_name="chembl_activities",
                         operation="INSERT",
                         conn=conn):
            cur.execute(sql, params)

    Args:
        query: The SQL string being executed (used for hash + prefix only).
        schema_name: Optional schema for categorization.
        table_name: Optional table name for categorization.
        operation: Optional SQL verb (SELECT, INSERT, etc.).
        conn: An open psycopg2 connection to write the slow-query row.
              If None, only a WARNING log is emitted.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration_ms = (time.monotonic() - start) * 1000

        if duration_ms >= SLOW_QUERY_THRESHOLD_MS:
            query_hash = hashlib.md5(query.encode(), usedforsecurity=False).hexdigest()
            query_prefix = query[:200].replace("\n", " ").strip()

            logger.warning(
                "Slow query detected",
                extra={
                    "duration_ms": round(duration_ms, 3),
                    "query_hash": query_hash,
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "operation": operation,
                },
            )

            if conn is not None:
                _write_slow_query_log(
                    conn=conn,
                    duration_ms=duration_ms,
                    query_hash=query_hash,
                    query_prefix=query_prefix,
                    schema_name=schema_name,
                    table_name=table_name,
                    operation=operation,
                )


def _write_slow_query_log(
    conn,
    duration_ms: float,
    query_hash: str,
    query_prefix: str,
    schema_name: Optional[str],
    table_name: Optional[str],
    operation: Optional[str],
) -> None:
    """Insert a row into meta.slow_query_log. Best-effort — never raises."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.slow_query_log
                    (duration_ms, query_hash, query_prefix, schema_name,
                     table_name, operation, pod_name, service_name)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    round(duration_ms, 3),
                    query_hash,
                    query_prefix,
                    schema_name,
                    table_name,
                    operation,
                    _POD_NAME,
                    _SERVICE_NAME,
                ),
            )
        conn.commit()
    except Exception as exc:
        logger.debug("Failed to write slow_query_log: %s", exc)
