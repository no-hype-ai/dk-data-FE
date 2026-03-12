"""Unified rate limiter for MCP tools.

Feature: 015-assessment-dashboard-integration
Task: T060

Loads per-source rate limits from config/rate_limits.yaml.
Uses token bucket algorithm for rate limiting.
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, Optional

import yaml

from loguru import logger


_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "rate_limits.yaml"


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float, burst: int):
        self.rate = rate          # tokens per second
        self.burst = burst        # max tokens
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to acquire a token. Returns True if granted."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class MCPRateLimiter:
    """Rate limiter that loads per-source config from rate_limits.yaml."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or _CONFIG_PATH
        self._config: Dict = {}
        self._buckets: Dict[str, TokenBucket] = {}
        self._load_config()

    def _load_config(self):
        """Load rate limit configuration from YAML."""
        if not self._config_path.exists():
            logger.warning(f"Rate limits config not found: {self._config_path}")
            self._config = {"defaults": {"requests_per_second": 5, "timeout_seconds": 30, "burst_limit": 10}}
            return

        try:
            with open(self._config_path) as f:
                self._config = yaml.safe_load(f)
            if not isinstance(self._config, dict) or "defaults" not in self._config:
                raise ValueError("rate_limits.yaml must have a 'defaults' section")
            logger.info(f"Loaded rate limits for {len(self._config.get('sources', {}))} sources")
        except Exception as e:
            logger.error(f"Failed to load rate_limits.yaml: {e}")
            raise

        # Pre-create global CMS bucket (max 8 req/s across all CMS datasets)
        # CMS recommends max 8 req/s across all datasets combined
        self._buckets["_cms_global"] = TokenBucket(rate=8.0, burst=12)

    def _get_source_config(self, source: str) -> dict:
        """Get config for a source, falling back to defaults."""
        defaults = self._config.get("defaults", {})
        sources = self._config.get("sources", {})
        source_cfg = sources.get(source, {})
        return {**defaults, **source_cfg}

    def _get_bucket(self, source: str) -> TokenBucket:
        """Get or create token bucket for a source."""
        if source not in self._buckets:
            cfg = self._get_source_config(source)
            rate = cfg.get("requests_per_second", 5)
            burst = cfg.get("burst_limit", 10)
            self._buckets[source] = TokenBucket(rate=rate, burst=burst)
        return self._buckets[source]

    async def acquire(self, source: str) -> bool:
        """Acquire rate limit token for a source. Returns True if granted."""
        bucket = self._get_bucket(source)
        return await bucket.acquire()

    def get_timeout(self, source: str) -> float:
        """Get configured timeout for a source in seconds."""
        cfg = self._get_source_config(source)
        return float(cfg.get("timeout_seconds", 30))

    def get_backoff_config(self, source: str) -> dict:
        """Get backoff configuration for a source."""
        cfg = self._get_source_config(source)
        return {
            "base_delay": cfg.get("base_delay_seconds", 1),
            "max_delay": cfg.get("max_delay_seconds", 30),
            "max_retries": cfg.get("max_retries", 3),
            "jitter": cfg.get("jitter", True),
        }


# Module-level singleton
_rate_limiter: Optional[MCPRateLimiter] = None


def get_rate_limiter() -> MCPRateLimiter:
    """Get the singleton rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = MCPRateLimiter()
    return _rate_limiter
