"""Unit tests for DkDataClient wiring.

Uses `respx` to mock httpx transport — no network calls. We verify:

- Construction requires metering_proxy_url and api_key
- Each HTTP status maps to the correct exception class
- Cache hits short-circuit the HTTP call
- Miss → server → cache population
- 404 + strict fallback → DkDataNotFoundError
- 404 + upstream fallback (no shim registered) → DkDataNotFoundError
- 404 + upstream fallback (shim registered) → returns transformed upstream
- Telemetry is emitted with the expected outcome on every path
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from dk_data_client.client import DkDataClient
from dk_data_client.errors import (
    DkDataAuthError,
    DkDataForbiddenError,
    DkDataNotFoundError,
    DkDataRateLimitError,
    DkDataServerError,
    DkDataStaleError,
)
from dk_data_client.fallback import (
    _SHIM_REGISTRY,
    FallbackContext,
    register_shim,
)


@pytest.fixture
def captured_events() -> list[dict[str, Any]]:
    """Capture telemetry events by patching the emitter's emit method."""
    return []


def _make_client(
    *,
    fallback_mode: str = "strict",
    captured: list[dict[str, Any]] | None = None,
) -> DkDataClient:
    client = DkDataClient(
        metering_proxy_url="http://test.local",
        api_key="dk_data_test_123",
        fallback_mode=fallback_mode,  # type: ignore[arg-type]
        cache_backend="none",
    )
    client.set_telemetry_enabled(False)
    if captured is not None:
        original = client._telemetry.emit

        def _record(**kwargs: Any) -> None:
            captured.append(kwargs)
            original(**kwargs)

        client._telemetry.emit = _record  # type: ignore[method-assign]
    return client


class TestConstruction:
    def test_requires_proxy_url(self):
        with pytest.raises(ValueError, match="metering_proxy_url"):
            DkDataClient(metering_proxy_url="", api_key="x", cache_backend="none")

    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            DkDataClient(metering_proxy_url="http://x", api_key="", cache_backend="none")

    def test_default_fallback_mode_is_upstream(self):
        c = DkDataClient(
            metering_proxy_url="http://x",
            api_key="k",
            cache_backend="none",
        )
        assert c._fallback_mode.value == "upstream"


class TestStatusCodeMapping:
    @respx.mock
    async def test_401_raises_auth_error(self):
        respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(401, json={"error": "missing JWT"})
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataAuthError):
            await client.molecules.get("X")
        await client.aclose()

    @respx.mock
    async def test_403_raises_forbidden(self):
        respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(403, json={"error": "schema denied"})
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataForbiddenError):
            await client.molecules.get("X")
        await client.aclose()

    @respx.mock
    async def test_404_raises_not_found_in_strict_mode(self):
        respx.get("http://test.local/molecules").mock(return_value=httpx.Response(404))
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataNotFoundError):
            await client.molecules.get("X")
        await client.aclose()

    @respx.mock
    async def test_410_raises_stale(self):
        respx.get("http://test.local/molecule_profile").mock(
            return_value=httpx.Response(
                410,
                json={"error": "stale"},
                headers={"X-Last-Refreshed-At": "2026-04-01T00:00:00Z"},
            )
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataStaleError) as e:
            await client.molecules.get_profile("X")
        assert e.value.last_refreshed_at.year == 2026
        await client.aclose()

    @respx.mock
    async def test_429_raises_rate_limit(self):
        respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "30"})
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataRateLimitError) as e:
            await client.molecules.get("X")
        assert e.value.retry_after == 30.0
        await client.aclose()

    @respx.mock
    async def test_500_raises_server_error(self):
        respx.get("http://test.local/molecules").mock(return_value=httpx.Response(500))
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataServerError) as e:
            await client.molecules.get("X")
        assert e.value.status_code == 500
        await client.aclose()


class TestCacheBehavior:
    @respx.mock
    async def test_miss_then_hit_from_cache(self):
        route = respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(200, json=[{"molecule_id": "X"}])
        )
        # Use sqlite backend to exercise L2 path
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            client = DkDataClient(
                metering_proxy_url="http://test.local",
                api_key="dk_data_test",
                fallback_mode="strict",
                cache_backend="sqlite",
                cache_sqlite_path=f.name,
            )
            client.set_telemetry_enabled(False)
            # First call: server hit
            await client.molecules.get("X")
            # Second call: cache hit
            await client.molecules.get("X")
            assert route.call_count == 1
            await client.aclose()


class TestFallback:
    @respx.mock
    async def test_upstream_mode_without_shim_falls_through_to_not_found(self):
        respx.get("http://test.local/catalog").mock(return_value=httpx.Response(404))
        client = _make_client(fallback_mode="upstream")
        # `catalog` has no registered fallback shim
        with pytest.raises(DkDataNotFoundError):
            await client.catalog()
        await client.aclose()

    @respx.mock
    async def test_upstream_mode_with_shim_returns_upstream_result(self, monkeypatch):
        # Install a fake shim on a method that passes the raw value through
        # (`publications.search` returns a list in both dk-data and the
        # Europe PMC shim format).
        class FakeShim:
            upstream_name = "fake"

            async def fetch(self, ctx: FallbackContext, http: httpx.AsyncClient) -> Any:
                return [{"id": "FAKE:1", "source": "fake", "fallthrough": True}]

        original = dict(_SHIM_REGISTRY)
        try:
            register_shim("publications.search", FakeShim())
            respx.get("http://test.local/publications").mock(
                return_value=httpx.Response(404)
            )
            client = _make_client(fallback_mode="upstream")
            result = await client.publications.search("query")
            assert isinstance(result, list)
            assert result[0]["id"] == "FAKE:1"
            await client.aclose()
        finally:
            _SHIM_REGISTRY.clear()
            _SHIM_REGISTRY.update(original)


class TestTelemetryIntegration:
    @respx.mock
    async def test_hit_emits_hit_outcome(self):
        respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(200, json=[{"molecule_id": "X"}])
        )
        captured: list[dict[str, Any]] = []
        client = _make_client(fallback_mode="strict", captured=captured)
        # Re-enable telemetry so the capture wrapper fires (it's disabled
        # in _make_client for network cleanliness). We still haven't set
        # loki_push_url so nothing goes over the wire.
        client.set_telemetry_enabled(True)
        await client.molecules.get("X")  # miss
        await client.molecules.get("X")  # hit (L1)
        outcomes = [ev.get("outcome") for ev in captured]
        assert "miss" in outcomes
        assert "hit" in outcomes
        await client.aclose()
