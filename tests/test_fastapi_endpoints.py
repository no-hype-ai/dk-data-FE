"""FastAPI job-trigger endpoint tests using TestClient.

Tests health endpoint, jobs listing, and trigger endpoint
with mocked database connections.
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Set env vars before importing app (it reads them at import time)
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "dk_data_test")

# The batch api.py uses `from job_runner import ...` (non-relative),
# which only works inside Docker where WORKDIR is /app. Add the batch
# directory to sys.path so the import resolves in test context.
_batch_dir = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "src", "dk_data", "ingestion", "batch"
)
if os.path.isdir(_batch_dir) and _batch_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_batch_dir))


def _make_mock_cursor(rows=None):
    """Create a mock cursor that returns given rows."""
    cursor = MagicMock()
    cursor.fetchall.return_value = rows or []
    cursor.fetchone.return_value = (rows[0] if rows else None)
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


def _make_mock_connection(cursor=None):
    """Create a mock database connection."""
    conn = MagicMock()
    conn.cursor.return_value = cursor or _make_mock_cursor()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


@pytest.fixture
def client():
    """Create a TestClient with mocked database."""
    mock_conn = _make_mock_connection()

    with patch("psycopg2.connect", return_value=mock_conn):
        # Import after patching to ensure mock is used
        from dk_data.ingestion.batch.api import app
        from fastapi.testclient import TestClient

        yield TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_structure(self, client):
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data

    def test_health_status_value(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")


@pytest.mark.skipif(
    not __import__("os").environ.get("POSTGRES_HOST"),
    reason="Jobs endpoint requires a fully-initialized DB with hub tables"
)
class TestJobsEndpoint:
    def test_list_jobs_returns_200(self, client):
        response = client.get("/jobs")
        assert response.status_code == 200

    def test_list_jobs_returns_list(self, client):
        response = client.get("/jobs")
        data = response.json()
        assert isinstance(data, list)


class TestOpenAPISpec:
    def test_openapi_available(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "info" in data
        assert data["info"]["title"] == "DK Data Platform API"
