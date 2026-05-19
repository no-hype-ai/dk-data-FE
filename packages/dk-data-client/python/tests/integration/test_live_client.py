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

# T026: live JWT-mint smoke test requires the deployed metering proxy.
# Set these env vars to the running stack (metering-proxy URL + consumer key).
# Skipped in normal unit-test runs — only exercised by the manual-trigger
# workflow (see .github/workflows/jwt-mint-smoke.yml, created in T072).
DK_DATA_BASE_URL = os.environ.get("DK_DATA_BASE_URL")
DK_DATA_API_KEY = os.environ.get("DK_DATA_API_KEY")

skipif_no_stack = pytest.mark.skipif(
    not (INTEGRATION_URL and INTEGRATION_KEY),
    reason="ephemeral dk-data-FE stack not available (set DK_DATA_INTEGRATION_URL/_KEY)",
)

skipif_no_live_stack = pytest.mark.skipif(
    not (DK_DATA_BASE_URL and DK_DATA_API_KEY),
    reason="live dk-data stack not available (set DK_DATA_BASE_URL and DK_DATA_API_KEY)",
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
        assert isinstance(result, (dict, list))


@skipif_no_live_stack
class TestJWTMintSmoke:
    """T026: end-to-end smoke test for the JWT minting path.

    Requires ``DK_DATA_BASE_URL`` and ``DK_DATA_API_KEY`` env vars pointing
    at a running metering-proxy stack. Skipped in normal CI unit-test runs —
    only exercised by the manual-trigger workflow (T072).

    The ``"fallthrough": False`` assertion proves that the silver hub
    `mol_silver.resolve_molecule()` responded directly, not the upstream
    fallback shim. A JWT-related failure (wrong secret, missing role grant)
    would surface here as a non-200 HTTP error inside DkDataClient.
    """

    @pytest.fixture
    async def live_client(self):
        from dk_data_client import DkDataClient

        c = DkDataClient(
            metering_proxy_url=DK_DATA_BASE_URL,
            api_key=DK_DATA_API_KEY,
            fallback_mode="strict",
            cache_backend="none",
            client_name="jwt-mint-smoke-test",
        )
        c.set_telemetry_enabled(False)
        yield c
        await c.aclose()

    async def test_molecules_resolve_aspirin_no_fallthrough(self, live_client):
        """molecules.resolve('aspirin') must succeed and not fall through to shim."""
        result = await live_client.molecules.resolve("aspirin")
        # Must not raise — any JWT/auth failure raises DkDataError
        assert result is not None
        # fallthrough: False proves the silver hub answered, not the shim
        assert result.get("fallthrough") is False, (
            f"Expected fallthrough=False (silver hub answered), got: {result!r}"
        )


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
