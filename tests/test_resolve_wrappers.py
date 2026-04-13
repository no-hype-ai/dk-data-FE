"""
Tests for US-5 FastAPI resolve wrapper routes.

Feature 002-external-integration-foundation, US-5, T076.

Verifies:
1. All 7 new resolve wrapper routes are registered on the /data-platform router
2. Each route is protected by the router-level require_auth dependency
3. Missing JWT → 401 (inherited from router-level dep, not per-route)
4. ResolveRequest validates body (name_or_id required, min_length 1)

These tests exercise routing + request validation only. They do NOT exercise
the actual PL/pgSQL resolve functions — those need a live postgres with the
silver hubs materialized, and that's an integration test beyond the scope
of US-5's unit coverage. T074 covers the SQL grants test.
"""
# [RBAC][ZVAL][TESTE]

from datetime import datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


RESOLVE_ROUTES = [
    ("conditions", "/data-platform/conditions/resolve"),
    ("companies", "/data-platform/companies/resolve"),
    ("providers", "/data-platform/providers/resolve"),
    ("facilities", "/data-platform/facilities/resolve"),
    ("researchers", "/data-platform/researchers/resolve"),
    ("patents", "/data-platform/patents/resolve"),
    ("trademarks", "/data-platform/trademarks/resolve"),
]


def _live_secret() -> str:
    from dk_data.api.middleware.rbac import get_jwt_service

    return get_jwt_service().secret_key


def _mint_token(role: str = "analyst") -> str:
    from dk_data.api.middleware.rbac import get_jwt_service

    secret = get_jwt_service().secret_key
    now = datetime.utcnow()
    payload = {
        "sub": "test-user",
        "email": "test@datakinetic.io",
        "role": role,
        "permissions": ["gold:read", "silver:read"],
        "iat": now,
        "exp": now + timedelta(seconds=3600),
        "iss": "dk-data-platform",
        "aud": "dk-data-platform",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from dk_data.api.routes.data_platform import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Routing assertions — every new resolve wrapper is registered
# ---------------------------------------------------------------------------


def test_all_7_resolve_routes_registered():
    """Each of the 7 new wrapper paths must exist as a POST route."""
    from dk_data.api.routes.data_platform import router

    paths = {r.path for r in router.routes}
    for _entity, path in RESOLVE_ROUTES:
        assert path in paths, f"missing route: {path}"


def test_resolve_routes_are_post_only():
    """The wrappers are POST, not GET."""
    from dk_data.api.routes.data_platform import router

    for _entity, path in RESOLVE_ROUTES:
        route = next(r for r in router.routes if r.path == path)
        methods = getattr(route, "methods", set())
        assert "POST" in methods, f"{path} should accept POST; got {methods}"
        assert "GET" not in methods, f"{path} should NOT accept GET; got {methods}"


def test_resolve_routes_tagged_for_openapi():
    """Resolve routes should appear under a 'resolve' tag in OpenAPI for discovery."""
    from dk_data.api.routes.data_platform import router

    for _entity, path in RESOLVE_ROUTES:
        route = next(r for r in router.routes if r.path == path)
        tags = getattr(route, "tags", [])
        # Router default tag is "data-platform"; per-route we added "resolve"
        assert "resolve" in tags, f"{path} tags: {tags} should include 'resolve'"


# ---------------------------------------------------------------------------
# Auth — every new route inherits router-level require_auth (401 on no JWT)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity,path", RESOLVE_ROUTES, ids=[e for e, _ in RESOLVE_ROUTES])
def test_no_auth_returns_401(client: TestClient, entity: str, path: str):
    """Unauthenticated POST to any resolve wrapper MUST return 401."""
    response = client.post(path, json={"name_or_id": "test"})
    assert response.status_code == 401, (
        f"{path} should return 401 on missing auth; got {response.status_code}: "
        f"{response.text[:200]}"
    )


@pytest.mark.parametrize("entity,path", RESOLVE_ROUTES, ids=[e for e, _ in RESOLVE_ROUTES])
def test_invalid_jwt_returns_401(client: TestClient, entity: str, path: str):
    """Invalid JWT MUST be rejected."""
    response = client.post(
        path,
        json={"name_or_id": "test"},
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Request validation — Pydantic ZVAL tag
# ---------------------------------------------------------------------------


def test_missing_name_or_id_returns_422(client: TestClient):
    """Body without name_or_id should fail Pydantic validation → 422.

    Note: auth runs BEFORE body validation in FastAPI dependency ordering,
    so without a token we'd get 401, not 422. Use a valid token to reach
    the body validator.
    """
    token = _mint_token()
    response = client.post(
        "/data-platform/conditions/resolve",
        json={},  # missing name_or_id
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422, (
        f"missing name_or_id should be 422; got {response.status_code}: "
        f"{response.text[:200]}"
    )


def test_empty_name_or_id_returns_422(client: TestClient):
    """Empty name_or_id violates min_length=1 → 422."""
    token = _mint_token()
    response = client.post(
        "/data-platform/companies/resolve",
        json={"name_or_id": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_overlong_name_or_id_returns_422(client: TestClient):
    """name_or_id > 500 chars violates max_length → 422."""
    token = _mint_token()
    response = client.post(
        "/data-platform/providers/resolve",
        json={"name_or_id": "x" * 501},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_hint_is_optional(client: TestClient):
    """Body with only name_or_id (no hint) should pass validation.

    Reaches the resolve function which may fail on DB unavailability,
    but MUST NOT return 422 (validation) or 401 (auth).
    """
    token = _mint_token()
    response = client.post(
        "/data-platform/trademarks/resolve",
        json={"name_or_id": "aspirin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code not in (401, 422), (
        f"valid body should pass auth + validation; got {response.status_code}: "
        f"{response.text[:200]}"
    )
