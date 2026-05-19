"""JWT minting unit tests — Feature 003 (issue #283).

T022: mint() roundtrip — decode and verify all claims.
T023: error cases — unknown tier and unloaded secret.
T024: every tier in consumers.yaml is a key in TIER_TO_ROLE.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
import yaml

from dk_data.metering_proxy import jwt_mint
from dk_data.metering_proxy.jwt_mint import (
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_TTL_SECONDS,
    JWTMintError,
    TIER_TO_ROLE,
    load_secret_at_startup,
    mint,
)

# A deterministic 32-char test secret (never the real secret)
_TEST_SECRET = "testsecret_abcdefghijklmnopqrstu"


@pytest.fixture(autouse=True)
def _reset_secret(monkeypatch):
    """Ensure module-level _SECRET is reset before and after each test."""
    monkeypatch.setattr(jwt_mint, "_SECRET", None)
    yield
    monkeypatch.setattr(jwt_mint, "_SECRET", None)


@pytest.fixture
def loaded_secret(monkeypatch):
    """Set JWT_SECRET env var and call load_secret_at_startup()."""
    monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
    load_secret_at_startup()
    return _TEST_SECRET


# ---------------------------------------------------------------------------
# T022 — mint() roundtrip
# ---------------------------------------------------------------------------


class TestMintRoundtrip:
    def test_mint_roundtrip(self, loaded_secret):
        """Mint a token for blai/high and verify all claims decode correctly."""
        token = mint(consumer_alias="blai", tier="high")

        decoded = jwt.decode(
            token,
            loaded_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "role", "iss", "iat", "exp"]},
        )

        assert decoded["sub"] == "blai"
        assert decoded["role"] == "api_user"
        assert decoded["iss"] == JWT_ISSUER
        assert decoded["exp"] - decoded["iat"] == JWT_TTL_SECONDS
        assert abs(decoded["iat"] - int(time.time())) <= 5


# ---------------------------------------------------------------------------
# T023 — error cases
# ---------------------------------------------------------------------------


class TestMintErrors:
    def test_unknown_tier_raises(self, loaded_secret):
        """mint() with an unknown tier must raise JWTMintError(unknown_tier)."""
        with pytest.raises(JWTMintError) as exc_info:
            mint(consumer_alias="x", tier="nosuchtier")
        assert exc_info.value.error_type == "unknown_tier"

    def test_mint_before_startup_raises(self, monkeypatch):
        """mint() before load_secret_at_startup() must raise JWTMintError(not_loaded)."""
        monkeypatch.setattr(jwt_mint, "_SECRET", None)
        with pytest.raises(JWTMintError) as exc_info:
            mint(consumer_alias="x", tier="high")
        assert exc_info.value.error_type == "not_loaded"


# ---------------------------------------------------------------------------
# T024 — every consumer tier in configmap.yaml is in TIER_TO_ROLE
# ---------------------------------------------------------------------------

# Locate the configmap relative to the repo root — works from any CWD.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIGMAP_PATH = _REPO_ROOT / "k8s/apps/metering-proxy/base/configmap.yaml"


class TestEveryConfiguredTierIsMapped:
    def test_every_configured_tier_is_mapped(self):
        """Regression: every tier used in consumers.yaml must be in TIER_TO_ROLE.

        Adding a new consumer tier without extending TIER_TO_ROLE causes a
        silent runtime 500 on the hot path. This test makes it a CI failure.
        """
        assert _CONFIGMAP_PATH.exists(), (
            f"ConfigMap not found at {_CONFIGMAP_PATH}. "
            "Update the path if the file was moved."
        )

        raw = yaml.safe_load(_CONFIGMAP_PATH.read_text())
        # ConfigMap data.consumers.yaml is a string; parse the inner YAML.
        consumers_yaml_str = raw["data"]["consumers.yaml"]
        consumers_data = yaml.safe_load(consumers_yaml_str)

        consumers = consumers_data.get("consumers", {})
        assert consumers, "No consumers found in configmap.yaml"

        unknown_tiers = []
        for name, cfg in consumers.items():
            tier = cfg.get("tier", "")
            if tier not in TIER_TO_ROLE:
                unknown_tiers.append((name, tier))

        assert not unknown_tiers, (
            f"Consumers with tiers not in TIER_TO_ROLE: {unknown_tiers}. "
            "Add the tier(s) to jwt_mint.TIER_TO_ROLE."
        )


# ---------------------------------------------------------------------------
# T032 — load_secret_at_startup() validation
# ---------------------------------------------------------------------------


class TestLoadSecretAtStartup:
    def test_missing_secret_fails_startup(self, monkeypatch):
        """load_secret_at_startup() without JWT_SECRET must raise JWTMintError(secret_missing)."""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setattr(jwt_mint, "_SECRET", None)
        with pytest.raises(JWTMintError) as exc_info:
            load_secret_at_startup()
        assert exc_info.value.error_type == "secret_missing"

    def test_short_secret_fails_startup(self, monkeypatch):
        """load_secret_at_startup() with a too-short JWT_SECRET must raise JWTMintError(secret_too_short)."""
        monkeypatch.setenv("JWT_SECRET", "tooshort!!!")
        monkeypatch.setattr(jwt_mint, "_SECRET", None)
        with pytest.raises(JWTMintError) as exc_info:
            load_secret_at_startup()
        assert exc_info.value.error_type == "secret_too_short"


# ---------------------------------------------------------------------------
# T033 — self_test() detects secret mismatch
# ---------------------------------------------------------------------------


class TestSelfTest:
    @pytest.mark.asyncio
    async def test_self_test_detects_secret_mismatch(self, monkeypatch):
        """self_test() must raise JWTMintError(self_test_signature) on a 401 response."""
        # Set the cached secret so mint() succeeds inside self_test.
        monkeypatch.setattr(jwt_mint, "_SECRET", _TEST_SECRET)

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(JWTMintError) as exc_info:
                await jwt_mint.self_test("http://localhost:3000")

        assert exc_info.value.error_type == "self_test_signature"
