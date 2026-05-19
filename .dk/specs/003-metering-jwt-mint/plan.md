# Implementation Plan — Metering Proxy JWT Minting

**Feature**: `003-metering-jwt-mint`
**Branch**: `feature/003-metering-jwt-mint`
**Active tags**: `[RBAC][SECRT][NOLOG][TESTE][AUDIT][GITOP]`

## Technical Context

| Dimension | Value |
|---|---|
| Language | Python 3.12 (metering proxy, tests, migrations runner) |
| Primary framework | FastAPI (metering proxy), PostgREST 12.2.3 (downstream) |
| JWT library | `PyJWT` (already in `pyproject.toml` via `jwt_service.py`) |
| Database | PostgreSQL 16 via CloudNativePG (`postgres-cluster` in `infra` ns) |
| Cluster deploy | Kustomize + ArgoCD, pod: `postgrest` deployment in `dk-data-prod` (metering-proxy is a sidecar) |
| Secrets | Doppler → k8s secret `dk-data-secrets`, key `JWT_SECRET` |
| Observability | Prometheus metrics from proxy, Grafana dashboards, Loki for logs |
| Performance targets | JWT mint p99 < 1 ms on hot path (SC-003); end-to-end proxy latency p99 unchanged |
| Scale | ~500 rpm per consumer high tier × 4 consumers + unlimited internal |
| Project type | Backend service modification (sidecar container) + SQL migration + infra config |

## Constitution Check

`.dk/memory/constitution.md` does not exist for this project — principles.md is the operative document. Principles check:

- **Simple**: scope is tight — mint + inject + grant + one migration + one env var. No speculative generalization.
- **Complete**: includes the grant migration, the PostgREST config change, the pre-flight guard on migration 218, observability, and doc updates. Not a partial fix.
- **Senior**: the reviewer-critical pieces — `NOLOG` proof, `RBAC` proof, tier-to-role mapping, rollback plan — are all enumerated.

Three-way observability binding (principle #6): the new metric `metering_proxy_jwt_minted_total` (definition) MUST be incremented in `proxy.py` (emission) and appear in a Grafana panel + an alert rule in the same PR (consumption). The `tests/observability/test_metric_coverage.py` check already enforces definition+emission; reviewers enforce consumption.

## Phase 0 — Research

Already-answered questions (see `research.md`):

1. **JWT library** — use `PyJWT` (already in the codebase via `jwt_service.py`; adding a second library is churn).
2. **JWT algorithm** — `HS256` with the shared secret. `RS256` would add key-pair management complexity with no benefit since PostgREST and the metering proxy share the same trust boundary.
3. **PyJWT performance** — HS256 encode with a cached secret is ~50 μs on modern x86. Adding 50 μs to a request that takes 5–30 ms is noise. No caching of the JWT across requests is needed — the TTL cost analysis is in `research.md`.
4. **PostgREST `PGRST_DB_ANON_ROLE` behavior** — setting it to a role with zero grants causes every unauthenticated query to fail with "permission denied" at the table layer. Unsetting it causes startup failure in 12.2.3. Chose the former (a new `dk_data_no_anon` role).
5. **Migration numbering** — next available after feature/002 lands: 228.
6. **Migration ordering** — ArgoCD-driven init jobs run migrations in sorted order; 228 runs before 218 alphabetically but 218 > 228 numerically. Check `src/dk_data/scripts/run_migrations.py` for the actual ordering (numeric prefix → monotonic). If numeric, 218 runs before 228. To fix: either renumber 228 to 218a (bad), or move the pre-flight guard into 218 itself — the latter is what the spec already calls for in FR-017.

## Phase 1 — Design

### Project structure

This feature touches the following areas:

```
src/dk_data/metering_proxy/
├── app.py                   # ← extend: startup secret validation, self-test
├── proxy.py                 # ← modify: mint JWT, inject as Authorization header
├── auth.py                  # (unchanged — consumer validation stays)
├── jwt_mint.py              # ← NEW: tier→role mapping, mint_jwt(), cached secret
└── metrics.py               # ← extend: jwt_minted_total, jwt_mint_errors_total

src/dk_data/sql/migrations/
├── 228_jwt_mint_schema_grants.sql   # ← NEW: api_user grants + dk_data_no_anon role
├── 229_drop_web_anon.sql            # ← RENAMED from 218 so it runs after 228
└── 229_drop_web_anon_rollback.sql   # ← RENAMED from 218_drop_web_anon_rollback.sql

k8s/apps/postgrest/base/
├── configmap.yaml           # ← modify: PGRST_DB_ANON_ROLE=dk_data_no_anon
└── deployment.yaml          # ← modify: JWT_SECRET env on metering-proxy sidecar

grafana/dashboards/
└── dk-data-adapter-telemetry.json   # ← modify: add JWT mint panel

grafana/alerts/
└── dk-data.yaml             # ← modify: add JWT mint success rate alert

tests/metering_proxy/
├── test_jwt_mint.py         # (file exists as stub from feature 002; populate)
├── test_auth.py             # (unchanged — still uses raw keys)
└── conftest.py              # ← modify: stub JWT secret in fixtures

packages/dk-data-client/python/tests/integration/
└── test_live_client.py      # ← update: assert real silver-hub read succeeds

.github/workflows/
└── integration-live.yaml    # ← NEW: manual-trigger live integration test

docs/
├── consumer-onboarding.md         # ← rewrite to match reality
├── runbooks/metering-proxy-401-debug.md  # ← rewrite to match reality
└── runbooks/rollback-web-anon-drop.md    # ← verify still accurate
```

### Core implementation sketch

**`src/dk_data/metering_proxy/jwt_mint.py`** (new, ~80 lines)

```python
"""JWT minting for the metering proxy hot path.

Exactly one role in v0.1: `api_user`. Every consumer tier maps to it.
A second tier (e.g. `analyst` for write paths) can be added later by
extending TIER_TO_ROLE without touching callers.
"""
import os
import time
import jwt
from functools import lru_cache

TIER_TO_ROLE: dict[str, str] = {
    "unlimited": "api_user",
    "high": "api_user",
    "standard": "api_user",
}

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "metering-proxy"
JWT_TTL_SECONDS = 60
JWT_SECRET_MIN_LENGTH = 32  # mirror the init-container check


class JWTMintError(Exception):
    """Raised when the signing secret is missing, too short, or the tier is unknown."""


def _load_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise JWTMintError("JWT_SECRET env var is not set")
    if len(secret) < JWT_SECRET_MIN_LENGTH:
        raise JWTMintError(
            f"JWT_SECRET is {len(secret)} chars; must be at least {JWT_SECRET_MIN_LENGTH}"
        )
    return secret


# Cached across the process lifetime. Never re-read from disk per request.
_SECRET: str | None = None


def load_secret_at_startup() -> str:
    """Called from app.lifespan() during startup. Raises on misconfiguration so
    the readiness probe stays failed until the operator fixes the secret."""
    global _SECRET
    _SECRET = _load_secret()
    return _SECRET


def mint(*, consumer_alias: str, tier: str) -> str:
    """Mint a short-lived JWT for a validated consumer request.

    Called on the hot path — O(50μs) with cached secret.
    """
    if _SECRET is None:
        raise JWTMintError("JWT secret not loaded; did startup run?")
    role = TIER_TO_ROLE.get(tier)
    if role is None:
        raise JWTMintError(f"unknown consumer tier: {tier!r}")
    now = int(time.time())
    payload = {
        "role": role,
        "sub": consumer_alias,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, _SECRET, algorithm=JWT_ALGORITHM)
```

**`src/dk_data/metering_proxy/proxy.py`** — patch the forward path. Add a `consumer_alias` + `tier` argument and inject the JWT:

```python
# In proxy_request(), replace the header-building block:
proxy_headers = {
    k: v
    for k, v in headers.items()
    if k.lower() not in ("host", "authorization", "content-length")
}
if consumer_alias is not None and tier is not None:
    token = jwt_mint.mint(consumer_alias=consumer_alias, tier=tier)
    proxy_headers["Authorization"] = f"Bearer {token}"
    metrics.JWT_MINTED_TOTAL.labels(tier=tier).inc()
```

The call site in `app.py:proxy_handler` already has `consumer.alias` and `consumer.tier` in scope after `validate_key` succeeds — pass them through.

**`src/dk_data/metering_proxy/app.py`** — extend `lifespan()`:

```python
# In lifespan() startup:
try:
    jwt_mint.load_secret_at_startup()
except JWTMintError as e:
    logger.error("jwt_secret_missing_or_invalid", error=str(e))
    raise  # fail the container so kubernetes restarts it

# Self-test against PostgREST (startup only):
await _self_test_jwt_round_trip()
```

The self-test mints one token, calls `GET /health` via PostgREST (which returns 200 without touching the database), and asserts the response is not 401. Any 401 means the secret mismatches — fail startup, operator fixes Doppler.

### Migration: `228_jwt_mint_schema_grants.sql`

```sql
-- Feature 003-metering-jwt-mint
-- Create dk_data_no_anon (PostgREST's new anon fallback, no grants)
-- and grant api_user the schema access consumers need.
--
-- This migration is idempotent. It uses IF NOT EXISTS, ALTER DEFAULT
-- PRIVILEGES, and GRANT ... IF NOT EXISTS where supported; otherwise
-- wraps in DO blocks that check pg_has_role / has_schema_privilege.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dk_data_no_anon') THEN
        CREATE ROLE dk_data_no_anon NOINHERIT NOLOGIN;
    END IF;
END
$$;

-- api_user schema grants
GRANT USAGE ON SCHEMA
    mol_silver, mol_gold, mol_api,
    hcs_silver, hcs_gold,
    ind_silver, ind_gold,
    hcp_silver, hcp_gold,
    ip_silver, ip_gold,
    mart, scoring
TO api_user;

-- SELECT on every existing table
GRANT SELECT ON ALL TABLES IN SCHEMA mol_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_api TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ind_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ind_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcp_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcp_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ip_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ip_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA scoring TO api_user;

-- ALTER DEFAULT PRIVILEGES so new tables inherit the grant
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_silver GRANT SELECT ON TABLES TO api_user;
-- ... (one per schema)

-- EXECUTE on every resolve_* function (enumerate explicitly)
GRANT EXECUTE ON FUNCTION mol_silver.resolve_molecule(text) TO api_user;
GRANT EXECUTE ON FUNCTION mol_silver.resolve_drug_product(text) TO api_user;
GRANT EXECUTE ON FUNCTION mol_silver.resolve_company(text) TO api_user;
GRANT EXECUTE ON FUNCTION mol_silver.resolve_target(text) TO api_user;
GRANT EXECUTE ON FUNCTION hcs_silver.resolve_provider(text) TO api_user;
GRANT EXECUTE ON FUNCTION hcs_silver.resolve_facility(text) TO api_user;
GRANT EXECUTE ON FUNCTION ind_silver.resolve_condition(text) TO api_user;
GRANT EXECUTE ON FUNCTION hcp_silver.resolve_researcher(text) TO api_user;
GRANT EXECUTE ON FUNCTION ip_silver.resolve_patent(text) TO api_user;
GRANT EXECUTE ON FUNCTION ip_silver.resolve_trademark(text) TO api_user;
```

### Migration rename (218 → 229)

`218_drop_web_anon.sql` and `218_drop_web_anon_rollback.sql` are renamed to `229_drop_web_anon.sql` and `229_drop_web_anon_rollback.sql`. No content change. The file numeric prefix is the only thing that changes, so the runner applies 228 (this feature's schema grants) before 229 (drop web_anon). No pre-flight DO guard is needed — ordering is enforced by filename.

Why a rename instead of a pre-flight guard: a DO guard only works if the prerequisite migration runs BEFORE the guarded migration. The migration runner sorts by numeric prefix and stops on first failure, so if 218 runs first and its guard raises, 228 never runs and the deploy is stuck. Rename is the minimal correct fix. See `research.md:R-009` for full rationale.

### ConfigMap & Deployment patches

`k8s/apps/postgrest/base/configmap.yaml`:
```yaml
PGRST_DB_ANON_ROLE: "dk_data_no_anon"   # was: "web_anon"
```

`k8s/apps/postgrest/base/deployment.yaml` — metering-proxy sidecar env block:
```yaml
- name: JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: dk-data-secrets
      key: JWT_SECRET
```

### Observability

- **Metric definition** — `src/dk_data/metering_proxy/metrics.py`:
  ```python
  JWT_MINTED_TOTAL = Counter(
      "metering_proxy_jwt_minted_total",
      "Number of JWTs minted for forwarded requests, by consumer tier",
      ["tier"],
  )
  JWT_MINT_ERRORS_TOTAL = Counter(
      "metering_proxy_jwt_mint_errors_total",
      "Number of JWT mint failures (should be zero at steady state)",
      ["error_type"],
  )
  ```
- **Emission** — at the injection point in `proxy.py` (above).
- **Consumption** — `grafana/dashboards/dk-data-adapter-telemetry.json` gets a new panel; `grafana/alerts/dk-data.yaml` gets a rule:
  ```yaml
  - alert: MeteringProxyJWTMintSuccessRateLow
    expr: |
      rate(metering_proxy_jwt_minted_total[5m])
        / (rate(metering_proxy_jwt_minted_total[5m])
           + rate(metering_proxy_jwt_mint_errors_total[5m]))
        < 0.999
    for: 5m
    labels: { severity: warning }
  ```

### Integration test workflow

`.github/workflows/integration-live.yaml` — `workflow_dispatch` trigger, runs:
```bash
DK_DATA_BASE_URL=https://data.behaviorlabs.ai \
DK_DATA_API_KEY=${{ secrets.DK_DATA_INTEGRATION_KEY }} \
pytest packages/dk-data-client/python/tests/integration/test_live_client.py -v
```

Operator manually triggers this after every production deploy of feature 003.

## Phase 2 — Test strategy

- **Unit** (`tests/metering_proxy/test_jwt_mint.py`):
  - Mint → decode roundtrip with a dummy 32-char secret produces role=api_user, sub=alias, iss=metering-proxy, exp ≤ iat+60
  - Unknown tier raises JWTMintError
  - Missing JWT_SECRET env raises on `load_secret_at_startup()`
  - Secret shorter than 32 chars raises
  - `mint()` called before `load_secret_at_startup()` raises
  - PyJWT decode with a different secret fails (proves signature is real)
- **Unit** (`tests/metering_proxy/test_auth.py`): existing tests unchanged; add one that asserts the forwarded headers never contain the raw API key
- **Unit** (`tests/metering_proxy/test_schema_allowlist.py`): existing test updated to assert: when the proxy rejects on allowlist, NO JWT is minted (metric counter delta is zero)
- **Integration** (live, manual): `test_live_client.py` calls `molecules.resolve("aspirin")` and asserts a non-empty `fallthrough=False` response (proves the silver hub responded, not the upstream shim)
- **Security regression** (`tests/metering_proxy/test_nolog.py` — new): spy on the structlog processor chain in-process, run a request, assert no log record contains the raw API key, minted JWT, or signing secret. Enforces FR-020 and the `[NOLOG]` tag.

## Phase 3 — Rollout

1. Merge this PR to `main`
2. CI builds image tag `main-<sha>` → promote to `prod-<sha>`
3. ArgoCD syncs `dk-data-staging` first (if the staging overlay is updated)
4. Staging smoke test: manual `curl` with a staging consumer key → 200 from `/mol_silver/molecules`
5. ArgoCD syncs `dk-data-prod`
6. Migration job runs 228 (creates `dk_data_no_anon`, grants `api_user`)
7. Migration job runs 218 (drops `web_anon`; pre-flight guard passes because 228 already created `dk_data_no_anon`)
8. Operator triggers `.github/workflows/integration-live.yaml` → green
9. Operator verifies Grafana panel shows non-zero `metering_proxy_jwt_minted_total`
10. Operator verifies `requests_executed_as_anon_total` is zero
11. Issue #283 closed

## Rollback plan

If the feature breaks production:

1. **Fast rollback**: revert the ConfigMap change (`PGRST_DB_ANON_ROLE: web_anon`) via a single-line git revert + ArgoCD sync. This restores the old broken-but-not-crashing behavior until the root cause is understood. `web_anon` still exists at this point because migration 218 is gated behind 228.
2. **Image rollback**: revert the metering proxy image tag in the prod overlay to the last known good tag. The grant migration stays (it's additive and harmless).
3. **Role removal**: if for some reason the `dk_data_no_anon` role is the problem, rollback SQL:
   ```sql
   DROP ROLE dk_data_no_anon;
   ```
   (combined with the ConfigMap revert in step 1).

No irreversible operations in this feature. The grant migration is additive; the role creation is reversible; the code changes are reversible.

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| JWT secret mismatch between proxy and PostgREST | Low | High (all requests 401) | Startup self-test fails readiness probe |
| Tier not in TIER_TO_ROLE map | Low | Medium (requests 500) | Unit test covers every tier present in consumers.yaml; add CI grep for new tiers |
| Migration 228 grants too wide | Medium | Medium (consumer sees a schema they shouldn't) | Proxy allowlist stays the enforcement point; db grants are just "is this consumer's schema reachable at all" |
| Migration 218 runs before 228 via sort-order bug | Low | High (web_anon gone, PostgREST falls back to non-existent role) | Pre-flight DO block in 218 errors out |
| Raw API key leaks to log through structlog | Low | High (audit violation) | New `test_nolog.py` regression test; `[NOLOG]` tag already active |
| JWT mint adds > 1 ms p99 | Low | Low | Benchmark in unit test; PyJWT HS256 is ~50 μs |
