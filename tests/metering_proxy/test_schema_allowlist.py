"""T024 — Metering proxy enforces `allowed_schemas` per consumer.

Feature: 002-external-integration-foundation (US-3)

Schema detection is URL-path-prefix based — see schemas.py
`extract_schema_from_path`. A request to `/mol_silver/molecules`
targets the `mol_silver` schema.
"""

from __future__ import annotations

import pytest


class TestAllowlistEnforcement:
    def test_allowed_schema_returns_200(self, client):
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert response.status_code == 200

    def test_disallowed_schema_returns_403(self, client):
        # behavior-labs-ai is NOT allowed to read `hcs_silver`
        response = client.get(
            "/hcs_silver/providers",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    def test_consumer_id_is_in_error_message(self, client):
        response = client.get(
            "/hcs_silver/providers",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        body = response.json()
        assert "blai" in body["message"]
        assert "hcs_silver" in body["message"]

    def test_different_consumers_have_different_allowlists(self, client):
        # dk-os is allowed api + meta, not mol_silver
        response = client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_dkos_test_key"},
        )
        assert response.status_code == 403

    def test_default_schema_is_api(self, client):
        # A path with no schema prefix falls through to `api`.
        # dk-os has `api` in its allowlist.
        response = client.get(
            "/health_view",
            headers={"Authorization": "Bearer dk_data_dkos_test_key"},
        )
        # dkos has api in allowlist, so 200 — not 403
        assert response.status_code == 200
