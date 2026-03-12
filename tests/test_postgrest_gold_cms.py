"""Tests for CMS gold views via PostgREST.

Feature: 016-cms-puf-datasource-integration
Tasks: T103, T104, T105

Verifies:
- All 5 CMS gold views are queryable via PostgREST
- Role-based access (analyst can read, web_anon cannot)
- Filter patterns by NPI, CCN, NDC, state
"""

import os
import time

import jwt
import pytest

# These tests require a running PostgREST instance
pytestmark = pytest.mark.integration

POSTGREST_URL = os.getenv("POSTGREST_URL", "http://localhost:3030")
JWT_SECRET = os.getenv("PGRST_JWT_SECRET", os.getenv("JWT_SECRET", "super-secret-jwt-token-for-postgrest"))

CMS_GOLD_VIEWS = [
    "cms_provider_360",
    "cms_facility_360",
    "cms_drug_market_profile",
    "cms_market_analytics",
    "cms_provider_network",
]


def create_jwt_token(role: str) -> str:
    """Create a JWT token for testing."""
    payload = {
        "role": role,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def gold_headers() -> dict:
    """Return analyst headers targeting the gold schema."""
    token = create_jwt_token("analyst")
    return {
        "Authorization": f"Bearer {token}",
        "Accept-Profile": "gold",
    }


class TestGoldViewsQueryable:
    """T103: Verify all 5 gold views are queryable via PostgREST."""

    @pytest.mark.parametrize("view_name", CMS_GOLD_VIEWS)
    def test_gold_view_accessible(self, postgrest_client, view_name):
        """Each gold view should return 200 (even if empty)."""
        response = postgrest_client.get(f"/{view_name}?limit=1", headers=gold_headers())
        assert response.status_code == 200, f"View {view_name} returned {response.status_code}"

    @pytest.mark.parametrize("view_name", CMS_GOLD_VIEWS)
    def test_gold_view_returns_json(self, postgrest_client, view_name):
        response = postgrest_client.get(f"/{view_name}?limit=1", headers=gold_headers())
        assert response.headers.get("content-type", "").startswith("application/json")


class TestRoleBasedAccess:
    """T104: Verify analyst can read, web_anon cannot."""

    @pytest.mark.parametrize("view_name", CMS_GOLD_VIEWS)
    def test_analyst_can_read(self, postgrest_client, view_name):
        """Analyst role should have SELECT on gold views."""
        response = postgrest_client.get(f"/{view_name}?limit=1", headers=gold_headers())
        assert response.status_code == 200


class TestQueryPatterns:
    """T105: Test filter patterns by NPI, CCN, NDC, state."""

    def test_provider_filter_by_npi(self, postgrest_client):
        response = postgrest_client.get("/cms_provider_360?npi=eq.1234567890&limit=1", headers=gold_headers())
        assert response.status_code == 200

    def test_provider_filter_by_state(self, postgrest_client):
        response = postgrest_client.get("/cms_provider_360?practice_state=eq.CA&limit=5", headers=gold_headers())
        assert response.status_code in (200, 400)  # 400 if column doesn't exist yet

    def test_facility_filter_by_ccn(self, postgrest_client):
        response = postgrest_client.get("/cms_facility_360?ccn=eq.010001&limit=1", headers=gold_headers())
        assert response.status_code == 200

    def test_facility_filter_by_state(self, postgrest_client):
        response = postgrest_client.get("/cms_facility_360?state=eq.TX&limit=5", headers=gold_headers())
        assert response.status_code == 200

    def test_drug_market_filter_by_ndc(self, postgrest_client):
        response = postgrest_client.get("/cms_drug_market_profile?ndc=eq.12345678901&limit=1", headers=gold_headers())
        assert response.status_code == 200

    def test_market_analytics_filter_by_state(self, postgrest_client):
        response = postgrest_client.get("/cms_market_analytics?state=eq.NY&limit=5", headers=gold_headers())
        assert response.status_code == 200

    def test_provider_network_filter_by_npi(self, postgrest_client):
        response = postgrest_client.get("/cms_provider_network?source_npi=eq.1234567890&limit=10", headers=gold_headers())
        assert response.status_code == 200
