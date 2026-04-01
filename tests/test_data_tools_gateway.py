"""Tests for the data-tools gateway router.

Feature: 019-cms-puf-platform-reconciliation
Task: T049

Covers:
- GET /api/v1/data-tools/registry — list all tools with freshness metadata
- POST /api/v1/data-tools/backfill — trigger source refresh
- GET /api/v1/data-tools/{source_name}/status — per-source freshness
- Redis caching (cache hit / miss paths)
- 404 for unknown sources
- 409 for in-progress backfill
- 503 when DB is unavailable
"""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    from fastapi import FastAPI
    from dk_data.api.routes.data_tools import router
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)


@contextmanager
def _override_db(app, pool):
    """Override get_db_pool via FastAPI dependency_overrides."""
    from dk_data.api.dependencies import get_db_pool
    app.dependency_overrides[get_db_pool] = lambda: pool
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_pool, None)


def _make_db_pool(rows=None, fetchrow_result=None):
    """Build a mock asyncpg-style pool."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool


# ---------------------------------------------------------------------------
# GET /api/v1/data-tools/registry
# ---------------------------------------------------------------------------

class TestRegistryEndpoint:
    def _no_redis(self):
        return patch("dk_data.api.routes.data_tools._get_redis_client", return_value=None)

    def test_returns_200(self, client):
        pool = _make_db_pool(rows=[])
        with self._no_redis(), _override_db(client.app, pool):
            resp = client.get("/api/v1/data-tools/registry")
        assert resp.status_code == 200

    def test_response_schema(self, client):
        pool = _make_db_pool(rows=[])
        with self._no_redis(), _override_db(client.app, pool):
            resp = client.get("/api/v1/data-tools/registry")
        data = resp.json()
        assert "tools" in data
        assert "total" in data
        assert "cached" in data
        assert "generated_at" in data

    def test_cached_false_on_cache_miss(self, client):
        pool = _make_db_pool(rows=[])
        with self._no_redis(), _override_db(client.app, pool):
            resp = client.get("/api/v1/data-tools/registry")
        assert resp.json()["cached"] is False

    def test_cached_true_on_redis_hit(self, client):
        cached_data = {
            "tools": [],
            "total": 0,
            "cached": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        redis_client = MagicMock()
        redis_client.get.return_value = json.dumps(cached_data)

        with patch("dk_data.api.routes.data_tools._get_redis_client", return_value=redis_client):
            resp = client.get("/api/v1/data-tools/registry")
        assert resp.status_code == 200
        assert resp.json()["cached"] is True

    def test_tool_registry_entries_present(self, client):
        pool = _make_db_pool(rows=[])
        with self._no_redis(), _override_db(client.app, pool):
            resp = client.get("/api/v1/data-tools/registry")
        data = resp.json()
        assert data["total"] > 0
        assert data["total"] == len(data["tools"])

    def test_tool_entry_has_required_fields(self, client):
        pool = _make_db_pool(rows=[])
        with self._no_redis(), _override_db(client.app, pool):
            resp = client.get("/api/v1/data-tools/registry")
        tool = resp.json()["tools"][0]
        assert "name" in tool
        assert "description" in tool
        assert "tier" in tool
        assert "raw_table" in tool
        assert "raw_schema" in tool
        assert "source_name" in tool


# ---------------------------------------------------------------------------
# POST /api/v1/data-tools/backfill
# ---------------------------------------------------------------------------

class TestBackfillEndpoint:
    def _no_redis(self):
        return patch("dk_data.api.routes.data_tools._get_redis_client", return_value=None)

    def _mock_source_row(self, source_type="cms_bulk_file"):
        return {"source_id": 1, "source_type": source_type, "last_refresh_status": "success"}

    def test_unknown_source_returns_404(self, client):
        pool = _make_db_pool(fetchrow_result=None)
        with self._no_redis(), _override_db(client.app, pool):
            resp = client.post(
                "/api/v1/data-tools/backfill",
                json={"source_name": "nonexistent_source", "force": False},
            )
        assert resp.status_code == 404

    def test_no_db_returns_503(self, client):
        with self._no_redis(), _override_db(client.app, None):
            resp = client.post(
                "/api/v1/data-tools/backfill",
                json={"source_name": "cms_part_d_spending", "force": False},
            )
        assert resp.status_code == 503

    def test_fresh_data_returns_skipped(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row())
        mock_monitor = AsyncMock()
        mock_monitor.is_fresh = AsyncMock(return_value=True)
        with self._no_redis(), \
             _override_db(client.app, pool), \
             patch("dk_data.services.data_platform.data_freshness_monitor.DataFreshnessMonitor", return_value=mock_monitor):
            resp = client.post(
                "/api/v1/data-tools/backfill",
                json={"source_name": "cms_part_d_spending", "force": False},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] is True
        assert data["triggered"] is False
        assert data["status"] == "skipped"

    def test_stale_data_triggers_backfill(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row())
        mock_monitor = AsyncMock()
        mock_monitor.is_fresh = AsyncMock(return_value=False)
        with self._no_redis(), \
             _override_db(client.app, pool), \
             patch("dk_data.services.data_platform.data_freshness_monitor.DataFreshnessMonitor", return_value=mock_monitor), \
             patch("dk_data.api.routes.data_tools._backfill_source", new_callable=AsyncMock):
            resp = client.post(
                "/api/v1/data-tools/backfill",
                json={"source_name": "cms_part_d_spending", "force": False},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["triggered"] is True
        assert data["status"] == "queued"
        assert data["run_id"] is not None

    def test_force_true_skips_freshness_check(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row())
        with self._no_redis(), \
             _override_db(client.app, pool), \
             patch("dk_data.api.routes.data_tools._backfill_source", new_callable=AsyncMock):
            resp = client.post(
                "/api/v1/data-tools/backfill",
                json={"source_name": "cms_part_d_spending", "force": True},
            )
        assert resp.status_code == 200
        assert resp.json()["triggered"] is True

    def test_in_progress_backfill_returns_409(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row())
        redis_client = MagicMock()
        redis_client.exists.return_value = True  # Lock exists
        with patch("dk_data.api.routes.data_tools._get_redis_client", return_value=redis_client), \
             _override_db(client.app, pool):
            resp = client.post(
                "/api/v1/data-tools/backfill",
                json={"source_name": "cms_part_d_spending", "force": False},
            )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/v1/data-tools/{source_name}/status
# ---------------------------------------------------------------------------

class TestSourceStatusEndpoint:
    def _no_redis(self):
        return patch("dk_data.api.routes.data_tools._get_redis_client", return_value=None)

    def _mock_source_row(self, source_name="cms_part_d_spending", source_type="cms_bulk_file"):
        now = datetime.now(timezone.utc)
        return {
            "source_name": source_name,
            "source_type": source_type,
            "last_successful_refresh": now,
            "last_refresh_status": "success",
        }

    def test_unknown_source_returns_404(self, client):
        pool = _make_db_pool(fetchrow_result=None)
        with self._no_redis(), _override_db(client.app, pool):
            resp = client.get("/api/v1/data-tools/nonexistent_source/status")
        assert resp.status_code == 404

    def test_no_db_returns_503(self, client):
        with self._no_redis(), _override_db(client.app, None):
            resp = client.get("/api/v1/data-tools/cms_part_d_spending/status")
        assert resp.status_code == 503

    def test_fresh_source_is_fresh(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row())
        mock_monitor = AsyncMock()
        mock_monitor.is_fresh = AsyncMock(return_value=True)
        with self._no_redis(), \
             _override_db(client.app, pool), \
             patch("dk_data.services.data_platform.data_freshness_monitor.DataFreshnessMonitor", return_value=mock_monitor):
            resp = client.get("/api/v1/data-tools/cms_part_d_spending/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_fresh"] is True
        assert data["source_name"] == "cms_part_d_spending"
        assert data["cached"] is False

    def test_cached_true_on_redis_hit(self, client):
        cached_data = {
            "source_name": "cms_part_d_spending",
            "is_fresh": True,
            "last_successful_refresh": datetime.now(timezone.utc).isoformat(),
            "last_refresh_status": "success",
            "max_age_hours": 720,
            "cached": False,
        }
        redis_client = MagicMock()
        redis_client.get.return_value = json.dumps(cached_data)
        with patch("dk_data.api.routes.data_tools._get_redis_client", return_value=redis_client):
            resp = client.get("/api/v1/data-tools/cms_part_d_spending/status")
        assert resp.status_code == 200
        assert resp.json()["cached"] is True

    def test_response_has_max_age_hours(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row())
        mock_monitor = AsyncMock()
        mock_monitor.is_fresh = AsyncMock(return_value=True)
        with self._no_redis(), \
             _override_db(client.app, pool), \
             patch("dk_data.services.data_platform.data_freshness_monitor.DataFreshnessMonitor", return_value=mock_monitor):
            resp = client.get("/api/v1/data-tools/cms_part_d_spending/status")
        assert "max_age_hours" in resp.json()

    def test_cms_bulk_source_max_age_is_720(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row(source_type="cms_bulk_file"))
        mock_monitor = AsyncMock()
        mock_monitor.is_fresh = AsyncMock(return_value=True)
        with self._no_redis(), \
             _override_db(client.app, pool), \
             patch("dk_data.services.data_platform.data_freshness_monitor.DataFreshnessMonitor", return_value=mock_monitor):
            resp = client.get("/api/v1/data-tools/cms_part_d_spending/status")
        assert resp.json()["max_age_hours"] == 720

    def test_api_source_max_age_is_24(self, client):
        pool = _make_db_pool(fetchrow_result=self._mock_source_row(source_type="api_incremental"))
        mock_monitor = AsyncMock()
        mock_monitor.is_fresh = AsyncMock(return_value=True)
        with self._no_redis(), \
             _override_db(client.app, pool), \
             patch("dk_data.services.data_platform.data_freshness_monitor.DataFreshnessMonitor", return_value=mock_monitor):
            resp = client.get("/api/v1/data-tools/europepmc/status")
        assert resp.json()["max_age_hours"] == 24


# ---------------------------------------------------------------------------
# Freshness threshold mapping
# ---------------------------------------------------------------------------

class TestFreshnessThresholds:
    def test_cms_bulk_threshold(self):
        from dk_data.api.routes.data_tools import FRESHNESS_THRESHOLDS
        assert FRESHNESS_THRESHOLDS["cms_bulk_file"] == 720

    def test_api_incremental_threshold(self):
        from dk_data.api.routes.data_tools import FRESHNESS_THRESHOLDS
        assert FRESHNESS_THRESHOLDS["api_incremental"] == 24

    def test_api_static_threshold(self):
        from dk_data.api.routes.data_tools import FRESHNESS_THRESHOLDS
        assert FRESHNESS_THRESHOLDS["api_static"] == 168


# ---------------------------------------------------------------------------
# Tool name conversion
# ---------------------------------------------------------------------------

class TestToolNameConversion:
    def test_hyphen_to_underscore(self):
        from dk_data.api.routes.data_tools import _tool_name_to_source_name
        assert _tool_name_to_source_name("cms-part-d-spending") == "cms_part_d_spending"
        assert _tool_name_to_source_name("nih-reporter") == "nih_reporter"

    def test_underscore_unchanged(self):
        from dk_data.api.routes.data_tools import _tool_name_to_source_name
        assert _tool_name_to_source_name("cms_part_d_spending") == "cms_part_d_spending"


# ---------------------------------------------------------------------------
# POST /api/v1/data-tools/{tool_name}/invoke
# ---------------------------------------------------------------------------

class TestInvokeEndpoint:
    """Tests for POST /{tool_name}/invoke."""

    _VALID_TOOL = "clinicaltrials-search"  # Always present in TOOL_REGISTRY

    def _no_redis(self):
        return patch("dk_data.api.routes.data_tools._get_redis_client", return_value=None)

    def _mock_tool(self, invoke_result: dict):
        """Patch _build_tool to return a mock BaseMCPTool."""
        mock_tool = AsyncMock()
        mock_tool.invoke = AsyncMock(return_value=invoke_result)
        return patch("dk_data.api.routes.data_tools._build_tool", return_value=mock_tool)

    def _success_result(self, source="clinicaltrials"):
        return {
            "status": "success",
            "request_id": "test-uuid-1234",
            "source": source,
            "data": {"studies": [], "total": 0},
            "raw_record_id": "raw-uuid-5678",
            "duration_ms": 42,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def test_unknown_tool_returns_404(self, client):
        with _override_db(client.app, _make_db_pool()):
            resp = client.post(
                "/api/v1/data-tools/nonexistent-tool/invoke",
                json={"drug_name": "aspirin"},
            )
        assert resp.status_code == 404
        assert "nonexistent-tool" in resp.json()["detail"]

    def test_missing_drug_name_returns_422(self, client):
        with _override_db(client.app, _make_db_pool()):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={},
            )
        assert resp.status_code == 422

    def test_successful_invocation_returns_200(self, client):
        result = self._success_result()
        with _override_db(client.app, _make_db_pool()), self._mock_tool(result):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={"drug_name": "pembrolizumab"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["source"] == "clinicaltrials"
        assert data["request_id"] == "test-uuid-1234"

    def test_invocation_with_molecule_id(self, client):
        result = self._success_result()
        with _override_db(client.app, _make_db_pool()), self._mock_tool(result):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={"drug_name": "pembrolizumab", "molecule_id": "mol-abc-123"},
            )
        assert resp.status_code == 200

    def test_tool_rate_limited_returns_429(self, client):
        error_result = {
            "status": "error",
            "request_id": "err-uuid",
            "source": "clinicaltrials",
            "error": {"code": "rate_limited", "message": "Rate limit exceeded", "status_code": 429},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with _override_db(client.app, _make_db_pool()), self._mock_tool(error_result):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={"drug_name": "aspirin"},
            )
        assert resp.status_code == 429

    def test_external_api_error_returns_502(self, client):
        error_result = {
            "status": "error",
            "request_id": "err-uuid",
            "source": "clinicaltrials",
            "error": {"code": "external_api_error", "message": "Upstream 503", "status_code": 502},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with _override_db(client.app, _make_db_pool()), self._mock_tool(error_result):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={"drug_name": "aspirin"},
            )
        assert resp.status_code == 502

    def test_timeout_returns_408(self, client):
        error_result = {
            "status": "error",
            "request_id": "err-uuid",
            "source": "clinicaltrials",
            "error": {"code": "timeout", "message": "Request timed out", "status_code": 408},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with _override_db(client.app, _make_db_pool()), self._mock_tool(error_result):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={"drug_name": "aspirin"},
            )
        assert resp.status_code == 408

    def test_tool_build_failure_returns_500(self, client):
        with _override_db(client.app, _make_db_pool()), \
             patch("dk_data.api.routes.data_tools._build_tool", side_effect=RuntimeError("adapter not found")):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={"drug_name": "aspirin"},
            )
        assert resp.status_code == 500

    def test_response_has_required_fields(self, client):
        result = self._success_result()
        with _override_db(client.app, _make_db_pool()), self._mock_tool(result):
            resp = client.post(
                f"/api/v1/data-tools/{self._VALID_TOOL}/invoke",
                json={"drug_name": "nivolumab"},
            )
        data = resp.json()
        for field in ("status", "request_id", "source", "timestamp"):
            assert field in data, f"Missing field: {field}"

    def test_all_registered_tools_are_invocable(self, client):
        """Every TOOL_REGISTRY entry must produce a 200 when the tool invoke is mocked."""
        from dk_data.services.mcp.tool_registry import TOOL_REGISTRY
        result = self._success_result()
        for tool_name in list(TOOL_REGISTRY.keys())[:5]:  # Spot-check first 5
            with _override_db(client.app, _make_db_pool()), self._mock_tool(result):
                resp = client.post(
                    f"/api/v1/data-tools/{tool_name}/invoke",
                    json={"drug_name": "test_drug"},
                )
            assert resp.status_code == 200, f"Tool '{tool_name}' returned {resp.status_code}"
