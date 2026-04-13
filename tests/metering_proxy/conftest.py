"""Shared fixtures for metering-proxy tests.

All tests here construct the FastAPI app directly and use
`httpx.AsyncClient(app=...)` or starlette TestClient against it.
No real Postgres is required — the upstream proxy call is patched
out per-test so we test the metering layer in isolation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dk_data.metering_proxy import app as app_module
from dk_data.metering_proxy.auth import ConsumerConfig, ConsumerKeyStore


def _build_test_key_store() -> ConsumerKeyStore:
    """Construct a ConsumerKeyStore pre-populated with deterministic test keys."""
    store = ConsumerKeyStore()
    store._loaded = True
    # rpm_limit is deliberately large here so a test doing many
    # sequential requests does not trip the bucket; the real consumer
    # tiers live in k8s/apps/metering-proxy/base/configmap.yaml.
    test_consumers = {
        "behavior-labs-ai": ConsumerConfig(
            name="behavior-labs-ai",
            alias="blai",
            allowed_schemas=["mol_silver", "mol_gold", "mol_api"],
            rpm_limit=500,
            tier="high",
            api_keys=["dk_data_blai_test_key"],
        ),
        "dk-os": ConsumerConfig(
            name="dk-os",
            alias="dkos",
            allowed_schemas=["api", "meta"],
            rpm_limit=200,
            tier="standard",
            api_keys=["dk_data_dkos_test_key"],
        ),
        # Dedicated unlimited consumer for load-sensitive tests
        "load-test": ConsumerConfig(
            name="load-test",
            alias="load",
            allowed_schemas=["mol_silver", "api"],
            rpm_limit=0,  # 0 = unlimited
            tier="unlimited",
            api_keys=["dk_data_load_test_key"],
        ),
    }
    for consumer in test_consumers.values():
        store._consumers[consumer.alias] = consumer
        for key in consumer.api_keys:
            store._key_to_consumer[key] = consumer.alias
    return store


@pytest.fixture
def patched_app(monkeypatch):
    """Patch the global app_module state for a single test.

    - Replace the key store with a deterministic test one
    - Stub out the upstream proxy so no network call happens
    - Reset rate limiter + audit state between tests
    """
    from dk_data.metering_proxy.rate_limiter import RateLimiter

    monkeypatch.setattr(app_module, "key_store", _build_test_key_store())
    monkeypatch.setattr(app_module, "rate_limiter", RateLimiter())
    monkeypatch.setattr(app_module, "_seen_consumers", set())

    # Stub the upstream proxy to return a deterministic fake response
    class FakeUpstreamResponse:
        def __init__(self, status_code: int = 200, content: bytes = b'[{"ok":true}]', headers: dict[str, str] | None = None) -> None:
            self.status_code = status_code
            self.content = content
            self.headers = headers or {"content-type": "application/json"}

    async def fake_proxy_request(**kwargs: Any) -> FakeUpstreamResponse:
        return FakeUpstreamResponse()

    monkeypatch.setattr(app_module, "proxy_request", fake_proxy_request)
    # Disable async worker for deterministic tests
    app_module.audit_writer._stopped = True
    yield app_module.app
    app_module.audit_writer._stopped = False


@pytest.fixture
def client(patched_app):
    return TestClient(patched_app)
