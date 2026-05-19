"""FR-020 / [NOLOG] regression: no secret, no minted JWT, no raw API key in logs.

Feature: 003-metering-jwt-mint (issue #283)
Tag: [NOLOG] — see .dk/memory/tags.md

Every request through the metering proxy touches three sensitive values:
  1. The raw consumer API key (e.g. dk_data_blai_test_key)
  2. The minted JWT Bearer token (starts with 'Bearer eyJ' when base64-encoded)
  3. The JWT signing secret (JWT_SECRET env var)

None of these must appear as a substring in any log record produced during
request processing. This test enforces FR-020 and the [NOLOG] tag.

The proxy is tested in isolation using the `patched_app` fixture (which stubs
out the upstream proxy_request so no network calls are made) and structlog's
`capture_logs()` context manager for in-process log capture.

If structlog's capture_logs() doesn't capture records from all loggers (e.g.
if a code path uses stdlib logging instead), pytest's `caplog` is used as a
fallback to catch those.
"""

from __future__ import annotations

import logging

import pytest
import structlog.testing
from fastapi.testclient import TestClient

from dk_data.metering_proxy import jwt_mint

# Must match the value in conftest.py test key store
_RAW_API_KEY = "dk_data_blai_test_key"

# Deterministic 32-char test secret — never the real secret
_TEST_SECRET = "testsecret_abcdefghijklmnopqrstu"

# JWT bearer tokens are base64url-encoded JSON; the standard header
# {"alg":"HS256","typ":"JWT"} encodes to eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
# so any minted HS256 JWT will start with "eyJhbGci". The generic JWT prefix "eyJ"
# is enough to catch any JWT variant in a Bearer header.
_JWT_PREFIX = "eyJ"


@pytest.fixture
def nolog_client(monkeypatch, patched_app):
    """Return a TestClient with JWT minting fully wired and the raw secret set.

    Reuses `patched_app` (proxy_request stubbed out) from conftest.py and
    additionally loads the JWT signing secret so requests go through the full
    mint path.
    """
    monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
    monkeypatch.setattr(jwt_mint, "_SECRET", None)
    jwt_mint.load_secret_at_startup()
    yield TestClient(patched_app)
    # Reset the in-process secret cache so other tests start clean
    monkeypatch.setattr(jwt_mint, "_SECRET", None)


def _all_string_values(record: dict) -> list[str]:
    """Extract every string-valued field from a structlog log record dict."""
    return [v for v in record.values() if isinstance(v, str)]


class TestNoLogSecrets:
    """[NOLOG] regression: sensitive values must not appear in any log record."""

    def test_raw_api_key_not_in_structlog_records(self, nolog_client):
        """The raw consumer API key must not appear in any structlog event."""
        with structlog.testing.capture_logs() as captured:
            response = nolog_client.get(
                "/mol_silver/molecules",
                headers={"Authorization": f"Bearer {_RAW_API_KEY}"},
            )
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        violations = [
            record
            for record in captured
            if any(_RAW_API_KEY in s for s in _all_string_values(record))
        ]
        assert not violations, (
            f"Raw API key '{_RAW_API_KEY}' found in {len(violations)} structlog record(s):\n"
            + "\n".join(f"  {r}" for r in violations)
        )

    def test_jwt_bearer_prefix_not_in_structlog_records(self, nolog_client):
        """A minted JWT token (Bearer eyJ...) must not appear in any structlog event."""
        with structlog.testing.capture_logs() as captured:
            response = nolog_client.get(
                "/mol_silver/molecules",
                headers={"Authorization": f"Bearer {_RAW_API_KEY}"},
            )
        assert response.status_code == 200

        violations = [
            record
            for record in captured
            if any(_JWT_PREFIX in s for s in _all_string_values(record))
        ]
        assert not violations, (
            f"JWT bearer prefix '{_JWT_PREFIX}' found in {len(violations)} structlog record(s):\n"
            + "\n".join(f"  {r}" for r in violations)
            + "\n\nA minted JWT token must never be written to logs."
        )

    def test_jwt_secret_not_in_structlog_records(self, nolog_client):
        """The JWT signing secret must not appear in any structlog event."""
        with structlog.testing.capture_logs() as captured:
            response = nolog_client.get(
                "/mol_silver/molecules",
                headers={"Authorization": f"Bearer {_RAW_API_KEY}"},
            )
        assert response.status_code == 200

        violations = [
            record
            for record in captured
            if any(_TEST_SECRET in s for s in _all_string_values(record))
        ]
        assert not violations, (
            f"JWT signing secret found in {len(violations)} structlog record(s):\n"
            + "\n".join(f"  {r}" for r in violations)
            + "\n\nThe JWT_SECRET value must never be written to logs."
        )

    def test_raw_api_key_not_in_stdlib_logs(self, nolog_client, caplog):
        """Fallback: raw API key must not appear in stdlib logging output either.

        Some code paths (third-party libraries, uvicorn access logs) use stdlib
        logging rather than structlog. caplog captures all stdlib logger output.
        """
        with caplog.at_level(logging.DEBUG):
            response = nolog_client.get(
                "/mol_silver/molecules",
                headers={"Authorization": f"Bearer {_RAW_API_KEY}"},
            )
        assert response.status_code == 200

        violations = [
            record.getMessage()
            for record in caplog.records
            if _RAW_API_KEY in record.getMessage()
        ]
        assert not violations, (
            f"Raw API key found in {len(violations)} stdlib log record(s):\n"
            + "\n".join(f"  {m!r}" for m in violations)
        )

    def test_jwt_secret_not_in_stdlib_logs(self, nolog_client, caplog):
        """Fallback: JWT signing secret must not appear in stdlib logging output."""
        with caplog.at_level(logging.DEBUG):
            response = nolog_client.get(
                "/mol_silver/molecules",
                headers={"Authorization": f"Bearer {_RAW_API_KEY}"},
            )
        assert response.status_code == 200

        violations = [
            record.getMessage()
            for record in caplog.records
            if _TEST_SECRET in record.getMessage()
        ]
        assert not violations, (
            f"JWT signing secret found in {len(violations)} stdlib log record(s):\n"
            + "\n".join(f"  {m!r}" for m in violations)
        )
