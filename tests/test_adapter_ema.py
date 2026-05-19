"""Tests for the EMA adapter (Task 1.3 — DB-first BaseAdapter port).

TDD: RED first (no Adapter class yet), then GREEN after implementation.
No pytest-asyncio: coroutines are driven with asyncio.run() in plain sync tests.
No respx: DB is faked with hand-rolled async context manager helpers.
"""

import asyncio
import datetime
import pytest

# ---------------------------------------------------------------------------
# Fake asyncpg pool helpers
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


# ---------------------------------------------------------------------------
# Fake rows
# ---------------------------------------------------------------------------

def _make_fake_rows():
    """Two fake EMA rows; row 0 has a datetime.date to exercise isoformat."""

    class _FakeRow(dict):
        """dict subclass — dict(fakerow) works as-is."""
        pass

    row0 = _FakeRow({
        "product_number": "EMEA/H/C/001234",
        "product_name": "Aspirex",
        "active_substance": "aspirin",
        "inn": "acetylsalicylic acid",
        "atc_code": "B01AC06",
        "marketing_authorization_holder": "AcmePharma",
        "authorization_status": "Authorised",
        "authorization_date": datetime.date(2020, 3, 15),  # triggers isoformat branch
        "medicine_type": "Centrally authorised product",
        "therapeutic_area": "Cardiovascular",
        "pharmacotherapeutic_group": "Platelet aggregation inhibitors",
        "epar_url": "https://www.ema.europa.eu/epar/aspirex",
        "summary_url": "https://www.ema.europa.eu/summary/aspirex",
        "molecule_id": "mol-001",
    })
    row1 = _FakeRow({
        "product_number": "EMEA/H/C/005678",
        "product_name": "Aspirol",
        "active_substance": "aspirin",
        "inn": "acetylsalicylic acid",
        "atc_code": "B01AC06",
        "marketing_authorization_holder": "BetaPharma",
        "authorization_status": "Withdrawn",
        "authorization_date": "2018-06-01",  # already a string — no isoformat
        "medicine_type": "Centrally authorised product",
        "therapeutic_area": "Cardiovascular",
        "pharmacotherapeutic_group": "Platelet aggregation inhibitors",
        "epar_url": None,
        "summary_url": None,
        "molecule_id": "mol-002",
    })
    return [row0, row1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAdapterContract:
    """Adapter class satisfies BaseAdapter contract."""

    def test_adapter_contract(self):
        from dk_data.services.mcp.adapters.ema import Adapter
        from dk_data.services.mcp.adapters.base import BaseAdapter

        assert issubclass(Adapter, BaseAdapter)
        a = Adapter()
        assert a.source_name == "ema"
        assert a.raw_table == "ema"
        assert a.raw_schema == "mol_raw"
        assert a.full_table_name == "mol_raw.ema"
        assert a.normalize({"x": 1}) == {"x": 1}


class TestDbQueryResults:
    """db_query returns correctly shaped results on hit."""

    def test_db_query_returns_results_for_known_substance(self):
        from dk_data.services.mcp.adapters.ema import Adapter

        pool = _FakePool(_make_fake_rows())
        result = asyncio.run(Adapter().db_query("aspirin", pool))

        assert result is not None
        assert result["total"] == 2
        assert len(result["results"]) == 2

        # row 0 had a datetime.date — must be converted to ISO str
        row0 = result["results"][0]
        assert isinstance(row0["authorization_date"], str)
        assert row0["authorization_date"] == "2020-03-15"


class TestDbQueryNoneOnNoRows:
    """db_query returns None (not raises, not empty dict) when no rows."""

    def test_db_query_none_on_no_rows(self):
        from dk_data.services.mcp.adapters.ema import Adapter

        pool = _FakePool([])
        result = asyncio.run(Adapter().db_query("unknown_drug_xyz", pool))
        assert result is None


class TestDbQueryRaisesOnError:
    """db_query propagates real DB errors — does NOT swallow to None."""

    def test_db_query_raises_on_db_error(self):
        from dk_data.services.mcp.adapters.ema import Adapter

        pool = _FakePoolRaises(RuntimeError("db down"))
        with pytest.raises(RuntimeError, match="db down"):
            asyncio.run(Adapter().db_query("aspirin", pool))


class TestQueryIndexedFriendly:
    """The SQL query must not contain LIKE or % (silver antipattern S2 safety)."""

    def test_query_is_indexed_friendly_no_like(self):
        from dk_data.services.mcp.adapters.ema import _EMA_SILVER_QUERY

        sql_upper = _EMA_SILVER_QUERY.upper()
        assert "LIKE" not in sql_upper, "Query must not use LIKE (silver rule S2)"
        assert "%" not in _EMA_SILVER_QUERY, "Query must not use % wildcard"
        assert "mol_silver.ema" in _EMA_SILVER_QUERY.lower(), (
            "Query must select FROM mol_silver.ema"
        )
