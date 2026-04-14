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


class TestExecuteGrants:
    @pytest.mark.parametrize("func_path", RESOLVE_FUNCTIONS_10)
    def test_grants_execute_on_all_10_resolve_functions(self, migration_sql, func_path):
        expected = f"GRANT EXECUTE ON FUNCTION {func_path}"
        assert expected in migration_sql, (
            f"Missing EXECUTE grant for resolve function {func_path!r}. "
            f"Expected substring: {expected!r}"
        )

    def test_ten_resolve_functions_present(self, migration_sql):
        found = sum(
            1
            for fn in RESOLVE_FUNCTIONS_10
            if f"GRANT EXECUTE ON FUNCTION {fn}" in migration_sql
        )
        assert found == 10, (
            f"Expected EXECUTE grants for 10 resolve functions, found {found}. "
            f"Check that all entries in RESOLVE_FUNCTIONS_10 appear in the migration."
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
