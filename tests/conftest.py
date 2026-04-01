"""
Pytest configuration and shared fixtures for dk-data tests.
"""

import sys
import types
import os

# ---------------------------------------------------------------------------
# Stub out heavy dependencies that are not installed in the test environment.
# This allows MCP adapter unit tests to run without the full service stack.
# ---------------------------------------------------------------------------
_STUB_MODULES = [
    "aiohttp",
    "redis",
    "redis.asyncio",
    "tenacity",
    "opentelemetry",
    "opentelemetry.trace",
    "opentelemetry.instrumentation",
    "opentelemetry.instrumentation.fastapi",
    "opentelemetry.sdk",
    "opentelemetry.sdk.trace",
    "opentelemetry.exporter",
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "prometheus_client",
    "psycopg2",
    "psycopg2.pool",
    "psycopg2.extras",
    "kubernetes",
    "kubernetes.client",
    "kubernetes.config",
]

for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)
import pytest
import httpx


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
