"""
Contract tests for migration 216_missing_mol_api_views.sql.

Feature: 002-external-integration-foundation (US-4, T072)

The migration creates exactly one new view — `mol_api.competitive_scores` —
which is a derived numeric score layered on top of
`mol_gold.competitive_landscape`. This test file asserts:

- Only `mol_api.competitive_scores` is created (not the originally-planned
  4 other views that were dropped after the silver-layer architectural
  correction)
- The view selects from `mol_gold.competitive_landscape`
- The score formula matches the documented weights:
    approved (max_phase >= 4) → 10
    phase 3 → 5
    phase 2 → 2
    phase 1 → 1
    else → 0
    plus 0.5 * LN(1 + active_trials)
- The grant gives analyst + api_user SELECT
- web_anon is never granted anything (migration 218 drops it)
- The migration is transaction-wrapped
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
    / "216_missing_mol_api_views.sql"
)


@pytest.fixture
def migration_sql() -> str:
    return MIGRATION.read_text()


class TestMigrationFileExists:
    def test_file_present(self):
        assert MIGRATION.exists()


class TestTransactionSafety:
    def test_begins_with_begin(self, migration_sql):
        assert "BEGIN;" in migration_sql

    def test_ends_with_commit(self, migration_sql):
        assert "COMMIT;" in migration_sql

    def test_lock_timeout_set(self, migration_sql):
        assert "SET LOCAL lock_timeout" in migration_sql


class TestSchemaBootstrap:
    def test_creates_mol_api_if_missing(self, migration_sql):
        assert "CREATE SCHEMA IF NOT EXISTS mol_api" in migration_sql

    def test_grants_schema_usage(self, migration_sql):
        assert "GRANT USAGE ON SCHEMA mol_api TO analyst, api_user" in migration_sql


class TestCompetitiveScoresView:
    def test_view_created(self, migration_sql):
        assert "CREATE OR REPLACE VIEW mol_api.competitive_scores" in migration_sql

    def test_view_selects_from_gold_landscape(self, migration_sql):
        assert "FROM mol_gold.competitive_landscape" in migration_sql

    @pytest.mark.parametrize(
        "column",
        [
            "molecule_id",
            "inchi_key",
            "canonical_name",
            "therapeutic_areas",
            "development_status",
            "max_phase",
            "active_trials",
            "total_trials",
            "sponsor_count",
            "indications",
            "sponsors",
            "competitive_score",
            "computed_at",
        ],
    )
    def test_view_exposes_column(self, migration_sql, column):
        assert column in migration_sql

    def test_grants_select_to_analyst_and_api_user(self, migration_sql):
        assert (
            "GRANT SELECT ON mol_api.competitive_scores TO analyst, api_user"
            in migration_sql
        )

    def test_no_web_anon_grant(self, migration_sql):
        assert "web_anon" not in migration_sql.lower()


class TestScoreFormula:
    """Check the CASE weights match the documented scoring table."""

    def test_approved_weight_10(self, migration_sql):
        assert "WHEN cl.max_phase >= 4 THEN 10" in migration_sql

    def test_phase_3_weight_5(self, migration_sql):
        assert "WHEN cl.max_phase = 3" in migration_sql
        assert "THEN 5" in migration_sql

    def test_phase_2_weight_2(self, migration_sql):
        assert "WHEN cl.max_phase = 2" in migration_sql
        assert "THEN 2" in migration_sql

    def test_phase_1_weight_1(self, migration_sql):
        assert "WHEN cl.max_phase = 1" in migration_sql
        assert "THEN 1" in migration_sql

    def test_preclinical_else_zero(self, migration_sql):
        assert "ELSE 0" in migration_sql

    def test_momentum_bonus(self, migration_sql):
        # 0.5 * LN(1 + COALESCE(active_trials, 0))
        assert "0.5" in migration_sql
        assert "LN(1 + COALESCE" in migration_sql
        assert "active_trials" in migration_sql

    def test_score_cast_to_numeric(self, migration_sql):
        assert "NUMERIC(6, 2)" in migration_sql


class TestDroppedViewsNotCreated:
    """The 4 originally-planned views must not be created — they were
    dropped after the silver-layer architectural correction."""

    @pytest.mark.parametrize(
        "view",
        [
            "mol_api.boxed_warnings",
            "mol_api.contraindications",
            "mol_api.companies",
            "mol_api.publications",
        ],
    )
    def test_dropped_view_not_created(self, migration_sql, view):
        assert f"CREATE OR REPLACE VIEW {view}" not in migration_sql
        assert f"CREATE VIEW {view}" not in migration_sql

    def test_only_one_view_created(self, migration_sql):
        # Exactly one CREATE OR REPLACE VIEW statement in the whole file
        count = migration_sql.count("CREATE OR REPLACE VIEW")
        assert count == 1, f"expected exactly 1 CREATE OR REPLACE VIEW, found {count}"


class TestDocumentation:
    def test_view_has_comment(self, migration_sql):
        assert "COMMENT ON VIEW mol_api.competitive_scores" in migration_sql

    def test_comment_explains_formula(self, migration_sql):
        # Surface-level check that the formula is documented in the view
        # comment so consumers can look it up via psql \d+.
        assert "Score formula" in migration_sql
