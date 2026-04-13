"""Contract tests for migration 226_pg_stat_statements.sql."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = (
    REPO_ROOT / "src" / "dk_data" / "sql" / "migrations" / "226_pg_stat_statements.sql"
)


@pytest.fixture
def sql() -> str:
    return MIGRATION.read_text()


class TestMigrationShape:
    def test_file_exists(self) -> None:
        assert MIGRATION.exists()

    def test_creates_extension(self, sql: str) -> None:
        assert "CREATE EXTENSION IF NOT EXISTS pg_stat_statements" in sql

    def test_transaction_wrapped(self, sql: str) -> None:
        # Extension creation IS transactional, so this migration
        # should be wrapped (unlike 225 which uses CONCURRENTLY)
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql

    def test_grants_to_analyst_and_api_user(self, sql: str) -> None:
        assert "GRANT SELECT ON public.pg_stat_statements TO analyst, api_user" in sql

    def test_no_web_anon_grant(self, sql: str) -> None:
        # The query text in pg_stat_statements can leak schema info
        # to anonymous readers — keep it gated.
        code_only = "\n".join(
            line for line in sql.splitlines() if not line.lstrip().startswith("--")
        )
        assert "web_anon" not in code_only

    def test_creates_top_slow_queries_helper(self, sql: str) -> None:
        assert "CREATE OR REPLACE VIEW meta.top_slow_queries" in sql

    def test_helper_view_grants_select(self, sql: str) -> None:
        assert "GRANT SELECT ON meta.top_slow_queries TO analyst, api_user" in sql

    def test_documents_shared_preload_requirement(self, sql: str) -> None:
        # The migration's header comment must mention the
        # shared_preload_libraries requirement so anyone running
        # it knows the infra-side change is also needed.
        assert "shared_preload_libraries" in sql
        assert "pg_stat_statements" in sql

    def test_statement_timeout_set(self, sql: str) -> None:
        assert "SET LOCAL statement_timeout" in sql

    def test_idempotent_extension_creation(self, sql: str) -> None:
        assert "CREATE EXTENSION IF NOT EXISTS" in sql

    def test_uses_information_schema_guard_for_view_grant(self, sql: str) -> None:
        # The GRANT SELECT on the view is wrapped in a check so it
        # doesn't fail if the view doesn't exist (when shared_preload
        # is not yet set in the cluster config).
        assert "information_schema.views" in sql
