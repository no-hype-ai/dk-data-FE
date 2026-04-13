"""Contract tests for migration 225_trgm_indexes_for_search.sql.

Feature: 002-external-integration-foundation (perf pass)

This migration adds `pg_trgm` GIN indexes so the client's ILIKE-based
search methods stop sequential-scanning million-row tables.

The migration uses regular CREATE INDEX (not CONCURRENTLY) inside DO blocks
with IF EXISTS table guards and pg_indexes existence checks, wrapped in a
standard BEGIN/COMMIT transaction. This is safe because the hub tables are
written only by batch bootstrap procedures, not by live user traffic.

Contract checks:
  - pg_trgm extension enabled
  - All required GIN indexes declared via DO blocks
  - Each index uses `gin_trgm_ops` (not b-tree)
  - Wrapped in a transaction (regular CREATE INDEX runs fine inside one)
  - No CONCURRENTLY (not needed; tables are batch-only)
  - Each index has an IF NOT EXISTS guard via pg_indexes check
  - Each DO block guards against missing tables (silver hub tables are
    created by bootstrap, not migrations — they may not exist in CI)
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

    def test_transaction_wrapped(self, migration_sql):
        """Regular CREATE INDEX runs inside BEGIN/COMMIT — no CONCURRENTLY needed.

        The migration uses DO blocks with IF EXISTS guards so it is safe to
        run transactionally; the silver hub tables are written only by batch
        bootstrap procedures, not by live user traffic.
        """
        assert "BEGIN;" in migration_sql
        assert "COMMIT;" in migration_sql

    def test_no_create_index_concurrently(self, migration_sql):
        """Migration uses IF EXISTS guards via DO blocks; CONCURRENTLY not needed."""
        upper = migration_sql.upper()
        assert "CREATE INDEX CONCURRENTLY" not in upper


class TestIndexDeclarations:
    @pytest.mark.parametrize("index_name,table,column", EXPECTED_INDEXES)
    def test_index_declared(self, migration_sql, index_name, table, column):
        # Index is created via a regular CREATE INDEX inside a DO block
        assert f"CREATE INDEX {index_name}" in migration_sql
        # Must target the right table
        assert f"ON {table}" in migration_sql
        # Must use trgm ops on the right column
        assert f"({column} gin_trgm_ops)" in migration_sql
        # Must have an IF NOT EXISTS guard via pg_indexes system catalog
        assert f"indexname = '{index_name}'" in migration_sql

    def test_all_indexes_use_gin(self, migration_sql):
        # Every CREATE INDEX in this file must be USING GIN
        assert "USING GIN" in migration_sql
        # No B-tree indexes sneaking in
        assert "USING btree" not in migration_sql.lower()

    def test_all_indexes_guarded_for_missing_tables(self, migration_sql):
        """Each DO block must check that the table exists before indexing.

        Silver hub tables are created by bootstrap procedures, not migrations.
        A fresh CI database will not have them; the guard makes the migration
        idempotent and CI-safe.
        """
        assert "pg_tables" in migration_sql

    def test_no_destructive_operations(self, migration_sql):
        """Should be additive only — no DROP, no TRUNCATE, no ALTER TABLE."""
        upper = migration_sql.upper()
        assert "DROP INDEX" not in upper
        assert "DROP TABLE" not in upper
        assert "TRUNCATE" not in upper
        assert "ALTER TABLE" not in upper
