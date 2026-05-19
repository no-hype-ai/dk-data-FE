"""
Pytest configuration and shared fixtures for dk-data tests.
"""

import os
import pytest
import httpx

# Load .env for local dev so JWT_SECRET and POSTGRES_PASSWORD are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require running services)"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security validation tests"
    )


@pytest.fixture(scope="session")
def postgres_connection():
    """Create a PostgreSQL connection for testing."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        database=os.getenv("POSTGRES_DB", "dk_data_test"),
    )
    yield conn
    conn.close()


@pytest.fixture
def db_cursor(postgres_connection):
    """Create a database cursor that auto-rollbacks after each test."""
    cursor = postgres_connection.cursor()
    yield cursor
    postgres_connection.rollback()
    cursor.close()


@pytest.fixture
def ingestion_connection_pool(monkeypatch):
    """Initialize the ingestion connection pool against the test database.

    Patches the global _connection_pool in dk_data.ingestion.utils.database so
    that log_to_meta() and other ingestion helpers connect to the CI test DB
    instead of the production database URL from environment.
    """
    from psycopg2 import pool as pg_pool
    import dk_data.ingestion.utils.database as db_module

    test_pool = pg_pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=5,
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        database=os.getenv("POSTGRES_DB", "dk_data_test"),
    )
    monkeypatch.setattr(db_module, "_connection_pool", test_pool)
    yield test_pool
    test_pool.closeall()
    monkeypatch.setattr(db_module, "_connection_pool", None)


@pytest.fixture(scope="session")
def postgrest_client():
    """Create an httpx client for PostgREST API testing.

    Requires POSTGREST_URL env var (set by CI) or defaults to localhost:3030.
    """
    base_url = os.getenv("POSTGREST_URL", "http://localhost:3030")
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        yield client


# ---------------------------------------------------------------------------
# Feature: 001-silver-medallion-rebuild — T002
# Real CNPG postgres fixtures (no DB mocks — per spec FR requirement and
# the project's test policy from lessons.md)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def cnpg_conn():
    """Session-scoped direct psycopg2 connection to the real test Postgres.

    Targets dk_data_test.  CI sets POSTGRES_HOST/USER/PASSWORD/DB.
    Local dev: run 'docker compose up postgres' or point at a CNPG cluster.

    Does NOT use build_dsn() here because the test DB may not have the full
    FR-022 GUC set applied; we want raw access for schema setup.
    """
    import psycopg2 as pg

    conn = pg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        database=os.getenv("POSTGRES_DB", "dk_data_test"),
        options="-c statement_timeout=60000",
    )
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture
def cnpg_cursor(cnpg_conn):
    """Per-test cursor that rolls back after the test.

    Use this for silver-hub tests that need a real DB but must not leave
    data behind.
    """
    cur = cnpg_conn.cursor()
    yield cur
    cnpg_conn.rollback()
    cur.close()


@pytest.fixture(scope="session")
def prestaged_meta_schema(cnpg_meta_schemas, cnpg_conn):
    """Apply 005-prestaged-hydration's post-migration-229 schema to
    ``meta.transform_runs`` (status text, details jsonb + indexes).

    Depends on ``cnpg_meta_schemas`` for the base table. Idempotent.
    Scoped session-wide so every prestaged test sees the same state.
    """
    cur = cnpg_conn.cursor()
    cur.execute("""
        ALTER TABLE meta.transform_runs
          ADD COLUMN IF NOT EXISTS status  text,
          ADD COLUMN IF NOT EXISTS details jsonb;
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS meta_transform_runs_status_idx
            ON meta.transform_runs (status)
         WHERE status IS NOT NULL
           AND status <> 'legacy';
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS meta_transform_runs_run_label_idx
            ON meta.transform_runs ((details ->> 'run_label'))
         WHERE details ? 'run_label';
    """)
    cnpg_conn.commit()
    cur.close()
    yield


@pytest.fixture(scope="session")
def cnpg_meta_schemas(cnpg_conn):
    """Ensure meta.* tables used by T016 / T017 exist in the test DB.

    Idempotent — runs once per test session.  Mirrors the production
    migrations 001–003a without needing a full migration runner.
    """
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS meta;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta.job_locks (
            name       text        PRIMARY KEY,
            locked_by  text        NOT NULL,
            locked_at  timestamptz DEFAULT NOW(),
            expires_at timestamptz NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta.refresh_state (
            procedure_name       text        PRIMARY KEY,
            last_chunk_position  text        NOT NULL,
            last_commit_at       timestamptz DEFAULT NOW(),
            status               text        DEFAULT 'in_progress'
                CHECK (status IN ('in_progress', 'completed', 'failed'))
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta.linkage_conflicts (
            conflict_id      bigserial    PRIMARY KEY,
            detected_at      timestamptz  DEFAULT NOW(),
            source           text         NOT NULL,
            identifier       text         NOT NULL,
            existing_hub_id  bigint       NOT NULL,
            new_hub_id       bigint       NOT NULL,
            procedure_name   text         NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta.transform_runs (
            run_id         bigserial    PRIMARY KEY,
            procedure_name text         NOT NULL,
            chunk_position text         NOT NULL,
            started_at     timestamptz  NOT NULL,
            ended_at       timestamptz  NOT NULL,
            rows_processed bigint       NOT NULL,
            wal_bytes      bigint       NOT NULL
        );
    """)
    cnpg_conn.commit()
    cur.close()
    yield
