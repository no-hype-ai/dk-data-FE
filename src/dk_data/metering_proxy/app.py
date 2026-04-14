"""FastAPI metering proxy sidecar for PostgREST.

Runs as a sidecar container in the PostgREST Deployment on port 3001.
Provides consumer authentication, schema-level access control,
per-consumer rate limiting, and Prometheus metrics.

Architecture:
    Consumer -> metering-proxy:3001 -> PostgREST:3000 (localhost)
"""

import os
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from dk_data.metering_proxy import jwt_mint
from dk_data.metering_proxy.audit import AuditWriter
from dk_data.metering_proxy.auth import ConsumerKeyStore
from dk_data.metering_proxy.jwt_mint import JWTMintError
from dk_data.metering_proxy.concurrency import ConsumerConcurrencyGuard
from dk_data.metering_proxy.metrics import (
    ACTIVE_CONSUMERS,
    AUTH_FAILURES_TOTAL,
    IN_FLIGHT_REQUESTS,
    LOAD_SHED_TOTAL,
    RATE_LIMIT_REJECTIONS_TOTAL,
    REQUEST_DURATION_SECONDS,
    REQUESTS_TOTAL,
    RESPONSE_BYTES_TOTAL,
    SCHEMA_ACCESS_DENIED_TOTAL,
)
from dk_data.metering_proxy.proxy import POSTGREST_URL, close_client, proxy_request
from dk_data.metering_proxy.rate_limiter import RateLimiter
from dk_data.metering_proxy.rate_limiter_redis import (
    RedisRateLimiter,
    build_redis_rate_limiter,
)
from dk_data.metering_proxy.schemas import (
    BYPASS_PATHS,
    check_schema_access,
    extract_schema_from_path,
)
from dk_data.observability.logging import setup_logging

logger = structlog.get_logger(__name__)

# Global state
key_store = ConsumerKeyStore()
rate_limiter: RateLimiter | RedisRateLimiter = RateLimiter()
audit_writer = AuditWriter()
concurrency_guard = ConsumerConcurrencyGuard()
_seen_consumers: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    global rate_limiter
    setup_logging(service_name="metering-proxy")
    jwt_mint.load_secret_at_startup()
    await jwt_mint.self_test(POSTGREST_URL)
    logger.info("jwt_self_test_ok")
    key_store.load()

    # Try to upgrade to the Redis-backed rate limiter if the proxy is
    # running with ≥2 replicas (see T024d). Fall back to in-memory on
    # any failure — never block startup on Redis.
    redis_url = os.getenv("METERING_PROXY_REDIS_URL")
    if redis_url:
        redis_limiter = await build_redis_rate_limiter(redis_url)
        if redis_limiter is not None:
            rate_limiter = redis_limiter
            logger.info("rate_limiter_backend", backend="redis", url=redis_url)
        else:
            logger.warning(
                "rate_limiter_redis_unavailable",
                fallback="in-memory",
                url=redis_url,
            )
    else:
        logger.info("rate_limiter_backend", backend="in-memory")

    # Start the async audit writer (T024a/b/b1)
    await audit_writer.start()

    logger.info(
        "metering_proxy_started",
        consumers=key_store.consumer_count,
        audit_sink=audit_writer.sink,
    )
    yield
    await audit_writer.stop()
    if isinstance(rate_limiter, RedisRateLimiter):
        await rate_limiter.close()
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


def _ms(since: float) -> int:
    return int((time.monotonic() - since) * 1000)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_handler(request: Request, path: str):
    """Main proxy handler — authenticates, rate-limits, and forwards to PostgREST."""
    start_time = time.monotonic()
    full_path = f"/{path}"
    method = request.method
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex

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
        audit_writer.emit(
            consumer_id="anonymous",
            method=method,
            path=full_path,
            schema="unknown",
            status_code=401,
            latency_ms=_ms(start_time),
            request_id=request_id,
            extra={"reason": "missing_token"},
        )
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
        audit_writer.emit(
            consumer_id="anonymous",
            method=method,
            path=full_path,
            schema="unknown",
            status_code=401,
            latency_ms=_ms(start_time),
            request_id=request_id,
            extra={"reason": "invalid_key"},
        )
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
            audit_writer.emit(
                consumer_id=consumer_alias,
                method=method,
                path=full_path,
                schema=target_schema,
                status_code=403,
                latency_ms=_ms(start_time),
                request_id=request_id,
                extra={"reason": "schema_denied"},
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": f"Consumer '{consumer_alias}' is not authorized for schema '{target_schema}'.",
                },
            )

    schema_label = target_schema or "default"

    # --- Rate Limiting ---
    # Both in-memory (sync) and Redis-backed (async) limiters land here.
    if isinstance(rate_limiter, RedisRateLimiter):
        allowed, remaining, reset_secs = await rate_limiter.check(
            consumer_alias, consumer.rpm_limit
        )
    else:
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
        audit_writer.emit(
            consumer_id=consumer_alias,
            method=method,
            path=full_path,
            schema=schema_label,
            status_code=429,
            latency_ms=_ms(start_time),
            request_id=request_id,
            extra={"reason": "rate_limited", "rpm_limit": consumer.rpm_limit},
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

    # --- Concurrency guard (load-shedding) ---
    # This is the backstop for cluster protection. If rate-limiting by
    # RPM alone were sufficient, a 500rpm × 10-replica consumer could
    # still hold 50 slow DB connections simultaneously. The semaphore
    # caps in-flight requests per consumer so a single bad consumer
    # cannot monopolize the Postgres connection pool.
    async with concurrency_guard.acquire(
        consumer_alias, consumer.max_in_flight
    ) as acquired:
        if not acquired:
            LOAD_SHED_TOTAL.labels(consumer=consumer_alias).inc()
            REQUESTS_TOTAL.labels(
                consumer=consumer_alias,
                schema=schema_label,
                method=method,
                status="503",
            ).inc()
            logger.warning(
                "load_shed",
                consumer=consumer_alias,
                max_in_flight=consumer.max_in_flight,
                active=concurrency_guard.active_count(consumer_alias),
            )
            audit_writer.emit(
                consumer_id=consumer_alias,
                method=method,
                path=full_path,
                schema=schema_label,
                status_code=503,
                latency_ms=_ms(start_time),
                request_id=request_id,
                extra={"reason": "load_shed", "max_in_flight": consumer.max_in_flight},
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": "service_unavailable",
                    "message": (
                        f"Consumer '{consumer_alias}' has {consumer.max_in_flight} "
                        "concurrent requests in flight. Back off and retry."
                    ),
                },
                headers={
                    "Retry-After": "1",
                    "X-Consumer": consumer_alias,
                    "X-In-Flight": str(concurrency_guard.active_count(consumer_alias)),
                    "X-Max-In-Flight": str(consumer.max_in_flight),
                },
            )

        IN_FLIGHT_REQUESTS.labels(consumer=consumer_alias).set(
            concurrency_guard.active_count(consumer_alias)
        )

        # --- Proxy to PostgREST ---
        try:
            response = await _forward_request(
                request,
                full_path,
                consumer_alias,
                schema_label,
                consumer_alias=consumer.alias,
                tier=consumer.tier,
            )
        except JWTMintError as e:
            logger.error(
                "jwt_mint_failed",
                consumer=consumer.alias,
                error_type=e.error_type,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal",
                    "message": "jwt mint failure",
                },
            )

    # Concurrency guard released; update the gauge
    IN_FLIGHT_REQUESTS.labels(consumer=consumer_alias).set(
        concurrency_guard.active_count(consumer_alias)
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

    audit_writer.emit(
        consumer_id=consumer_alias,
        method=method,
        path=full_path,
        schema=schema_label,
        status_code=response.status_code,
        latency_ms=int(duration * 1000),
        request_id=request_id,
    )

    return response


async def _forward_request(
    request: Request,
    path: str,
    consumer: str,
    schema: str,
    consumer_alias: str | None = None,
    tier: str | None = None,
) -> Response:
    """Forward request to PostgREST and record metrics.

    JWTMintError is intentionally NOT caught here — it propagates up
    to proxy_handler which returns a 500 with a safe error body.
    """
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
            consumer_alias=consumer_alias,
            tier=tier,
        )
    except JWTMintError:
        # Re-raise so proxy_handler can return a 500 with the correct body.
        raise
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
