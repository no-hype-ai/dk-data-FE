"""Redis-backed rate limiter for the metering proxy.

Feature: 002-external-integration-foundation (US-3, T024e)

Why this exists: the in-memory `RateLimiter` in `rate_limiter.py` is
per-replica. When the proxy runs ≥2 replicas (T024d mandates this
for HA), each replica holds its own token bucket, so the effective
rate limit becomes `N × configured_rpm`. For internal-tier consumers
with `rpm_limit=0` (unlimited) this is fine, but for any consumer
with a real cap it is a correctness bug.

This module provides a Redis-backed token bucket that uses a single
shared counter across all replicas. It is strictly additive to the
in-memory implementation — if Redis is unavailable at startup, the
proxy falls back to the in-memory limiter and emits a warning. This
preserves the "telemetry-must-never-break-requests" invariant.

Contract:
    - `check(consumer, rpm_limit)` returns `(allowed, remaining, reset_seconds)`
    - Buckets refill at `rpm_limit / 60` tokens per second
    - Burst capacity = `max(1, rpm_limit // 10)` (matches in-memory limiter)
    - A consumer with `rpm_limit=0` is always allowed

Implementation: a Lua script runs atomically inside Redis so the
refill + token consumption can't race across replicas. The script
takes the consumer key, current timestamp, and rpm_limit as
arguments; returns `(allowed, remaining, reset_seconds)`.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

logger = logging.getLogger("dk_data.metering_proxy.rate_limiter_redis")

# Redis Lua script for atomic token bucket refill + consume.
#
# KEYS[1] = bucket key (e.g., "dk-data:rl:behavior-labs-ai")
# ARGV[1] = rpm_limit (e.g., 500)
# ARGV[2] = now_ms   (client-provided for determinism)
#
# Returns: { allowed (1|0), tokens_remaining, reset_seconds }
_LUA_TOKEN_BUCKET = r"""
local key = KEYS[1]
local rpm_limit = tonumber(ARGV[1])
local now_ms = tonumber(ARGV[2])

if rpm_limit == 0 then
  return {1, 999999, 0}
end

local burst = math.max(1, math.floor(rpm_limit / 10))
local refill_per_ms = rpm_limit / 60000.0

local stored = redis.call("HMGET", key, "tokens", "last_refill_ms")
local tokens = tonumber(stored[1])
local last_refill_ms = tonumber(stored[2])

if tokens == nil then
  tokens = burst
  last_refill_ms = now_ms
end

local elapsed = now_ms - last_refill_ms
if elapsed < 0 then elapsed = 0 end
tokens = math.min(burst, tokens + elapsed * refill_per_ms)

local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end

redis.call("HMSET", key, "tokens", tokens, "last_refill_ms", now_ms)
redis.call("PEXPIRE", key, 300000)

local reset_ms = 0
if tokens < 1 and refill_per_ms > 0 then
  reset_ms = (1 - tokens) / refill_per_ms
end

return {allowed, math.floor(tokens), math.floor(reset_ms / 1000)}
"""


class AsyncRedisLike(Protocol):
    async def eval(self, script: str, numkeys: int, *args: str) -> list: ...
    async def close(self) -> None: ...


class RedisRateLimiter:
    """Distributed rate limiter backed by Redis.

    Instantiate with a connected redis client (from `redis.asyncio`).
    Call `check(consumer, rpm_limit)` on every request.
    """

    def __init__(self, client: AsyncRedisLike, *, key_prefix: str = "dk-data:rl:") -> None:
        self._client = client
        self._key_prefix = key_prefix

    async def check(
        self, consumer: str, rpm_limit: int
    ) -> tuple[bool, int, float]:
        """Atomically refill + consume one token.

        Returns `(allowed, remaining, reset_seconds)` with the same
        semantics as the in-memory limiter.
        """
        key = f"{self._key_prefix}{consumer}"
        now_ms = str(int(time.time() * 1000))
        try:
            result = await self._client.eval(
                _LUA_TOKEN_BUCKET,
                1,
                key,
                str(rpm_limit),
                now_ms,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("redis rate limit eval failed — fail-open: %s", e)
            return True, rpm_limit, 0.0
        allowed = bool(result[0])
        remaining = int(result[1])
        reset_seconds = float(result[2])
        return allowed, remaining, reset_seconds

    async def close(self) -> None:
        await self._client.close()


async def build_redis_rate_limiter(url: str) -> RedisRateLimiter | None:
    """Construct a RedisRateLimiter or return None on failure.

    The proxy caller should fall back to the in-memory limiter when
    this returns None (so a flaky Redis at startup does not break the
    proxy entirely).
    """
    try:
        import redis.asyncio as aioredis  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "redis package not installed — Redis rate limiter unavailable"
        )
        return None
    try:
        client = aioredis.from_url(url, decode_responses=True)
        # Quick ping so we fail fast on unreachable Redis
        await client.ping()
    except Exception as e:  # noqa: BLE001
        logger.warning("redis connection failed at %s: %s", url, e)
        return None
    return RedisRateLimiter(client)
