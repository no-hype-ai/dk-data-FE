"""
Pytest configuration and shared fixtures for dk-data tests.
"""

import os
import pytest


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
