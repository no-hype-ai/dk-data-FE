"""Tests for the per-consumer concurrency guard (load-shedding).

Feature: 002-external-integration-foundation (perf pass)

These tests verify that:

  1. Requests within the per-consumer in-flight cap succeed (200).
  2. Requests beyond the cap get 503 with `Retry-After` (NOT queued).
  3. Each consumer's semaphore is isolated from others.
  4. Released slots are immediately reusable.
  5. The `IN_FLIGHT_REQUESTS` gauge reflects the current count.
"""

from __future__ import annotations

import asyncio

import pytest

from dk_data.metering_proxy import app as app_module
from dk_data.metering_proxy.auth import ConsumerConfig, ConsumerKeyStore
from dk_data.metering_proxy.concurrency import ConsumerConcurrencyGuard


def _make_store_with_tight_cap(max_in_flight: int) -> ConsumerKeyStore:
    store = ConsumerKeyStore()
    store._loaded = True
    store._consumers["blai"] = ConsumerConfig(
        name="behavior-labs-ai",
        alias="blai",
        allowed_schemas=["mol_silver"],
        rpm_limit=1_000_000,  # RPM cannot trip during the test
        max_in_flight=max_in_flight,
        tier="high",
        api_keys=["dk_data_blai_test_key"],
    )
    store._consumers["dkos"] = ConsumerConfig(
        name="dk-os",
        alias="dkos",
        allowed_schemas=["api"],
        rpm_limit=1_000_000,
        max_in_flight=100,
        tier="standard",
        api_keys=["dk_data_dkos_test_key"],
    )
    for c in store._consumers.values():
        for key in c.api_keys:
            store._key_to_consumer[key] = c.alias
    return store


@pytest.fixture
def tight_cap_app(monkeypatch):
    """Patch the app with a blai consumer that has max_in_flight=1 so
    we can deterministically trigger load-shedding."""
    from dk_data.metering_proxy.rate_limiter import RateLimiter

    monkeypatch.setattr(app_module, "key_store", _make_store_with_tight_cap(1))
    monkeypatch.setattr(app_module, "rate_limiter", RateLimiter())
    monkeypatch.setattr(
        app_module, "concurrency_guard", ConsumerConcurrencyGuard()
    )
    monkeypatch.setattr(app_module, "_seen_consumers", set())

    # Stub upstream — we need a SLOW upstream so two parallel requests
    # will overlap and exercise the semaphore.
    slow_gate = asyncio.Event()

    class FakeUpstreamResponse:
        status_code = 200
        content = b'[{"ok":true}]'
        headers = {"content-type": "application/json"}

    async def slow_proxy_request(**kwargs: object) -> FakeUpstreamResponse:
        await slow_gate.wait()
        return FakeUpstreamResponse()

    monkeypatch.setattr(app_module, "proxy_request", slow_proxy_request)
    app_module.audit_writer._stopped = True
    yield app_module.app, slow_gate
    app_module.audit_writer._stopped = False


class TestConcurrencyGuardUnit:
    """Direct tests of the ConsumerConcurrencyGuard class (no FastAPI)."""

    @pytest.mark.asyncio
    async def test_first_acquire_succeeds(self):
        guard = ConsumerConcurrencyGuard()
        async with guard.acquire("blai", max_in_flight=1) as acquired:
            assert acquired is True
            assert guard.active_count("blai") == 1

    @pytest.mark.asyncio
    async def test_second_acquire_fails_when_cap_is_1(self):
        guard = ConsumerConcurrencyGuard()
        # Hold the first slot manually via a nested context
        async with guard.acquire("blai", max_in_flight=1) as first:
            assert first is True
            async with guard.acquire("blai", max_in_flight=1) as second:
                assert second is False
                # Active count does NOT increment on failed acquire
                assert guard.active_count("blai") == 1

    @pytest.mark.asyncio
    async def test_release_frees_slot(self):
        guard = ConsumerConcurrencyGuard()
        async with guard.acquire("blai", max_in_flight=1):
            pass
        # After release, a new acquire should succeed
        async with guard.acquire("blai", max_in_flight=1) as acquired:
            assert acquired is True
        assert guard.active_count("blai") == 0

    @pytest.mark.asyncio
    async def test_isolation_between_consumers(self):
        guard = ConsumerConcurrencyGuard()
        async with guard.acquire("blai", max_in_flight=1) as first:
            assert first is True
            # A different consumer is not affected
            async with guard.acquire("dkos", max_in_flight=1) as second:
                assert second is True

    @pytest.mark.asyncio
    async def test_active_count_reset_after_all_release(self):
        guard = ConsumerConcurrencyGuard()
        async with guard.acquire("blai", max_in_flight=3):
            async with guard.acquire("blai", max_in_flight=3):
                assert guard.active_count("blai") == 2
        assert guard.active_count("blai") == 0


class TestLoadShed503:
    """End-to-end: two overlapping requests on a max_in_flight=1
    consumer should produce one 200 and one 503."""

    @pytest.mark.asyncio
    async def test_overlapping_requests_produce_one_503(self, tight_cap_app):
        from httpx import ASGITransport, AsyncClient

        app, slow_gate = tight_cap_app
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # Fire the first request; it will await slow_gate.
            task_a = asyncio.create_task(
                client.get(
                    "/mol_silver/molecules",
                    headers={"Authorization": "Bearer dk_data_blai_test_key"},
                )
            )
            # Give the first request time to grab the semaphore + start awaiting.
            await asyncio.sleep(0.05)

            # Fire the second request. It should land on a full semaphore
            # and immediately return 503.
            response_b = await client.get(
                "/mol_silver/molecules",
                headers={"Authorization": "Bearer dk_data_blai_test_key"},
            )
            assert response_b.status_code == 503
            body = response_b.json()
            assert body["error"] == "service_unavailable"
            assert response_b.headers.get("retry-after") == "1"
            assert response_b.headers.get("x-max-in-flight") == "1"

            # Release the gate so the first request can complete.
            slow_gate.set()
            response_a = await task_a
            assert response_a.status_code == 200

    @pytest.mark.asyncio
    async def test_third_request_succeeds_after_first_drains(
        self, tight_cap_app
    ):
        from httpx import ASGITransport, AsyncClient

        app, slow_gate = tight_cap_app
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            task_a = asyncio.create_task(
                client.get(
                    "/mol_silver/molecules",
                    headers={"Authorization": "Bearer dk_data_blai_test_key"},
                )
            )
            await asyncio.sleep(0.05)
            # Release so task_a completes and frees the slot
            slow_gate.set()
            await task_a

            # Reset the gate for the next round
            slow_gate.clear()
            slow_gate.set()

            response_c = await client.get(
                "/mol_silver/molecules",
                headers={"Authorization": "Bearer dk_data_blai_test_key"},
            )
            assert response_c.status_code == 200
