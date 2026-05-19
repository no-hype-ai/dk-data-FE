"""DB-first dispatch contract — WS4 SP1 (feature 211).

H1 decision table (specs/211-ws4-staging-main-reconcile/contracts/
dispatch-decision-table.md) + gate predicate + outcome metric + the
gate-off invariant that proves SC-001 (zero default behaviour change,
blocker B001 — no flaky live golden capture).

Pure unit tests: in-process fake pool + asyncio.run (no live DB, no
pytest-asyncio / respx dependency).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from dk_data.services.mcp import dbfirst_gate, dispatch
from dk_data.services.mcp.adapters.base import BaseAdapter
from dk_data.observability import metrics


# --- fakes -----------------------------------------------------------------

class _FakeConn:
    def __init__(self, rows=None, exc=None):
        self._rows = rows or []
        self._exc = exc

    async def fetch(self, *args, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._rows


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, rows=None, exc=None):
        self._conn = _FakeConn(rows=rows, exc=exc)

    def acquire(self):
        return _FakeAcquire(self._conn)


class _HitAdapter(BaseAdapter):
    source_name = "x"
    raw_table = "x"
    raw_schema = "raw"

    def normalize(self, api_response: dict) -> dict:  # pragma: no cover
        return api_response

    async def db_query(self, drug_name, db_pool):
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("q", drug_name)
        if not rows:
            return None
        return {"source": "x_local", "results": rows}


class _MissAdapter(_HitAdapter):
    async def db_query(self, drug_name, db_pool):
        return None


class _EmptyAdapter(_HitAdapter):
    async def db_query(self, drug_name, db_pool):
        return {}  # falsy → treated as miss → fallthrough (R4)


class _RaiseAdapter(_HitAdapter):
    async def db_query(self, drug_name, db_pool):
        raise RuntimeError("db down")


class _NoOverrideAdapter(BaseAdapter):
    source_name = "x"
    raw_table = "x"
    raw_schema = "raw"

    def normalize(self, api_response: dict) -> dict:  # pragma: no cover
        return api_response


SLUG = "chembl-search"


def _outcome(slug, outcome):
    return metrics.MCP_DBFIRST_OUTCOME_TOTAL.labels(source=slug, outcome=outcome)._value.get()


def _run(slug, drug, *, gate, sources, adapter, pool, monkeypatch):
    if gate is None:
        monkeypatch.delenv("MCP_DBFIRST_ENABLED", raising=False)
    else:
        monkeypatch.setenv("MCP_DBFIRST_ENABLED", gate)
    if sources is None:
        monkeypatch.delenv("MCP_DBFIRST_SOURCES", raising=False)
    else:
        monkeypatch.setenv("MCP_DBFIRST_SOURCES", sources)
    monkeypatch.setattr(dispatch, "_load_db_adapter", lambda mod: adapter, raising=True)

    called = {"pool": False}

    async def _fake_get_pool():
        called["pool"] = True
        return pool

    monkeypatch.setattr(dispatch, "get_db_pool", _fake_get_pool, raising=True)
    result = asyncio.run(dispatch.try_db_first(slug, drug))
    return result, called


# --- gate predicate --------------------------------------------------------

def test_gate_predicate(monkeypatch):
    monkeypatch.setenv("MCP_DBFIRST_ENABLED", "true")
    monkeypatch.setenv("MCP_DBFIRST_SOURCES", "chembl-search, ema-search")
    assert dbfirst_gate.gate_on("chembl-search") is True
    assert dbfirst_gate.gate_on("ema-search") is True
    assert dbfirst_gate.gate_on("pubmed-search") is False  # not allow-listed
    monkeypatch.setenv("MCP_DBFIRST_ENABLED", "false")
    assert dbfirst_gate.gate_on("chembl-search") is False  # master off
    monkeypatch.delenv("MCP_DBFIRST_ENABLED", raising=False)
    monkeypatch.delenv("MCP_DBFIRST_SOURCES", raising=False)
    assert dbfirst_gate.gate_on("chembl-search") is False  # default off


# --- SC-001 / B001 gate-off invariant -------------------------------------

def test_gate_off_returns_none_and_never_touches_pool(monkeypatch):
    before = _outcome(SLUG, "disabled")
    result, called = _run(
        SLUG, "imatinib", gate=None, sources=None,
        adapter=_HitAdapter(), pool=_FakePool(rows=[{"r": 1}]),
        monkeypatch=monkeypatch,
    )
    assert result is None
    assert called["pool"] is False  # dispatch must short-circuit before any DB work
    assert _outcome(SLUG, "disabled") == before + 1


# --- decision table rows 2-5 ----------------------------------------------

def test_missing_adapter_is_disabled(monkeypatch):
    before = _outcome(SLUG, "disabled")
    result, _ = _run(SLUG, "x", gate="true", sources=SLUG,
                      adapter=None, pool=_FakePool(), monkeypatch=monkeypatch)
    assert result is None
    assert _outcome(SLUG, "disabled") == before + 1


def test_adapter_without_db_query_override_is_disabled(monkeypatch):
    before = _outcome(SLUG, "disabled")
    result, _ = _run(SLUG, "x", gate="true", sources=SLUG,
                      adapter=_NoOverrideAdapter(), pool=_FakePool(),
                      monkeypatch=monkeypatch)
    assert result is None
    assert _outcome(SLUG, "disabled") == before + 1


def test_no_pool_is_disabled(monkeypatch):
    before = _outcome(SLUG, "disabled")
    result, _ = _run(SLUG, "x", gate="true", sources=SLUG,
                      adapter=_HitAdapter(), pool=None, monkeypatch=monkeypatch)
    assert result is None
    assert _outcome(SLUG, "disabled") == before + 1


def test_served_returns_payload_no_http(monkeypatch):
    before = _outcome(SLUG, "served")
    result, called = _run(SLUG, "imatinib", gate="true", sources=SLUG,
                           adapter=_HitAdapter(), pool=_FakePool(rows=[{"r": 1}]),
                           monkeypatch=monkeypatch)
    assert result == {
        "tool": SLUG,
        "data": {"source": "x_local", "results": [{"r": 1}]},
        "error": None,
        "status_code": 200,
    }
    assert called["pool"] is True
    assert _outcome(SLUG, "served") == before + 1


def test_miss_falls_through(monkeypatch):
    before = _outcome(SLUG, "fallthrough")
    result, _ = _run(SLUG, "x", gate="true", sources=SLUG,
                      adapter=_MissAdapter(), pool=_FakePool(),
                      monkeypatch=monkeypatch)
    assert result is None
    assert _outcome(SLUG, "fallthrough") == before + 1


def test_empty_result_falls_through(monkeypatch):
    before = _outcome(SLUG, "fallthrough")
    result, _ = _run(SLUG, "x", gate="true", sources=SLUG,
                      adapter=_EmptyAdapter(), pool=_FakePool(),
                      monkeypatch=monkeypatch)
    assert result is None  # R4: empty/zero-row is a miss, NOT served-empty
    assert _outcome(SLUG, "fallthrough") == before + 1


def test_db_error_raises_502_no_fallthrough(monkeypatch):
    before = _outcome(SLUG, "error")
    with pytest.raises(HTTPException) as ei:
        _run(SLUG, "x", gate="true", sources=SLUG,
             adapter=_RaiseAdapter(), pool=_FakePool(),
             monkeypatch=monkeypatch)
    assert ei.value.status_code == 502
    assert ei.value.detail["stage"] == "db_query"
    assert _outcome(SLUG, "error") == before + 1


# --- T006: BaseAdapter.db_query contract + feature-015 surface preserved ---

def test_base_adapter_db_query_default_is_async_none():
    import inspect
    assert inspect.iscoroutinefunction(BaseAdapter.db_query)
    assert asyncio.run(_NoOverrideAdapter().db_query("x", object())) is None


def test_feature015_surface_preserved_on_base():
    # FR-001/FR-005: db_query is ADDITIVE — these feature-015 members must
    # still exist with their original behaviour.
    a = _NoOverrideAdapter()
    assert a.full_table_name == "raw.x"
    assert a.validate_against_bronze({"any": "thing"}) is True
    assert a.build_url("http://h", "d", {}) == "http://h?query=d"

    class _Res:
        canonical_name = "d"

    assert a.build_urls_with_resolution("http://h", _Res(), {}) == ["http://h?query=d"]
