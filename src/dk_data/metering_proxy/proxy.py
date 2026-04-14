"""Reverse proxy to PostgREST.

Forwards validated requests from the metering proxy to PostgREST
running on localhost:3000 within the same pod.
"""

import os

import httpx
import structlog

from dk_data.metering_proxy import jwt_mint, metrics
from dk_data.metering_proxy.jwt_mint import JWTMintError

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
    *,
    consumer_alias: str | None = None,
    tier: str | None = None,
) -> httpx.Response:
    """Forward a request to PostgREST.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: URL path to forward
        headers: Request headers (raw Authorization is stripped)
        body: Request body bytes
        query_string: URL query string
        consumer_alias: Validated consumer alias used as JWT sub claim.
                        When None the request is a bypass path (/health,
                        /ready, /metrics) that never reaches this function
                        in normal operation.
        tier: Consumer tier used to select the PostgreSQL role in the JWT.
              Must be provided together with consumer_alias.

    Returns:
        httpx.Response from PostgREST

    Raises:
        JWTMintError: If consumer_alias and tier are both provided but
                      minting fails.  Callers (app.py) catch this and
                      return 500.
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

    if consumer_alias is not None and tier is not None:
        # Normal (authenticated) path: mint a PostgREST JWT and inject it.
        try:
            token = jwt_mint.mint(consumer_alias=consumer_alias, tier=tier)
            proxy_headers["Authorization"] = f"Bearer {token}"
            metrics.JWT_MINTED_TOTAL.labels(tier=tier).inc()
        except JWTMintError as e:
            metrics.JWT_MINT_ERRORS_TOTAL.labels(error_type=e.error_type).inc()
            raise
    else:
        # Bypass path (consumer_alias or tier is None): should be unreachable
        # in normal operation because /health|/ready|/metrics are handled
        # directly in app.py and never routed here.  Increment the
        # FR-010 bug-detector counter and continue without a JWT.
        metrics.REQUESTS_FORWARDED_WITHOUT_JWT_TOTAL.inc()

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
