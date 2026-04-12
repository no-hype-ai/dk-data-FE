"""
T081: Bootstrap resumability tests — validate the resume/lock patterns work correctly.

These are integration tests that verify the meta-table patterns used by all
bootstrap procedures behave as expected WITHOUT actually running bootstraps.
Tests cover:
- Refresh state resume: reading last_chunk_position to skip already-processed rows
- Job lock prevents double-run: INSERT conflict when lock already held
- Stale lock can be overwritten: DELETE stale (expires_at past) then INSERT succeeds
- Zero duplicates: ON CONFLICT DO UPDATE must not inflate row counts
"""
import pytest

import psycopg2
import os

def _hub_tables_exist():
    """Check if hub tables exist (created by 031_silver_hub_rebuild migrations, not top-level)."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            user=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
            dbname=os.environ.get("POSTGRES_DB", "dk_data"),
        )
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='mol_silver' AND table_name='molecules'")
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception:
        return False

pytestmark = [
    pytest.mark.skipif(
        not _hub_tables_exist(),
        reason="Hub tables not available (031_silver_hub_rebuild migrations not applied in CI)"
    ),
    pytest.mark.integration,
]


class TestRefreshStateResumePattern:
    """meta.refresh_state correctly resumes from a saved checkpoint."""

    def test_refresh_state_resume_pattern(self, db_cursor):
        """
        Inserting a refresh_state row with last_chunk_position='1000' and then
        reading it back should return 1000 — simulating a restart that would
        skip rows with id <= 1000.
        """
        proc_name = "_test_resume_pattern_"

        # Clean up from prior test runs (if any)
        db_cursor.execute(
            "DELETE FROM meta.refresh_state WHERE procedure_name = %s",
            (proc_name,),
        )

        # Simulate: procedure ran one chunk and committed position 1000
        db_cursor.execute(
            """
            INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
            VALUES (%s, '1000', 'in_progress')
            """,
            (proc_name,),
        )

        # Simulate restart: read last_chunk_position
        db_cursor.execute(
            "SELECT last_chunk_position FROM meta.refresh_state WHERE procedure_name = %s",
            (proc_name,),
        )
        row = db_cursor.fetchone()
        assert row is not None, "refresh_state row not found after INSERT"
        resume_pos = int(row[0])
        assert resume_pos == 1000, (
            f"Expected last_chunk_position=1000, got {resume_pos}. "
            "Bootstrap would process rows with id > 1000 — correct resume behavior."
        )

    def test_refresh_state_upsert_preserves_existing(self, db_cursor):
        """
        ON CONFLICT DO UPDATE in refresh_state should NOT reset position back
        to '0' if the row is already 'in_progress'.
        """
        proc_name = "_test_upsert_preserve_"

        db_cursor.execute(
            "DELETE FROM meta.refresh_state WHERE procedure_name = %s",
            (proc_name,),
        )
        # Existing in-progress row with position 5000
        db_cursor.execute(
            """
            INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
            VALUES (%s, '5000', 'in_progress')
            """,
            (proc_name,),
        )

        # Bootstrap start: INSERT ... ON CONFLICT DO UPDATE only when status <> 'in_progress'
        db_cursor.execute(
            """
            INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
            VALUES (%s, '0', 'in_progress')
            ON CONFLICT (procedure_name) DO UPDATE
                SET status = 'in_progress', last_commit_at = NOW()
                WHERE meta.refresh_state.status <> 'in_progress'
            """,
            (proc_name,),
        )

        db_cursor.execute(
            "SELECT last_chunk_position FROM meta.refresh_state WHERE procedure_name = %s",
            (proc_name,),
        )
        pos = int(db_cursor.fetchone()[0])
        assert pos == 5000, (
            f"ON CONFLICT should preserve existing position 5000 when already in_progress, got {pos}"
        )


class TestJobLockPreventsDoubleRun:
    """A valid (non-expired) job lock should prevent a second acquire attempt."""

    def test_job_lock_prevents_double_run(self, db_cursor):
        """
        With a valid lock in meta.job_locks, a second INSERT ... ON CONFLICT DO NOTHING
        must not insert a row — simulating the double-run guard.
        """
        lock_name = "_test_lock_double_run_"

        # Clean up
        db_cursor.execute(
            "DELETE FROM meta.job_locks WHERE name = %s", (lock_name,)
        )

        # First acquire
        db_cursor.execute(
            """
            INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
            VALUES (%s, 'pid_111', NOW(), NOW() + INTERVAL '4 hours')
            ON CONFLICT (name) DO NOTHING
            """,
            (lock_name,),
        )

        # Second acquire attempt (simulates second pod/process)
        db_cursor.execute(
            """
            INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
            VALUES (%s, 'pid_222', NOW(), NOW() + INTERVAL '4 hours')
            ON CONFLICT (name) DO NOTHING
            """,
            (lock_name,),
        )

        # Only one lock row should exist; locked_by should still be pid_111
        db_cursor.execute(
            "SELECT locked_by FROM meta.job_locks WHERE name = %s",
            (lock_name,),
        )
        row = db_cursor.fetchone()
        assert row is not None, "Lock row disappeared unexpectedly"
        assert row[0] == "pid_111", (
            f"Second INSERT should not overwrite lock; expected locked_by='pid_111', got '{row[0]}'"
        )


class TestStaleLockCanBeOverwritten:
    """An expired lock (expires_at in the past) can be cleared and re-acquired."""

    def test_stale_lock_can_be_overwritten(self, db_cursor):
        """
        With an expired lock, DELETE stale (expires_at < NOW()) then INSERT
        must succeed, giving the new holder the lock.
        """
        lock_name = "_test_stale_lock_"

        # Clean up
        db_cursor.execute(
            "DELETE FROM meta.job_locks WHERE name = %s", (lock_name,)
        )

        # Insert an expired (stale) lock
        db_cursor.execute(
            """
            INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
            VALUES (%s, 'old_pid', NOW() - INTERVAL '5 hours', NOW() - INTERVAL '1 hour')
            """,
            (lock_name,),
        )

        # Bootstrap stale-lock delete pattern
        db_cursor.execute(
            "DELETE FROM meta.job_locks WHERE name = %s AND expires_at < NOW()",
            (lock_name,),
        )

        # Verify stale lock was deleted
        db_cursor.execute(
            "SELECT COUNT(*) FROM meta.job_locks WHERE name = %s",
            (lock_name,),
        )
        count = db_cursor.fetchone()[0]
        assert count == 0, "Stale lock should have been deleted"

        # New acquire should succeed
        db_cursor.execute(
            """
            INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
            VALUES (%s, 'new_pid', NOW(), NOW() + INTERVAL '4 hours')
            ON CONFLICT (name) DO NOTHING
            """,
            (lock_name,),
        )

        db_cursor.execute(
            "SELECT locked_by FROM meta.job_locks WHERE name = %s",
            (lock_name,),
        )
        row = db_cursor.fetchone()
        assert row is not None, "New lock INSERT failed"
        assert row[0] == "new_pid", (
            f"Expected new lock holder 'new_pid', got '{row[0]}'"
        )


class TestZeroDuplicateRows:
    """ON CONFLICT DO UPDATE must not inflate row counts."""

    def test_zero_duplicate_rows_molecules(self, db_cursor):
        """
        Insert 3 molecules with known inchi_keys. Re-run INSERT ... ON CONFLICT
        DO UPDATE. Total count must remain 3.

        This validates that mol_silver.bootstrap_molecules uses correct
        upsert semantics for the inchi_key unique constraint.
        """
        test_inchi_keys = [
            "RYYVLZVUVIJVGH-UHFFFAOYSA-N",  # aspirin
            "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",  # ibuprofen
            "HEFNNWSXXWATRW-UHFFFAOYSA-N",  # acetaminophen
        ]

        # Clean up any prior test rows
        db_cursor.execute(
            "DELETE FROM mol_silver.molecules WHERE inchi_key = ANY(%s)",
            (test_inchi_keys,),
        )

        # First insert
        for inchi_key in test_inchi_keys:
            db_cursor.execute(
                """
                INSERT INTO mol_silver.molecules (inchi_key, canonical_name, is_biologic)
                VALUES (%s, %s, false)
                ON CONFLICT (inchi_key) DO UPDATE SET
                    last_updated_at = NOW()
                """,
                (inchi_key, f"test_molecule_{inchi_key[:8]}"),
            )

        # Re-run (simulates resume / re-bootstrap)
        for inchi_key in test_inchi_keys:
            db_cursor.execute(
                """
                INSERT INTO mol_silver.molecules (inchi_key, canonical_name, is_biologic)
                VALUES (%s, %s, false)
                ON CONFLICT (inchi_key) DO UPDATE SET
                    last_updated_at = NOW()
                """,
                (inchi_key, f"test_molecule_{inchi_key[:8]}"),
            )

        # Count must be exactly 3
        db_cursor.execute(
            "SELECT COUNT(*) FROM mol_silver.molecules WHERE inchi_key = ANY(%s)",
            (test_inchi_keys,),
        )
        count = db_cursor.fetchone()[0]
        assert count == 3, (
            f"Expected 3 rows after double-insert with ON CONFLICT DO UPDATE, got {count}. "
            "Duplicate rows would cause incorrect hub counts downstream."
        )

    def test_zero_duplicate_rows_conditions(self, db_cursor):
        """
        Insert 3 conditions with known mesh_descriptor_ids. Re-run with
        ON CONFLICT (mesh_descriptor_id) DO UPDATE. Total count must remain 3.
        """
        test_mesh_ids = ["D001249", "D003924", "D006973"]  # Anxiety, Diabetes type 2, Hypertension

        db_cursor.execute(
            "DELETE FROM ind_silver.conditions WHERE mesh_descriptor_id = ANY(%s)",
            (test_mesh_ids,),
        )

        for mesh_id in test_mesh_ids:
            db_cursor.execute(
                """
                INSERT INTO ind_silver.conditions (mesh_descriptor_id, canonical_name)
                VALUES (%s, %s)
                ON CONFLICT (mesh_descriptor_id) DO UPDATE SET
                    canonical_name  = EXCLUDED.canonical_name,
                    last_updated_at = NOW()
                """,
                (mesh_id, f"test_condition_{mesh_id}"),
            )

        # Second pass
        for mesh_id in test_mesh_ids:
            db_cursor.execute(
                """
                INSERT INTO ind_silver.conditions (mesh_descriptor_id, canonical_name)
                VALUES (%s, %s)
                ON CONFLICT (mesh_descriptor_id) DO UPDATE SET
                    canonical_name  = EXCLUDED.canonical_name,
                    last_updated_at = NOW()
                """,
                (mesh_id, f"test_condition_{mesh_id}_v2"),
            )

        db_cursor.execute(
            "SELECT COUNT(*) FROM ind_silver.conditions WHERE mesh_descriptor_id = ANY(%s)",
            (test_mesh_ids,),
        )
        count = db_cursor.fetchone()[0]
        assert count == 3, (
            f"Expected 3 ind_silver.conditions rows, got {count}. "
            "ON CONFLICT (mesh_descriptor_id) DO UPDATE must not create duplicates."
        )
