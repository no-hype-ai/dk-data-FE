"""Operator decision 2026-05-17 (Option 1) — Accept-Profile pass-through.

The metering proxy must authorize against the PostgREST profile header
(`Accept-Profile` on reads, `Content-Profile` on writes) when present,
because PostgREST uses that header to pick the schema it actually serves
from. Authorizing against the URL path segment alone means a bare path
like `/tavr_program_year` falls through to the `api` default and a
consumer entitled to `hcs_gold` (but not `api`) is wrongly denied.

Precedence: explicit profile header > path segment > `api` default.
An unrecognized profile must NOT become the authorization target — a
bogus header cannot widen access, and PostgREST rejects unknown
profiles, so falling back keeps "what we authorize" == "what PostgREST
serves".

Mesh handoff: edwards-meadow → dk-data-FE
`metering-proxy-schema-routing-for-allowed-consumers`.
"""

from __future__ import annotations

from dk_data.metering_proxy.schemas import extract_schema_from_path


class TestExtractSchemaProfilePrecedence:
    """Unit-level precedence rules for extract_schema_from_path."""

    def test_profile_header_overrides_path_segment(self):
        assert (
            extract_schema_from_path("/mol_silver/molecules", "hcs_gold")
            == "hcs_gold"
        )

    def test_bare_path_with_profile_resolves_to_profile_schema(self):
        # The core `em` scenario: GET /tavr_program_year with
        # Accept-Profile: hcs_gold. Without the header this falls
        # through to "api"; with it, it must resolve to hcs_gold.
        assert (
            extract_schema_from_path("/tavr_program_year", "hcs_gold")
            == "hcs_gold"
        )

    def test_no_profile_falls_back_to_path_segment(self):
        assert (
            extract_schema_from_path("/mol_silver/molecules", None)
            == "mol_silver"
        )

    def test_no_profile_no_known_segment_defaults_to_api(self):
        assert extract_schema_from_path("/tavr_program_year", None) == "api"

    def test_unknown_profile_falls_through_to_path(self):
        # A bogus profile must not become the authorization target.
        assert (
            extract_schema_from_path("/mol_silver/molecules", "not_a_schema")
            == "mol_silver"
        )

    def test_unknown_profile_with_bare_path_defaults_to_api(self):
        assert (
            extract_schema_from_path("/tavr_program_year", "not_a_schema")
            == "api"
        )

    def test_empty_profile_treated_as_absent(self):
        assert (
            extract_schema_from_path("/mol_silver/molecules", "") == "mol_silver"
        )

    def test_profile_is_case_insensitive(self):
        # Consistent with the existing path-segment lowercasing.
        assert (
            extract_schema_from_path("/tavr_program_year", "HCS_GOLD")
            == "hcs_gold"
        )

    def test_bypass_path_returns_none_even_with_profile(self):
        assert extract_schema_from_path("/health", "hcs_gold") is None

    def test_default_signature_still_works_without_profile(self):
        # Backwards compatibility: existing call sites pass path only.
        assert extract_schema_from_path("/mol_silver/x") == "mol_silver"


class TestProfileRoutingThroughProxy:
    """End-to-end: the production `em` scenario through the proxy.

    Mirrors k8s/apps/metering-proxy/base/configmap.yaml:102-106 —
    edwards-meadow (alias `em`) is allowed [hcs_silver, hcs_gold, meta]
    but NOT `api`.
    """

    def test_accept_profile_routes_authorized_consumer_to_allowed_schema(
        self, client
    ):
        # Bare path → would resolve to `api` (em not allowed) → 403.
        # With Accept-Profile: hcs_gold → resolves to hcs_gold → 200.
        response = client.get(
            "/tavr_program_year?limit=1",
            headers={
                "Authorization": "Bearer dk_data_em_test_key",
                "Accept-Profile": "hcs_gold",
            },
        )
        assert response.status_code == 200

    def test_bare_path_without_profile_still_denied_for_em(self, client):
        # Regression guard: without the profile header, em hitting a
        # bare path still falls through to `api` and is denied.
        response = client.get(
            "/tavr_program_year?limit=1",
            headers={"Authorization": "Bearer dk_data_em_test_key"},
        )
        assert response.status_code == 403
        assert "api" in response.json()["message"]

    def test_accept_profile_unauthorized_schema_denied_against_profile(
        self, client
    ):
        # blai is allowed mol_* but not hcs_gold. Requesting hcs_gold
        # via Accept-Profile must be denied AGAINST hcs_gold (not api).
        response = client.get(
            "/whatever?limit=1",
            headers={
                "Authorization": "Bearer dk_data_blai_test_key",
                "Accept-Profile": "hcs_gold",
            },
        )
        assert response.status_code == 403
        body = response.json()
        assert "hcs_gold" in body["message"]

    def test_content_profile_honored_for_write(self, client):
        # Writes use Content-Profile, not Accept-Profile.
        response = client.post(
            "/tavr_program_year",
            headers={
                "Authorization": "Bearer dk_data_em_test_key",
                "Content-Profile": "hcs_gold",
            },
            json={},
        )
        assert response.status_code == 200

    def test_accept_profile_ignored_on_write(self, client):
        # On a write, Accept-Profile must NOT grant access — only
        # Content-Profile does (PostgREST convention).
        response = client.post(
            "/tavr_program_year",
            headers={
                "Authorization": "Bearer dk_data_em_test_key",
                "Accept-Profile": "hcs_gold",
            },
            json={},
        )
        assert response.status_code == 403
        assert "api" in response.json()["message"]
