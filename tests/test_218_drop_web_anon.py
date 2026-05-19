"""
Contract tests for migration 218_drop_web_anon.sql and its rollback.

Feature: 002-external-integration-foundation (US-2, T088)

The migration drops the legacy `web_anon` role entirely. The rollback is
deliberately minimum — it restores ONLY USAGE on `api`, SELECT on
`api.health`, and SELECT on `api.data_catalog` — not the full legacy grant
set (per F-D014).

This test file asserts:

- The drop migration is transaction-wrapped, idempotent, and dynamic
  (discovers schemas via information_schema rather than hardcoding)
- Role detachment from authenticator happens before DROP ROLE
- Grant revocation loops cover tables, sequences, functions, USAGE, and
  default privileges
- The rollback restores only the minimum grants, and does not re-add any
  of the legacy broad grants from migrations 086, 092, 117, 136, 043, 061
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DROP_MIGRATION = (
    REPO_ROOT / "src" / "dk_data" / "sql" / "migrations" / "218_drop_web_anon.sql"
)
ROLLBACK_MIGRATION = (
    REPO_ROOT
    / "src"
    / "dk_data"
    / "sql"
    / "migrations"
    / "218_drop_web_anon_rollback.sql"
)


@pytest.fixture
def drop_sql() -> str:
    return DROP_MIGRATION.read_text()


@pytest.fixture
def rollback_sql() -> str:
    return ROLLBACK_MIGRATION.read_text()


class TestFilesExist:
    def test_drop_present(self):
        assert DROP_MIGRATION.exists()

    def test_rollback_present(self):
        assert ROLLBACK_MIGRATION.exists()


class TestDropTransactionSafety:
    def test_begins_with_begin(self, drop_sql):
        assert "BEGIN;" in drop_sql

    def test_ends_with_commit(self, drop_sql):
        assert "COMMIT;" in drop_sql

    def test_statement_timeout_at_least_60s(self, drop_sql):
        assert "SET LOCAL statement_timeout" in drop_sql
        # REVOKE across many schemas can be slow
        assert "'120s'" in drop_sql or "'60s'" in drop_sql or "'90s'" in drop_sql

    def test_lock_timeout_set(self, drop_sql):
        assert "SET LOCAL lock_timeout" in drop_sql


class TestIdempotency:
    def test_checks_role_exists_before_action(self, drop_sql):
        # Bail-out guard: if web_anon is already gone, the migration should
        # succeed without trying to drop it again.
        assert "pg_roles" in drop_sql
        assert "rolname = 'web_anon'" in drop_sql


class TestDynamicSchemaDiscovery:
    """The migration must discover schemas dynamically so it catches
    schemas added by migrations that post-date the audit (e.g., hcs_raw
    PUF tables from migration 092)."""

    def test_uses_information_schema_role_table_grants(self, drop_sql):
        assert "information_schema.role_table_grants" in drop_sql

    def test_filters_on_grantee_web_anon(self, drop_sql):
        assert "grantee = 'web_anon'" in drop_sql

    def test_uses_distinct_table_schema(self, drop_sql):
        assert "DISTINCT table_schema" in drop_sql


class TestRevokeCoverage:
    """Every privilege class web_anon might hold must be revoked."""

    def test_revokes_all_on_tables(self, drop_sql):
        assert "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA" in drop_sql

    def test_revokes_all_on_sequences(self, drop_sql):
        assert "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA" in drop_sql

    def test_revokes_all_on_functions(self, drop_sql):
        assert "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA" in drop_sql

    def test_revokes_schema_usage(self, drop_sql):
        assert "REVOKE USAGE ON SCHEMA" in drop_sql

    def test_revokes_default_privileges(self, drop_sql):
        assert (
            "ALTER DEFAULT PRIVILEGES IN SCHEMA" in drop_sql
            and "REVOKE ALL ON TABLES FROM web_anon" in drop_sql
        )


class TestAuthenticatorDetachment:
    """web_anon must be detached from authenticator before DROP ROLE."""

    def test_revoke_from_authenticator(self, drop_sql):
        assert "REVOKE web_anon FROM authenticator" in drop_sql

    def test_drop_role_present(self, drop_sql):
        assert "DROP ROLE web_anon" in drop_sql

    def test_detach_before_drop(self, drop_sql):
        """REVOKE ... FROM authenticator must come before DROP ROLE."""
        revoke_idx = drop_sql.find("REVOKE web_anon FROM authenticator")
        drop_idx = drop_sql.find("DROP ROLE web_anon")
        assert revoke_idx >= 0 and drop_idx >= 0
        assert revoke_idx < drop_idx


class TestRollbackTransactionSafety:
    def test_begins_with_begin(self, rollback_sql):
        assert "BEGIN;" in rollback_sql

    def test_ends_with_commit(self, rollback_sql):
        assert "COMMIT;" in rollback_sql


class TestRollbackMinimumRestore:
    def test_recreates_role_if_missing(self, rollback_sql):
        assert "CREATE ROLE web_anon NOLOGIN" in rollback_sql
        assert "pg_roles" in rollback_sql

    def test_regrants_to_authenticator(self, rollback_sql):
        assert "GRANT web_anon TO authenticator" in rollback_sql

    def test_grants_usage_on_api(self, rollback_sql):
        assert "GRANT USAGE ON SCHEMA api TO web_anon" in rollback_sql

    def test_grants_select_on_api_health(self, rollback_sql):
        assert "GRANT SELECT ON api.health TO web_anon" in rollback_sql

    def test_grants_select_on_api_data_catalog(self, rollback_sql):
        assert "GRANT SELECT ON api.data_catalog TO web_anon" in rollback_sql


class TestIndependentOrdering:
    """Regression guard against the early design that had a pre-flight DO block
    inside migration 218 checking for a role created in 228. That ordering
    coupling would have deadlocked the migration runner if 218 ran before 228.

    These tests prove the two migrations are fully independent — each touches
    only its own target role and has no reference to the other's role.
    """

    def test_migration_218_and_228_are_independent(self):
        """218 must not mention api_user; 228 must not mention web_anon."""
        drop_sql = DROP_MIGRATION.read_text()
        grants_migration = (
            REPO_ROOT
            / "src"
            / "dk_data"
            / "sql"
            / "migrations"
            / "228_jwt_mint_schema_grants.sql"
        )
        grants_sql = grants_migration.read_text()

        def strip_comments(sql: str) -> str:
            return "\n".join(
                line for line in sql.splitlines() if not line.lstrip().startswith("--")
            )

        drop_code = strip_comments(drop_sql)
        grants_code = strip_comments(grants_sql)

        assert "api_user" not in drop_code, (
            "218_drop_web_anon.sql references api_user in executable SQL — this "
            "creates an ordering dependency on migration 228. Remove the reference "
            "so the two migrations are independent."
        )
        assert "web_anon" not in grants_code, (
            "228_jwt_mint_schema_grants.sql references web_anon in executable SQL — "
            "this creates an ordering dependency on migration 218. Remove the "
            "reference so the two migrations are independent."
        )


class TestRollbackDoesNotBroaden:
    """F-D014: rollback must not restore the full legacy grant set.
    Any hint of the old broad schemas is a regression."""

    @pytest.mark.parametrize(
        "schema",
        [
            "mol_silver",
            "hcs_silver",
            "ind_silver",
            "hcp_silver",
            "ip_silver",
            "hcs_gold",
            "mol_gold",
            "hcs_raw",
            "mol_raw",
        ],
    )
    def test_rollback_does_not_grant_broad_schema(self, rollback_sql, schema):
        """The rollback must not re-issue USAGE or SELECT on any broad
        legacy schema. Only `api` is allowed."""
        # The schema name may appear in a comment explaining what is
        # intentionally NOT being restored; we only care about actual grants.
        grant_patterns = [
            f"GRANT USAGE ON SCHEMA {schema} TO web_anon",
            f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO web_anon",
            f"GRANT SELECT ON SCHEMA {schema}",
        ]
        for pattern in grant_patterns:
            assert pattern not in rollback_sql, (
                f"Rollback broadens grants: found '{pattern}'. "
                "Rollback is minimum-only per F-D014."
            )

    def test_no_grant_select_on_all_tables(self, rollback_sql):
        # Rollback should never `GRANT SELECT ON ALL TABLES IN SCHEMA ... TO web_anon`.
        assert (
            "GRANT SELECT ON ALL TABLES IN SCHEMA" not in rollback_sql
        ), "Rollback must not restore schema-wide SELECT grants"
