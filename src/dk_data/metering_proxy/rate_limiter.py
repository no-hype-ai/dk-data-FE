"""In-memory token bucket rate limiter.

Per-consumer rate limiting using a simple token bucket algorithm.
This is the initial implementation; Redis-backed rate limiting
is a future enhancement.

Each consumer has a bucket that refills at `rpm_limit / 60` tokens
per second, with a burst capacity equal to `rpm_limit / 10` (minimum 1).
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenBucket:
    """Token bucket for a single consumer."""

    rpm_limit: int
    burst: int
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.burst)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        # Tokens per second = rpm_limit / 60
        refill_rate = self.rpm_limit / 60.0
        self.tokens = min(self.burst, self.tokens + elapsed * refill_rate)
        self.last_refill = now

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed."""
        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    @property
    def remaining(self) -> int:
        """Current tokens remaining (after refill)."""
        self._refill()
        return int(self.tokens)

    @property
    def reset_seconds(self) -> float:
        """Seconds until next token is available."""
        if self.tokens >= 1.0:
            return 0.0
        refill_rate = self.rpm_limit / 60.0
        if refill_rate == 0:
            return 0.0
        return (1.0 - self.tokens) / refill_rate


class RateLimiter:
    """Per-consumer in-memory rate limiter."""

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def get_or_create_bucket(
        self, consumer: str, rpm_limit: int, burst: Optional[int] = None
    ) -> TokenBucket:
        """Get or create a token bucket for a consumer."""
        if consumer not in self._buckets:
            if burst is None:
                burst = max(1, rpm_limit // 10)
            self._buckets[consumer] = TokenBucket(
                rpm_limit=rpm_limit, burst=burst
            )
        return self._buckets[consumer]

    def check(self, consumer: str, rpm_limit: int) -> tuple[bool, int, float]:
        """Check rate limit for a consumer.

        Returns:
            Tuple of (allowed, remaining, reset_seconds)
        """
        if rpm_limit == 0:
            # Unlimited
            return True, 999999, 0.0

        bucket = self.get_or_create_bucket(consumer, rpm_limit)
        allowed = bucket.consume()
        return allowed, bucket.remaining, bucket.reset_seconds

    def reset(self, consumer: str) -> None:
        """Reset rate limit state for a consumer."""
        self._buckets.pop(consumer, None)
