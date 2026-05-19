"""
Contract tests for migration 217_resolve_function_grants.sql.

Feature: 002-external-integration-foundation (US-5, T074)

The migration grants EXECUTE on the 11 silver-hub resolve functions to
`analyst` and `api_user`. This test file asserts:

- All 11 expected functions are listed in the migration
- Schema-wide GRANT EXECUTE ON ALL FUNCTIONS is used (safer than matching
  individual argument signatures)
- USAGE is granted on every silver schema touched
- ALTER DEFAULT PRIVILEGES is set so future resolve functions inherit the
  grant
- No web_anon grants (migration 218 drops it)
- The migration is transaction-wrapped and has timeouts
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
    / "217_resolve_function_grants.sql"
)

EXPECTED_FUNCTIONS = [
    ("mol_silver", "resolve_molecule"),
    ("mol_silver", "resolve_drug_product"),
    ("mol_silver", "resolve_target"),
    ("mol_silver", "resolve_company"),
    ("ind_silver", "resolve_condition"),
    ("hcs_silver", "resolve_provider"),
    ("hcs_silver", "resolve_facility"),
    ("hcp_silver", "resolve_researcher"),
    ("ip_silver", "resolve_patent"),
    ("ip_silver", "resolve_trademark"),
    ("ip_silver", "resolve_design"),
]

EXPECTED_SCHEMAS = ["mol_silver", "ind_silver", "hcs_silver", "hcp_silver", "ip_silver"]


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

    def test_statement_timeout_set(self, migration_sql):
        assert "SET LOCAL statement_timeout" in migration_sql

    def test_lock_timeout_set(self, migration_sql):
        assert "SET LOCAL lock_timeout" in migration_sql


class TestFunctionListing:
    @pytest.mark.parametrize("schema,func", EXPECTED_FUNCTIONS)
    def test_function_in_list(self, migration_sql, schema, func):
        # The migration lists functions as 'schema.function_name' strings in
        # a fns[] TEXT[] array.
        assert f"{schema}.{func}" in migration_sql

    def test_eleven_functions_listed(self, migration_sql):
        # Count distinct schema.function entries
        found = sum(
            1
            for schema, func in EXPECTED_FUNCTIONS
            if f"{schema}.{func}" in migration_sql
        )
        assert found == 11, f"expected 11 resolve functions, found {found}"


class TestSchemaUsageGrants:
    @pytest.mark.parametrize("schema", EXPECTED_SCHEMAS)
    def test_usage_granted_to_analyst_and_api_user(self, migration_sql, schema):
        # Accept either exact spacing variant (schema name may be padded)
        assert (
            f"GRANT USAGE ON SCHEMA {schema} TO analyst, api_user" in migration_sql
            or f"GRANT USAGE ON SCHEMA {schema}  TO analyst, api_user" in migration_sql
        ), f"missing USAGE grant on {schema}"


class TestExecuteGrants:
    def test_uses_grant_execute_on_all_functions(self, migration_sql):
        # Schema-wide grant is safer than matching individual argument lists.
        assert (
            "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA" in migration_sql
        )

    @pytest.mark.parametrize("schema", EXPECTED_SCHEMAS)
    def test_grant_execute_covers_schema(self, migration_sql, schema):
        # Either via the format() dynamic loop (which splits on '.') or a
        # literal schema-wide grant.
        literal = (
            f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {schema} TO analyst, api_user"
            in migration_sql
        )
        dynamic = (
            f"{schema}.resolve_" in migration_sql
            and "split_part(fn, '.', 1)" in migration_sql
        )
        assert literal or dynamic, f"no EXECUTE grant path for {schema}"

    def test_grants_to_analyst(self, migration_sql):
        assert "analyst" in migration_sql

    def test_grants_to_api_user(self, migration_sql):
        assert "api_user" in migration_sql


class TestDefaultPrivileges:
    """Future resolve functions should inherit the grant without needing a
    follow-up migration."""

    @pytest.mark.parametrize("schema", EXPECTED_SCHEMAS)
    def test_default_privilege_set(self, migration_sql, schema):
        assert (
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT EXECUTE ON FUNCTIONS TO analyst, api_user"
            in migration_sql
            or f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema}  GRANT EXECUTE ON FUNCTIONS TO analyst, api_user"
            in migration_sql
        )


class TestNoWebAnonGrants:
    def test_no_web_anon_in_grant_statements(self, migration_sql):
        # Strip comment lines (starting with --) before checking — the
        # header block explains *why* web_anon is excluded, which is fine.
        code_only = "\n".join(
            line for line in migration_sql.splitlines() if not line.lstrip().startswith("--")
        )
        assert "web_anon" not in code_only, (
            "web_anon appears in executable SQL — migration 218 drops this role"
        )


class TestDefensiveness:
    """Each grant should be wrapped in an exception handler so a single
    missing function doesn't abort the migration."""

    def test_exception_handler_present(self, migration_sql):
        assert "EXCEPTION WHEN OTHERS THEN" in migration_sql

    def test_raises_notice_on_skip(self, migration_sql):
        assert "RAISE NOTICE 'skipping grant" in migration_sql
