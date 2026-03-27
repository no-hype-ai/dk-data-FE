"""Tests for the agents API router.

Feature: 019-cms-puf-platform-reconciliation
Task: T043

Covers:
- GET /api/v1/agents — list all 7 agents
- POST /api/v1/agents/{agent_id}/run — 202 Accepted, async
- POST /api/v1/agents/{unknown}/run — 404
- GET /api/v1/agents/{agent_id}/runs — run history (mocked DB)
- GET /api/v1/agents/quarantine — paginated quarantine records
- AGENT_REGISTRY contains all 7 expected agents
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    """FastAPI test app with agents router only."""
    from fastapi import FastAPI
    from dk_data.api.routes.agents import router
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)


@contextmanager
def _override_db(app, pool):
    """Context manager to override get_db_pool via FastAPI dependency_overrides."""
    from dk_data.api.dependencies import get_db_pool
    app.dependency_overrides[get_db_pool] = lambda: pool
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_pool, None)


# ---------------------------------------------------------------------------
# AGENT_REGISTRY tests
# ---------------------------------------------------------------------------

class TestAgentRegistry:
    EXPECTED_AGENTS = [
        "service_line_inference",
        "idn_hierarchy",
        "referral_network",
        "contact_verification",
        "staffing_decomposition",
        "equipment_inventory",
        "publication_evidence_extractor",
    ]

    def test_all_7_agents_registered(self):
        from dk_data.api.routes.agents import AGENT_REGISTRY
        missing = [a for a in self.EXPECTED_AGENTS if a not in AGENT_REGISTRY]
        assert missing == [], f"Missing agents: {missing}"

    def test_agent_registry_has_required_fields(self):
        from dk_data.api.routes.agents import AGENT_REGISTRY
        required = {"agent_id", "display_name", "description", "module", "silver_table", "default_limit"}
        for agent_id, meta in AGENT_REGISTRY.items():
            missing = required - set(meta.keys())
            assert missing == set(), f"Agent '{agent_id}' missing fields: {missing}"

    def test_agent_ids_match_keys(self):
        from dk_data.api.routes.agents import AGENT_REGISTRY
        for key, meta in AGENT_REGISTRY.items():
            assert meta["agent_id"] == key, (
                f"AGENT_REGISTRY key '{key}' != agent_id '{meta['agent_id']}'"
            )


# ---------------------------------------------------------------------------
# GET /api/v1/agents
# ---------------------------------------------------------------------------

class TestListAgents:
    def test_returns_7_agents(self, client):
        resp = client.get("/api/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 7
        assert len(data["agents"]) == 7

    def test_response_schema(self, client):
        resp = client.get("/api/v1/agents")
        agent = resp.json()["agents"][0]
        assert "agent_id" in agent
        assert "display_name" in agent
        assert "description" in agent
        assert "silver_table" in agent
        assert "default_limit" in agent

    def test_publication_evidence_extractor_present(self, client):
        resp = client.get("/api/v1/agents")
        ids = [a["agent_id"] for a in resp.json()["agents"]]
        assert "publication_evidence_extractor" in ids


# ---------------------------------------------------------------------------
# POST /api/v1/agents/{agent_id}/run
# ---------------------------------------------------------------------------

class TestTriggerAgentRun:
    def test_valid_agent_returns_202(self, client):
        resp = client.post(
            "/api/v1/agents/service_line_inference/run",
            json={"limit": 10},
        )
        assert resp.status_code == 202

    def test_response_has_run_id(self, client):
        resp = client.post(
            "/api/v1/agents/idn_hierarchy/run",
            json={"limit": 50},
        )
        data = resp.json()
        assert "run_id" in data
        assert len(data["run_id"]) == 36  # UUID

    def test_response_status_is_queued(self, client):
        resp = client.post(
            "/api/v1/agents/referral_network/run",
            json={"limit": 50},
        )
        assert resp.json()["status"] == "queued"

    def test_unknown_agent_returns_404(self, client):
        resp = client.post(
            "/api/v1/agents/nonexistent_agent/run",
            json={"limit": 50},
        )
        assert resp.status_code == 404

    def test_limit_reflected_in_response(self, client):
        resp = client.post(
            "/api/v1/agents/contact_verification/run",
            json={"limit": 25},
        )
        assert resp.json()["limit"] == 25

    def test_agent_id_reflected_in_response(self, client):
        resp = client.post(
            "/api/v1/agents/staffing_decomposition/run",
            json={"limit": 50},
        )
        assert resp.json()["agent_id"] == "staffing_decomposition"

    def test_queued_at_present(self, client):
        resp = client.post(
            "/api/v1/agents/equipment_inventory/run",
            json={"limit": 50},
        )
        assert "queued_at" in resp.json()


# ---------------------------------------------------------------------------
# GET /api/v1/agents/{agent_id}/runs
# ---------------------------------------------------------------------------

class TestAgentRunHistory:
    def _mock_db_pool(self, rows):
        pool = MagicMock()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))
        return pool

    def test_unknown_agent_returns_404(self, client):
        resp = client.get("/api/v1/agents/no_such_agent/runs")
        assert resp.status_code == 404

    def test_no_db_returns_503(self, client):
        with _override_db(client.app, None):
            resp = client.get("/api/v1/agents/service_line_inference/runs")
        assert resp.status_code == 503

    def test_returns_empty_list_when_no_runs(self, client):
        mock_pool = self._mock_db_pool([])
        with _override_db(client.app, mock_pool):
            resp = client.get("/api/v1/agents/service_line_inference/runs")
        assert resp.status_code == 200
        assert resp.json()["runs"] == []
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/agents/quarantine
# ---------------------------------------------------------------------------

class TestGetQuarantine:
    def _mock_db_pool_quarantine(self, rows, total=0):
        pool = MagicMock()
        conn = AsyncMock()
        count_row = {"total": total}
        conn.fetch = AsyncMock(return_value=rows)
        conn.fetchrow = AsyncMock(return_value=count_row)
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))
        return pool

    def test_no_db_returns_503(self, client):
        with _override_db(client.app, None):
            resp = client.get("/api/v1/agents/quarantine")
        assert resp.status_code == 503

    def test_returns_paginated_response(self, client):
        mock_pool = self._mock_db_pool_quarantine([], total=0)
        with _override_db(client.app, mock_pool):
            resp = client.get("/api/v1/agents/quarantine")
        assert resp.status_code == 200
        data = resp.json()
        assert "records" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_default_page_is_1(self, client):
        mock_pool = self._mock_db_pool_quarantine([], total=0)
        with _override_db(client.app, mock_pool):
            resp = client.get("/api/v1/agents/quarantine")
        assert resp.json()["page"] == 1


# ---------------------------------------------------------------------------
# Helper: _get_agent_class_name
# ---------------------------------------------------------------------------

class TestGetAgentClassName:
    def test_snake_to_pascal(self):
        from dk_data.api.routes.agents import _get_agent_class_name
        assert _get_agent_class_name("service_line_inference") == "ServiceLineInferenceAgent"
        assert _get_agent_class_name("idn_hierarchy") == "IdnHierarchyAgent"
        assert _get_agent_class_name("publication_evidence_extractor") == "PublicationEvidenceExtractorAgent"
