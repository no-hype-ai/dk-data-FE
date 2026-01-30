"""
Base API Client for External Services.

Provides a consistent interface for all external API clients with:
- Async HTTP requests via httpx
- Retry logic with exponential backoff via tenacity
- Rate limiting
- Caching integration
- Error handling and logging
"""

import asyncio
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Generic, Optional, TypeVar

import httpx
from loguru import logger
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")


@dataclass
class APIResponse:
    """Standard API response wrapper."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    source: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RateLimiter:
    """Simple rate limiter for API calls."""

    requests_per_second: float
    _last_request: datetime = field(default_factory=datetime.now)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self) -> None:
        """Wait if necessary to respect rate limit."""
        async with self._lock:
            now = datetime.now()
            min_interval = timedelta(seconds=1.0 / self.requests_per_second)
            time_since_last = now - self._last_request

            if time_since_last < min_interval:
                wait_time = (min_interval - time_since_last).total_seconds()
                await asyncio.sleep(wait_time)

            self._last_request = datetime.now()


@dataclass
class APIClientConfig:
    """Configuration for an external API client."""

    base_url: str
    timeout: float = 30.0
    max_retries: int = 5
    retry_min_wait: float = 1.0
    retry_max_wait: float = 60.0
    requests_per_second: float = 10.0
    cache_ttl: int = 86400  # 24 hours default
    headers: Dict[str, str] = field(default_factory=dict)


class BaseAPIClient(ABC, Generic[T]):
    """
    Base class for external API clients.

    Subclasses should implement:
    - _parse_response(): Convert raw response to domain objects
    - Any source-specific query methods

    Usage:
        class MyAPIClient(BaseAPIClient[MyResponse]):
            def __init__(self):
                config = APIClientConfig(
                    base_url="https://api.example.com",
                    cache_ttl=3600
                )
                super().__init__(config)

            async def get_data(self, id: str) -> MyResponse:
                return await self._get(f"/data/{id}")
    """

    def __init__(
        self,
        config: APIClientConfig,
        cache_manager: Optional["CacheManager"] = None
    ):
        self.config = config
        self.cache = cache_manager
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = RateLimiter(config.requests_per_second)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                headers=self.config.headers,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _cache_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate a cache key for an endpoint and parameters."""
        key_data = f"{self.config.base_url}{endpoint}"
        if params:
            sorted_params = sorted(params.items())
            key_data += str(sorted_params)
        return hashlib.sha256(key_data.encode()).hexdigest()

    async def _get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Make a GET request with caching and retry logic.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            use_cache: Whether to use caching

        Returns:
            Parsed JSON response
        """
        cache_key = self._cache_key(endpoint, params)

        # Check cache first
        if use_cache and self.cache:
            cached = await self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {endpoint}")
                return cached

        # Make request with retry logic
        response_data = await self._request_with_retry("GET", endpoint, params=params)

        # Cache the response
        if use_cache and self.cache:
            await self.cache.set(cache_key, response_data, ttl=self.config.cache_ttl)

        return response_data

    async def _post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a POST request with retry logic.

        Args:
            endpoint: API endpoint path
            data: Form data
            json_data: JSON body data

        Returns:
            Parsed JSON response
        """
        return await self._request_with_retry(
            "POST",
            endpoint,
            data=data,
            json_data=json_data
        )

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with retry logic and rate limiting.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Form data
            json_data: JSON body data

        Returns:
            Parsed JSON response

        Raises:
            httpx.HTTPStatusError: If request fails after all retries
        """
        client = await self._get_client()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(
                multiplier=1,
                min=self.config.retry_min_wait,
                max=self.config.retry_max_wait
            ),
            retry=retry_if_exception_type((
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
            )),
            reraise=True
        ):
            with attempt:
                # Rate limiting
                await self._rate_limiter.acquire()

                logger.debug(f"{method} {self.config.base_url}{endpoint}")

                response = await client.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    data=data,
                    json=json_data,
                )

                # Handle rate limiting responses
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    raise httpx.ReadTimeout("Rate limited")

                response.raise_for_status()
                return response.json()

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the external API is healthy and accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        pass


class CacheManager:
    """
    Cache manager interface for API clients.

    This is a simple interface - the actual implementation
    uses Redis (see cache_manager.py).
    """

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        raise NotImplementedError

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a value in cache with TTL."""
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        """Delete a value from cache."""
        raise NotImplementedError


# ==========================================
# Critical vs Non-Critical Source Handling
# ==========================================

class CriticalAPIError(Exception):
    """Raised when a critical data source fails."""
    pass


class NonCriticalAPIError(Exception):
    """Raised when a non-critical data source fails (allows graceful degradation)."""
    pass


# Critical sources - must succeed or fail the entire request
CRITICAL_SOURCES = frozenset([
    "umls",
    "clinicaltrials",
    "openfda",
    "rxnorm",
])

# Non-critical sources - can degrade gracefully
NON_CRITICAL_SOURCES = frozenset([
    "pubmed",
    "patentsview",
    "sec_edgar",
    "mesh",
])


def is_critical_source(source_name: str) -> bool:
    """Check if a data source is critical."""
    return source_name.lower() in CRITICAL_SOURCES
