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


class TestRetryBehavior:
    """Verifies retry-with-backoff logic in _http_call (issue #281).

    The client retries at most once on transient failures:
      * 503 + Retry-After (capped at 5s)
      * 429 + Retry-After (capped at 5s)
      * transport errors (connection reset, timeout) — 0.5s + jitter

    It MUST NOT retry on 401/403/404/410 (semantic / stateful responses)
    or on any other 5xx status. The cap prevents a misbehaving server
    from wedging the caller; beyond one retry the caller owns strategy.
    """

    @respx.mock
    async def test_200_on_first_try_no_retry(self, monkeypatch):
        """Happy path: no retry, no sleep when the first response is 200."""
        route = respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(200, json=[{"molecule_id": "X"}])
        )
        # Fail loudly if anyone reaches asyncio.sleep on the happy path.
        import dk_data_client.client as client_mod

        async def _no_sleep(_: float) -> None:
            raise AssertionError("asyncio.sleep called on the no-retry path")

        monkeypatch.setattr(client_mod.asyncio, "sleep", _no_sleep)
        client = _make_client(fallback_mode="strict")
        result = await client.molecules.get("X")
        assert result == {"molecule_id": "X"}
        assert route.call_count == 1
        await client.aclose()

    @respx.mock
    async def test_503_with_retry_after_retries_then_succeeds(self, monkeypatch):
        """503 + Retry-After → sleep per header, retry once, return 200."""
        slept: list[float] = []

        async def _capture_sleep(seconds: float) -> None:
            slept.append(seconds)

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _capture_sleep)
        route = respx.get("http://test.local/molecules").mock(
            side_effect=[
                httpx.Response(503, headers={"Retry-After": "1"}),
                httpx.Response(200, json=[{"molecule_id": "X"}]),
            ]
        )
        client = _make_client(fallback_mode="strict")
        result = await client.molecules.get("X")
        assert result == {"molecule_id": "X"}
        assert route.call_count == 2
        assert slept == [1.0]
        await client.aclose()

    @respx.mock
    async def test_503_retry_after_caps_at_5_seconds(self, monkeypatch):
        """Retry-After: 10 is capped to 5.0 so a misbehaving server can't
        wedge the caller for longer than the cap."""
        slept: list[float] = []

        async def _capture_sleep(seconds: float) -> None:
            slept.append(seconds)

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _capture_sleep)
        respx.get("http://test.local/molecules").mock(
            side_effect=[
                httpx.Response(503, headers={"Retry-After": "10"}),
                httpx.Response(200, json=[{"molecule_id": "X"}]),
            ]
        )
        client = _make_client(fallback_mode="strict")
        await client.molecules.get("X")
        assert slept == [5.0]
        await client.aclose()

    @respx.mock
    async def test_503_without_retry_after_uses_default_delay(self, monkeypatch):
        """Missing or unparseable Retry-After falls back to a 1s default
        so retry still happens promptly."""
        slept: list[float] = []

        async def _capture_sleep(seconds: float) -> None:
            slept.append(seconds)

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _capture_sleep)
        respx.get("http://test.local/molecules").mock(
            side_effect=[
                httpx.Response(503),  # no Retry-After header
                httpx.Response(200, json=[{"molecule_id": "X"}]),
            ]
        )
        client = _make_client(fallback_mode="strict")
        await client.molecules.get("X")
        assert slept == [1.0]
        await client.aclose()

    @respx.mock
    async def test_429_retries_automatically_before_raising(self, monkeypatch):
        """429 retries once; if the retry also fails, the caller sees the
        usual DkDataRateLimitError — the automatic retry is transparent."""
        slept: list[float] = []

        async def _capture_sleep(seconds: float) -> None:
            slept.append(seconds)

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _capture_sleep)
        route = respx.get("http://test.local/molecules").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "2"}),
                httpx.Response(429, headers={"Retry-After": "2"}),
            ]
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataRateLimitError) as e:
            await client.molecules.get("X")
        assert route.call_count == 2
        assert slept == [2.0]
        # Second 429 surfaces as DkDataRateLimitError with retry_after preserved
        assert e.value.retry_after == 2.0
        await client.aclose()

    @respx.mock
    async def test_429_then_200_succeeds_on_retry(self, monkeypatch):
        """429 → wait → 200 is the happy path for a transient rate-limit."""
        slept: list[float] = []

        async def _capture_sleep(seconds: float) -> None:
            slept.append(seconds)

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _capture_sleep)
        respx.get("http://test.local/molecules").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "1"}),
                httpx.Response(200, json=[{"molecule_id": "X"}]),
            ]
        )
        client = _make_client(fallback_mode="strict")
        result = await client.molecules.get("X")
        assert result == {"molecule_id": "X"}
        assert slept == [1.0]
        await client.aclose()

    @respx.mock
    async def test_transport_error_retried_once_then_succeeds(self, monkeypatch):
        """Connection reset / timeout → back off 0.5-1.0s, retry once."""
        slept: list[float] = []

        async def _capture_sleep(seconds: float) -> None:
            slept.append(seconds)

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _capture_sleep)
        route = respx.get("http://test.local/molecules").mock(
            side_effect=[
                httpx.ConnectError("connection reset"),
                httpx.Response(200, json=[{"molecule_id": "X"}]),
            ]
        )
        client = _make_client(fallback_mode="strict")
        result = await client.molecules.get("X")
        assert result == {"molecule_id": "X"}
        assert route.call_count == 2
        # Jittered backoff lands in [0.5, 1.0).
        assert len(slept) == 1
        assert 0.5 <= slept[0] < 1.0
        await client.aclose()

    @respx.mock
    async def test_transport_error_twice_raises_server_error(self, monkeypatch):
        """Two consecutive transport errors → DkDataServerError with
        status_code=0 so the caller can tell it's a transport failure
        rather than an upstream 5xx."""

        async def _no_sleep(_: float) -> None:
            return

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _no_sleep)
        route = respx.get("http://test.local/molecules").mock(
            side_effect=[
                httpx.ConnectError("connection reset"),
                httpx.ReadTimeout("timeout"),
            ]
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataServerError) as e:
            await client.molecules.get("X")
        assert e.value.status_code == 0
        assert route.call_count == 2
        await client.aclose()

    @respx.mock
    async def test_401_not_retried(self, monkeypatch):
        """401 is a semantic failure (bad JWT) — no retry."""

        async def _no_sleep(_: float) -> None:
            raise AssertionError("should not sleep on 401")

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _no_sleep)
        route = respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(401)
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataAuthError):
            await client.molecules.get("X")
        assert route.call_count == 1
        await client.aclose()

    @respx.mock
    async def test_403_not_retried(self, monkeypatch):
        """403 is a semantic failure (schema denied) — no retry."""

        async def _no_sleep(_: float) -> None:
            raise AssertionError("should not sleep on 403")

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _no_sleep)
        route = respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(403)
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataForbiddenError):
            await client.molecules.get("X")
        assert route.call_count == 1
        await client.aclose()

    @respx.mock
    async def test_404_not_retried(self, monkeypatch):
        """404 is a semantic failure (resource missing) — no retry."""

        async def _no_sleep(_: float) -> None:
            raise AssertionError("should not sleep on 404")

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _no_sleep)
        route = respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(404)
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataNotFoundError):
            await client.molecules.get("X")
        assert route.call_count == 1
        await client.aclose()

    @respx.mock
    async def test_410_not_retried(self, monkeypatch):
        """410 (stale) is a state, not a transient failure — no retry."""

        async def _no_sleep(_: float) -> None:
            raise AssertionError("should not sleep on 410")

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _no_sleep)
        route = respx.get("http://test.local/molecule_profile").mock(
            return_value=httpx.Response(
                410,
                headers={"X-Last-Refreshed-At": "2026-04-01T00:00:00Z"},
            )
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataStaleError):
            await client.molecules.get_profile("X")
        assert route.call_count == 1
        await client.aclose()

    @respx.mock
    async def test_500_not_retried(self, monkeypatch):
        """Only 503 triggers a retry among 5xx codes; 500/502/504 fail
        fast so operators see the real error without the retry masking
        a deeper issue."""

        async def _no_sleep(_: float) -> None:
            raise AssertionError("should not sleep on 500")

        import dk_data_client.client as client_mod

        monkeypatch.setattr(client_mod.asyncio, "sleep", _no_sleep)
        route = respx.get("http://test.local/molecules").mock(
            return_value=httpx.Response(500)
        )
        client = _make_client(fallback_mode="strict")
        with pytest.raises(DkDataServerError) as e:
            await client.molecules.get("X")
        assert e.value.status_code == 500
        assert route.call_count == 1
        await client.aclose()
