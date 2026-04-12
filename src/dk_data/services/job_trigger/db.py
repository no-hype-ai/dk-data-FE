"""Job Trigger DB connection management with TTL-based recycling.

Feature: 001-silver-medallion-rebuild
Task: T193 — Connection TTL: recycle DB connections every 1000 requests or 1 hour

Wraps the shared connection pool from dk_data.ingestion.utils.database and adds
a lightweight request-count + time-based recycling policy for the job-trigger
service, which is a long-running process that accumulates stale connections.
"""

import logging
import threading
import time
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection as PgConnection

from dk_data.ingestion.utils.database import get_connection_params
from dk_data.ingestion.utils.database import build_dsn

logger = logging.getLogger(__name__)

# Recycle the connection pool after this many requests OR this many seconds
_MAX_REQUESTS_PER_CONN = 1000
_MAX_CONN_AGE_SECONDS = 3600  # 1 hour

_lock = threading.Lock()
_conn: PgConnection | None = None
_conn_created_at: float = 0.0
_conn_request_count: int = 0


def _is_conn_expired() -> bool:
    """Return True if the connection should be recycled."""
    if _conn is None:
        return True
    age = time.monotonic() - _conn_created_at
    return (
        _conn_request_count >= _MAX_REQUESTS_PER_CONN
        or age >= _MAX_CONN_AGE_SECONDS
        or _conn.closed != 0
    )


def _open_connection() -> PgConnection:
    """Open a new direct psycopg2 connection (bypasses PgBouncer pool)."""
    get_connection_params()
    conn = psycopg2.connect(build_dsn(application_name="job-trigger"))
    conn.autocommit = False
    return conn


def _recycle() -> None:
    """Close old connection and open a new one. Must be called under _lock."""
    global _conn, _conn_created_at, _conn_request_count

    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass

    _conn = _open_connection()
    _conn_created_at = time.monotonic()
    _conn_request_count = 0
    logger.debug("Job-trigger DB connection recycled")


@contextmanager
def get_job_trigger_connection() -> Generator[PgConnection, None, None]:
    """Yield a psycopg2 connection with TTL-based recycling.

    Recycles after _MAX_REQUESTS_PER_CONN requests or _MAX_CONN_AGE_SECONDS.
    Thread-safe via a module-level lock.

    Usage:
        with get_job_trigger_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.commit()
    """
    global _conn_request_count

    with _lock:
        if _is_conn_expired():
            _recycle()
        _conn_request_count += 1
        conn = _conn

    try:
        yield conn
    except Exception:
        # On any exception, force recycle on next call
        with _lock:
            _conn_request_count = _MAX_REQUESTS_PER_CONN
        raise
