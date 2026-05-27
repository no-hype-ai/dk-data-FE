"""Unit tests for MOA enrichment tiers — static + DB cache + resolver.

No external services required. DB interactions are stubbed with an
asyncpg-shaped fake pool/connection. Resolver tests stub the OpenFDA
client.
"""

from __future__ import annotations

import pytest

from dk_data.services.ground_truth.competitive_graph_service.moa_enrichment import (
    MoaEnrichment,
    lookup_moa,
    static_lookup,
)
from dk_data.services.ground_truth.competitive_graph_service.moa_enrichment_repo import (
    NEGATIVE_HIT,
)


# ───────────────────────────── stub pool / client ──────────────────────────


class _StubConn:
    def __init__(self, fetchrow_result=None):
        self._fetchrow_result = fetchrow_result
        self.executed: list[tuple] = []

    async def fetchrow(self, sql, *args):
        return self._fetchrow_result

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


class _StubPool:
    def __init__(self, fetchrow_result=None):
        self.conn = _StubConn(fetchrow_result)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                return pool.conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()


class _StubOpenFDA:
    """Minimal stand-in for OpenFDAClient.search_drug_labels."""

    def __init__(self, labels_for_moa=None, labels_for_epc=None):
        self._labels_for_moa = labels_for_moa or []
        self._labels_for_epc = labels_for_epc or []

    async def search_drug_labels(self, query, search_field, limit):
        if search_field.endswith("pharm_class_moa"):
            return self._labels_for_moa
        if search_field.endswith("pharm_class_epc"):
            return self._labels_for_epc
        return []


class _StubLabel:
    def __init__(self, pharm_class_moa=None, pharm_class_epc=None):
        self.pharm_class_moa = pharm_class_moa or []
        self.pharm_class_epc = pharm_class_epc or []


# ───────────────────────────── static_lookup ───────────────────────────────


def test_static_lookup_exact():
    e = static_lookup("TNF-alpha inhibitor")
    assert e is not None
    assert e.targets == ("TNF",)
    assert e.atc_prefix == "L04AB"


def test_static_lookup_case_insensitive():
    assert static_lookup("PD-1 INHIBITOR") is static_lookup("pd-1 inhibitor")


def test_static_lookup_loose_match_via_suffix_strip():
    # "TNF antagonist" → strip " antagonist" → "tnf" → prefix-match "tnf-alpha inhibitor"
    e = static_lookup("TNF antagonist")
    assert e is not None
    assert e.targets == ("TNF",)


def test_static_lookup_returns_none_for_unknown():
    assert static_lookup("completely made up moa") is None


def test_static_lookup_handles_empty_input():
    assert static_lookup(None) is None
    assert static_lookup("") is None
    assert static_lookup("   ") is None


# ───────────────────────────── lookup_moa async ────────────────────────────


@pytest.mark.asyncio
async def test_lookup_moa_static_hit_short_circuits():
    """Static dict hit means DB and API are never touched."""
    result = await lookup_moa(
        "TNF-alpha inhibitor", db_pool=None, openfda_client=None
    )
    assert result is not None
    assert result.targets == ("TNF",)


@pytest.mark.asyncio
async def test_lookup_moa_db_positive_hit():
    """DB returns a positive cached row → no API call."""
    pool = _StubPool(
        fetchrow_result={
            "fda_pharm_class_moa": "Some MoA",
            "fda_pharm_class_epc": "Some EPC",
            "targets": ["FOO"],
            "atc_prefix": "X01AA",
            "is_negative": False,
        }
    )
    result = await lookup_moa(
        "novel moa", db_pool=pool, openfda_client=_StubOpenFDA()
    )
    assert result is not None
    assert result.fda_pharm_class_epc == "Some EPC"
    assert result.targets == ("FOO",)


@pytest.mark.asyncio
async def test_lookup_moa_db_negative_hit_returns_none():
    """Negative cache row prevents re-querying the API."""
    pool = _StubPool(
        fetchrow_result={
            "fda_pharm_class_moa": None,
            "fda_pharm_class_epc": None,
            "targets": [],
            "atc_prefix": None,
            "is_negative": True,
        }
    )
    result = await lookup_moa(
        "previously-unknown moa", db_pool=pool, openfda_client=_StubOpenFDA()
    )
    assert result is None


@pytest.mark.asyncio
async def test_lookup_moa_cache_miss_resolves_via_openfda_and_persists():
    """Miss in both static + DB → OpenFDA resolver runs and result is cached."""
    pool = _StubPool(fetchrow_result=None)
    openfda = _StubOpenFDA(
        labels_for_moa=[
            _StubLabel(pharm_class_moa=["Some Novel Mechanism [MoA]"]),
        ],
        labels_for_epc=[
            _StubLabel(pharm_class_epc=["Some Novel Class [EPC]"]),
        ],
    )
    result = await lookup_moa(
        "totally novel inhibitor", db_pool=pool, openfda_client=openfda
    )
    assert result is not None
    # Resolver should strip the trailing "[EPC]" / "[MoA]" annotations.
    assert result.fda_pharm_class_epc == "Some Novel Class"
    assert result.fda_pharm_class_moa == "Some Novel Mechanism"
    # And the result should have been persisted (1 INSERT executed).
    assert any("INSERT" in sql for sql, _ in pool.conn.executed)


@pytest.mark.asyncio
async def test_lookup_moa_cache_miss_openfda_empty_persists_negative():
    """Miss everywhere → write negative sentinel to suppress future calls."""
    pool = _StubPool(fetchrow_result=None)
    openfda = _StubOpenFDA(labels_for_moa=[], labels_for_epc=[])
    result = await lookup_moa(
        "truly unknown blocker", db_pool=pool, openfda_client=openfda
    )
    assert result is None
    insert_args = next(
        args for sql, args in pool.conn.executed if "INSERT" in sql
    )
    # is_negative is positional arg #8 (0-indexed = 7) per the INSERT statement.
    assert insert_args[7] is True  # is_negative
    assert insert_args[5] == "negative"  # source


@pytest.mark.asyncio
async def test_negative_hit_sentinel_distinguishable():
    """Sanity: NEGATIVE_HIT is a singleton, comparable by `is`."""
    assert NEGATIVE_HIT is NEGATIVE_HIT
    assert not isinstance(NEGATIVE_HIT, MoaEnrichment)
