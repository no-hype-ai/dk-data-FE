"""Unit tests for the two-tier cache."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dk_data_client.cache import (
    SqliteCacheBackend,
    TwoTierCache,
    _NEVER_CACHE,
    _ttl_for,
    build_cache,
    make_key,
)


class TestCacheKey:
    def test_key_is_deterministic(self):
        k1 = make_key("molecules.get", {"id": "CHEMBL25"})
        k2 = make_key("molecules.get", {"id": "CHEMBL25"})
        assert k1 == k2

    def test_different_args_differ(self):
        k1 = make_key("molecules.get", {"id": "CHEMBL25"})
        k2 = make_key("molecules.get", {"id": "CHEMBL50"})
        assert k1 != k2

    def test_different_methods_differ(self):
        k1 = make_key("molecules.get", {"id": "X"})
        k2 = make_key("molecules.getProfile", {"id": "X"})
        assert k1 != k2

    def test_key_includes_method_prefix(self):
        k = make_key("molecules.get", {"id": "X"})
        assert k.startswith("molecules.get:")

    def test_arg_order_is_normalized(self):
        k1 = make_key("foo", {"a": 1, "b": 2})
        k2 = make_key("foo", {"b": 2, "a": 1})
        assert k1 == k2


class TestTTLTable:
    def test_gold_backed_are_24h(self):
        assert _ttl_for("molecules.getProfile") == 24 * 3600
        assert _ttl_for("molecules.getCompetitiveLandscape") == 24 * 3600

    def test_never_cache_returns_none(self):
        assert _ttl_for("molecules.getResolutionQueue") is None
        assert _ttl_for("health") is None
        assert _ttl_for("serverInfo") is None

    def test_never_cache_list_has_expected_members(self):
        assert "molecules.getResolutionQueue" in _NEVER_CACHE
        assert "health" in _NEVER_CACHE

    def test_unknown_method_gets_default_ttl(self):
        assert _ttl_for("some.random.method") == 3600


class TestTwoTierCache:
    async def test_l1_only_miss_then_set(self):
        cache = TwoTierCache(l2=None)
        hit = await cache.get("molecules.get", {"id": "X"})
        assert hit is None
        await cache.set("molecules.get", {"id": "X"}, {"canonical_name": "aspirin"})
        hit = await cache.get("molecules.get", {"id": "X"})
        assert hit is not None
        assert hit.tier == "l1"
        assert hit.value == {"canonical_name": "aspirin"}

    async def test_never_cache_never_hits(self):
        cache = TwoTierCache(l2=None)
        await cache.set("molecules.getResolutionQueue", {}, ["some", "list"])
        hit = await cache.get("molecules.getResolutionQueue", {})
        assert hit is None  # write was a no-op

    async def test_l2_populates_l1_on_hit(self, tmp_path: Path):
        l2 = SqliteCacheBackend(tmp_path / "cache.db")
        cache = TwoTierCache(l2=l2)
        await cache.set("molecules.get", {"id": "A"}, {"name": "alpha"})

        # New cache instance hitting the same SQLite file should find it in L2
        cache2 = TwoTierCache(l2=SqliteCacheBackend(tmp_path / "cache.db"))
        hit = await cache2.get("molecules.get", {"id": "A"})
        assert hit is not None
        assert hit.tier == "l2"
        assert hit.value == {"name": "alpha"}

        # A second fetch should now come from L1 on the same cache
        hit2 = await cache2.get("molecules.get", {"id": "A"})
        assert hit2 is not None
        assert hit2.tier == "l1"

        await cache.close()
        await cache2.close()


class TestBuildCache:
    def test_build_none(self):
        cache = build_cache("none")
        assert cache._l2 is None

    def test_build_redis_requires_url(self):
        with pytest.raises(ValueError, match="cache_redis_url"):
            build_cache("redis")

    def test_build_sqlite(self, tmp_path: Path):
        cache = build_cache("sqlite", sqlite_path=str(tmp_path / "x.db"))
        assert cache._l2 is not None

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="unknown cache backend"):
            build_cache("memcached")  # type: ignore[arg-type]
