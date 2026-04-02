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


@pytest.fixture(scope="session")
def postgrest_client():
    """Create an httpx client for PostgREST API testing.

    Requires POSTGREST_URL env var (set by CI) or defaults to localhost:3030.
    """
    base_url = os.getenv("POSTGREST_URL", "http://localhost:3030")
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        yield client
