"""T022 — Metering proxy returns 401 on missing or unknown API keys.

Feature: 002-external-integration-foundation (US-3)

Schema detection uses the first URL path segment (see schemas.py
`extract_schema_from_path`), so requests that don't start with a
known schema prefix target the default schema (`api`). The tests
here use `/mol_silver/molecules` to exercise the schema allowlist
path — behavior-labs-ai has `mol_silver` in its allowlist.
"""

from __future__ import annotations

import os

import jwt
import pytest

from dk_data.metering_proxy import jwt_mint


class TestMissingAuth:
    def test_no_authorization_header_returns_401(self, client):
        response = client.get("/mol_silver/molecules")
        assert response.status_code == 401
        body = response.json()
        assert body["error"] == "unauthorized"

    def test_non_bearer_scheme_returns_401(self, client):
        response = client.get(
            "/mol_silver/molecules", headers={"Authorization": "Basic abc=="}
        )
        assert response.status_code == 401

    def test_empty_bearer_returns_401(self, client):
        response = client.get(
            "/mol_silver/molecules", headers={"Authorization": "Bearer "}
        )
        assert response.status_code == 401


class TestUnknownKey:
    def test_invalid_key_returns_401(self, client):
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_unknown_consumer_xyz"},
        )
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"

    def test_typo_in_valid_key_returns_401(self, client):
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_ke"},
        )
        assert response.status_code == 401


class TestValidKey:
    def test_valid_key_for_allowed_schema_returns_200(self, client):
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert response.status_code == 200

    def test_valid_key_sets_consumer_header_in_response(self, client):
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert response.headers.get("x-consumer") == "blai"

    def test_valid_key_sets_rate_limit_headers(self, client):
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers


class TestBypassPaths:
    @pytest.mark.parametrize("path", ["/health", "/ready", "/metrics"])
    def test_bypass_paths_need_no_auth(self, client, path):
        response = client.get(path)
        assert 200 <= response.status_code < 300


# ---------------------------------------------------------------------------
# T025 — forwarded headers strip raw API key; JWT replaces it
# ---------------------------------------------------------------------------

_TEST_SECRET = "testsecret_abcdefghijklmnopqrstu"


class TestForwardedHeadersStripRawApiKey:
    """T025: the raw consumer API key must never be forwarded to PostgREST.

    Wave 2A (proxy.py / app.py) injects a minted JWT as the replacement
    Authorization header. Until that change lands, the assertion on JWT
    presence is conditional so the test still validates key-stripping.
    """

    def test_forwarded_headers_strip_raw_api_key(self, monkeypatch, patched_app):
        """Raw API key must not appear in any forwarded header value."""
        from fastapi.testclient import TestClient
        from dk_data.metering_proxy import app as app_module

        # Set up JWT secret so minting works when Wave 2A is in place
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(jwt_mint, "_SECRET", None)
        jwt_mint.load_secret_at_startup()

        raw_key = "dk_data_blai_test_key"
        captured: dict = {}

        async def capturing_proxy_request(**kwargs):
            captured["headers"] = dict(kwargs.get("headers", {}))

            class _FakeResp:
                status_code = 200
                content = b'[{"ok":true}]'
                headers = {"content-type": "application/json"}

            return _FakeResp()

        monkeypatch.setattr(app_module, "proxy_request", capturing_proxy_request)

        client = TestClient(patched_app)
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": f"Bearer {raw_key}"},
        )

        assert response.status_code == 200
        assert captured, "proxy_request was never called"

        forwarded_headers = captured["headers"]

        # Assert raw key absent from all header values
        for value in forwarded_headers.values():
            assert raw_key not in value, (
                f"Raw API key found in forwarded header value: {value!r}"
            )

        # Assert raw key absent from any Authorization header value
        auth_val = forwarded_headers.get("authorization", "")
        assert raw_key not in auth_val, (
            f"Raw API key found in forwarded Authorization header: {auth_val!r}"
        )

        # Wave 2A: if Authorization header was injected, verify it is a valid JWT
        if auth_val.startswith("Bearer "):
            token = auth_val[7:]
            decoded = jwt.decode(
                token,
                _TEST_SECRET,
                algorithms=["HS256"],
                options={"require": ["sub", "role", "iss"]},
            )
            assert decoded["sub"] == "blai"
            assert decoded["iss"] == "metering-proxy"
