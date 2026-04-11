"""Concurrency tests for meta.job_locks.

Feature: 001-silver-medallion-rebuild
Task: T016
FR-025: acquire / release / TTL expiration / contention.

Requires a real Postgres connection (cnpg_conn fixture from conftest.py).
These tests are marked 'integration' — they are skipped in unit test runs.
"""

import time
import threading
import pytest
from datetime import datetime, timezone, timedelta


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_job_locks(cnpg_conn, cnpg_meta_schemas):
    """Remove any test locks before and after each test."""
    cur = cnpg_conn.cursor()
    cur.execute("DELETE FROM meta.job_locks WHERE name LIKE 'test_%'")
    cnpg_conn.commit()
    cur.close()
    yield
    cur = cnpg_conn.cursor()
    cur.execute("DELETE FROM meta.job_locks WHERE name LIKE 'test_%'")
    cnpg_conn.commit()
    cur.close()


def _acquire(conn, name: str, locked_by: str, ttl_seconds: int = 60) -> bool:
    """Try to acquire a job lock.  Returns True on success, False if already held."""
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO meta.job_locks (name, locked_by, expires_at)
            VALUES (%s, %s, NOW() + INTERVAL '%s seconds')
            """,
            (name, locked_by, ttl_seconds),
        )
        conn.commit()
        cur.close()
        return True
    except Exception:
        conn.rollback()
        return False


def _release(conn, name: str) -> None:
    """Release a job lock."""
    cur = conn.cursor()
    cur.execute("DELETE FROM meta.job_locks WHERE name = %s", (name,))
    conn.commit()
    cur.close()


def _is_held(conn, name: str) -> bool:
    """Check if a lock is currently held (ignoring TTL)."""
    cur = conn.cursor()
    cur.execute("SELECT EXISTS(SELECT 1 FROM meta.job_locks WHERE name = %s)", (name,))
    result = cur.fetchone()[0]
    cur.close()
    return result


def _is_expired(conn, name: str) -> bool:
    """Check if a lock exists but is expired."""
    cur = conn.cursor()
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM meta.job_locks WHERE name = %s AND expires_at < NOW())",
        (name,),
    )
    result = cur.fetchone()[0]
    cur.close()
    return result


class TestAcquire:
    def test_acquire_new_lock(self, cnpg_conn):
        assert _acquire(cnpg_conn, "test_acquire_new", "pod-1/42")
        assert _is_held(cnpg_conn, "test_acquire_new")

    def test_acquire_blocked_by_existing_lock(self, cnpg_conn):
        _acquire(cnpg_conn, "test_blocked", "pod-1/42")
        # Second attempt on the same name must fail (PRIMARY KEY violation)
        assert not _acquire(cnpg_conn, "test_blocked", "pod-2/99")

    def test_acquire_after_release(self, cnpg_conn):
        _acquire(cnpg_conn, "test_after_release", "pod-1/42")
        _release(cnpg_conn, "test_after_release")
        assert _acquire(cnpg_conn, "test_after_release", "pod-2/99")


class TestRelease:
    def test_release_removes_lock(self, cnpg_conn):
        _acquire(cnpg_conn, "test_release", "pod-1/42")
        _release(cnpg_conn, "test_release")
        assert not _is_held(cnpg_conn, "test_release")

    def test_release_nonexistent_is_noop(self, cnpg_conn):
        # Releasing a lock that doesn't exist must not raise
        _release(cnpg_conn, "test_release_nonexistent_xyz")
        assert not _is_held(cnpg_conn, "test_release_nonexistent_xyz")


class TestTTLExpiration:
    def test_expired_lock_is_detectable(self, cnpg_conn):
        """A lock with expires_at in the past is still in the table but detectable."""
        cur = cnpg_conn.cursor()
        cur.execute(
            """
            INSERT INTO meta.job_locks (name, locked_by, expires_at)
            VALUES ('test_ttl_expired', 'pod-stale/0', NOW() - INTERVAL '1 second')
            ON CONFLICT (name) DO UPDATE
              SET locked_by = EXCLUDED.locked_by,
                  expires_at = EXCLUDED.expires_at
            """
        )
        cnpg_conn.commit()
        cur.close()

        # The row exists but is expired
        assert _is_held(cnpg_conn, "test_ttl_expired")
        assert _is_expired(cnpg_conn, "test_ttl_expired")

    def test_callers_should_skip_expired_lock(self, cnpg_conn):
        """Pattern: callers check expires_at < NOW() before deciding the job is running.

        This mirrors what the bootstrap procedures do: DELETE stale rows before
        trying to INSERT.
        """
        cur = cnpg_conn.cursor()
        # Insert a stale lock
        cur.execute(
            """
            INSERT INTO meta.job_locks (name, locked_by, expires_at)
            VALUES ('test_ttl_skip', 'pod-stale/0', NOW() - INTERVAL '5 seconds')
            ON CONFLICT (name) DO UPDATE
              SET locked_by = EXCLUDED.locked_by,
                  expires_at = EXCLUDED.expires_at
            """
        )
        cnpg_conn.commit()
        cur.close()

        # Bootstrap pattern: delete stale, then re-acquire
        cur = cnpg_conn.cursor()
        cur.execute(
            "DELETE FROM meta.job_locks WHERE name = 'test_ttl_skip' AND expires_at < NOW()"
        )
        cnpg_conn.commit()
        cur.close()

        # Now a new acquire should succeed
        assert _acquire(cnpg_conn, "test_ttl_skip", "pod-new/1")


class TestContention:
    def test_only_one_thread_acquires_lock(self, cnpg_conn):
        """Two concurrent threads competing for the same lock: exactly one wins."""
        import psycopg2

        results = []

        def _try_acquire(lock_name: str, holder: str):
            # Each thread needs its own connection
            conn = psycopg2.connect(
                host=cnpg_conn.info.host,
                port=cnpg_conn.info.port,
                user=cnpg_conn.info.user,
                password=cnpg_conn.info.password,
                database=cnpg_conn.info.dbname,
            )
            try:
                ok = _acquire(conn, lock_name, holder)
                results.append(ok)
            finally:
                conn.close()

        t1 = threading.Thread(target=_try_acquire, args=("test_contention", "pod-A/1"))
        t2 = threading.Thread(target=_try_acquire, args=("test_contention", "pod-B/2"))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        # Exactly one success
        assert results.count(True) == 1
        assert results.count(False) == 1
