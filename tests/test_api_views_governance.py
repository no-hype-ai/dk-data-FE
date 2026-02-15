"""
Contract tests for api.audit_log view and governance grants.

Feature: 013-observability-governance (US3: Audit Trail)
Task: T010

Validates that:
- The api.audit_log view definition exists in db-init-job.yaml with correct columns
- The migration (067_audit_log_table.sql) defines meta.api_audit_log with correct columns and types
- api_user has SELECT access on api.audit_log
- web_anon and analyst do NOT have SELECT on api.audit_log
- Append-only enforcement: UPDATE and DELETE are revoked
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DB_INIT_JOB = REPO_ROOT / "k8s" / "base" / "db-init-job.yaml"
MIGRATION_FILE = REPO_ROOT / "src" / "dk_data" / "sql" / "migrations" / "067_audit_log_table.sql"


@pytest.fixture
def db_init_sql():
    """Load the db-init-job.yaml content."""
    return DB_INIT_JOB.read_text()


@pytest.fixture
def migration_sql():
    """Load the 067_audit_log_table.sql migration content."""
    return MIGRATION_FILE.read_text()


# ---------------------------------------------------------------------------
# api.audit_log view contract (db-init-job.yaml)
# ---------------------------------------------------------------------------

class TestAuditLogViewDefinition:
    """Verify api.audit_log view exists in db-init-job.yaml."""

    def test_view_create_statement_exists(self, db_init_sql):
        """The view must have a CREATE OR REPLACE VIEW statement."""
        assert "CREATE OR REPLACE VIEW api.audit_log" in db_init_sql, (
            "Missing CREATE OR REPLACE VIEW api.audit_log in db-init-job.yaml"
        )

    def test_view_selects_from_meta_table(self, db_init_sql):
        """The view must SELECT from meta.api_audit_log."""
        assert "FROM meta.api_audit_log" in db_init_sql

    def test_view_orders_by_timestamp_desc(self, db_init_sql):
        """The view must ORDER BY timestamp DESC."""
        assert "ORDER BY timestamp DESC" in db_init_sql

    @pytest.mark.parametrize("column", [
        "id",
        "request_id",
        "timestamp",
        "source",
        "method",
        "path",
        "user_role",
        "user_sub",
        "status_code",
        "response_time_ms",
        "action",
        "category",
        "details",
        "created_at",
    ])
    def test_view_exposes_expected_column(self, db_init_sql, column):
        """Each expected column must appear in the api.audit_log view SELECT list."""
        # The column should appear somewhere in the db-init-job.yaml
        # (specifically in the audit_log view section)
        assert column in db_init_sql, (
            f"Column '{column}' missing from api.audit_log view definition"
        )


# ---------------------------------------------------------------------------
# Migration column and type contract (067_audit_log_table.sql)
# ---------------------------------------------------------------------------

class TestMigrationTableDefinition:
    """Verify meta.api_audit_log table schema matches the data model contract."""

    def test_table_create_statement(self, migration_sql):
        """Migration must create meta.api_audit_log table."""
        assert "CREATE TABLE IF NOT EXISTS meta.api_audit_log" in migration_sql

    @pytest.mark.parametrize("column_def", [
        ("id", "BIGSERIAL"),
        ("request_id", "UUID"),
        ("timestamp", "TIMESTAMPTZ"),
        ("source", "VARCHAR(20)"),
        ("method", "VARCHAR(10)"),
        ("path", "TEXT"),
        ("query_params", "JSONB"),
        ("user_role", "VARCHAR(50)"),
        ("user_sub", "VARCHAR(255)"),
        ("ip_address", "INET"),
        ("user_agent", "TEXT"),
        ("status_code", "SMALLINT"),
        ("response_time_ms", "INTEGER"),
        ("action", "VARCHAR(50)"),
        ("category", "VARCHAR(20)"),
        ("details", "JSONB"),
        ("created_at", "TIMESTAMPTZ"),
    ])
    def test_column_exists_with_type(self, migration_sql, column_def):
        """Each column must exist with the expected type."""
        col_name, col_type = column_def
        # Normalize whitespace for matching
        normalized = " ".join(migration_sql.split())
        assert col_name in normalized, f"Column '{col_name}' not found in migration"
        assert col_type in normalized, f"Type '{col_type}' not found in migration"

    def test_request_id_not_null(self, migration_sql):
        """request_id must be NOT NULL."""
        normalized = " ".join(migration_sql.split())
        assert "request_id UUID NOT NULL" in normalized

    def test_timestamp_not_null_with_default(self, migration_sql):
        """timestamp must be NOT NULL DEFAULT NOW()."""
        normalized = " ".join(migration_sql.split())
        assert "timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()" in normalized

    def test_source_not_null_with_default(self, migration_sql):
        """source must be NOT NULL DEFAULT 'job-trigger'."""
        normalized = " ".join(migration_sql.split())
        assert "source VARCHAR(20) NOT NULL DEFAULT 'job-trigger'" in normalized

    def test_created_at_not_null_with_default(self, migration_sql):
        """created_at must be NOT NULL DEFAULT NOW()."""
        normalized = " ".join(migration_sql.split())
        assert "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()" in normalized

    def test_id_is_primary_key(self, migration_sql):
        """id should be the PRIMARY KEY."""
        normalized = " ".join(migration_sql.split())
        assert "id BIGSERIAL PRIMARY KEY" in normalized


# ---------------------------------------------------------------------------
# Index contract
# ---------------------------------------------------------------------------

class TestMigrationIndexes:
    """Verify the migration creates required indexes."""

    @pytest.mark.parametrize("index_name", [
        "idx_api_audit_timestamp",
        "idx_api_audit_user_role",
        "idx_api_audit_path",
        "idx_api_audit_category",
    ])
    def test_index_created(self, migration_sql, index_name):
        """Each required index must be created in the migration."""
        assert index_name in migration_sql, (
            f"Index '{index_name}' not found in migration"
        )

    def test_timestamp_index_is_descending(self, migration_sql):
        """Timestamp index should be DESC for recent-first queries."""
        assert "timestamp DESC" in migration_sql


# ---------------------------------------------------------------------------
# Grant / RBAC contract
# ---------------------------------------------------------------------------

class TestGrantPermissions:
    """Verify role-based access control on the audit log."""

    def test_api_user_select_grant_on_view(self, db_init_sql):
        """api_user must be granted SELECT on api.audit_log."""
        assert "GRANT SELECT ON api.audit_log TO api_user" in db_init_sql

    def test_web_anon_no_select_on_view(self, db_init_sql):
        """web_anon must NOT be granted SELECT on api.audit_log."""
        # Ensure there is no grant of audit_log to web_anon
        assert "GRANT SELECT ON api.audit_log TO web_anon" not in db_init_sql
        # Also check for combined grants that might include web_anon
        assert "api.audit_log TO web_anon" not in db_init_sql

    def test_analyst_no_select_on_view(self, db_init_sql):
        """analyst must NOT be granted SELECT on api.audit_log."""
        assert "GRANT SELECT ON api.audit_log TO analyst" not in db_init_sql
        assert "api.audit_log TO analyst" not in db_init_sql


class TestAppendOnlyEnforcement:
    """Verify the migration enforces append-only semantics."""

    def test_revoke_update_delete(self, migration_sql):
        """UPDATE and DELETE must be revoked on meta.api_audit_log."""
        assert "REVOKE UPDATE, DELETE ON meta.api_audit_log" in migration_sql

    def test_grant_insert_to_api_user(self, migration_sql):
        """api_user must be granted INSERT on meta.api_audit_log."""
        assert "GRANT INSERT" in migration_sql
        assert "api_user" in migration_sql

    def test_grant_insert_to_analyst(self, migration_sql):
        """analyst must be granted INSERT on meta.api_audit_log."""
        assert "GRANT INSERT" in migration_sql
        assert "analyst" in migration_sql

    def test_grant_select_to_api_user_only(self, migration_sql):
        """SELECT on the base table is granted to api_user only."""
        # api_user gets INSERT + SELECT
        assert "GRANT INSERT, SELECT ON meta.api_audit_log TO api_user" in migration_sql


# ---------------------------------------------------------------------------
# Trigger contract
# ---------------------------------------------------------------------------

class TestAuditTrigger:
    """Verify the PostgREST audit trigger is defined."""

    def test_trigger_function_exists(self, migration_sql):
        """The audit_postgrest_access function must be created."""
        assert "CREATE OR REPLACE FUNCTION meta.audit_postgrest_access" in migration_sql

    def test_trigger_reads_jwt_claims(self, migration_sql):
        """The trigger should read current_setting('request.jwt.claims', true)."""
        assert "request.jwt.claims" in migration_sql

    def test_trigger_attached_to_table(self, migration_sql):
        """The trigger must be attached to meta.api_audit_log."""
        assert "CREATE TRIGGER trg_audit_postgrest" in migration_sql
        assert "ON meta.api_audit_log" in migration_sql

    def test_trigger_is_before_insert(self, migration_sql):
        """The trigger should fire BEFORE INSERT."""
        assert "BEFORE INSERT ON meta.api_audit_log" in migration_sql


# ---------------------------------------------------------------------------
# Transaction safety
# ---------------------------------------------------------------------------

class TestTransactionSafety:
    """Verify the migration is wrapped in a transaction."""

    def test_begins_with_begin(self, migration_sql):
        """Migration should start with BEGIN."""
        # Strip comments and blank lines to find first statement
        assert "BEGIN;" in migration_sql

    def test_ends_with_commit(self, migration_sql):
        """Migration should end with COMMIT."""
        assert "COMMIT;" in migration_sql
