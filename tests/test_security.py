"""
Security validation tests for dk-data API.

T015: Validates JWT authentication and role-based access control.
These tests verify:
- Anonymous access is properly restricted
- JWT tokens are validated correctly
- Role-based permissions are enforced
"""

import os
import pytest
import jwt
import time

# Test configuration
POSTGREST_URL = os.getenv("POSTGREST_URL", "http://localhost:3030")
JWT_SECRET = os.getenv("JWT_SECRET", "test-secret-must-be-at-least-32-chars")


def create_jwt_token(role: str, secret: str = JWT_SECRET, expired: bool = False) -> str:
    """Create a JWT token for testing."""
    exp = int(time.time()) - 3600 if expired else int(time.time()) + 3600
    payload = {
        "role": role,
        "exp": exp,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class TestAnonymousAccess:
    """Test that anonymous access is properly restricted."""

    def test_health_endpoint_accessible_anonymously(self, postgrest_client):
        """api.health should be accessible without authentication."""
        response = postgrest_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert data[0]["status"] == "ok"

    def test_data_catalog_accessible_anonymously(self, postgrest_client):
        """api.data_catalog should be accessible without authentication."""
        response = postgrest_client.get("/data_catalog")
        assert response.status_code == 200

    def test_targets_requires_authentication(self, postgrest_client):
        """api.targets should NOT be accessible without authentication."""
        response = postgrest_client.get("/targets")
        # Should return 401 Unauthorized or 403 Forbidden
        assert response.status_code in (401, 403)

    def test_scoring_requires_authentication(self, postgrest_client):
        """api.scoring should NOT be accessible without authentication."""
        response = postgrest_client.get("/scoring")
        assert response.status_code in (401, 403)

    def test_data_sources_requires_authentication(self, postgrest_client):
        """api.data_sources should NOT be accessible without authentication."""
        response = postgrest_client.get("/data_sources")
        assert response.status_code in (401, 403)


class TestJWTValidation:
    """Test JWT token validation."""

    def test_invalid_jwt_rejected(self, postgrest_client):
        """Requests with invalid JWT tokens should be rejected."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        response = postgrest_client.get("/targets", headers=headers)
        assert response.status_code in (401, 403)

    def test_expired_jwt_rejected(self, postgrest_client):
        """Requests with expired JWT tokens should be rejected."""
        token = create_jwt_token("analyst", expired=True)
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/targets", headers=headers)
        assert response.status_code in (401, 403)

    def test_wrong_secret_jwt_rejected(self, postgrest_client):
        """Requests with JWT signed by wrong secret should be rejected."""
        token = create_jwt_token("analyst", secret="wrong-secret-key-for-testing-purposes")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/targets", headers=headers)
        assert response.status_code in (401, 403)


class TestRoleBasedAccess:
    """Test role-based access control."""

    def test_analyst_can_read_targets(self, postgrest_client):
        """Analyst role should have read access to targets."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/targets", headers=headers)
        assert response.status_code == 200

    def test_analyst_can_read_scoring(self, postgrest_client):
        """Analyst role should have read access to scoring."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/scoring", headers=headers)
        assert response.status_code == 200

    def test_analyst_can_read_data_sources(self, postgrest_client):
        """Analyst role should have read access to data_sources."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/data_sources", headers=headers)
        assert response.status_code == 200

    def test_api_user_full_access(self, postgrest_client):
        """api_user role should have full read access to all API views."""
        token = create_jwt_token("api_user")
        headers = {"Authorization": f"Bearer {token}"}

        for endpoint in ["/health", "/data_catalog", "/targets", "/scoring", "/data_sources"]:
            response = postgrest_client.get(endpoint, headers=headers)
            assert response.status_code == 200, f"api_user should access {endpoint}"

    def test_web_anon_limited_access(self, postgrest_client):
        """web_anon role should only access health and data_catalog."""
        token = create_jwt_token("web_anon")
        headers = {"Authorization": f"Bearer {token}"}

        # Should have access
        response = postgrest_client.get("/health", headers=headers)
        assert response.status_code == 200

        response = postgrest_client.get("/data_catalog", headers=headers)
        assert response.status_code == 200

        # Should NOT have access
        response = postgrest_client.get("/targets", headers=headers)
        assert response.status_code in (401, 403)


class TestJWTSecretRequirements:
    """Test JWT secret security requirements."""

    def test_jwt_secret_minimum_length(self):
        """JWT secret must be at least 32 characters (256 bits)."""
        secret = os.getenv("JWT_SECRET", "")
        assert len(secret) >= 32, (
            f"JWT_SECRET must be at least 32 characters for HS256 security. "
            f"Current length: {len(secret)}"
        )


# Pytest fixtures
@pytest.fixture
def postgrest_client():
    """Create an HTTP client for PostgREST."""
    import httpx

    with httpx.Client(base_url=POSTGREST_URL, timeout=10.0) as client:
        yield client
