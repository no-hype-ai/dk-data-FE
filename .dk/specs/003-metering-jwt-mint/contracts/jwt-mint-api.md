# Contracts — Metering Proxy JWT Minting

No external HTTP API changes. The contract here describes the **internal interface between the metering proxy and PostgREST**, and the **function-level interface** the new `jwt_mint` module exposes to the rest of the proxy.

## Interface 1: Metering proxy → PostgREST

### Before this feature

```
GET /<schema>/<path> HTTP/1.1
Host: postgrest.internal
X-Request-Id: <uuid>
Accept: application/json
```

The `Authorization` header was stripped. PostgREST fell back to `PGRST_DB_ANON_ROLE=web_anon` and queried as that role.

### After this feature

```
GET /<schema>/<path> HTTP/1.1
Host: postgrest.internal
X-Request-Id: <uuid>
Accept: application/json
Authorization: Bearer <jwt>
```

Where `<jwt>` is:

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
.
{
  "sub": "<consumer-alias>",
  "role": "api_user",
  "iss": "metering-proxy",
  "iat": <now-unix>,
  "exp": <now-unix + 60>
}
.
<HMAC-SHA256 signature over base64url(header).base64url(payload) using JWT_SECRET>
```

Constraints:
- `alg` is always `HS256` (PostgREST is configured to accept this algorithm).
- `role` is always a real database role present in `pg_roles` and granted by migration 228 for `api_user`, or a future migration for additional roles.
- `sub` is the consumer's **alias**, never the raw API key.
- `exp - iat` is exactly 60.
- `iss` is always the literal string `metering-proxy`.

### PostgREST configuration changes

| Setting | Before | After |
|---|---|---|
| `PGRST_JWT_SECRET` | (set, sourced from `dk-data-secrets.JWT_SECRET`) | unchanged |
| `PGRST_JWT_ROLE_CLAIM_KEY` | `.role` | unchanged |
| `PGRST_DB_ANON_ROLE` | `web_anon` | `dk_data_no_anon` |

Rationale: keeping `PGRST_JWT_ROLE_CLAIM_KEY=.role` means PostgREST continues to use the top-level `role` claim. No structural change to the claim; only the content changes (it used to be whatever FastAPI set, now it's always `api_user`).

---

## Interface 2: `jwt_mint` module API (Python)

Module path: `src/dk_data/metering_proxy/jwt_mint.py`

### Public surface

```python
TIER_TO_ROLE: dict[str, str]
# Module-level constant. Key: consumer tier. Value: database role name.
# Contract: every tier present in k8s/apps/metering-proxy/base/configmap.yaml
# consumers list MUST be a key in this dict (enforced by unit test).

JWT_ALGORITHM: str  # = "HS256"
JWT_ISSUER: str  # = "metering-proxy"
JWT_TTL_SECONDS: int  # = 60
JWT_SECRET_MIN_LENGTH: int  # = 32


class JWTMintError(Exception):
    """Raised on any mint-time failure: missing secret, short secret,
    unknown tier, or mint-before-startup. Propagated to the proxy
    handler which returns HTTP 500 and increments
    metering_proxy_jwt_mint_errors_total{error_type=<name>}."""


def load_secret_at_startup() -> str:
    """Called from app.lifespan() exactly once during container startup.

    Reads JWT_SECRET from env, validates length, caches the value for
    the process lifetime. Raises JWTMintError on missing or invalid
    secret — the caller is expected to let the exception propagate so
    the container fails readiness.

    Idempotent: calling again is a no-op if already loaded with the
    same value.
    """


def mint(*, consumer_alias: str, tier: str) -> str:
    """Hot-path JWT mint.

    Args:
        consumer_alias: The ConsumerConfig.alias (e.g. "blai").
            Becomes the JWT's `sub` claim.
        tier: The ConsumerConfig.tier (e.g. "high"). Looked up in
            TIER_TO_ROLE to derive the JWT's `role` claim.

    Returns:
        A bearer-ready JWT string (no "Bearer " prefix).

    Raises:
        JWTMintError: If the secret has not been loaded, or if tier
            is not in TIER_TO_ROLE.

    Performance contract: p99 < 100 μs on current CI hardware; the
    function is expected to be called on the hot path of every
    authenticated request.
    """


def self_test(postgrest_url: str) -> None:
    """Mint a test JWT and verify PostgREST accepts the signature.

    Called from app.lifespan() after load_secret_at_startup(), before
    the proxy starts accepting traffic. Issues one HTTP GET to
    postgrest_url/health with the test JWT in the Authorization header.

    Args:
        postgrest_url: e.g. "http://localhost:3000"

    Raises:
        JWTMintError: On any failure that suggests a secret mismatch:
          - Network failure (PostgREST not up yet)
          - 401 from PostgREST (secret values differ)
          - 403 from PostgREST (role claim rejected)
    """
```

### Call site constraints

- `mint()` MUST be called inside `proxy.py:proxy_request()` AFTER the `Authorization: Bearer <api_key>` header has been stripped.
- `mint()` MUST NOT be called before `load_secret_at_startup()`.
- `mint()` MUST NOT be called concurrently from multiple threads without external synchronization (PyJWT is thread-safe but the proxy is single-process async anyway).
- The result of `mint()` MUST be wrapped in `f"Bearer {token}"` by the caller and added to the forwarded headers dict.

---

## Interface 3: Prometheus metrics

New counters exposed at `GET /metrics` on the metering proxy:

### `metering_proxy_jwt_minted_total`

- **Type**: `Counter`
- **Labels**: `tier` (one of: `unlimited`, `high`, `standard`)
- **Meaning**: Number of JWTs minted and injected into forwarded requests.
- **Emission site**: `src/dk_data/metering_proxy/proxy.py`, immediately after the `Authorization: Bearer <jwt>` header is set on the forwarded request.
- **Dashboard panel**: `grafana/dashboards/dk-data-adapter-telemetry.json` — "JWTs minted per second, by tier".
- **Alert rule**: See below.

### `metering_proxy_jwt_mint_errors_total`

- **Type**: `Counter`
- **Labels**: `error_type` (one of: `secret_missing`, `secret_too_short`, `unknown_tier`, `not_loaded`)
- **Meaning**: Number of mint failures. Expected steady-state: zero.
- **Emission site**: `src/dk_data/metering_proxy/proxy.py`, inside the `except JWTMintError` block.
- **Dashboard panel**: "JWT mint errors by type".
- **Alert rule**: See below.

### Alert rule

```yaml
- alert: MeteringProxyJWTMintSuccessRateLow
  expr: |
    rate(metering_proxy_jwt_minted_total[5m])
      / (rate(metering_proxy_jwt_minted_total[5m])
         + rate(metering_proxy_jwt_mint_errors_total[5m]))
      < 0.999
  for: 5m
  labels:
    severity: warning
    team: data-platform
  annotations:
    summary: "Metering proxy JWT mint success rate below 99.9%"
    description: |
      The metering proxy has failed to mint JWTs at a rate above 0.1%
      over the last 5 minutes. Check:
      1. JWT_SECRET env var in the metering-proxy sidecar
      2. Consumer tier values in consumers.yaml vs. TIER_TO_ROLE map
      3. Recent deploys
```

---

## Interface 4: Database migrations

### Migration 228 — `228_jwt_mint_schema_grants.sql`

**Pre-conditions**:
- `api_user` role exists (pre-existing in the cluster).
- Target schemas exist: `mol_silver`, `mol_gold`, `mol_api`, `hcs_silver`, `hcs_gold`, `ind_silver`, `ind_gold`, `hcp_silver`, `hcp_gold`, `ip_silver`, `ip_gold`, `mart`, `scoring`.

**Post-conditions**:
- Role `dk_data_no_anon` exists.
- `api_user` has USAGE on all 13 target schemas.
- `api_user` has SELECT on all existing tables in those schemas.
- Default privileges are set so future tables in those schemas auto-grant SELECT to `api_user`.
- `api_user` has EXECUTE on 10 resolve functions across the hubs.

**Idempotency**: running this migration twice produces the same end state with no errors. `CREATE ROLE IF NOT EXISTS` for the role; `GRANT` statements are inherently idempotent.

### Migration 218 — `218_drop_web_anon.sql` (modified)

**New pre-flight**:
```sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dk_data_no_anon') THEN
        RAISE EXCEPTION
            'Migration 218 (drop web_anon) requires feature 003 '
            '(metering-jwt-mint) to be deployed. Apply migration 228 '
            'which creates dk_data_no_anon, then re-run.';
    END IF;
END
$$;
```

**Behavior**:
- If `dk_data_no_anon` exists → migration proceeds, drops `web_anon`.
- If `dk_data_no_anon` does not exist → migration raises, runner exits non-zero, no drop.

---

## Interface 5: k8s manifests

### `k8s/apps/postgrest/base/configmap.yaml`

```diff
  PGRST_DB_ANON_ROLE: "dk_data_no_anon"   # was: "web_anon"
```

### `k8s/apps/postgrest/base/deployment.yaml`

Add to the `metering-proxy` sidecar container env block:

```yaml
env:
- name: POSTGREST_URL
  value: http://localhost:3000
# ... existing vars ...
- name: JWT_SECRET                 # NEW
  valueFrom:
    secretKeyRef:
      name: dk-data-secrets
      key: JWT_SECRET
```

### `.github/workflows/integration-live.yaml` (new)

```yaml
name: Integration — Live cluster
on:
  workflow_dispatch:
jobs:
  live:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install client package
        run: pip install -e packages/dk-data-client/python
      - name: Run live integration test
        env:
          DK_DATA_BASE_URL: https://data.behaviorlabs.ai
          DK_DATA_API_KEY: ${{ secrets.DK_DATA_INTEGRATION_KEY }}
        run: pytest packages/dk-data-client/python/tests/integration/test_live_client.py -v
```

---

## Out of scope for this contract

- Changes to consumer-facing HTTP status codes (all existing error responses remain unchanged)
- Changes to the rate-limiting, audit-logging, or concurrency-guard interfaces
- Changes to the `dk-data-client` package's public API
- Changes to the PostgREST version or any other infrastructure image
