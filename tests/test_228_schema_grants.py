"""
Contract tests for migration 228_jwt_mint_schema_grants.sql.

Feature: 003-metering-jwt-mint (issue #283)

The migration grants api_user (the role every authenticated request switches
into via the JWT `role` claim the metering proxy mints) USAGE + SELECT on the
13 client-readable schemas, ALTER DEFAULT PRIVILEGES so future tables inherit
the SELECT grant, and EXECUTE on the 10 silver-hub resolve functions.

This test file asserts (without requiring a live Postgres connection):

- The migration file exists
- The migration is transaction-wrapped
- GRANT USAGE ON SCHEMA is present for all 13 schemas
- GRANT SELECT ON ALL TABLES IN SCHEMA is present for all 13 schemas
- ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES is present for all 13 schemas
- GRANT EXECUTE ON FUNCTION is present for all 10 resolve functions
- web_anon does not appear (this is the api_user migration, not web_anon)
- dk_data_no_anon does not appear (design simplification — no anon role here)
- No write privileges (INSERT, UPDATE, DELETE, TRUNCATE) are granted
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
    / "228_jwt_mint_schema_grants.sql"
)

SCHEMAS_13 = [
    "mol_silver",
    "mol_gold",
    "mol_api",
    "hcs_silver",
    "hcs_gold",
    "ind_silver",
    "ind_gold",
    "hcp_silver",
    "hcp_gold",
    "ip_silver",
    "ip_gold",
    "mart",
    "scoring",
]

RESOLVE_FUNCTIONS_10 = [
    "mol_silver.resolve_molecule",
    "mol_silver.resolve_drug_product",
    "mol_silver.resolve_company",
    "mol_silver.resolve_target",
    "hcs_silver.resolve_provider",
    "hcs_silver.resolve_facility",
    "ind_silver.resolve_condition",
    "hcp_silver.resolve_researcher",
    "ip_silver.resolve_patent",
    "ip_silver.resolve_trademark",
]


@pytest.fixture
def migration_sql() -> str:
    return MIGRATION.read_text()


class TestFileExists:
    def test_file_exists(self):
        assert MIGRATION.exists(), (
            f"Migration not found at {MIGRATION}. "
            "Wave 1 should have created 228_jwt_mint_schema_grants.sql."
        )


class TestTransactionWrapped:
    def test_transaction_wrapped(self, migration_sql):
        assert "BEGIN;" in migration_sql, "Migration must start a transaction with BEGIN;"
        assert "COMMIT;" in migration_sql, "Migration must end the transaction with COMMIT;"


class TestUsageGrants:
    @pytest.mark.parametrize("schema", SCHEMAS_13)
    def test_grants_usage_on_all_13_schemas(self, migration_sql, schema):
        expected = f"GRANT USAGE ON SCHEMA {schema} TO api_user"
        assert expected in migration_sql, (
            f"Missing USAGE grant on schema {schema!r}. "
            f"Expected: {expected!r}"
        )


class TestSelectGrants:
    @pytest.mark.parametrize("schema", SCHEMAS_13)
    def test_grants_select_on_all_tables_in_13_schemas(self, migration_sql, schema):
        expected = f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO api_user"
        assert expected in migration_sql, (
            f"Missing SELECT grant on all tables in schema {schema!r}. "
            f"Expected: {expected!r}"
        )


class TestDefaultPrivileges:
    @pytest.mark.parametrize("schema", SCHEMAS_13)
    def test_sets_default_privileges_for_13_schemas(self, migration_sql, schema):
        expected = (
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO api_user"
        )
        assert expected in migration_sql, (
            f"Missing ALTER DEFAULT PRIVILEGES for schema {schema!r}. "
            f"Expected: {expected!r}"
        )


class TestExecuteGrantsDeferredToMigration217:
    """Migration 228 does NOT grant EXECUTE on the resolve functions —
    migration 217_resolve_function_grants.sql already does that with a
    schema-wide ``GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ... TO api_user``
    plus ``ALTER DEFAULT PRIVILEGES``. Re-granting in 228 would duplicate
    work and requires matching exact argument signatures — which the
    earlier draft of this migration got wrong and broke the CI migration
    run (see the fix commit that ships with this test).

    This test class asserts that 228 has NO ``GRANT EXECUTE`` statements,
    so the resolve-function coverage stays in 217 where it belongs.
    """

    def test_migration_228_has_no_execute_grants(self, migration_sql):
        code_only = "\n".join(
            line
            for line in migration_sql.splitlines()
            if not line.lstrip().startswith("--")
        )
        assert "GRANT EXECUTE" not in code_only, (
            "228_jwt_mint_schema_grants.sql contains GRANT EXECUTE statements "
            "in executable SQL. Those belong in migration 217 — 228 is for "
            "schema-level USAGE + SELECT grants only."
        )


class TestRoleIsolation:
    def test_does_not_reference_web_anon(self, migration_sql):
        # Strip comment lines — the header block explains context (why web_anon
        # is being replaced) and may mention web_anon there. Only executable
        # SQL must not reference it.
        code_only = "\n".join(
            line
            for line in migration_sql.splitlines()
            if not line.lstrip().startswith("--")
        )
        assert "web_anon" not in code_only, (
            "228_jwt_mint_schema_grants.sql references web_anon in executable SQL. "
            "This is the api_user migration; web_anon is handled by migration 218."
        )

    def test_does_not_create_dk_data_no_anon(self, migration_sql):
        code_only = "\n".join(
            line
            for line in migration_sql.splitlines()
            if not line.lstrip().startswith("--")
        )
        assert "dk_data_no_anon" not in code_only, (
            "228_jwt_mint_schema_grants.sql must not create or reference "
            "dk_data_no_anon in executable SQL. Design simplification: the anon "
            "role is not created in this migration."
        )


class TestReadOnly:
    """api_user is a read-only role — no write privileges must be granted."""

    @pytest.mark.parametrize(
        "write_privilege",
        ["INSERT", "UPDATE", "DELETE", "TRUNCATE"],
    )
    def test_does_not_grant_write(self, migration_sql, write_privilege):
        # Strip comment lines to avoid false positives in inline docs
        code_only = "\n".join(
            line
            for line in migration_sql.splitlines()
            if not line.lstrip().startswith("--")
        )
        assert f"GRANT {write_privilege}" not in code_only, (
            f"Migration grants {write_privilege} to api_user — this role is "
            "read-only. Remove the write privilege grant."
        )


# ---------------------------------------------------------------------------
# T050 — FR-011: api_user must never receive write privileges (explicit class)
# ---------------------------------------------------------------------------

class TestApiUserCannotWrite:
    """FR-011: api_user is strictly read-only — no write privilege may appear."""

    @staticmethod
    def _code_only(migration_sql: str) -> str:
        return "\n".join(
            line
            for line in migration_sql.splitlines()
            if not line.lstrip().startswith("--")
        )

    def test_does_not_grant_insert(self, migration_sql):
        assert "GRANT INSERT" not in self._code_only(migration_sql), (
            "Migration grants INSERT — api_user is read-only."
        )

    def test_does_not_grant_update(self, migration_sql):
        assert "GRANT UPDATE" not in self._code_only(migration_sql), (
            "Migration grants UPDATE — api_user is read-only."
        )

    def test_does_not_grant_delete(self, migration_sql):
        assert "GRANT DELETE" not in self._code_only(migration_sql), (
            "Migration grants DELETE — api_user is read-only."
        )

    def test_does_not_grant_truncate(self, migration_sql):
        assert "GRANT TRUNCATE" not in self._code_only(migration_sql), (
            "Migration grants TRUNCATE — api_user is read-only."
        )

    def test_does_not_grant_all_to_api_user(self, migration_sql):
        """GRANT ALL would silently include write privileges even if not listed individually."""
        code_only = self._code_only(migration_sql)
        for line in code_only.splitlines():
            if "GRANT ALL" in line:
                assert "api_user" not in line, (
                    f"GRANT ALL with api_user found: {line!r}. "
                    "api_user is a read-only role — GRANT ALL is forbidden."
                )


# ---------------------------------------------------------------------------
# T051 — FR-012/FR-013: resolve-function EXECUTE grants live in migration 217
# ---------------------------------------------------------------------------

class TestResolveFunctionGrantsAreInMigration217:
    """Migration 217_resolve_function_grants.sql is the canonical home for
    EXECUTE grants on the silver-hub resolve functions. It uses a schema-wide
    ``GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ... TO analyst, api_user`` which
    sidesteps the argument-signature matching problem (the resolve functions
    don't all take ``(text)``). Migration 228 deliberately does NOT duplicate
    this work — any reintroduction of a per-function EXECUTE grant in 228
    would be a regression.
    """

    def test_migration_217_exists(self):
        path = (
            REPO_ROOT
            / "src"
            / "dk_data"
            / "sql"
            / "migrations"
            / "217_resolve_function_grants.sql"
        )
        assert path.exists(), (
            "Migration 217_resolve_function_grants.sql is missing. It is the "
            "canonical source of EXECUTE grants on silver resolve functions; "
            "migration 228 depends on it being present."
        )

    def test_migration_217_grants_execute_to_api_user(self):
        path = (
            REPO_ROOT
            / "src"
            / "dk_data"
            / "sql"
            / "migrations"
            / "217_resolve_function_grants.sql"
        )
        sql = path.read_text()
        assert "api_user" in sql, (
            "Migration 217 does not mention api_user. It must grant EXECUTE "
            "to api_user for the JWT minting feature (003) to work."
        )
        assert "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA" in sql, (
            "Migration 217 must use schema-wide GRANT EXECUTE ON ALL FUNCTIONS "
            "(not per-function with a signature)."
        )


# ---------------------------------------------------------------------------
# T052 — FR-014: default privileges apply to TABLES only (not functions/sequences)
# ---------------------------------------------------------------------------

class TestNewTableInheritsSelectGrant:
    """FR-014: ALTER DEFAULT PRIVILEGES must target ON TABLES — not ON FUNCTIONS or ON SEQUENCES."""

    def test_default_privileges_apply_to_tables_only(self, migration_sql):
        """Every ALTER DEFAULT PRIVILEGES line must reference ON TABLES, not ON FUNCTIONS
        or ON SEQUENCES. This ensures the auto-grant is scoped to new tables only."""
        for line in migration_sql.splitlines():
            stripped = line.strip()
            if stripped.startswith("ALTER DEFAULT PRIVILEGES"):
                assert "ON TABLES" in stripped, (
                    f"ALTER DEFAULT PRIVILEGES line does not specify ON TABLES: {line!r}"
                )
                assert "ON FUNCTIONS" not in stripped, (
                    f"ALTER DEFAULT PRIVILEGES line specifies ON FUNCTIONS — "
                    f"only ON TABLES is permitted: {line!r}"
                )
                assert "ON SEQUENCES" not in stripped, (
                    f"ALTER DEFAULT PRIVILEGES line specifies ON SEQUENCES — "
                    f"only ON TABLES is permitted: {line!r}"
                )
