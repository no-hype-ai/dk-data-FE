"""
API Middleware.

Implements T335: Cache-Control headers and request tracking.
Implements T012: AuditLoggingMiddleware for API request auditing.
"""

import base64
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional

import psycopg2
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from loguru import logger

# Thread pool for async audit writes (avoids blocking the event loop)
_audit_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audit")


class CacheControlMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add Cache-Control headers to API responses.

    Different cache strategies for different endpoint types:
    - Static data (drug info): longer cache
    - Dynamic data (trials): shorter cache
    - User-specific data: no cache
    - Export downloads: no cache
    """

    # Cache duration in seconds by path pattern
    CACHE_RULES: Dict[str, int] = {
        # Long cache (1 hour) - relatively static data
        "/api/v1/drugbank/": 3600,
        "/api/v1/regulatory/": 3600,
        "/api/v1/lifecycle/": 3600,

        # Medium cache (5 minutes) - semi-dynamic data
        "/api/v1/graph/": 300,
        "/api/v1/coverage/": 300,
        "/api/v1/kols/": 300,
        "/api/v1/rwe/": 300,

        # Short cache (1 minute) - frequently changing
        "/api/v1/news/": 60,
        "/api/v1/search/": 60,
        "/api/v1/visualize/": 60,

        # No cache - user-specific or dynamic
        "/api/v1/export/": 0,
        "/api/v1/onboarding/": 0,
        "/api/v1/feedback/": 0,
        "/api/v1/insights/": 0,
    }

    # Paths that should never be cached
    NO_CACHE_PATHS = [
        "/api/v1/export/download/",
        "/api/v1/export/status/",
        "/api/v1/onboarding/",
        "/api/v1/feedback/",
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Skip non-GET requests
        if request.method != "GET":
            response.headers["Cache-Control"] = "no-store"
            return response

        # Skip if response already has Cache-Control
        if "Cache-Control" in response.headers:
            return response

        path = request.url.path

        # Check no-cache paths first
        for no_cache_path in self.NO_CACHE_PATHS:
            if path.startswith(no_cache_path):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                return response

        # Find matching cache rule
        cache_seconds = 0
        for pattern, seconds in self.CACHE_RULES.items():
            if path.startswith(pattern):
                cache_seconds = seconds
                break

        # Set Cache-Control header
        if cache_seconds > 0:
            response.headers["Cache-Control"] = f"public, max-age={cache_seconds}"
            response.headers["Vary"] = "Accept, Accept-Encoding"
        else:
            response.headers["Cache-Control"] = "no-store"

        return response


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request tracking headers.

    Adds:
    - X-Request-ID: Unique request identifier
    - X-Response-Time: Time taken to process request
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or use provided request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store in request state for access in handlers
        request.state.request_id = request_id

        # Track timing
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as e:
            # Log error with request ID
            logger.error(f"Request {request_id} failed: {e}")
            raise

        # Calculate response time
        process_time = time.time() - start_time

        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{process_time:.3f}s"

        # Log request completion
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "response_time_ms": int(process_time * 1000),
            }
        )

        return response


class CORSHeadersMiddleware(BaseHTTPMiddleware):
    """
    Simple CORS middleware for API responses.

    Note: FastAPI's built-in CORSMiddleware is preferred for production.
    This is a lightweight alternative for development.
    """

    def __init__(
        self,
        app: ASGIApp,
        allow_origins: Optional[list] = None,
        allow_methods: Optional[list] = None,
        allow_headers: Optional[list] = None,
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allow_headers = allow_headers or ["*"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Handle preflight
        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        # Add CORS headers
        origin = request.headers.get("Origin", "*")
        if "*" in self.allow_origins or origin in self.allow_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)
        response.headers["Access-Control-Max-Age"] = "86400"

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Only add HSTS in production (when not localhost)
        if request.url.hostname not in ["localhost", "127.0.0.1"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to write API audit trail entries to meta.ops_api_audit_log.

    Feature: 013-observability-governance (US3: Audit Trail)
    Task: T012

    Captures request metadata (method, path, user role, response time) and
    writes audit entries asynchronously via a background thread pool so the
    main request/response cycle is not blocked.

    Skips auditing for /health and /metrics endpoints to avoid noise.
    """

    # Paths excluded from audit logging
    SKIP_PATHS = ("/health", "/metrics")

    def __init__(self, app: ASGIApp, database_url: Optional[str] = None):
        super().__init__(app)
        self.database_url = database_url or os.getenv("DATABASE_URL", "")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip health and metrics endpoints
        if path in self.SKIP_PATHS:
            return await call_next(request)

        start_time = time.time()

        # Collect request metadata before calling next handler
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        method = request.method
        query_params = dict(request.query_params) if request.query_params else None
        ip_address = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or None
        user_agent = request.headers.get("User-Agent")

        # Extract user_role and user_sub from JWT Authorization header
        user_role = None
        user_sub = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[7:]
                # Decode payload without verification (we only need claims for audit)
                parts = token.split(".")
                if len(parts) >= 2:
                    # Pad base64 if needed
                    payload_b64 = parts[1]
                    padding = 4 - len(payload_b64) % 4
                    if padding != 4:
                        payload_b64 += "=" * padding
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    user_role = payload.get("role")
                    user_sub = payload.get("sub")
            except Exception:
                # JWT decode failures are not audit-blocking
                pass

        # Process the request
        try:
            response = await call_next(request)
        except Exception:
            raise

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        status_code = response.status_code

        # Write audit entry asynchronously (fire-and-forget)
        audit_entry = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "query_params": json.dumps(query_params) if query_params else None,
            "user_role": user_role,
            "user_sub": user_sub,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "source": "job-trigger",
        }

        if self.database_url:
            _audit_executor.submit(self._write_audit_entry, audit_entry)

        return response

    def _write_audit_entry(self, entry: dict) -> None:
        """Write a single audit entry to meta.ops_api_audit_log (runs in thread pool)."""
        conn = None
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO meta.ops_api_audit_log
                    (request_id, method, path, query_params, user_role, user_sub,
                     ip_address, user_agent, status_code, response_time_ms, source)
                VALUES
                    (%(request_id)s, %(method)s, %(path)s, %(query_params)s,
                     %(user_role)s, %(user_sub)s, %(ip_address)s::INET,
                     %(user_agent)s, %(status_code)s, %(response_time_ms)s, %(source)s)
                """,
                entry,
            )
            conn.commit()
            cursor.close()
        except Exception as exc:
            logger.warning(f"Audit log write failed: {exc}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


def setup_middleware(app):
    """
    Configure all middleware for the FastAPI application.

    Usage in main.py:
        from .middleware import setup_middleware
        setup_middleware(app)
    """
    # Order matters: outermost middleware runs first

    # Security headers (outermost)
    app.add_middleware(SecurityHeadersMiddleware)

    # Request tracking
    app.add_middleware(RequestTrackingMiddleware)

    # Audit logging (after tracking, before cache control)
    app.add_middleware(AuditLoggingMiddleware)

    # Cache control
    app.add_middleware(CacheControlMiddleware)

    logger.info("API middleware configured")
