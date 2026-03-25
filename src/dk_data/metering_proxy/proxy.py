"""Reverse proxy to PostgREST.

Forwards validated requests from the metering proxy to PostgREST
running on localhost:3000 within the same pod.
"""

import os

import httpx
import structlog

logger = structlog.get_logger(__name__)

POSTGREST_URL = os.getenv("POSTGREST_URL", "http://localhost:3000")

# Shared httpx client — created lazily at startup
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Get the shared httpx async client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=POSTGREST_URL,
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
            ),
        )
    return _client


async def close_client() -> None:
    """Close the shared httpx client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def proxy_request(
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes | None = None,
    query_string: str = "",
) -> httpx.Response:
    """Forward a request to PostgREST.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: URL path to forward
        headers: Request headers (Authorization is stripped)
        body: Request body bytes
        query_string: URL query string

    Returns:
        httpx.Response from PostgREST
    """
    client = get_client()

    # Build the target URL
    url = path
    if query_string:
        url = f"{path}?{query_string}"

    # Strip metering proxy auth headers — PostgREST uses its own JWT auth
    proxy_headers = {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("host", "authorization", "content-length")
    }

    try:
        response = await client.request(
            method=method,
            url=url,
            headers=proxy_headers,
            content=body,
        )
        return response
    except httpx.ConnectError:
        logger.error("postgrest_connection_error", url=url)
        raise
    except httpx.TimeoutException:
        logger.error("postgrest_timeout", url=url, method=method)
        raise
