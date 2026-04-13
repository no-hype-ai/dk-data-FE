"""Unit tests for the migration runner's non-transactional detection.

Feature: 002-external-integration-foundation (k8s/db audit)

The migration runner now auto-detects migrations containing
non-transactional operations (CREATE INDEX CONCURRENTLY, VACUUM
FULL, etc.) and switches to autocommit mode for them. These tests
pin the detection logic so a regression doesn't silently break
migration 225 (or any future migration that uses CONCURRENTLY).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dk_data.scripts.run_migrations import (
    NON_TRANSACTIONAL_MARKERS,
    is_non_transactional,
)


class TestNonTransactionalDetection:
    @pytest.mark.parametrize(
        "sql",
        [
            "CREATE INDEX CONCURRENTLY idx_foo ON tbl (col)",
            "create index concurrently idx_foo on tbl (col)",  # case
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx ON tbl (col)",
            "DROP INDEX CONCURRENTLY idx_foo",
            "REINDEX CONCURRENTLY INDEX idx_foo",
            "ALTER SYSTEM SET shared_buffers = '4GB'",
            "VACUUM FULL mol_silver.molecules",
            "VACUUM ANALYZE mol_silver.molecules",
            "CLUSTER mol_silver.molecules USING idx_pk",
        ],
    )
    def test_detects_non_transactional_operations(self, sql: str) -> None:
        assert is_non_transactional(sql) is True

    @pytest.mark.parametrize(
        "sql",
        [
            "CREATE INDEX idx_foo ON tbl (col)",  # not concurrent
            "CREATE TABLE foo (id int)",
            "INSERT INTO foo VALUES (1)",
            "SELECT * FROM foo",
            "BEGIN; CREATE TABLE foo (); COMMIT;",
            "GRANT SELECT ON foo TO bar",
            "ALTER TABLE foo ADD COLUMN bar text",
        ],
    )
    def test_normal_sql_is_transactional(self, sql: str) -> None:
        assert is_non_transactional(sql) is False

    def test_ignores_sql_in_full_line_comments(self) -> None:
        sql = """
        -- This migration could use CREATE INDEX CONCURRENTLY but does not
        -- See: docs/runbooks/whatever.md
        CREATE TABLE foo (id int);
        """
        assert is_non_transactional(sql) is False

    def test_ignores_sql_in_inline_comments(self) -> None:
        sql = """
        BEGIN;
        CREATE TABLE foo (id int);  -- formerly used CONCURRENTLY VACUUM hack
        COMMIT;
        """
        assert is_non_transactional(sql) is False

    def test_real_migration_225_detected(self) -> None:
        repo = Path(__file__).parent.parent
        sql = (
            repo / "src" / "dk_data" / "sql" / "migrations"
            / "225_trgm_indexes_for_search.sql"
        ).read_text()
        assert is_non_transactional(sql) is True, (
            "Migration 225 contains CREATE INDEX CONCURRENTLY and must "
            "be detected; otherwise the runner will fail with "
            "'cannot run inside a transaction block'"
        )

    def test_real_migration_215_not_detected(self) -> None:
        repo = Path(__file__).parent.parent
        sql = (
            repo / "src" / "dk_data" / "sql" / "migrations"
            / "215_deprecate_redundant_ci_views.sql"
        ).read_text()
        assert is_non_transactional(sql) is False

    def test_markers_list_includes_critical_operations(self) -> None:
        # Safety net — these are the operations that ABSOLUTELY must be
        # in the markers list. Removing any of them would silently
        # break a migration in production.
        assert "CREATE INDEX CONCURRENTLY" in NON_TRANSACTIONAL_MARKERS
        assert "VACUUM FULL" in NON_TRANSACTIONAL_MARKERS
        assert "ALTER SYSTEM" in NON_TRANSACTIONAL_MARKERS
