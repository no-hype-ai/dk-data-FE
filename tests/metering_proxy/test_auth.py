"""T022 — Metering proxy returns 401 on missing or unknown API keys.

Feature: 002-external-integration-foundation (US-3)

Schema detection uses the first URL path segment (see schemas.py
`extract_schema_from_path`), so requests that don't start with a
known schema prefix target the default schema (`api`). The tests
here use `/mol_silver/molecules` to exercise the schema allowlist
path — behavior-labs-ai has `mol_silver` in its allowlist.
"""

from __future__ import annotations

import pytest


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
