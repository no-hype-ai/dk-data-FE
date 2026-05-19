"""
API Dependencies

Provides dependency injection for database connections and services.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import os
from typing import Optional, AsyncGenerator
from loguru import logger

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

    Prefers individual POSTGRES_* variables when POSTGRES_HOST is set, to avoid
    stale DATABASE_URL values (e.g. pointing at old postgres.postgres.svc hostnames).
    Falls back to DATABASE_URL only when POSTGRES_HOST is absent (local dev without
    individual vars set).

    Required environment variables:
    - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
      (preferred — used in all k8s deployments via dk-data-secrets)
    - DATABASE_URL: full connection string fallback for local dev only
    """
    db_host = os.getenv('POSTGRES_HOST')
    if db_host:
        db_port = os.getenv('POSTGRES_PORT', '5432')
        db_name = os.getenv('POSTGRES_DB', 'dk_data')
        db_user = os.getenv('POSTGRES_USER', 'postgres')
        db_pass = os.getenv('POSTGRES_PASSWORD')
        if not db_pass:
            logger.warning("POSTGRES_PASSWORD not set in environment. Database connection may fail.")
            db_pass = ''
        return f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'

    db_url = os.getenv('DATABASE_URL')
    if db_url:
        return db_url

    logger.warning("Neither POSTGRES_HOST nor DATABASE_URL set; using localhost defaults.")
    return 'postgresql://postgres:@localhost:5432/dk_data'


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


# Service factories
async def get_gold_service():
    """Get GoldAggregationService instance."""
    from ..services.data_platform import GoldAggregationService

    pool = await get_db_pool()
    if pool is None:
        return None
    return GoldAggregationService(pool)


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

    In production, this would validate JWT tokens and return user info.
    For internal-only molecule API routes, returns a default service user.

    Returns:
        dict: User info with id, email, and roles
    """
    # Internal-only API - no authentication required for molecule routes
    # This stub enables route registration without full auth setup
    return {
        "id": "system",
        "email": "system@datakinetic.io",
        "roles": ["admin", "api_user"],
        "authenticated": True,
    }
