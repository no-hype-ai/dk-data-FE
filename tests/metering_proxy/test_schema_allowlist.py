"""T024 — Metering proxy enforces `allowed_schemas` per consumer.

Feature: 002-external-integration-foundation (US-3)

Schema detection is URL-path-prefix based — see schemas.py
`extract_schema_from_path`. A request to `/mol_silver/molecules`
targets the `mol_silver` schema.
"""

from __future__ import annotations

from prometheus_client import generate_latest



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


# ---------------------------------------------------------------------------
# T025a — allowlist rejection must not mint a JWT (FR-015)
# ---------------------------------------------------------------------------


class TestAllowlistRejectionsDoNotMintJWT:
    """T025a: schema-denied requests (403) must not increment JWT_MINTED_TOTAL.

    FR-015: the allowlist enforcement layer must reject BEFORE a JWT is
    minted so the unauthorized schema never appears in any JWT claim.
    """

    def test_allowlist_rejection_does_not_mint_jwt(self, client):
        """A 403 response must not increment JWT_MINTED_TOTAL for any tier."""

        def _read_jwt_minted_total() -> float:
            """Sum JWT_MINTED_TOTAL across all tier label-sets."""
            output = generate_latest().decode()
            total = 0.0
            for line in output.splitlines():
                if line.startswith("dk_data_metering_jwt_minted_total{") and not line.startswith("#"):
                    try:
                        total += float(line.split()[-1])
                    except ValueError:
                        pass
            return total

        before = _read_jwt_minted_total()

        response = client.get(
            "/hcs_silver/providers",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )

        after = _read_jwt_minted_total()

        assert response.status_code == 403
        assert after == before, (
            f"JWT_MINTED_TOTAL incremented on a 403: before={before}, after={after}. "
            "The allowlist check must reject before jwt_mint.mint() is called."
        )
