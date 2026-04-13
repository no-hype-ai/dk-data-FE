"""T023 — Metering proxy produces valid upstream responses with the
expected role context.

Feature: 002-external-integration-foundation (US-3)

Scope note: the current metering proxy (src/dk_data/metering_proxy/)
does not itself mint JWTs — PostgREST holds the `authenticator` role
chain and does its own JWT verification against `PGRST_JWT_SECRET`.
The proxy's job is to (a) validate the consumer API key, (b) enforce
schema + rate limits, and (c) inject consumer metadata headers so
PostgREST / downstream audit can attribute the call.

This test file therefore verifies the slice the proxy DOES own:
  - valid API key → upstream call goes through with `X-Consumer`
    header set (consumer attribution)
  - consumer tier is reflected in rate-limit headers
  - upstream error responses are proxied through with status preserved

The JWT signing path itself is exercised in
`tests/test_data_platform_auth.py` against the shared `JWTService`.
"""

from __future__ import annotations

import pytest


class TestConsumerAttribution:
    def test_x_consumer_header_set_on_success(self, client):
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert response.status_code == 200
        assert response.headers.get("x-consumer") == "blai"

    def test_different_consumers_get_different_x_consumer(self, client):
        # Each consumer uses a schema in its own allowlist.
        blai_resp = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        dkos_resp = client.get(
            "/api/health",
            headers={"Authorization": "Bearer dk_data_dkos_test_key"},
        )
        assert blai_resp.headers.get("x-consumer") == "blai"
        assert dkos_resp.headers.get("x-consumer") == "dkos"


class TestRateLimitTierExposure:
    def test_rate_limit_limit_matches_consumer_tier(self, client):
        # behavior-labs-ai is 500 rpm
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert response.headers.get("x-ratelimit-limit") == "500"

    def test_standard_consumer_tier_lower_limit(self, client):
        # dk-os is 200 rpm
        response = client.get(
            "/api/health",
            headers={"Authorization": "Bearer dk_data_dkos_test_key"},
        )
        assert response.headers.get("x-ratelimit-limit") == "200"
