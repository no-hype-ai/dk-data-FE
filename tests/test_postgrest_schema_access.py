"""
PostgREST schema access tests for Assessment Dashboard Integration.

Feature: 015-assessment-dashboard-integration
Task: T011 — Verify analyst can access mol_gold, mol_silver, xenon, meta schemas
       and web_anon CANNOT access restricted schemas via PostgREST.

Tests verify SC-001 (PostgREST exposes new schemas) and SC-007 (role-based access).
"""

import os
import time
import jwt as pyjwt
import pytest

import psycopg2

def _hub_tables_exist():
    """Check if hub tables exist (created by 031_silver_hub_rebuild migrations, not top-level)."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            user=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
            dbname=os.environ.get("POSTGRES_DB", "dk_data"),
        )
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='mol_silver' AND table_name='molecules'")
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception:
        return False

pytestmark = [
    pytest.mark.skipif(
        not _hub_tables_exist(),
        reason="Hub tables not available (031_silver_hub_rebuild migrations not applied in CI)"
    ),
    pytest.mark.integration,
]

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


class TestAnalystSchemaAccess:
    """Test that analyst role can access mol_gold, mol_silver, xenon, and meta schemas."""

    def test_analyst_can_select_mol_gold_molecule_profile(self, postgrest_client):
        """Analyst should have SELECT access to mol_gold tables."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "mol_gold"}
        response = postgrest_client.get("/molecule_profile", headers=headers)
        # 200 = data returned, 204 = no content (empty table) — both mean access granted
        assert response.status_code in (200, 204), (
            f"Analyst should access mol_gold.molecule_profile, got {response.status_code}"
        )

    def test_analyst_can_select_mol_silver(self, postgrest_client):
        """Analyst should have SELECT access to mol_silver tables."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "mol_silver"}
        response = postgrest_client.get("/clinical_trials", headers=headers)
        assert response.status_code in (200, 204), (
            f"Analyst should access mol_silver.clinical_trials, got {response.status_code}"
        )

    def test_analyst_can_select_meta(self, postgrest_client):
        """Analyst should have SELECT access to meta schema tables."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "meta"}
        response = postgrest_client.get("/migration_history", headers=headers)
        assert response.status_code in (200, 204, 404), (
            f"Analyst should access meta schema, got {response.status_code}"
        )

    def test_analyst_can_read_xenon_assessment_generated(self, postgrest_client):
        """Analyst should have SELECT access to xenon.assessment_generated."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "xenon"}
        response = postgrest_client.get("/assessment_generated", headers=headers)
        assert response.status_code in (200, 204), (
            f"Analyst should access xenon.assessment_generated, got {response.status_code}"
        )

    def test_analyst_can_read_xenon_publication_evidence(self, postgrest_client):
        """Analyst should have SELECT access to xenon.publication_evidence."""
        token = create_jwt_token("analyst")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "xenon"}
        response = postgrest_client.get("/publication_evidence", headers=headers)
        assert response.status_code in (200, 204), (
            f"Analyst should access xenon.publication_evidence, got {response.status_code}"
        )


class TestWebAnonSchemaRestriction:
    """Test that web_anon role CANNOT access restricted schemas."""

    def test_web_anon_cannot_access_mol_gold(self, postgrest_client):
        """web_anon should NOT access mol_gold tables."""
        token = create_jwt_token("web_anon")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "mol_gold"}
        response = postgrest_client.get("/molecule_profile", headers=headers)
        assert response.status_code in (401, 403, 404), (
            f"web_anon should not access mol_gold, got {response.status_code}"
        )

    def test_web_anon_cannot_access_mol_silver(self, postgrest_client):
        """web_anon should NOT access mol_silver tables."""
        token = create_jwt_token("web_anon")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "mol_silver"}
        response = postgrest_client.get("/clinical_trials", headers=headers)
        assert response.status_code in (401, 403, 404), (
            f"web_anon should not access mol_silver, got {response.status_code}"
        )

    def test_web_anon_cannot_access_xenon(self, postgrest_client):
        """web_anon should NOT access xenon schema tables."""
        token = create_jwt_token("web_anon")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "xenon"}
        response = postgrest_client.get("/assessment_generated", headers=headers)
        assert response.status_code in (401, 403, 404), (
            f"web_anon should not access xenon, got {response.status_code}"
        )

    def test_web_anon_cannot_access_meta(self, postgrest_client):
        """web_anon should NOT access meta schema tables."""
        token = create_jwt_token("web_anon")
        headers = {"Authorization": f"Bearer {token}", "Accept-Profile": "meta"}
        response = postgrest_client.get("/migration_history", headers=headers)
        assert response.status_code in (401, 403, 404), (
            f"web_anon should not access meta, got {response.status_code}"
        )


class TestUnauthenticatedAccess:
    """Test that unauthenticated requests cannot access restricted schemas."""

    def test_no_auth_cannot_access_mol_gold(self, postgrest_client):
        """Unauthenticated requests should not access mol_gold."""
        response = postgrest_client.get("/molecule_profile", headers={"Accept-Profile": "mol_gold"})
        assert response.status_code in (401, 403, 404)

    def test_no_auth_cannot_access_xenon(self, postgrest_client):
        """Unauthenticated requests should not access xenon."""
        response = postgrest_client.get("/assessment_generated", headers={"Accept-Profile": "xenon"})
        assert response.status_code in (401, 403, 404)
