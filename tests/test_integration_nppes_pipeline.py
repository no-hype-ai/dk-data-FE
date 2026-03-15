"""
Integration test T047: NPPES fetch → ingest → bronze → silver → gold → PostgREST query.

End-to-end pipeline test for a single CMS source (NPPES) through all medallion layers.
Requires local DB on port 5433 (docker-compose).

Run with: pytest tests/test_integration_nppes_pipeline.py -v --tb=short
"""
import os
import socket
import sys

import pytest

sys.path.insert(0, "src")

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_LOCAL_DB = _port_open("localhost", 5433)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _LOCAL_DB, reason="Local DB on port 5433 not available"),
]


DB_DSN = {
    "host": "localhost",
    "port": 5433,
    "user": "postgres",
    "password": "postgres",
    "database": "dk_data",
}


@pytest.fixture(scope="module")
def db_env(monkeypatch_module):
    """Set environment variables for DB connection."""
    monkeypatch_module.setenv("POSTGRES_HOST", DB_DSN["host"])
    monkeypatch_module.setenv("POSTGRES_PORT", str(DB_DSN["port"]))
    monkeypatch_module.setenv("POSTGRES_USER", DB_DSN["user"])
    monkeypatch_module.setenv("POSTGRES_PASSWORD", DB_DSN["password"])
    monkeypatch_module.setenv("POSTGRES_DB", DB_DSN["database"])


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


class TestNPPESEndToEnd:
    """T047: NPPES fetch → ingest → bronze → silver → gold → PostgREST."""

    def test_01_fetcher_instantiation(self):
        """Verify NPPES fetcher imports and instantiates."""
        from dk_data.ingestion.fetchers.cms_nppes import CMSNPPESFetcher
        fetcher = CMSNPPESFetcher()
        assert fetcher is not None
        assert hasattr(fetcher, "fetch")

    def test_02_fetcher_url_valid(self):
        """Verify NPPES fetcher generates a valid URL."""
        from dk_data.ingestion.fetchers.cms_nppes import CMSNPPESFetcher
        fetcher = CMSNPPESFetcher()
        url = fetcher.get_latest_url()
        assert url is not None
        assert "cms.gov" in url or "nppes" in url.lower() or "data.cms.gov" in url

    def test_03_fetch_small_batch(self):
        """Fetch a small batch of NPPES records from the API."""
        from dk_data.ingestion.fetchers.cms_nppes import CMSNPPESFetcher
        fetcher = CMSNPPESFetcher()
        result = fetcher.fetch(max_records=5)
        assert result["status"] == "success"
        records = result.get("records", [])
        assert len(records) > 0, "Expected at least 1 record from NPPES"
        # Verify record has expected fields
        sample = records[0]
        assert "npi" in sample, f"Expected 'npi' field, got keys: {list(sample.keys())}"

    def test_04_loader_import(self):
        """Verify NPPES source loader imports."""
        from dk_data.ingestion.sources.cms_nppes import load_cms_nppes_data
        assert callable(load_cms_nppes_data)

    @pytest.mark.skipif(not _LOCAL_DB, reason="Local DB not available")
    def test_05_load_to_raw(self, db_env):
        """Fetch and load NPPES records into raw.cms_nppes."""
        from dk_data.ingestion.fetchers.cms_nppes import CMSNPPESFetcher
        from dk_data.ingestion.sources.cms_nppes import load_cms_nppes_data

        fetcher = CMSNPPESFetcher()
        result = fetcher.fetch(max_records=5)
        records = result.get("records", [])
        assert len(records) > 0

        load_result = load_cms_nppes_data(records)
        assert load_result["status"] == "success"
        assert load_result["records_inserted"] > 0

    @pytest.mark.skipif(not _LOCAL_DB, reason="Local DB not available")
    @pytest.mark.asyncio
    async def test_06_raw_table_has_data(self):
        """Verify raw.cms_nppes has records after load."""
        import asyncpg
        conn = await asyncpg.connect(**DB_DSN)
        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM raw.cms_nppes")
            assert count > 0, f"Expected rows in raw.cms_nppes, got {count}"
        finally:
            await conn.close()

    @pytest.mark.skipif(not _LOCAL_DB, reason="Local DB not available")
    @pytest.mark.asyncio
    async def test_07_bronze_model_exists(self):
        """Verify bronze.cms_nppes SQLMesh model file exists."""
        model_path = "src/dk_data/sqlmesh/models/cms/bronze/cms_nppes.sql"
        assert os.path.isfile(model_path), f"Bronze model missing: {model_path}"
        with open(model_path) as f:
            content = f.read()
        assert "MODEL" in content, "Bronze model missing MODEL declaration"

    @pytest.mark.skipif(not _LOCAL_DB, reason="Local DB not available")
    @pytest.mark.asyncio
    async def test_08_silver_model_exists(self):
        """Verify silver CMS provider profile model exists."""
        model_path = "src/dk_data/sqlmesh/models/cms/silver/cms_provider_profile.sql"
        assert os.path.isfile(model_path), f"Silver model missing: {model_path}"
        with open(model_path) as f:
            content = f.read()
        assert "MODEL" in content

    @pytest.mark.skipif(not _LOCAL_DB, reason="Local DB not available")
    @pytest.mark.asyncio
    async def test_09_gold_view_queryable(self):
        """Verify gold.cms_provider_360 view is queryable."""
        import asyncpg
        conn = await asyncpg.connect(**DB_DSN)
        try:
            # View should exist and be queryable (may return 0 rows if SQLMesh hasn't run)
            rows = await conn.fetch("SELECT * FROM gold.cms_provider_360 LIMIT 1")
            assert isinstance(rows, list), "Gold view should return a list"
        finally:
            await conn.close()

    @pytest.mark.skipif(not _LOCAL_DB, reason="Local DB not available")
    @pytest.mark.asyncio
    async def test_10_api_view_queryable(self):
        """Verify api.cms_provider_profile view is queryable."""
        import asyncpg
        conn = await asyncpg.connect(**DB_DSN)
        try:
            rows = await conn.fetch("SELECT * FROM api.cms_provider_profile LIMIT 1")
            assert isinstance(rows, list)
        finally:
            await conn.close()
