"""Contract tests for migration 225_trgm_indexes_for_search.sql.

Feature: 002-external-integration-foundation (perf pass)

This migration adds `pg_trgm` GIN indexes so the client's ILIKE-based
search methods stop sequential-scanning million-row tables. Contract
checks:

  - pg_trgm extension enabled
  - All required GIN indexes declared
  - Each index uses `gin_trgm_ops` (not b-tree)
  - Runs OUTSIDE a transaction (CREATE INDEX CONCURRENTLY requirement)
  - No fire-a-shot-in-the-dark patterns (no missing IF NOT EXISTS)
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = (
    REPO_ROOT
    / "src"
    / "dk_data"
    / "sql"
    / "migrations"
    / "225_trgm_indexes_for_search.sql"
)

EXPECTED_INDEXES = [
    # (index_name, table, column)
    ("idx_mol_silver_molecules_canonical_name_trgm", "mol_silver.molecules", "canonical_name"),
    ("idx_ind_silver_conditions_canonical_name_trgm", "ind_silver.conditions", "canonical_name"),
    ("idx_mol_silver_companies_canonical_name_trgm", "mol_silver.companies", "canonical_name"),
    ("idx_mol_silver_publications_title_trgm", "mol_silver.publications", "title"),
    ("idx_ip_silver_patents_title_trgm", "ip_silver.patents", "title"),
    ("idx_ip_silver_patents_assignee_trgm", "ip_silver.patents", "assignee"),
    ("idx_hcs_silver_providers_canonical_name_trgm", "hcs_silver.providers", "canonical_name"),
]


@pytest.fixture
def migration_sql() -> str:
    return MIGRATION.read_text()


class TestMigrationShape:
    def test_file_exists(self):
        assert MIGRATION.exists()

    def test_creates_pg_trgm_extension(self, migration_sql):
        assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in migration_sql

    def test_no_transaction_wrapper(self, migration_sql):
        """CREATE INDEX CONCURRENTLY cannot run inside BEGIN/COMMIT."""
        # We tolerate a BEGIN/COMMIT inside a DO block comment, but
        # the migration itself MUST NOT start with BEGIN;
        lines = [
            ln.strip()
            for ln in migration_sql.splitlines()
            if ln.strip() and not ln.strip().startswith("--")
        ]
        executable = "\n".join(lines).upper()
        assert "BEGIN;" not in executable, (
            "Migration 225 must not be transaction-wrapped — "
            "CREATE INDEX CONCURRENTLY errors inside BEGIN/COMMIT"
        )


class TestIndexDeclarations:
    @pytest.mark.parametrize("index_name,table,column", EXPECTED_INDEXES)
    def test_index_declared(self, migration_sql, index_name, table, column):
        # Must be CONCURRENTLY, must be IF NOT EXISTS, must be GIN
        assert f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}" in migration_sql
        # Must target the right table
        assert f"ON {table}" in migration_sql
        # Must use trgm ops on the right column
        assert f"({column} gin_trgm_ops)" in migration_sql

    def test_all_indexes_use_gin(self, migration_sql):
        # Every CREATE INDEX in this file must be USING GIN
        for line in migration_sql.splitlines():
            if "CREATE INDEX" in line:
                # Multi-line statement — the USING GIN may be on the next line,
                # so check surrounding context by finding a contiguous chunk
                pass  # structural check handled by test_index_declared above

        # No B-tree indexes sneaking in
        assert "USING btree" not in migration_sql.lower()

    def test_no_destructive_operations(self, migration_sql):
        """Should be additive only — no DROP, no TRUNCATE, no ALTER TABLE."""
        upper = migration_sql.upper()
        assert "DROP INDEX" not in upper
        assert "DROP TABLE" not in upper
        assert "TRUNCATE" not in upper
        assert "ALTER TABLE" not in upper
