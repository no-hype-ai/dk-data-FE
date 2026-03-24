"""
API Dependencies

Provides dependency injection for database connections and services.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import os
from typing import Optional, AsyncGenerator
from loguru import logger

try:
    from fastapi import Header as _Header
except ImportError:
    # Fallback for non-FastAPI contexts (tests, CLI scripts)
    def _Header(default=None):  # type: ignore[misc]
        return default

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None
    ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg not installed, async database features disabled")


# Global connection pool
_db_pool: Optional["asyncpg.Pool"] = None


def get_database_url() -> str:
    """Build database URL from environment.

    Required environment variables (set in .env file):
    - DATABASE_URL: Full connection string, OR
    - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    """
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        return db_url

    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_port = os.getenv('POSTGRES_PORT', '5432')
    db_name = os.getenv('POSTGRES_DB', 'dk_data')
    db_user = os.getenv('POSTGRES_USER', 'postgres')
    db_pass = os.getenv('POSTGRES_PASSWORD')

    if not db_pass:
        logger.warning("POSTGRES_PASSWORD not set in environment. Database connection may fail.")
        db_pass = ''

    return f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'


def get_sync_db_url() -> str:
    """Get database URL for synchronous connections (psycopg2).

    This is the same as get_database_url() but provided as a separate function
    for clarity when used with psycopg2 instead of asyncpg.
    """
    return get_database_url()


async def init_db_pool():
    """Initialize database connection pool."""
    global _db_pool

    if not ASYNCPG_AVAILABLE:
        logger.warning("asyncpg not available, skipping pool initialization")
        return

    if _db_pool is None:
        try:
            db_url = get_database_url()
            _db_pool = await asyncpg.create_pool(
                db_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")


async def close_db_pool():
    """Close database connection pool."""
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None
        logger.info("Database connection pool closed")


async def get_db_pool() -> Optional["asyncpg.Pool"]:
    """Get database connection pool (dependency)."""
    global _db_pool
    if _db_pool is None:
        await init_db_pool()
    return _db_pool


async def get_db_connection() -> AsyncGenerator:
    """Get database connection from pool (dependency)."""
    pool = await get_db_pool()
    if pool is None:
        raise Exception("Database pool not available")

    async with pool.acquire() as conn:
        yield conn


async def get_resolver_service():
    """Get IdentifierResolver instance."""
    from ..services.data_platform import IdentifierResolver, FuzzyMatcher

    pool = await get_db_pool()
    if pool is None:
        return None

    fuzzy_matcher = FuzzyMatcher(pool)
    return IdentifierResolver(pool, fuzzy_matcher=fuzzy_matcher)


async def get_queue_service():
    """Get ResolutionQueueService instance."""
    from ..services.data_platform import ResolutionQueueService

    pool = await get_db_pool()
    if pool is None:
        return None
    return ResolutionQueueService(pool)


async def get_current_user() -> dict:
    """
    Get current authenticated user (stub for internal-only API).

    For internal-only molecule API routes, returns a default service user.
    Data-tools routes use get_jwt_user() for real JWT validation.

    Returns:
        dict: User info with id, email, and roles
    """
    # Internal-only API - no authentication required for molecule routes
    # This stub enables route registration without full auth setup
    return {
        "id": "system",
        "email": "system@datakinetic.io",
        "roles": ["admin", "api_user"],
        "role": "api_user",
        "authenticated": True,
    }


def _get_jwt_secret() -> str:
    """Load JWT secret — same key as PostgREST uses."""
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        logger.warning("JWT_SECRET not set — JWT validation will fail")
    return secret


async def get_jwt_user(
    authorization: Optional[str] = _Header(None),
) -> dict:
    """Validate a JWT bearer token using the shared PostgREST JWT secret.

    Accepts the same tokens that PostgREST accepts. The ``role`` claim
    determines the Postgres role (web_anon, analyst, api_user).

    For internal/service calls without a token, falls back to api_user.

    Args:
        authorization: Raw Authorization header value (injected by FastAPI).

    Returns:
        dict with sub, role, raw_token (for forwarding to PostgREST).
    """
    import jwt as pyjwt  # PyJWT

    # Allow unauthenticated internal calls (e.g., from CronJobs within the cluster)
    if not authorization:
        return {
            "sub": "system",
            "role": "api_user",
            "raw_token": None,
            "authenticated": False,
        }

    token = authorization.removeprefix("Bearer ").strip()
    secret = _get_jwt_secret()

    if not secret:
        # No secret configured — pass through as api_user for dev/local
        return {
            "sub": "anonymous",
            "role": "api_user",
            "raw_token": token,
            "authenticated": False,
        }

    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        return {
            "sub": payload.get("sub", "unknown"),
            "role": payload.get("role", "web_anon"),
            "raw_token": token,
            "authenticated": True,
        }
    except pyjwt.ExpiredSignatureError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
