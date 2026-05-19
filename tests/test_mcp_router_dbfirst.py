"""TDD tests for DB-first router dispatch (Task 1.1, PR #415 Phase 1).

Uses TestClient (sync) to avoid pytest-asyncio / respx dependencies.
Patches only the Adapter.db_query and HTTP *Tool.invoke methods — so we
test the router's dispatch logic in isolation, not the SQL or HTTP code.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dk_data.services.mcp.router import TOOL_REGISTRY, router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPENFDA_ADAPTER_MODULE = "dk_data.services.mcp.adapters.openfda_labels"
_OPENFDA_SLUG = "openfda-labels-search"


def _make_app(db_pool=None):
    """Build a minimal test FastAPI app with the MCP router mounted."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    # Directly inject pool onto app.state (bypasses lifespan for unit tests)
    app.state.db_pool = db_pool
    return app


class _FakePool:
    """Sentinel pool so the router knows a pool is available."""


# ---------------------------------------------------------------------------
# Test 1: DB hit returns DB data — HTTP path must NOT be called
# ---------------------------------------------------------------------------


def test_db_hit_returns_db_data_without_http(monkeypatch):
    """DB-first: when db_query returns a dict, the response comes from DB and
    the HTTP adapter.invoke() is never called."""

    db_result = {"source": "openfda_local", "results": [{"x": 1}]}

    adapter_mod = importlib.import_module(_OPENFDA_ADAPTER_MODULE)

    async def fake_db_query(self, drug_name, db_pool):  # noqa: ARG001
        return db_result

    monkeypatch.setattr(adapter_mod.Adapter, "db_query", fake_db_query)
    monkeypatch.setattr(
        importlib.import_module("dk_data.services.mcp.adapters").__dict__[
            "OpenFDALabelsTool"
        ],
        "invoke",
        AsyncMock(side_effect=AssertionError("HTTP path must not be called")),
    )

    app = _make_app(db_pool=_FakePool())
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/data-tools/{_OPENFDA_SLUG}/invoke",
        json={"drug_name": "aspirin"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"] == db_result, f"Expected DB data in response, got: {body}"
    assert body["error"] is None


# ---------------------------------------------------------------------------
# Test 2: db_query raises → 5xx with structured error, no HTTP fallback
# ---------------------------------------------------------------------------


def test_db_query_raise_returns_5xx_not_silent_fallback(monkeypatch):
    """DB error must surface as 5xx — the router must NOT silently fall through
    to HTTP as if it were a cache miss."""

    adapter_mod = importlib.import_module(_OPENFDA_ADAPTER_MODULE)

    async def exploding_db_query(self, drug_name, db_pool):  # noqa: ARG001
        raise RuntimeError("db down")

    monkeypatch.setattr(adapter_mod.Adapter, "db_query", exploding_db_query)
    monkeypatch.setattr(
        importlib.import_module("dk_data.services.mcp.adapters").__dict__[
            "OpenFDALabelsTool"
        ],
        "invoke",
        AsyncMock(side_effect=AssertionError("HTTP fallback must not be called on db error")),
    )

    app = _make_app(db_pool=_FakePool())
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/data-tools/{_OPENFDA_SLUG}/invoke",
        json={"drug_name": "aspirin"},
    )

    assert resp.status_code in (500, 502), (
        f"Expected 5xx for db error, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", {})
    # detail may be a dict or string; either way the error info must be present
    detail_str = str(detail)
    assert "db down" in detail_str or "db_query" in detail_str, (
        f"Expected db error info in detail, got: {detail_str}"
    )
    assert "stage" in detail_str or "db_query" in detail_str, (
        f"Expected 'stage' key in detail, got: {detail_str}"
    )


# ---------------------------------------------------------------------------
# Test 3: db_query returns None → fall through to HTTP
# ---------------------------------------------------------------------------


def test_db_miss_falls_through_to_http(monkeypatch):
    """When db_query returns None (miss), the router must fall through to the
    HTTP adapter.invoke() path and return its result."""

    adapter_mod = importlib.import_module(_OPENFDA_ADAPTER_MODULE)

    async def miss_db_query(self, drug_name, db_pool):  # noqa: ARG001
        return None  # cache miss

    http_result = {"tool": _OPENFDA_SLUG, "data": {"via": "http"}, "status_code": 200, "error": None}

    monkeypatch.setattr(adapter_mod.Adapter, "db_query", miss_db_query)

    # Patch the OpenFDALabelsTool.invoke on the class in the adapters package
    openfda_tool_cls = importlib.import_module("dk_data.services.mcp.adapters").__dict__[
        "OpenFDALabelsTool"
    ]
    monkeypatch.setattr(openfda_tool_cls, "invoke", AsyncMock(return_value=http_result))

    app = _make_app(db_pool=_FakePool())
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/data-tools/{_OPENFDA_SLUG}/invoke",
        json={"drug_name": "aspirin"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"] == {"via": "http"}, f"Expected HTTP data, got: {body}"


# ---------------------------------------------------------------------------
# Test 4: unknown slug → 404
# ---------------------------------------------------------------------------


def test_unknown_tool_404():
    """Requesting a slug that exists in neither registry → 404."""
    app = _make_app(db_pool=_FakePool())
    client = TestClient(app)

    resp = client.post(
        "/api/v1/data-tools/nonexistent-tool-xyz/invoke",
        json={"drug_name": "aspirin"},
    )

    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Test 5: DB path skipped when pool is None → HTTP path used
# ---------------------------------------------------------------------------


def test_db_path_skipped_when_pool_is_none(monkeypatch):
    """When db_pool is None the router must skip the DB path entirely and
    go directly to the HTTP adapter.invoke() path."""

    adapter_mod = importlib.import_module(_OPENFDA_ADAPTER_MODULE)

    monkeypatch.setattr(
        adapter_mod.Adapter,
        "db_query",
        AsyncMock(side_effect=AssertionError("db_query must not be called when pool is None")),
    )
    monkeypatch.setattr(
        importlib.import_module("dk_data.services.mcp.adapters").__dict__[
            "OpenFDALabelsTool"
        ],
        "invoke",
        AsyncMock(
            return_value={
                "tool": _OPENFDA_SLUG,
                "data": {"via": "http"},
                "status_code": 200,
                "error": None,
            }
        ),
    )

    app = _make_app(db_pool=None)
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/data-tools/{_OPENFDA_SLUG}/invoke",
        json={"drug_name": "aspirin"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"via": "http"}


# ---------------------------------------------------------------------------
# Test 6: DB path skipped when adapter module has no Adapter class → HTTP used
# ---------------------------------------------------------------------------


def test_db_path_skipped_when_module_has_no_adapter(monkeypatch):
    """When a tool's adapter_module does not export an Adapter class the router
    must skip the DB path and fall through to the HTTP *Tool.invoke() path.

    Uses fda-drugs-search (FdaDrugsTool) which genuinely has no Adapter
    subclass — hta_decisions now has Adapter so it can no longer serve as
    the "no Adapter" sentinel for this test.

    The mock is applied to the *exact instance* the dispatcher uses
    (router.TOOL_REGISTRY["fda-drugs-search"]), NOT to a class
    re-imported by module path. tests/test_mcp_data_tools.py installs a
    custom sys.modules loader that replaces dk_data.services.mcp.adapters.*
    module objects at collection time, so `from ...fda_drugs import
    FdaDrugsTool` can return a *different* class object than the one
    backing the registry instance — patching that class would miss and the
    real network-calling invoke() would run. Patching the instance attribute
    is immune to that pollution and targets the true object under test.
    """

    fda_tool = TOOL_REGISTRY["fda-drugs-search"]
    monkeypatch.setattr(
        fda_tool,
        "invoke",
        AsyncMock(
            return_value={
                "tool": "fda-drugs-search",
                "data": {"via": "http-fda"},
                "status_code": 200,
                "error": None,
            }
        ),
    )

    app = _make_app(db_pool=_FakePool())
    client = TestClient(app)

    resp = client.post(
        "/api/v1/data-tools/fda-drugs-search/invoke",
        json={"drug_name": "aspirin"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"via": "http-fda"}
