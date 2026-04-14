"""JWT minting for the metering proxy hot path.

Feature: 003-metering-jwt-mint (issue #283)

Why this exists: the metering proxy strips the inbound ``Authorization``
header (which contains the raw consumer API key) before forwarding to
PostgREST. Without a replacement, PostgREST falls back to its anonymous
role, which has USAGE on almost none of the exposed schemas, and the
client gets nothing back. This module mints a short-lived HS256 JWT,
signed with the shared ``JWT_SECRET``, that PostgREST recognizes and
uses to switch into the real database role (currently ``api_user``)
via the ``role`` claim.

Design notes:
- **Single role** — every current consumer tier maps to ``api_user``.
  The dict is extensible; a future ``analyst`` role for tiers that need
  write or fuzzy-search paths is a one-line change with no caller
  impact.
- **Per-request mint, 60s TTL** — at ~50μs per HS256 encode (PyJWT on
  modern x86) a JWT cache is more complexity than value. The short TTL
  also means a rotated secret propagates to every in-flight token
  within one minute with no dual-secret machinery.
- **Secret loaded once** — ``load_secret_at_startup`` is called from
  ``app.lifespan`` and caches the secret in a module-level variable.
  Per-request ``os.getenv`` would be a wasted syscall and offers no
  fresh value (the secret comes from a k8s secret mount that only
  changes on pod restart).
- **NOLOG tag compliance** — neither the raw API key, the minted JWT,
  nor the signing secret may appear in any log record. The mint
  function takes the consumer ALIAS (a short opaque label like
  ``"blai"``) as its subject claim, never the key. Logging sites in
  proxy.py and app.py use the alias for correlation.
"""

from __future__ import annotations

import os
import time

import httpx
import jwt

# -----------------------------------------------------------------------------
# Tier → role mapping
# -----------------------------------------------------------------------------

# Every tier currently present in k8s/apps/metering-proxy/base/configmap.yaml
# maps to api_user in v0.1. A unit test asserts every tier in consumers.yaml
# is a key here — adding a new tier to the config without extending this dict
# will fail CI instead of silently returning a 500 at runtime.
TIER_TO_ROLE: dict[str, str] = {
    "unlimited": "api_user",
    "high": "api_user",
    "standard": "api_user",
}

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "metering-proxy"
JWT_TTL_SECONDS = 60
# Mirrors the init-container length check in k8s/apps/postgrest/base/deployment.yaml
# (the busybox init container that validates JWT_SECRET before the pod is healthy).
JWT_SECRET_MIN_LENGTH = 32


class JWTMintError(Exception):
    """Raised on any mint-time failure.

    Bucketed by ``error_type`` for metrics — the string value is used as
    the Prometheus label on ``metering_proxy_jwt_mint_errors_total``.
    """

    def __init__(self, message: str, *, error_type: str) -> None:
        super().__init__(message)
        self.error_type = error_type


# -----------------------------------------------------------------------------
# Module-level cached secret
# -----------------------------------------------------------------------------

# The signing secret is loaded exactly once at container startup (from
# app.lifespan) and cached here for the process lifetime. Never re-read.
_SECRET: str | None = None


def load_secret_at_startup() -> str:
    """Load and validate ``JWT_SECRET`` from the environment.

    Called from ``app.lifespan()`` during container startup. Any failure
    here propagates out so the FastAPI lifespan fails, the container
    exits non-zero, and kubelet restarts it — the readiness probe never
    flips to ready and no traffic is routed to the misconfigured pod.

    Idempotent on repeated calls with the same underlying env value.
    """
    global _SECRET
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise JWTMintError(
            "JWT_SECRET env var is not set", error_type="secret_missing"
        )
    if len(secret) < JWT_SECRET_MIN_LENGTH:
        raise JWTMintError(
            f"JWT_SECRET is {len(secret)} chars; must be at least "
            f"{JWT_SECRET_MIN_LENGTH} for {JWT_ALGORITHM}",
            error_type="secret_too_short",
        )
    _SECRET = secret
    return _SECRET


def mint(*, consumer_alias: str, tier: str) -> str:
    """Mint a short-lived JWT for a validated consumer request.

    Called on the hot path — one HS256 encode per forwarded request,
    ~50μs with the cached secret. The returned string is the raw JWT;
    the caller wraps it in ``f"Bearer {token}"`` before setting the
    ``Authorization`` header on the forwarded request.

    Args:
        consumer_alias: The ``ConsumerConfig.alias`` (e.g. ``"blai"``).
            Becomes the JWT ``sub`` claim. Never the raw API key.
        tier: The ``ConsumerConfig.tier`` (e.g. ``"high"``). Looked up
            in ``TIER_TO_ROLE`` to derive the JWT ``role`` claim.

    Returns:
        The signed JWT as a bearer-ready string (no ``"Bearer "`` prefix).

    Raises:
        JWTMintError: If the secret has not been loaded
            (``error_type="not_loaded"``) or ``tier`` is not in
            ``TIER_TO_ROLE`` (``error_type="unknown_tier"``).
    """
    if _SECRET is None:
        raise JWTMintError(
            "JWT secret not loaded; did startup run?", error_type="not_loaded"
        )
    role = TIER_TO_ROLE.get(tier)
    if role is None:
        raise JWTMintError(
            f"unknown consumer tier: {tier!r}", error_type="unknown_tier"
        )
    now = int(time.time())
    payload = {
        "sub": consumer_alias,
        "role": role,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, _SECRET, algorithm=JWT_ALGORITHM)


# -----------------------------------------------------------------------------
# Startup self-test
# -----------------------------------------------------------------------------


async def self_test(postgrest_url: str) -> None:
    """Mint a test JWT and verify PostgREST accepts the signature.

    Called from ``app.lifespan()`` after ``load_secret_at_startup()``
    and before the proxy starts accepting traffic. Issues one HTTP GET
    to ``{postgrest_url}/`` (the OpenAPI root — returns 200 without
    touching any table) with the test JWT in the ``Authorization``
    header. Any non-2xx status suggests the proxy and PostgREST see
    different values of ``JWT_SECRET`` — we fail startup so the
    operator fixes the secret before the pod takes traffic.

    We hit ``/`` rather than ``/health`` because PostgREST's /health
    endpoint bypasses JWT verification entirely (see the PostgREST
    docs) — hitting it would give us a green test even with a broken
    secret. The OpenAPI root at ``/`` goes through the JWT layer.

    Args:
        postgrest_url: e.g. ``"http://localhost:3000"``

    Raises:
        JWTMintError: on any failure that suggests a secret mismatch:
            timeout, 401 (secret values differ), or 403 (role claim
            rejected).
    """
    # Use a fabricated alias + the "standard" tier for the self-test —
    # this is a synthetic identity, not a real consumer, and never
    # appears in audit or telemetry.
    token = mint(consumer_alias="self-test", tier="standard")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{postgrest_url}/", headers=headers)
    except httpx.HTTPError as e:
        raise JWTMintError(
            f"self-test could not reach PostgREST at {postgrest_url}: {e}",
            error_type="self_test_transport",
        ) from e
    if response.status_code == 401:
        raise JWTMintError(
            "self-test got 401 from PostgREST — JWT_SECRET mismatch between "
            "metering proxy and PostgREST. Check dk-data-secrets.JWT_SECRET.",
            error_type="self_test_signature",
        )
    if response.status_code == 403:
        raise JWTMintError(
            "self-test got 403 from PostgREST — role claim rejected. "
            "Check that api_user exists and has USAGE on the target schemas.",
            error_type="self_test_role",
        )
    if response.status_code >= 500:
        raise JWTMintError(
            f"self-test got {response.status_code} from PostgREST — "
            "upstream unhealthy at startup.",
            error_type="self_test_upstream",
        )
