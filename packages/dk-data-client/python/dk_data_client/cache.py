"""Two-tier cache for dk-data-client.

L1: in-process LRU via cachetools — hot path, zero network.
L2: Redis (production) or SQLite (dev/tests) — survives process restart.

Cache keys are content-addressed: `sha256(method:args)`. A given call
produces the same key on every request, and different arguments produce
different keys. No key normalization — if the caller passes differently-
ordered kwargs, they get different cache entries. (This is by design:
normalization is a lot of code that can silently collide.)

TTLs match the contract table in plan.md Phase 0 / contracts/client-
package-api.md (corrected per F-D019 drift audit).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cachetools import TTLCache

# orjson is ~5× faster than stdlib json for L2 cache serialization.
# It's optional (installed via `dk-data-client[fast]`) so the package
# stays slim by default. Fall back to stdlib if not present.
try:
    import orjson

    def _json_dumps(value: Any) -> bytes:
        return orjson.dumps(value, default=str)

    def _json_loads(data: str | bytes) -> Any:
        return orjson.loads(data)

    _HAS_ORJSON = True
except ImportError:  # pragma: no cover
    def _json_dumps(value: Any) -> bytes:  # type: ignore[misc]
        return json.dumps(value, default=str).encode("utf-8")

    def _json_loads(data: str | bytes) -> Any:  # type: ignore[misc]
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

    _HAS_ORJSON = False

CacheTier = Literal["l1", "l2", "none"]

# -----------------------------------------------------------------------------
# TTL table — see client-package-api.md. Keys are method names.
# -----------------------------------------------------------------------------

_DEFAULT_L1_TTL_SECONDS = 300  # 5 min — short because L1 is per-process
_L2_TTL_SECONDS: dict[str, int] = {
    # Gold-backed resources that rebuild nightly at 22:00 UTC
    "molecules.getProfile": 24 * 3600,
    "molecules.getCompetitiveLandscape": 24 * 3600,
    "molecules.getSafety": 24 * 3600,
    "companies.getPipeline": 24 * 3600,
    # Silver-backed lifecycle/identifier resources
    "molecules.get": 30 * 24 * 3600,
    "molecules.resolve": 30 * 24 * 3600,
    "companies.resolve": 30 * 24 * 3600,
    "conditions.resolve": 30 * 24 * 3600,
    "providers.resolve": 30 * 24 * 3600,
    # Drug labels / regulatory
    "molecules.getDrugLabels": 24 * 3600,
    "molecules.getBoxedWarnings": 24 * 3600,
    "molecules.getContraindications": 24 * 3600,
    # Clinical trials
    "molecules.getClinicalTrials": 6 * 3600,
    # Adverse events
    "molecules.getAdverseEvents": 24 * 3600,
    # Publications
    "publications.search": 24 * 3600,
    "publications.getByMolecule": 24 * 3600,
    "publications.getPubMed": 24 * 3600,
    "publications.getOpenAlex": 24 * 3600,
    # Patents
    "patents.search": 7 * 24 * 3600,
    "patents.getByMolecule": 7 * 24 * 3600,
}

_NEVER_CACHE: frozenset[str] = frozenset(
    {
        "molecules.getResolutionQueue",
        "health",
        "catalog",
        "dataSources",
        "serverInfo",
    }
)


def _ttl_for(method: str) -> int | None:
    """Return the L2 TTL for a method, or None if the method must not be cached."""
    if method in _NEVER_CACHE:
        return None
    return _L2_TTL_SECONDS.get(method, 3600)  # default 1h for anything not listed


def make_key(method: str, args: dict[str, Any]) -> str:
    """Content-addressed cache key: sha256 of method + canonicalized args.

    Uses stdlib json (not orjson) because we need sort_keys for
    deterministic ordering regardless of how the caller constructed
    the dict. orjson doesn't support sort_keys.
    """
    payload = json.dumps({"method": method, "args": args}, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{method}:{digest}"


# -----------------------------------------------------------------------------
# Backend interface
# -----------------------------------------------------------------------------


@dataclass
class CacheHit:
    value: Any
    tier: CacheTier


class CacheBackend(ABC):
    """Abstract interface for an L2 cache backend."""

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


# -----------------------------------------------------------------------------
# Redis backend
# -----------------------------------------------------------------------------


class RedisCacheBackend(CacheBackend):
    """Redis-backed L2 cache. Requires the `redis` extra."""

    def __init__(self, url: str) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError as e:
            raise RuntimeError(
                "Redis cache backend requires 'dk-data-client[redis]'; install the extra."
            ) from e
        # decode_responses=False so we can store raw bytes from orjson
        # and skip the str→bytes→str round trip on every operation.
        self._client = aioredis.from_url(url, decode_responses=False)

    async def get(self, key: str) -> Any | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return _json_loads(raw)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        # orjson.dumps returns bytes directly — skip str encoding.
        await self._client.set(key, _json_dumps(value), ex=ttl_seconds)

    async def close(self) -> None:
        await self._client.close()


# -----------------------------------------------------------------------------
# SQLite backend — synchronous under the hood, wrapped in async for interface
# parity. Intended for dev/test only (single-process, no concurrency
# guarantees beyond SQLite's own WAL mode).
# -----------------------------------------------------------------------------


class SqliteCacheBackend(CacheBackend):
    """SQLite-backed L2 cache for dev / single-process use.

    .. warning::
        SQLite performs **blocking I/O** on the asyncio event loop thread.
        Every ``get()`` and ``set()`` call blocks the entire event loop for
        the duration of the disk read/write.  This is acceptable for local
        development and unit tests (single-process, low concurrency, fast
        SSD) but will degrade throughput and latency under real load.

        Use ``RedisCacheBackend`` in production.  If you see this warning
        unexpectedly, check your ``DkDataClient(cache_backend=...)`` setting.
    """

    def __init__(self, db_path: str | Path = "~/.dk-data-client.sqlite") -> None:
        warnings.warn(
            "SqliteCacheBackend performs blocking I/O on the asyncio event loop. "
            "Use RedisCacheBackend in production (cache_backend='redis'). "
            "SQLite is safe only for dev/test environments.",
            stacklevel=2,
        )
        resolved = Path(os.path.expanduser(str(db_path)))
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(resolved), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, expires_at INTEGER)"
        )

    async def get(self, key: str) -> Any | None:
        row = self._conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at < int(time.time()):
            # Lazy eviction
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            return None
        try:
            return _json_loads(value)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = int(time.time()) + ttl_seconds
        # SQLite's BLOB column type accepts raw bytes from orjson.
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, _json_dumps(value), expires_at),
        )

    async def close(self) -> None:
        self._conn.close()


# -----------------------------------------------------------------------------
# Two-tier coordinator
# -----------------------------------------------------------------------------


class TwoTierCache:
    """Orchestrates L1 + L2 with a consistent get/set interface.

    On `get`:
      1. Check L1 — return immediately on hit with tier="l1"
      2. Check L2 — on hit, populate L1 and return with tier="l2"
      3. Return None (miss) otherwise

    On `set`: write to both tiers with method-specific L2 TTL.
    """

    def __init__(
        self,
        l2: CacheBackend | None,
        *,
        l1_max_items: int = 4096,  # larger than v0.1 (1024) to absorb scan traffic
        l1_ttl_seconds: int = _DEFAULT_L1_TTL_SECONDS,
    ) -> None:
        self._l1: TTLCache[str, Any] = TTLCache(maxsize=l1_max_items, ttl=l1_ttl_seconds)
        self._l2 = l2

    async def get(self, method: str, args: dict[str, Any]) -> CacheHit | None:
        if method in _NEVER_CACHE:
            return None
        key = make_key(method, args)
        if key in self._l1:
            return CacheHit(value=self._l1[key], tier="l1")
        if self._l2 is not None:
            l2_value = await self._l2.get(key)
            if l2_value is not None:
                self._l1[key] = l2_value
                return CacheHit(value=l2_value, tier="l2")
        return None

    async def set(self, method: str, args: dict[str, Any], value: Any) -> None:
        if method in _NEVER_CACHE:
            return
        key = make_key(method, args)
        self._l1[key] = value
        if self._l2 is not None:
            ttl = _ttl_for(method)
            if ttl is not None:
                await self._l2.set(key, value, ttl)

    async def close(self) -> None:
        if self._l2 is not None:
            await self._l2.close()


def build_cache(
    backend: Literal["redis", "sqlite", "none"] | None,
    *,
    redis_url: str | None = None,
    sqlite_path: str | None = None,
) -> TwoTierCache:
    """Factory helper to pick a backend based on the client config."""
    if backend is None or backend == "none":
        return TwoTierCache(l2=None)
    if backend == "redis":
        if not redis_url:
            raise ValueError("cache_backend='redis' requires cache_redis_url")
        return TwoTierCache(l2=RedisCacheBackend(redis_url))
    if backend == "sqlite":
        return TwoTierCache(l2=SqliteCacheBackend(sqlite_path or "~/.dk-data-client.sqlite"))
    raise ValueError(f"unknown cache backend: {backend!r}")
