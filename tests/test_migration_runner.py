"""
Migration Runner Tests
Feature: 013-observability-governance (US4)
Tasks: T015

Tests for the migration runner (src/dk_data/scripts/run_migrations.py):
- discover_migrations() finds and sorts SQL files by numeric prefix
- compute_checksum() produces consistent SHA-256 hashes
- apply_migration() executes SQL and records in tracking table
- Skip logic for already-applied migrations
- --baseline mode marks all as applied without executing
- Halt on failure behavior
"""

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from dk_data.scripts.run_migrations import (
    apply_migration,
    apply_pending,
    baseline,
    compute_checksum,
    discover_migrations,
    ensure_tracking_table,
    get_applied_migrations,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def migrations_dir():
    """Create a temp directory with sample migration SQL files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create migrations with gaps in numbering (like the real codebase)
        files = {
            "001_create_schemas.sql": "CREATE SCHEMA IF NOT EXISTS raw;",
            "002_role_restrictions.sql": "-- roles\nSELECT 1;",
            "020_mol_schemas.sql": "CREATE SCHEMA IF NOT EXISTS mol_raw;",
            "068_schema_migrations.sql": (
                "CREATE TABLE IF NOT EXISTS meta.schema_migrations "
                "(id SERIAL PRIMARY KEY);"
            ),
        }
        for filename, content in files.items():
            Path(tmpdir, filename).write_text(content)

        # Also add a non-SQL file that should be ignored
        Path(tmpdir, "README.md").write_text("# Not a migration")

        yield tmpdir


@pytest.fixture
def empty_dir():
    """Create an empty temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_conn():
    """Create a mock database connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


# ---------------------------------------------------------------------------
# discover_migrations() tests
# ---------------------------------------------------------------------------

class TestDiscoverMigrations:
    """Tests for migration file discovery and sorting."""

    def test_finds_sql_files(self, migrations_dir):
        """Should discover all .sql files in the directory."""
        migrations = discover_migrations(migrations_dir)
        assert len(migrations) == 4

    def test_sorts_by_numeric_prefix(self, migrations_dir):
        """Should sort migrations by numeric prefix as integers."""
        migrations = discover_migrations(migrations_dir)
        versions = [v for v, _, _ in migrations]
        assert versions == ["001", "002", "020", "068"]

    def test_returns_version_filename_filepath(self, migrations_dir):
        """Each tuple should contain (version, filename, filepath)."""
        migrations = discover_migrations(migrations_dir)
        version, filename, filepath = migrations[0]
        assert version == "001"
        assert filename == "001_create_schemas.sql"
        assert filepath.endswith("001_create_schemas.sql")
        assert os.path.isfile(filepath)

    def test_ignores_non_sql_files(self, migrations_dir):
        """Should ignore files without .sql extension."""
        migrations = discover_migrations(migrations_dir)
        filenames = [fn for _, fn, _ in migrations]
        assert "README.md" not in filenames

    def test_empty_directory(self, empty_dir):
        """Should return empty list for directory with no SQL files."""
        migrations = discover_migrations(empty_dir)
        assert migrations == []

    def test_nonexistent_directory(self):
        """Should return empty list for missing directory."""
        migrations = discover_migrations("/nonexistent/path")
        assert migrations == []

    def test_numeric_sort_not_lexicographic(self):
        """Prefixes like 2 and 20 should sort numerically, not as strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["2_b.sql", "20_c.sql", "1_a.sql", "100_d.sql"]:
                Path(tmpdir, name).write_text("SELECT 1;")

            migrations = discover_migrations(tmpdir)
            versions = [v for v, _, _ in migrations]
            assert versions == ["1", "2", "20", "100"]


# ---------------------------------------------------------------------------
# compute_checksum() tests
# ---------------------------------------------------------------------------

class TestComputeChecksum:
    """Tests for SHA-256 checksum computation."""

    def test_returns_sha256_hex(self):
        """Should return a 64-character hex SHA-256 digest."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("CREATE TABLE foo (id INT);")
            f.flush()
            checksum = compute_checksum(f.name)

        os.unlink(f.name)
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_consistent_results(self):
        """Same file content should always produce the same checksum."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("SELECT 1;")
            f.flush()
            c1 = compute_checksum(f.name)
            c2 = compute_checksum(f.name)

        os.unlink(f.name)
        assert c1 == c2

    def test_different_content_different_checksum(self):
        """Different file contents should produce different checksums."""
        checksums = []
        paths = []
        for content in ["SELECT 1;", "SELECT 2;"]:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sql", delete=False
            ) as f:
                f.write(content)
                f.flush()
                checksums.append(compute_checksum(f.name))
                paths.append(f.name)

        for p in paths:
            os.unlink(p)
        assert checksums[0] != checksums[1]

    def test_matches_hashlib_directly(self):
        """Result should match direct hashlib SHA-256 computation."""
        content = "CREATE SCHEMA IF NOT EXISTS test;"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write(content)
            f.flush()
            checksum = compute_checksum(f.name)

        os.unlink(f.name)
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert checksum == expected


# ---------------------------------------------------------------------------
# ensure_tracking_table() tests
# ---------------------------------------------------------------------------

class TestEnsureTrackingTable:
    """Tests for tracking table creation."""

    def test_executes_create_statements(self, mock_conn):
        """Should execute CREATE SCHEMA and CREATE TABLE IF NOT EXISTS."""
        conn, cursor = mock_conn
        ensure_tracking_table(conn)
        # Should have executed SQL via cursor
        assert cursor.execute.called
        sql = cursor.execute.call_args[0][0]
        assert "CREATE SCHEMA IF NOT EXISTS meta" in sql
        assert "CREATE TABLE IF NOT EXISTS meta.schema_migrations" in sql
        conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_applied_migrations() tests
# ---------------------------------------------------------------------------

class TestGetAppliedMigrations:
    """Tests for retrieving applied migration versions."""

    def test_returns_set_of_versions(self, mock_conn):
        """Should return a set of version strings."""
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [("001",), ("002",), ("020",)]
        result = get_applied_migrations(conn)
        assert result == {"001", "002", "020"}

    def test_returns_empty_set_when_no_migrations(self, mock_conn):
        """Should return empty set when no migrations have been applied."""
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        result = get_applied_migrations(conn)
        assert result == set()


# ---------------------------------------------------------------------------
# apply_migration() tests
# ---------------------------------------------------------------------------

class TestApplyMigration:
    """Tests for applying a single migration."""

    def test_executes_sql_and_records(self, mock_conn):
        """Should execute the migration SQL and insert tracking record."""
        conn, cursor = mock_conn
        sql_content = "CREATE TABLE IF NOT EXISTS test.foo (id INT);"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sql", delete=False
        ) as f:
            f.write(sql_content)
            f.flush()
            elapsed = apply_migration(
                conn, f.name, "099", "099_test.sql", "abc123"
            )

        os.unlink(f.name)

        # Should have executed the migration SQL first
        calls = cursor.execute.call_args_list
        assert len(calls) == 2

        # First call: the migration SQL
        assert sql_content in calls[0][0][0]

        # Second call: the INSERT into schema_migrations
        insert_sql = calls[1][0][0]
        assert "INSERT INTO meta.schema_migrations" in insert_sql
        insert_params = calls[1][0][1]
        assert insert_params[0] == "099"
        assert insert_params[1] == "099_test.sql"
        assert insert_params[2] == "abc123"
        assert insert_params[3] == "migration-runner"

        # Should commit
        conn.commit.assert_called_once()

        # Should return execution time in ms
        assert isinstance(elapsed, int)
        assert elapsed >= 0

    def test_returns_execution_time(self, mock_conn):
        """Should return non-negative integer milliseconds."""
        conn, cursor = mock_conn

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sql", delete=False
        ) as f:
            f.write("SELECT 1;")
            f.flush()
            elapsed = apply_migration(conn, f.name, "001", "001_test.sql", "xyz")

        os.unlink(f.name)
        assert isinstance(elapsed, int)
        assert elapsed >= 0


# ---------------------------------------------------------------------------
# apply_pending() — skip logic tests
# ---------------------------------------------------------------------------

class TestApplyPendingSkipLogic:
    """Tests for the skip/pending orchestration logic."""

    @patch("dk_data.scripts.run_migrations.get_connection")
    @patch("dk_data.scripts.run_migrations.apply_migration")
    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_skips_already_applied(
        self, mock_ensure, mock_get_applied, mock_apply, mock_get_conn,
        migrations_dir,
    ):
        """Already-applied migrations should be skipped."""
        conn = MagicMock()
        mock_get_applied.return_value = {"001", "002"}
        mock_apply.return_value = 10  # 10ms execution time

        result = apply_pending(conn, migrations_dir)
        assert result is True

        # Should only apply 020 and 068, not 001 and 002
        applied_versions = [
            c.args[2] for c in mock_apply.call_args_list
        ]
        assert "001" not in applied_versions
        assert "002" not in applied_versions
        assert "020" in applied_versions
        assert "068" in applied_versions

    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_no_pending_migrations(
        self, mock_ensure, mock_get_applied, migrations_dir
    ):
        """Should report no pending migrations when all are applied."""
        conn = MagicMock()
        mock_get_applied.return_value = {"001", "002", "020", "068"}

        result = apply_pending(conn, migrations_dir)
        assert result is True

    @patch("dk_data.scripts.run_migrations.apply_migration")
    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_dry_run_does_not_apply(
        self, mock_ensure, mock_get_applied, mock_apply, migrations_dir
    ):
        """Dry run should not call apply_migration."""
        conn = MagicMock()
        mock_get_applied.return_value = set()

        result = apply_pending(conn, migrations_dir, dry_run=True)
        assert result is True
        mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# Halt on failure tests
# ---------------------------------------------------------------------------

class TestHaltOnFailure:
    """Tests for halt-on-failure behavior."""

    @patch("dk_data.scripts.run_migrations.apply_migration")
    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_halts_on_first_error(
        self, mock_ensure, mock_get_applied, mock_apply, migrations_dir
    ):
        """Should stop at first failed migration and return False."""
        conn = MagicMock()
        mock_get_applied.return_value = set()

        # First migration succeeds, second fails
        mock_apply.side_effect = [10, Exception("syntax error at line 3")]

        result = apply_pending(conn, migrations_dir)
        assert result is False

        # Should have attempted only 2 migrations (001 OK, 002 FAIL)
        assert mock_apply.call_count == 2

        # Connection should have been rolled back on failure
        conn.rollback.assert_called_once()

    @patch("dk_data.scripts.run_migrations.apply_migration")
    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_failed_migration_not_recorded(
        self, mock_ensure, mock_get_applied, mock_apply, migrations_dir
    ):
        """Failed migration should NOT be inserted into tracking table.

        apply_migration raises before recording, so the tracking INSERT
        is only reached on success. The rollback ensures nothing persists.
        """
        conn = MagicMock()
        mock_get_applied.return_value = {"001"}  # 001 already applied

        # 002 fails immediately
        mock_apply.side_effect = Exception("relation does not exist")

        result = apply_pending(conn, migrations_dir)
        assert result is False

        # Verify rollback was called (transaction cleanup)
        conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Baseline mode tests
# ---------------------------------------------------------------------------

class TestBaseline:
    """Tests for --baseline mode."""

    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_baseline_marks_all_without_executing(
        self, mock_ensure, mock_get_applied, mock_conn, migrations_dir
    ):
        """Baseline should INSERT records without executing migration SQL."""
        conn, cursor = mock_conn
        mock_get_applied.return_value = set()

        result = baseline(conn, migrations_dir)
        assert result is True

        # Should have inserted 4 records (one per migration)
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if c.args and "INSERT INTO meta.schema_migrations" in c.args[0]
        ]
        assert len(insert_calls) == 4

        # All should use applied_by='baseline'
        for insert_call in insert_calls:
            params = insert_call.args[1]
            assert params[3] == "baseline"
            # execution_time_ms should be 0
            assert params[4] == 0

    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_baseline_skips_already_applied(
        self, mock_ensure, mock_get_applied, mock_conn, migrations_dir
    ):
        """Baseline should not re-insert already-applied migrations."""
        conn, cursor = mock_conn
        mock_get_applied.return_value = {"001", "002"}

        result = baseline(conn, migrations_dir)
        assert result is True

        # Should only insert for the 2 not-yet-applied (020, 068)
        insert_calls = [
            c for c in cursor.execute.call_args_list
            if c.args and "INSERT INTO meta.schema_migrations" in c.args[0]
        ]
        assert len(insert_calls) == 2

    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_baseline_all_already_applied(
        self, mock_ensure, mock_get_applied, mock_conn, migrations_dir
    ):
        """Should report no work when all already baselined."""
        conn, cursor = mock_conn
        mock_get_applied.return_value = {"001", "002", "020", "068"}

        result = baseline(conn, migrations_dir)
        assert result is True

    @patch("dk_data.scripts.run_migrations.get_applied_migrations")
    @patch("dk_data.scripts.run_migrations.ensure_tracking_table")
    def test_baseline_commits_transaction(
        self, mock_ensure, mock_get_applied, mock_conn, migrations_dir
    ):
        """Baseline should commit the transaction after inserting."""
        conn, cursor = mock_conn
        mock_get_applied.return_value = set()

        baseline(conn, migrations_dir)
        conn.commit.assert_called()


# ---------------------------------------------------------------------------
# CLI integration test (main)
# ---------------------------------------------------------------------------

class TestMainCLI:
    """Tests for the CLI entry point."""

    @patch("dk_data.scripts.run_migrations.get_connection")
    @patch("dk_data.scripts.run_migrations.apply_pending")
    def test_main_default_runs_apply_pending(self, mock_apply, mock_get_conn):
        """Default invocation should call apply_pending."""
        from dk_data.scripts.run_migrations import main

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_apply.return_value = True

        with patch("sys.argv", ["run_migrations"]):
            code = main()

        assert code == 0
        mock_apply.assert_called_once()

    @patch("dk_data.scripts.run_migrations.get_connection")
    @patch("dk_data.scripts.run_migrations.baseline")
    def test_main_baseline_flag(self, mock_baseline, mock_get_conn):
        """--baseline flag should call baseline()."""
        from dk_data.scripts.run_migrations import main

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_baseline.return_value = True

        with patch("sys.argv", ["run_migrations", "--baseline"]):
            code = main()

        assert code == 0
        mock_baseline.assert_called_once()

    @patch("dk_data.scripts.run_migrations.get_connection")
    def test_main_connection_failure(self, mock_get_conn):
        """Should return 1 when database connection fails."""
        from dk_data.scripts.run_migrations import main

        mock_get_conn.side_effect = psycopg2.OperationalError("connection refused")

        with patch("sys.argv", ["run_migrations"]):
            code = main()

        assert code == 1
