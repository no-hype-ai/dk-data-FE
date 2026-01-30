"""
SEC EDGAR Rate Limiter.

Implements token bucket algorithm for SEC EDGAR API rate limiting.
SEC EDGAR requires: 10 requests per second maximum.

Reference: https://www.sec.gov/developer
"""

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class SECRateLimiter:
    """
    Rate limiter for SEC EDGAR compliance.
    
    Uses token bucket algorithm:
    - Refill rate: 10 tokens per second
    - Bucket capacity: 10 tokens
    - Each request consumes 1 token
    """
    
    requests_per_second: float = 10.0
    _tokens: float = field(default=10.0, init=False)
    _last_update: float = field(default_factory=time.monotonic, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    async def acquire(self) -> None:
        """
        Wait if necessary to respect rate limit.
        
        This method will block until a token is available.
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            
            # Refill tokens based on elapsed time
            self._tokens = min(
                self.requests_per_second,
                self._tokens + elapsed * self.requests_per_second
            )
            self._last_update = now
            
            # If no tokens available, wait
            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self.requests_per_second
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
                self._last_update = time.monotonic()
            else:
                # Consume one token
                self._tokens -= 1.0
    
    def reset(self) -> None:
        """Reset the rate limiter (for testing)."""
        self._tokens = self.requests_per_second
        self._last_update = time.monotonic()
