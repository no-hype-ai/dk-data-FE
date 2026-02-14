"""Database connection utilities with connection pooling.

Feature: 002-production-readiness
Task: T022 - Graceful failure when secrets missing
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')
load_dotenv('.env', override=True)

logger = logging.getLogger(__name__)

# Connection pool singleton
_connection_pool: Optional[pool.ThreadedConnectionPool] = None


class MissingSecretError(Exception):
    """Raised when required secrets are not configured."""
    pass


def _check_required_secrets() -> None:
    """
    Validate that required database secrets are configured.

    Raises:
        MissingSecretError: If required secrets are missing.
    """
    required_secrets = ['POSTGRES_PASSWORD']
    missing = []

    for secret in required_secrets:
        value = os.getenv(secret)
        if not value or value in ('', 'postgres', 'changeme', 'REPLACE_WITH_SECURE_SECRET_IN_PRODUCTION'):
            missing.append(secret)

    if missing:
        error_msg = (
            f"\n{'='*60}\n"
            f"CONFIGURATION ERROR: Missing required secrets\n"
            f"{'='*60}\n"
            f"\nThe following required secrets are not configured:\n"
            f"  - {', '.join(missing)}\n"
            f"\nTo fix this:\n"
            f"\n1. For local development:\n"
            f"   cp .env.example .env\n"
            f"   # Edit .env and set {', '.join(missing)}\n"
            f"\n2. For production (recommended):\n"
            f"   Use Doppler to inject secrets:\n"
            f"   doppler run -- python your_script.py\n"
            f"\n3. For Kubernetes:\n"
            f"   Secrets are managed via DopplerSecret CRD.\n"
            f"   See .gitops/base/secrets/doppler-secret.yaml\n"
            f"\n{'='*60}\n"
        )
        logger.error(error_msg)
        raise MissingSecretError(error_msg)


def get_connection_params() -> dict:
    """
    Get database connection parameters from environment.

    Raises:
        MissingSecretError: If required secrets are not configured.
    """
    _check_required_secrets()

    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5433')),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD'),
        'database': os.getenv('POSTGRES_DB', 'dk_data'),
    }


def init_connection_pool(minconn: int = 1, maxconn: int = 10) -> pool.ThreadedConnectionPool:
    """Initialize the connection pool."""
    global _connection_pool

    if _connection_pool is None:
        params = get_connection_params()
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            **params
        )
        logger.info(f"Connection pool initialized: {params['host']}:{params['port']}/{params['database']}")

    return _connection_pool


def get_connection_pool() -> pool.ThreadedConnectionPool:
    """Get the existing connection pool or create one."""
    global _connection_pool

    if _connection_pool is None:
        init_connection_pool()

    return _connection_pool


def close_connection_pool() -> None:
    """Close all connections in the pool."""
    global _connection_pool

    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Connection pool closed")


@contextmanager
def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager for database connections from the pool.

    Usage:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM raw.cms_medicare_inpatient")
                rows = cur.fetchall()
    """
    pool = get_connection_pool()
    conn = pool.getconn()

    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor(dict_cursor: bool = False) -> Generator[psycopg2.extensions.cursor, None, None]:
    """
    Context manager for database cursors with automatic commit/rollback.

    Args:
        dict_cursor: If True, return rows as dictionaries instead of tuples.

    Usage:
        with get_cursor(dict_cursor=True) as cur:
            cur.execute("SELECT * FROM raw.cms_medicare_inpatient WHERE provider_id = %s", ('123456',))
            row = cur.fetchone()
            print(row['provider_name'])
    """
    with get_connection() as conn:
        cursor_factory = RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)

        try:
            yield cur
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cur.close()


def execute_sql_file(filepath: str) -> None:
    """
    Execute a SQL file against the database.

    Args:
        filepath: Path to the SQL file to execute.
    """
    with open(filepath, 'r') as f:
        sql = f.read()

    with get_cursor() as cur:
        cur.execute(sql)
        logger.info(f"Executed SQL file: {filepath}")


def table_exists(schema: str, table: str) -> bool:
    """Check if a table exists in the database."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            )
        """, (schema, table))
        return cur.fetchone()[0]


def get_table_count(schema: str, table: str) -> int:
    """Get the row count for a table."""
    with get_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
        return cur.fetchone()[0]


def truncate_table(schema: str, table: str) -> None:
    """Truncate a table (use with caution)."""
    with get_cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {schema}.{table} CASCADE")
        logger.info(f"Truncated table: {schema}.{table}")


def upsert_records(
    schema: str,
    table: str,
    records: list[dict],
    conflict_columns: list[str],
    update_columns: list[str]
) -> int:
    """
    Upsert records into a table using INSERT ... ON CONFLICT.

    Args:
        schema: Database schema name.
        table: Table name.
        records: List of dictionaries with column: value pairs.
        conflict_columns: Columns that define uniqueness.
        update_columns: Columns to update on conflict.

    Returns:
        Number of records processed.
    """
    if not records:
        return 0

    columns = list(records[0].keys())
    placeholders = ', '.join(['%s'] * len(columns))
    column_list = ', '.join(columns)
    conflict_list = ', '.join(conflict_columns)
    update_list = ', '.join([f"{col} = EXCLUDED.{col}" for col in update_columns])

    sql = f"""
        INSERT INTO {schema}.{table} ({column_list})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_list})
        DO UPDATE SET {update_list}
    """

    with get_cursor() as cur:
        for record in records:
            values = [record[col] for col in columns]
            cur.execute(sql, values)

    return len(records)
