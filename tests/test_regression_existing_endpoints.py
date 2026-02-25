"""
Regression tests for existing PostgREST endpoints after PGRST_DB_SCHEMAS expansion.

Feature: 015-assessment-dashboard-integration
Task: T012 — Verify SC-008: existing api.health and api.data_catalog endpoints
       return same structure after adding mol_gold, mol_silver, xenon, meta schemas.

These tests ensure that expanding PGRST_DB_SCHEMAS does not break existing functionality.
"""

import os
import pytest
import time
import jwt as pyjwt

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
    return pyjwt.encode(payload, secret, algorithm="HS256")


class TestHealthEndpointRegression:
    """Verify api.health endpoint unchanged after schema expansion."""

    def test_health_accessible_anonymously(self, postgrest_client):
        """api.health should remain accessible without authentication."""
        response = postgrest_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_expected_structure(self, postgrest_client):
        """api.health should return status=ok structure."""
        response = postgrest_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "status" in data[0]
        assert data[0]["status"] == "ok"

    def test_health_accessible_with_web_anon(self, postgrest_client):
        """web_anon should still access api.health."""
        token = create_jwt_token("web_anon")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/health", headers=headers)
        assert response.status_code == 200


class TestDataCatalogEndpointRegression:
    """Verify api.data_catalog endpoint unchanged after schema expansion."""

    def test_data_catalog_accessible_anonymously(self, postgrest_client):
        """api.data_catalog should remain accessible without authentication."""
        response = postgrest_client.get("/data_catalog")
        assert response.status_code == 200

    def test_data_catalog_returns_list(self, postgrest_client):
        """api.data_catalog should return a list of data source entries."""
        response = postgrest_client.get("/data_catalog")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestAuthenticatedEndpointRegression:
    """Verify authenticated api endpoints unchanged after schema expansion."""

    def test_analyst_can_still_read_targets(self, postgrest_client):
        """Analyst access to api.targets should be unchanged."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/targets", headers=headers)
        assert response.status_code == 200

    def test_analyst_can_still_read_scoring(self, postgrest_client):
        """Analyst access to api.scoring should be unchanged."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/scoring", headers=headers)
        assert response.status_code == 200

    def test_analyst_can_still_read_data_sources(self, postgrest_client):
        """Analyst access to api.data_sources should be unchanged."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}"}
        response = postgrest_client.get("/data_sources", headers=headers)
        assert response.status_code == 200

    def test_api_user_full_access_unchanged(self, postgrest_client):
        """api_user access to all API views should be unchanged."""
        token = create_jwt_token("api_user")
        headers = {"Authorization": f"Bearer {token}"}
        for endpoint in ["/health", "/data_catalog", "/targets", "/scoring", "/data_sources"]:
            response = postgrest_client.get(endpoint, headers=headers)
            assert response.status_code == 200, (
                f"api_user should still access {endpoint}, got {response.status_code}"
            )
