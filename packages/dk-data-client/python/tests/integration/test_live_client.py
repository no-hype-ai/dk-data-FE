"""Integration tests for dk-data-client (Python).

These tests assume an ephemeral dk-data-FE stack is running — see
`packages/dk-data-client/tests/integration/fixtures.py`. They are
skipped unless `DK_DATA_INTEGRATION_URL` and `DK_DATA_INTEGRATION_KEY`
are set. CI sets those automatically in the `integration` job.

Run locally:

    DK_DATA_INTEGRATION_URL=http://localhost:3001 \
    DK_DATA_INTEGRATION_KEY=dk_data_test_integration_key \
      pytest tests/integration/ -q
"""

from __future__ import annotations

import os

import pytest

from dk_data_client import DkDataClient
from dk_data_client.errors import DkDataError


INTEGRATION_URL = os.environ.get("DK_DATA_INTEGRATION_URL")
INTEGRATION_KEY = os.environ.get("DK_DATA_INTEGRATION_KEY")

skipif_no_stack = pytest.mark.skipif(
    not (INTEGRATION_URL and INTEGRATION_KEY),
    reason="ephemeral dk-data-FE stack not available (set DK_DATA_INTEGRATION_URL/_KEY)",
)


@pytest.fixture
async def client():
    c = DkDataClient(
        metering_proxy_url=INTEGRATION_URL or "http://localhost:3001",
        api_key=INTEGRATION_KEY or "test",
        fallback_mode="strict",
        cache_backend="none",
        client_name="integration-test",
    )
    c.set_telemetry_enabled(False)
    yield c
    await c.aclose()


@skipif_no_stack
class TestHealthAndCatalog:
    async def test_health_returns_200(self, client):
        result = await client.health()
        assert result is not None

    async def test_catalog_returns_dict(self, client):
        result = await client.catalog()
        assert isinstance(result, dict) or isinstance(result, list)


@skipif_no_stack
class TestMolecules:
    async def test_get_known_molecule(self, client):
        # CHEMBL25 is in the integration fixture (see fixture.sql)
        result = await client.molecules.get("CHEMBL25")
        assert result.get("molecule_id") == "CHEMBL25"
        assert "aspirin" in (result.get("canonical_name") or "").lower()

    async def test_get_unknown_molecule_raises_in_strict(self, client):
        with pytest.raises(DkDataError):
            await client.molecules.get("CHEMBL999999")

    async def test_search_by_name(self, client):
        results = await client.molecules.search("aspirin", limit=5)
        assert isinstance(results, list)
