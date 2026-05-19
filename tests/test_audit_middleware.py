"""
Tests for AuditLoggingMiddleware.

Feature: 013-observability-governance (US3: Audit Trail)
Task: T009

Validates that AuditLoggingMiddleware:
- Captures request_id, method, path, user_role (from JWT), status_code, response_time_ms
- Writes audit entries asynchronously to the database
- Excludes /health and /metrics endpoints from auditing
"""

import base64
import importlib.util
import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import AuditLoggingMiddleware directly from the middleware.py file
# to avoid triggering the full middleware package import chain (which
# pulls in RBAC dependencies that may not be available in test environments).
_middleware_path = os.path.join(
    os.path.dirname(__file__), "..", "src", "dk_data", "api", "middleware.py"
)
_middleware_path = os.path.abspath(_middleware_path)

# Register the module under a known name so @patch can resolve it
_spec = importlib.util.spec_from_file_location("_dk_base_middleware", _middleware_path)
_base_middleware = importlib.util.module_from_spec(_spec)
sys.modules["_dk_base_middleware"] = _base_middleware
_spec.loader.exec_module(_base_middleware)

AuditLoggingMiddleware = _base_middleware.AuditLoggingMiddleware

# Module path used in @patch decorators
_MOD = "_dk_base_middleware"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jwt(role: str = "analyst", sub: str = "user-123") -> str:
    """Build a minimal unsigned JWT (header.payload.signature) for testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"role": role, "sub": sub, "exp": int(time.time()) + 3600}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesignature"


def _build_app(database_url: str = "postgresql://test:test@localhost/test") -> FastAPI:
    """Create a minimal FastAPI app with AuditLoggingMiddleware attached."""
    app = FastAPI()
    app.add_middleware(AuditLoggingMiddleware, database_url=database_url)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics():
        return {"metrics": "ok"}

    @app.get("/jobs")
    async def list_jobs():
        return [{"job": "test"}]

    @app.post("/jobs/test/trigger")
    async def trigger():
        return {"status": "triggered"}

    return app


# ---------------------------------------------------------------------------
# Test: Core audit field capture
# ---------------------------------------------------------------------------

class TestAuditFieldCapture:
    """Verify that the middleware captures all expected fields from requests."""

    @patch(f"{_MOD}._audit_executor")
    def test_captures_method_and_path(self, mock_executor):
        """Audit entry must include request method and path."""
        client = TestClient(_build_app())
        client.get("/jobs")

        mock_executor.submit.assert_called_once()
        _fn, entry = mock_executor.submit.call_args[0]
        assert entry["method"] == "GET"
        assert entry["path"] == "/jobs"

    @patch(f"{_MOD}._audit_executor")
    def test_captures_status_code(self, mock_executor):
        """Audit entry must include the HTTP response status code."""
        client = TestClient(_build_app())
        client.get("/jobs")

        _, entry = mock_executor.submit.call_args[0]
        assert entry["status_code"] == 200

    @patch(f"{_MOD}._audit_executor")
    def test_captures_response_time_ms(self, mock_executor):
        """Audit entry must include response_time_ms as a non-negative integer."""
        client = TestClient(_build_app())
        client.get("/jobs")

        _, entry = mock_executor.submit.call_args[0]
        assert isinstance(entry["response_time_ms"], int)
        assert entry["response_time_ms"] >= 0

    @patch(f"{_MOD}._audit_executor")
    def test_captures_request_id_from_header(self, mock_executor):
        """Audit entry should use X-Request-ID header when provided."""
        client = TestClient(_build_app())
        client.get("/jobs", headers={"X-Request-ID": "abc-123-def"})

        _, entry = mock_executor.submit.call_args[0]
        assert entry["request_id"] == "abc-123-def"

    @patch(f"{_MOD}._audit_executor")
    def test_generates_request_id_when_missing(self, mock_executor):
        """Audit entry should generate a UUID request_id when header is absent."""
        client = TestClient(_build_app())
        client.get("/jobs")

        _, entry = mock_executor.submit.call_args[0]
        assert entry["request_id"] is not None
        assert len(entry["request_id"]) > 0

    @patch(f"{_MOD}._audit_executor")
    def test_captures_user_role_from_jwt(self, mock_executor):
        """Audit entry should extract user_role from the JWT Bearer token."""
        token = _make_jwt(role="analyst")
        client = TestClient(_build_app())
        client.get("/jobs", headers={"Authorization": f"Bearer {token}"})

        _, entry = mock_executor.submit.call_args[0]
        assert entry["user_role"] == "analyst"

    @patch(f"{_MOD}._audit_executor")
    def test_captures_user_sub_from_jwt(self, mock_executor):
        """Audit entry should extract user_sub from the JWT Bearer token."""
        token = _make_jwt(sub="user-456")
        client = TestClient(_build_app())
        client.get("/jobs", headers={"Authorization": f"Bearer {token}"})

        _, entry = mock_executor.submit.call_args[0]
        assert entry["user_sub"] == "user-456"

    @patch(f"{_MOD}._audit_executor")
    def test_user_role_none_without_auth(self, mock_executor):
        """Audit entry should have None user_role when no auth header is present."""
        client = TestClient(_build_app())
        client.get("/jobs")

        _, entry = mock_executor.submit.call_args[0]
        assert entry["user_role"] is None
        assert entry["user_sub"] is None

    @patch(f"{_MOD}._audit_executor")
    def test_captures_source_field(self, mock_executor):
        """Audit entry should include the source='job-trigger' default."""
        client = TestClient(_build_app())
        client.get("/jobs")

        _, entry = mock_executor.submit.call_args[0]
        assert entry["source"] == "job-trigger"

    @patch(f"{_MOD}._audit_executor")
    def test_captures_post_method(self, mock_executor):
        """Audit entry should capture POST method correctly."""
        client = TestClient(_build_app())
        client.post("/jobs/test/trigger")

        _, entry = mock_executor.submit.call_args[0]
        assert entry["method"] == "POST"
        assert entry["path"] == "/jobs/test/trigger"


# ---------------------------------------------------------------------------
# Test: Path exclusions
# ---------------------------------------------------------------------------

class TestPathExclusions:
    """Verify that /health and /metrics are excluded from audit logging."""

    @patch(f"{_MOD}._audit_executor")
    def test_health_excluded(self, mock_executor):
        """/health endpoint should NOT generate an audit entry."""
        client = TestClient(_build_app())
        client.get("/health")

        mock_executor.submit.assert_not_called()

    @patch(f"{_MOD}._audit_executor")
    def test_metrics_excluded(self, mock_executor):
        """/metrics endpoint should NOT generate an audit entry."""
        client = TestClient(_build_app())
        client.get("/metrics")

        mock_executor.submit.assert_not_called()

    @patch(f"{_MOD}._audit_executor")
    def test_normal_path_included(self, mock_executor):
        """Non-excluded paths should generate audit entries."""
        client = TestClient(_build_app())
        client.get("/jobs")

        mock_executor.submit.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Async database write
# ---------------------------------------------------------------------------

class TestAsyncDatabaseWrite:
    """Verify audit entries are written to the database asynchronously."""

    @patch(f"{_MOD}.build_dsn", return_value="postgresql://test:test@localhost/test")
    @patch(f"{_MOD}.psycopg2")
    def test_write_audit_entry_inserts_row(self, mock_psycopg2, mock_build_dsn):
        """_write_audit_entry should INSERT into meta.api_audit_log."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        middleware = AuditLoggingMiddleware(
            app=MagicMock(),
            database_url="postgresql://test:test@localhost/test",
        )

        entry = {
            "request_id": "test-uuid",
            "method": "GET",
            "path": "/jobs",
            "query_params": None,
            "user_role": "analyst",
            "user_sub": "user-1",
            "ip_address": None,
            "user_agent": "test-agent",
            "status_code": 200,
            "response_time_ms": 42,
            "source": "job-trigger",
        }

        middleware._write_audit_entry(entry)

        mock_psycopg2.connect.assert_called_once()
        mock_cursor.execute.assert_called_once()
        # Verify the SQL contains the INSERT statement
        sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO meta.api_audit_log" in sql
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch(f"{_MOD}.psycopg2")
    def test_write_audit_entry_handles_db_error(self, mock_psycopg2):
        """_write_audit_entry should log warning on database errors, not raise."""
        mock_psycopg2.connect.side_effect = Exception("Connection refused")

        middleware = AuditLoggingMiddleware(
            app=MagicMock(),
            database_url="postgresql://test:test@localhost/test",
        )

        entry = {
            "request_id": "test-uuid",
            "method": "GET",
            "path": "/jobs",
            "query_params": None,
            "user_role": None,
            "user_sub": None,
            "ip_address": None,
            "user_agent": None,
            "status_code": 200,
            "response_time_ms": 10,
            "source": "job-trigger",
        }

        # Should not raise -- audit failures are non-blocking
        middleware._write_audit_entry(entry)

    @patch(f"{_MOD}._audit_executor")
    def test_no_write_when_no_database_url(self, mock_executor):
        """When DATABASE_URL is empty, no audit write should be submitted."""
        app = FastAPI()
        app.add_middleware(AuditLoggingMiddleware, database_url="")

        @app.get("/jobs")
        async def jobs():
            return []

        client = TestClient(app)
        client.get("/jobs")

        mock_executor.submit.assert_not_called()

    @patch(f"{_MOD}._audit_executor")
    def test_executor_submit_called_with_write_method(self, mock_executor):
        """The middleware should submit _write_audit_entry to the thread pool."""
        client = TestClient(_build_app())
        client.get("/jobs")

        mock_executor.submit.assert_called_once()
        fn = mock_executor.submit.call_args[0][0]
        # The submitted function should be the _write_audit_entry method
        assert "write_audit_entry" in fn.__name__


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case handling in audit middleware."""

    @patch(f"{_MOD}._audit_executor")
    def test_malformed_jwt_does_not_crash(self, mock_executor):
        """A malformed JWT should not cause the middleware to fail."""
        client = TestClient(_build_app())
        client.get("/jobs", headers={"Authorization": "Bearer not.a.valid.jwt"})

        # Should still audit the request (with None role)
        mock_executor.submit.assert_called_once()
        _, entry = mock_executor.submit.call_args[0]
        # Role extraction may or may not succeed for malformed tokens
        # The key thing is the request was not blocked

    @patch(f"{_MOD}._audit_executor")
    def test_non_bearer_auth_ignored(self, mock_executor):
        """Non-Bearer authorization headers should not be parsed for JWT."""
        client = TestClient(_build_app())
        client.get("/jobs", headers={"Authorization": "Basic dXNlcjpwYXNz"})

        _, entry = mock_executor.submit.call_args[0]
        assert entry["user_role"] is None

    @patch(f"{_MOD}._audit_executor")
    def test_query_params_captured(self, mock_executor):
        """Query parameters should be captured in the audit entry."""
        client = TestClient(_build_app())
        client.get("/jobs?enabled_only=true&limit=10")

        _, entry = mock_executor.submit.call_args[0]
        params = json.loads(entry["query_params"])
        assert params["enabled_only"] == "true"
        assert params["limit"] == "10"

    @patch(f"{_MOD}._audit_executor")
    def test_ip_address_from_forwarded_for(self, mock_executor):
        """IP address should be extracted from X-Forwarded-For header."""
        client = TestClient(_build_app())
        client.get("/jobs", headers={"X-Forwarded-For": "10.0.0.1, 172.16.0.1"})

        _, entry = mock_executor.submit.call_args[0]
        assert entry["ip_address"] == "10.0.0.1"
