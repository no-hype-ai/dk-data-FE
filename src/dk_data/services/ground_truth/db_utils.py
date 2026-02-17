"""
Database Utilities for Ground Truth Service

Provides async database connection helpers that wrap the central
connection pool from dk_data.api.dependencies.

Part of DK Molecule Data Platform
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator:
    """Get an async database connection from the shared pool.

    Usage::

        async with get_db_connection() as conn:
            result = await conn.fetchval("SELECT 1")

    Yields an asyncpg Connection acquired from the global pool managed
    by ``dk_data.api.dependencies``.
    """
    # Late import to avoid circular dependency at module load time
    from dk_data.api.dependencies import get_db_pool

    pool = await get_db_pool()
    if pool is None:
        raise RuntimeError(
            "Database pool is not available. "
            "Ensure init_db_pool() has been called before using ground_truth services."
        )

    async with pool.acquire() as conn:
        yield conn
