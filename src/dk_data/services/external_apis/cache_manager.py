"""
Redis Cache Manager with Source-Aligned TTLs.

Provides caching for external API responses with TTLs that match
each data source's update frequency.
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import redis.asyncio as redis
from loguru import logger


class DataSource(str, Enum):
    """External data sources with their cache TTLs."""

    # Daily updates - 24 hour TTL
    CLINICALTRIALS = "clinicaltrials"
    OPENFDA_LABELS = "openfda_labels"
    ORANGE_BOOK = "orange_book"

    # Weekly updates - 7 day TTL
    OPENFDA_FAERS = "openfda_faers"
    RXNORM = "rxnorm"
    CMS_NADAC = "cms_nadac"
    PURPLE_BOOK = "purple_book"
    USPTO = "uspto"
    PUBCHEM = "pubchem"

    # Bi-weekly updates - 14 day TTL
    CHEMBL = "chembl"
    DRUGBANK = "drugbank"

    # Monthly updates - 30 day TTL
    UMLS = "umls"
    MESH = "mesh"

    # Quarterly/Annual updates - 90 day TTL
    ICD10 = "icd10"
    
    # Market Intelligence sources
    SEC_EDGAR = "sec_edgar"  # 7 day TTL (quarterly/annual filings)
    DAILYMED = "dailymed"  # 24 hour TTL (daily updates)

    # Default for unknown sources
    DEFAULT = "default"


# Source-aligned TTLs in seconds
SOURCE_TTL_MAP: dict[DataSource, int] = {
    # Daily (24 hours)
    DataSource.CLINICALTRIALS: 86400,
    DataSource.OPENFDA_LABELS: 86400,
    DataSource.ORANGE_BOOK: 86400,

    # Weekly (7 days)
    DataSource.OPENFDA_FAERS: 604800,
    DataSource.RXNORM: 604800,
    DataSource.CMS_NADAC: 604800,
    DataSource.PURPLE_BOOK: 604800,
    DataSource.USPTO: 604800,
    DataSource.PUBCHEM: 604800,

    # Bi-weekly (14 days)
    DataSource.CHEMBL: 1209600,
    DataSource.DRUGBANK: 1209600,

    # Monthly (30 days)
    DataSource.UMLS: 2592000,
    DataSource.MESH: 2592000,

    # Quarterly (90 days)
    DataSource.ICD10: 7776000,
    
    # Market Intelligence sources
    DataSource.SEC_EDGAR: 604800,  # 7 days (quarterly/annual filings)
    DataSource.DAILYMED: 86400,  # 24 hours (daily updates)

    # Default (24 hours)
    DataSource.DEFAULT: 86400,
}


@dataclass
class CacheConfig:
    """Redis cache configuration."""

    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    db: int = int(os.getenv("REDIS_CACHE_DB", "1"))
    password: Optional[str] = os.getenv("REDIS_PASSWORD")
    prefix: str = "gt:"  # Ground Truth prefix
    default_ttl: int = 86400  # 24 hours


class CacheManager:
    """
    Redis-based cache manager with source-aligned TTLs.

    Usage:
        cache = CacheManager()
        await cache.connect()

        # Cache with source-specific TTL
        await cache.set("my_key", {"data": "value"}, source=DataSource.CLINICALTRIALS)

        # Get cached value
        data = await cache.get("my_key")

        # Force refresh
        await cache.delete("my_key")

        await cache.close()
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Initialize the Redis connection."""
        if self._client is not None:
            return

        logger.info(f"Connecting to Redis at {self.config.host}:{self.config.port}")

        self._client = redis.Redis(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            decode_responses=True,
        )

        # Verify connectivity
        try:
            await self._client.ping()
            logger.info("Redis connection established")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    def _make_key(self, key: str) -> str:
        """Create a prefixed cache key."""
        return f"{self.config.prefix}{key}"

    def _get_ttl(
        self,
        source: Optional[DataSource] = None,
        ttl_override: Optional[int] = None
    ) -> int:
        """
        Get TTL for a cache entry.

        Args:
            source: Data source for source-aligned TTL
            ttl_override: Override TTL (takes precedence)

        Returns:
            TTL in seconds
        """
        if ttl_override is not None:
            return ttl_override

        if source is not None:
            return SOURCE_TTL_MAP.get(source, self.config.default_ttl)

        return self.config.default_ttl

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if self._client is None:
            await self.connect()

        full_key = self._make_key(key)

        try:
            value = await self._client.get(full_key)
            if value is None:
                return None

            return json.loads(value)
        except redis.RedisError as e:
            logger.warning(f"Redis get error for {key}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        source: Optional[DataSource] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a value in cache with source-aligned TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            source: Data source for TTL alignment
            ttl: Override TTL in seconds

        Returns:
            True if successful, False otherwise
        """
        if self._client is None:
            await self.connect()

        full_key = self._make_key(key)
        effective_ttl = self._get_ttl(source, ttl)

        try:
            serialized = json.dumps(value)
            await self._client.setex(full_key, effective_ttl, serialized)
            logger.debug(f"Cached {key} with TTL {effective_ttl}s")
            return True
        except (redis.RedisError, TypeError) as e:
            logger.warning(f"Redis set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete a value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False otherwise
        """
        if self._client is None:
            await self.connect()

        full_key = self._make_key(key)

        try:
            result = await self._client.delete(full_key)
            return result > 0
        except redis.RedisError as e:
            logger.warning(f"Redis delete error for {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        if self._client is None:
            await self.connect()

        full_key = self._make_key(key)

        try:
            return await self._client.exists(full_key) > 0
        except redis.RedisError:
            return False

    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key in seconds."""
        if self._client is None:
            await self.connect()

        full_key = self._make_key(key)

        try:
            ttl = await self._client.ttl(full_key)
            return max(0, ttl)  # -1 or -2 means expired/not found
        except redis.RedisError:
            return 0

    async def refresh_if_stale(
        self,
        key: str,
        threshold_percent: float = 0.2
    ) -> bool:
        """
        Check if a cached value is close to expiry and should be refreshed.

        Args:
            key: Cache key
            threshold_percent: Refresh when this percent of TTL remains

        Returns:
            True if refresh is recommended, False otherwise
        """
        ttl_remaining = await self.get_ttl(key)
        if ttl_remaining == 0:
            return True

        # Get original TTL from cached metadata if available
        # For simplicity, assume refresh at 20% remaining
        return ttl_remaining < (self.config.default_ttl * threshold_percent)

    async def clear_by_prefix(self, prefix: str) -> int:
        """
        Clear all cache entries matching a prefix.

        Args:
            prefix: Prefix to match (will be combined with config prefix)

        Returns:
            Number of keys deleted
        """
        if self._client is None:
            await self.connect()

        pattern = f"{self.config.prefix}{prefix}*"

        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                return await self._client.delete(*keys)
            return 0
        except redis.RedisError as e:
            logger.warning(f"Redis clear error for prefix {prefix}: {e}")
            return 0

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        if self._client is None:
            await self.connect()

        try:
            info = await self._client.info("memory")
            keys_count = await self._client.dbsize()

            return {
                "keys_count": keys_count,
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected": True,
            }
        except redis.RedisError:
            return {
                "keys_count": 0,
                "used_memory": "N/A",
                "connected": False,
            }


# Singleton instance
_cache_manager: Optional[CacheManager] = None


async def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance."""
    global _cache_manager

    if _cache_manager is None:
        _cache_manager = CacheManager()
        await _cache_manager.connect()

    return _cache_manager


async def close_cache_manager() -> None:
    """Close the global cache manager instance."""
    global _cache_manager

    if _cache_manager is not None:
        await _cache_manager.close()
        _cache_manager = None
