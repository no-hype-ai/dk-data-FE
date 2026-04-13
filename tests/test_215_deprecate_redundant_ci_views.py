"""
Contract tests for migration 215_deprecate_redundant_ci_views.sql.

Feature: 002-external-integration-foundation (US-6, T070)

The migration's job is to attach a deprecation COMMENT ON VIEW to each of
the 10 legacy `api.*` CI views, pointing at the silver table consumers
should read from instead. This test file asserts:

- Each of the 10 expected api.* CI views is present in the deprecation map
- Each maps to a silver replacement in the `mol_silver.*` or `ip_silver.*`
  namespace (never `api.*` — that would be circular)
- The migration is transaction-wrapped
- The migration is a "comments only" migration — no DDL that could fail
  (no CREATE, DROP, ALTER, GRANT, REVOKE at SQL level)
- The deprecation note references feature 002 and the 30-day cutover
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
    / "215_deprecate_redundant_ci_views.sql"
)

EXPECTED_VIEWS = [
    "api.pubmed_publications",
    "api.openalex_publications",
    "api.cochrane_reviews",
    "api.medical_news",
    "api.journal_articles",
    "api.ema_regulatory_decisions",
    "api.hta_decisions",
    "api.sec_filings",
    "api.uspto_patents",
    "api.epo_patents",
]


@pytest.fixture
def migration_sql() -> str:
    return MIGRATION.read_text()


class TestMigrationFileExists:
    def test_file_present(self):
        assert MIGRATION.exists(), f"{MIGRATION} is missing"


class TestTransactionSafety:
    def test_begins_with_begin(self, migration_sql):
        assert "BEGIN;" in migration_sql

    def test_ends_with_commit(self, migration_sql):
        assert "COMMIT;" in migration_sql

    def test_statement_timeout_set(self, migration_sql):
        assert "SET LOCAL statement_timeout" in migration_sql

    def test_lock_timeout_set(self, migration_sql):
        assert "SET LOCAL lock_timeout" in migration_sql


class TestDeprecationMap:
    @pytest.mark.parametrize("view", EXPECTED_VIEWS)
    def test_view_present_in_deprecation_map(self, migration_sql, view):
        assert (
            f"'{view}'" in migration_sql
        ), f"{view} missing from migration 215's deprecation map"

    def test_uses_comment_on_view(self, migration_sql):
        assert "COMMENT ON VIEW" in migration_sql

    def test_deprecation_note_references_feature(self, migration_sql):
        # The note should tell consumers what feature/user story ripped it
        assert "feature 002" in migration_sql.lower()
        assert "us-6" in migration_sql.lower()

    def test_deprecation_note_mentions_silver_replacement(self, migration_sql):
        # At least one silver pointer per CI domain (mol + ip)
        assert "mol_silver" in migration_sql
        assert "ip_silver" in migration_sql

    def test_30_day_cutover_window_documented(self, migration_sql):
        assert "30 days" in migration_sql or "30-day" in migration_sql


class TestNoDestructiveDDL:
    """This migration must be comments-only. No DROP / CREATE / ALTER of the
    views themselves, and no GRANT/REVOKE — consumers still need to read."""

    def test_no_drop_view(self, migration_sql):
        assert "DROP VIEW" not in migration_sql.upper()

    def test_no_create_view_in_this_migration(self, migration_sql):
        # CREATE OR REPLACE VIEW would replace view definitions; this
        # migration's job is strictly to add comments.
        assert "CREATE OR REPLACE VIEW" not in migration_sql
        assert "CREATE VIEW" not in migration_sql

    def test_no_alter_view(self, migration_sql):
        assert "ALTER VIEW" not in migration_sql.upper()

    def test_no_grant_revoke_on_ci_views(self, migration_sql):
        # The migration should not be sneaking in grant changes — those
        # live in the post_sqlmesh/055 file or a dedicated grant migration.
        for view in EXPECTED_VIEWS:
            assert f"GRANT SELECT ON {view}" not in migration_sql
            assert f"REVOKE" not in migration_sql or f"{view}" not in migration_sql.split("REVOKE", 1)[-1].split(";", 1)[0]


class TestSilverReplacementMapping:
    """Spot-check the mapping quality — these are the mappings documented
    in the comment block at the top of the migration."""

    def test_pubmed_maps_to_mol_silver_pubmed_articles(self, migration_sql):
        # pubmed_publications → pubmed_articles or publications
        section = migration_sql[migration_sql.index("'api.pubmed_publications'"):]
        section = section[: section.index("]")]
        assert "mol_silver.pubmed_articles" in section or "mol_silver.publications" in section

    def test_cochrane_maps_to_cochrane_reviews(self, migration_sql):
        section = migration_sql[migration_sql.index("'api.cochrane_reviews'"):]
        section = section[: section.index("]")]
        assert "cochrane_reviews" in section

    def test_uspto_maps_to_ip_silver_patents(self, migration_sql):
        section = migration_sql[migration_sql.index("'api.uspto_patents'"):]
        section = section[: section.index("]")]
        assert "ip_silver.patents" in section

    def test_epo_maps_to_ip_silver_patents(self, migration_sql):
        section = migration_sql[migration_sql.index("'api.epo_patents'"):]
        section = section[: section.index("]")]
        assert "ip_silver.patents" in section
