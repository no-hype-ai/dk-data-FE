"""Tests for the OpenFDA Labels adapter (Task 1.4 — H1: DB error ≠ silent miss).

TDD: RED first (current code swallows DB errors), then GREEN after fix.
No pytest-asyncio: coroutines are driven with asyncio.run() in plain sync tests.
No respx: DB is faked with hand-rolled async context manager helpers;
          _api_lookup is monkeypatched to control the HTTP-fallback boundary.
"""

import asyncio
import pytest

from dk_data.services.mcp.adapters.openfda_labels import Adapter
from dk_data.services.mcp.adapters.base import BaseAdapter


# ---------------------------------------------------------------------------
# Fake asyncpg pool helpers (same pattern as test_adapter_ema.py)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Minimal fake asyncpg connection."""

    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query, *args):
        return self._rows


class _FakePool:
    """Minimal fake asyncpg pool whose .acquire() is an async context manager."""

    def __init__(self, rows):
        self._conn = _FakeConn(rows)

    def acquire(self):
        return self

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc_info):
        pass


class _FakePoolRaises:
    """Fake pool whose connection.fetch() raises a given exception."""

    def __init__(self, exc):
        self._exc = exc

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def fetch(self, query, *args):
        raise self._exc

    async def __aexit__(self, *exc_info):
        pass


class _FakeRow(dict):
    """dict subclass so row["label_data"] works."""
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdapterContract:
    def test_adapter_contract(self):
        assert issubclass(Adapter, BaseAdapter)
        a = Adapter()
        assert a.source_name == "openfda_labels"
        assert a.raw_table == "openfda_labels"
        assert a.raw_schema == "mol_raw"
        assert a.normalize({"a": 1}) == {"a": 1}


class TestDbHitReturnsLocalNoApi:
    """DB hit → source:openfda_local returned; API must NOT be called."""

    def test_db_hit_returns_local_no_api(self):
        label_data = {"openfda": {"generic_name": ["aspirin"]}, "purpose": ["pain relief"]}
        rows = [_FakeRow({"label_data": label_data})]
        pool = _FakePool(rows)

        async def _must_not_call(*args, **kwargs):
            raise AssertionError("API must not be called on DB hit")

        adapter = Adapter()
        adapter._api_lookup = _must_not_call

        result = asyncio.run(adapter.db_query("aspirin", pool))

        assert result == {"source": "openfda_local", "results": [label_data]}


class TestDbGenuineMissFallsBackToApi:
    """Genuine miss (no rows) → falls back to _api_lookup; result is API dict."""

    def test_db_genuine_miss_falls_back_to_api(self):
        pool = _FakePool([])  # no rows

        api_result = {"source": "openfda", "results": [{"x": 1}]}

        async def _fake_api(drug_name):
            return api_result

        adapter = Adapter()
        adapter._api_lookup = _fake_api

        result = asyncio.run(adapter.db_query("aspirin", pool))

        assert result == api_result


class TestDbErrorRaisesNotSilentMiss:
    """H1 assertion: DB exception RAISES — not swallowed, not routed to API."""

    def test_db_error_raises_not_silent_miss(self):
        pool = _FakePoolRaises(RuntimeError("db down"))

        async def _must_not_call(*args, **kwargs):
            raise AssertionError("API fallback must NOT be called on DB error")

        adapter = Adapter()
        adapter._api_lookup = _must_not_call

        with pytest.raises(RuntimeError, match="db down"):
            asyncio.run(adapter.db_query("aspirin", pool))
