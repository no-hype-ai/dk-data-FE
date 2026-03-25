"""FastAPI metering proxy sidecar for PostgREST.

Runs as a sidecar container in the PostgREST Deployment on port 3001.
Provides consumer authentication, schema-level access control,
per-consumer rate limiting, and Prometheus metrics.

Architecture:
    Consumer -> metering-proxy:3001 -> PostgREST:3000 (localhost)
"""

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from dk_data.metering_proxy.auth import ConsumerKeyStore
from dk_data.metering_proxy.metrics import (
    ACTIVE_CONSUMERS,
    AUTH_FAILURES_TOTAL,
    RATE_LIMIT_REJECTIONS_TOTAL,
    REQUEST_DURATION_SECONDS,
    REQUESTS_TOTAL,
    RESPONSE_BYTES_TOTAL,
    SCHEMA_ACCESS_DENIED_TOTAL,
)
from dk_data.metering_proxy.proxy import close_client, proxy_request
from dk_data.metering_proxy.rate_limiter import RateLimiter
from dk_data.metering_proxy.schemas import (
    BYPASS_PATHS,
    check_schema_access,
    extract_schema_from_path,
)
from dk_data.observability.logging import setup_logging

logger = structlog.get_logger(__name__)

# Global state
key_store = ConsumerKeyStore()
rate_limiter = RateLimiter()
_seen_consumers: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    setup_logging(service_name="metering-proxy")
    key_store.load()
    logger.info(
        "metering_proxy_started",
        consumers=key_store.consumer_count,
    )
    yield
    await close_client()
    logger.info("metering_proxy_stopped")


app = FastAPI(
    title="dk-data Metering Proxy",
    description="Consumer authentication, rate limiting, and metering for PostgREST",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "metering-proxy"}


@app.get("/ready")
async def ready():
    """Readiness check — confirms consumer config is loaded."""
    return {
        "status": "ok",
        "consumers_loaded": key_store.consumer_count,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/-/reload")
async def reload_config():
    """Reload consumer configuration from ConfigMap.

    Useful after a ConfigMap update without pod restart.
    """
    key_store.reload()
    logger.info("config_reloaded", consumers=key_store.consumer_count)
    return {"status": "ok", "consumers": key_store.consumer_count}


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_handler(request: Request, path: str):
    """Main proxy handler — authenticates, rate-limits, and forwards to PostgREST."""
    start_time = time.monotonic()
    full_path = f"/{path}"
    method = request.method

    # Bypass auth for health/metrics/ready paths
    if full_path in BYPASS_PATHS:
        return await _forward_request(request, full_path, "internal", "system")

    # --- Authentication ---
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        AUTH_FAILURES_TOTAL.labels(reason="missing_token").inc()
        REQUESTS_TOTAL.labels(
            consumer="anonymous", schema="unknown", method=method, status="401"
        ).inc()
        return JSONResponse(
            status_code=401,
            content={
                "error": "unauthorized",
                "message": "Missing or invalid Authorization header. Expected: Bearer dk_data_...",
            },
        )

    api_key = auth_header[7:]  # Strip "Bearer "
    consumer = key_store.validate_key(api_key)

    if consumer is None:
        AUTH_FAILURES_TOTAL.labels(reason="invalid_key").inc()
        REQUESTS_TOTAL.labels(
            consumer="anonymous", schema="unknown", method=method, status="401"
        ).inc()
        logger.warning("auth_failed", reason="invalid_key")
        return JSONResponse(
            status_code=401,
            content={
                "error": "unauthorized",
                "message": "Invalid API key.",
            },
        )

    consumer_alias = consumer.alias

    # Track active consumers
    if consumer_alias not in _seen_consumers:
        _seen_consumers.add(consumer_alias)
        ACTIVE_CONSUMERS.set(len(_seen_consumers))

    # --- Schema Access Control ---
    target_schema = extract_schema_from_path(full_path)
    if target_schema is not None:
        if not check_schema_access(
            consumer_alias, consumer.allowed_schemas, target_schema
        ):
            SCHEMA_ACCESS_DENIED_TOTAL.labels(
                consumer=consumer_alias, schema=target_schema
            ).inc()
            REQUESTS_TOTAL.labels(
                consumer=consumer_alias,
                schema=target_schema,
                method=method,
                status="403",
            ).inc()
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": f"Consumer '{consumer_alias}' is not authorized for schema '{target_schema}'.",
                },
            )

    schema_label = target_schema or "default"

    # --- Rate Limiting ---
    allowed, remaining, reset_secs = rate_limiter.check(
        consumer_alias, consumer.rpm_limit
    )
    if not allowed:
        RATE_LIMIT_REJECTIONS_TOTAL.labels(consumer=consumer_alias).inc()
        REQUESTS_TOTAL.labels(
            consumer=consumer_alias,
            schema=schema_label,
            method=method,
            status="429",
        ).inc()
        logger.warning(
            "rate_limit_exceeded",
            consumer=consumer_alias,
            rpm_limit=consumer.rpm_limit,
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit of {consumer.rpm_limit} RPM exceeded.",
            },
            headers={
                "X-RateLimit-Limit": str(consumer.rpm_limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset_secs) + 1),
                "Retry-After": str(int(reset_secs) + 1),
            },
        )

    # --- Proxy to PostgREST ---
    response = await _forward_request(
        request, full_path, consumer_alias, schema_label
    )

    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(consumer.rpm_limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset_secs))
    response.headers["X-Consumer"] = consumer_alias

    # Record duration
    duration = time.monotonic() - start_time
    REQUEST_DURATION_SECONDS.labels(
        consumer=consumer_alias, schema=schema_label
    ).observe(duration)

    return response


async def _forward_request(
    request: Request,
    path: str,
    consumer: str,
    schema: str,
) -> Response:
    """Forward request to PostgREST and record metrics."""
    method = request.method

    # Read body for POST/PUT/PATCH
    body = None
    if method in ("POST", "PUT", "PATCH"):
        body = await request.body()

    # Forward headers (filter out hop-by-hop)
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower()
        not in (
            "host",
            "authorization",
            "content-length",
            "transfer-encoding",
            "connection",
        )
    }

    try:
        upstream_response = await proxy_request(
            method=method,
            path=path,
            headers=headers,
            body=body,
            query_string=str(request.query_params),
        )
    except Exception:
        REQUESTS_TOTAL.labels(
            consumer=consumer, schema=schema, method=method, status="502"
        ).inc()
        return JSONResponse(
            status_code=502,
            content={
                "error": "bad_gateway",
                "message": "PostgREST is unavailable.",
            },
        )

    status_str = str(upstream_response.status_code)
    REQUESTS_TOTAL.labels(
        consumer=consumer, schema=schema, method=method, status=status_str
    ).inc()

    # Track response bytes
    content = upstream_response.content
    RESPONSE_BYTES_TOTAL.labels(consumer=consumer, schema=schema).inc(len(content))

    # Build response with upstream headers
    response_headers = {}
    for key, value in upstream_response.headers.items():
        if key.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
            response_headers[key] = value

    return Response(
        content=content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )
