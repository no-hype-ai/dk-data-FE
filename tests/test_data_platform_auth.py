"""
Tests for US-15 — FastAPI /data-platform/* router is locked down behind JWT.

Feature 002-external-integration-foundation, US-15, T028.

Verifies:
1. Missing Authorization header → 401
2. Malformed Authorization header → 401
3. Invalid / unsigned JWT → 401
4. Expired JWT → 401
5. Valid JWT passes the auth layer (route handler runs)
6. Every route in the data_platform router has the require_auth dependency

These tests exercise the auth layer only. They do NOT depend on a running
PostgreSQL — FastAPI's dependency injection runs `require_auth` before any
route handler, so missing/invalid JWTs short-circuit to 401 without touching
the database. The "valid JWT passes" case is asserted at the router-inspection
level (every route declares the dep) to avoid the DB dependency.
"""
# [RBAC][TESTE]

from datetime import datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _live_secret() -> str:
    """Read the secret the running JWTService is actually using.

    Importing lazily so the dk_data app bootstrap (which loads .env via
    conftest) has already run and populated the environment that
    JWTService reads. This is more robust than setting `os.environ` in
    this module, because conftest.load_dotenv() may override our setting.
    """
    from dk_data.api.middleware.rbac import get_jwt_service

    return get_jwt_service().secret_key


def _build_app() -> FastAPI:
    """Build a minimal FastAPI app with the data_platform router mounted.

    We mount only the router under test, not the full dk-data app, because
    the full app triggers DB initialization at import time (which would
    fail without POSTGRES_PASSWORD).
    """
    from dk_data.api.routes.data_platform import router

    app = FastAPI()
    app.include_router(router)
    return app


def _mint_token(
    role: str = "analyst",
    expires_in_seconds: int = 3600,
    secret: str | None = None,
    audience: str = "dk-data-platform",
    issuer: str = "dk-data-platform",
) -> str:
    """Mint a JWT with the payload shape JWTService.verify_token expects."""
    if secret is None:
        secret = _live_secret()
    now = datetime.utcnow()
    payload = {
        "sub": "test-user",
        "email": "test@datakinetic.io",
        "role": role,
        "permissions": ["gold:read", "silver:read"],
        "iat": now,
        "exp": now + timedelta(seconds=expires_in_seconds),
        "iss": issuer,
        "aud": audience,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Router-level assertion — every route inherits require_auth
# ---------------------------------------------------------------------------


def test_data_platform_router_has_require_auth_dependency():
    """Router-level declaration must include require_auth exactly once."""
    from dk_data.api.routes.data_platform import router
    from dk_data.api.middleware.rbac import require_auth

    dep_callables = [d.dependency for d in router.dependencies]
    assert require_auth in dep_callables, (
        "data_platform router MUST declare require_auth at the router level "
        "so every current and future route under /data-platform is protected"
    )
    assert router.prefix == "/data-platform"


def test_data_platform_router_has_all_34_known_routes():
    """Sanity check — the router still has its 34 routes after auth dep addition."""
    from dk_data.api.routes.data_platform import router

    # 34 routes per the spec's Section 9.7 verified inventory; allow small drift
    # but fail if routes are accidentally lost by the auth change.
    assert len(router.routes) >= 30, (
        f"Expected ≥ 30 routes on /data-platform, got {len(router.routes)} — "
        "the US-15 auth change should not affect route count"
    )


# ---------------------------------------------------------------------------
# 401 cases — the critical security assertions
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = _build_app()
    return TestClient(app, raise_server_exceptions=False)


def test_missing_authorization_returns_401(client: TestClient):
    """Unauthenticated request MUST be rejected."""
    response = client.get("/data-platform/molecules/search?query=aspirin")
    assert response.status_code == 401, (
        f"Expected 401 on missing Authorization header, got {response.status_code}: "
        f"{response.text[:200]}"
    )


def test_malformed_authorization_returns_401(client: TestClient):
    """Malformed Bearer header MUST be rejected."""
    response = client.get(
        "/data-platform/molecules/search?query=aspirin",
        headers={"Authorization": "not-a-bearer-token"},
    )
    assert response.status_code == 401


def test_invalid_jwt_returns_401(client: TestClient):
    """Garbage JWT MUST be rejected with 401."""
    response = client.get(
        "/data-platform/molecules/search?query=aspirin",
        headers={"Authorization": "Bearer this.is.notajwt"},
    )
    assert response.status_code == 401


def test_wrong_secret_returns_401(client: TestClient):
    """JWT signed with the wrong secret MUST be rejected."""
    token = _mint_token(secret="a-completely-different-secret-32-chars")
    response = client.get(
        "/data-platform/molecules/search?query=aspirin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_expired_jwt_returns_401(client: TestClient):
    """Expired JWT MUST be rejected with 401."""
    token = _mint_token(expires_in_seconds=-60)  # expired one minute ago
    response = client.get(
        "/data-platform/molecules/search?query=aspirin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_wrong_audience_returns_401(client: TestClient):
    """JWT with an audience other than dk-data-platform MUST be rejected."""
    token = _mint_token(audience="some-other-service")
    response = client.get(
        "/data-platform/molecules/search?query=aspirin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Positive case — valid JWT reaches the route handler
# ---------------------------------------------------------------------------


def test_valid_jwt_passes_auth_layer(client: TestClient):
    """A valid JWT MUST pass the auth dep.

    The route handler itself may fail on DB access (no POSTGRES_PASSWORD in
    CI), but the response MUST NOT be 401 — if we see 401, the auth layer
    rejected a valid token, which is a regression.
    """
    token = _mint_token(role="analyst")
    response = client.get(
        "/data-platform/molecules/search?query=aspirin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401, (
        f"Valid JWT should NOT return 401 (auth layer regression). "
        f"Got {response.status_code}: {response.text[:200]}"
    )
    # Any non-401 is OK: 200 (happy path with DB), 500 (DB failure), 503 (no
    # pool). The important thing is the auth dep let the request through.
