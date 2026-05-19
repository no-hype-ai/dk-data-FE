"""Tests for the orange_book adapter (#415 WS3 Batch C)."""

import asyncio
import pytest

from dk_data.services.mcp.adapters.orange_book import Adapter
from dk_data.services.mcp.adapters.base import BaseAdapter


class _FakeConn:
    def __init__(self, rows): self._rows = rows
    async def fetch(self, query, *args): return self._rows


class _FakePool:
    def __init__(self, rows): self._conn = _FakeConn(rows)
    def acquire(self): return self
    async def __aenter__(self): return self._conn
    async def __aexit__(self, *exc): pass


class _FakePoolRaises:
    def __init__(self, exc): self._exc = exc
    def acquire(self): return self
    async def __aenter__(self): return self
    async def fetch(self, query, *args): raise self._exc
    async def __aexit__(self, *exc): pass


class TestContract:
    def test_contract(self):
        assert issubclass(Adapter, BaseAdapter)
        a = Adapter()
        assert a.source_name == "orange_book"
        assert a.raw_table == "orange_book"
        assert a.raw_schema == "mol_raw"
        assert a.normalize({"x": 1}) == {"x": 1}
        assert a.full_table_name == "mol_raw.orange_book"


class TestDbHit:
    def test_db_hit_returns_dict(self):
        rows = [dict(response_body={"hit": True})]
        result = asyncio.run(Adapter().db_query("aspirin", _FakePool(rows)))
        assert result == {"source": "orange_book_local", "results": [{"response_body": {"hit": True}}]}


class TestDbMiss:
    def test_db_miss_returns_none(self):
        assert asyncio.run(Adapter().db_query("nope", _FakePool([]))) is None


class TestDbErrorRaises:
    def test_db_error_propagates(self):
        with pytest.raises(RuntimeError, match="db down"):
            asyncio.run(Adapter().db_query("x", _FakePoolRaises(RuntimeError("db down"))))
