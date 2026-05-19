# Data Model — Metering Proxy JWT Minting

This feature does not introduce any new persistent schemas, tables, or rows. It introduces:
- One new database **role** (`dk_data_no_anon`)
- A new set of **grants** to the existing role `api_user`
- A short-lived **in-memory JWT** structure

## Database roles

| Role | Type | Creation site | Purpose |
|---|---|---|---|
| `dk_data_no_anon` | `NOINHERIT NOLOGIN` | Migration 228 (this feature) | Replaces `web_anon` as PostgREST's `PGRST_DB_ANON_ROLE`. Has zero grants on any schema, table, or function — every unauthenticated request fails with "permission denied" at the query layer. |
| `api_user` | Existing | Earlier migration (pre-existing) | The SELECT-only database role every authenticated request switches into via a JWT `role` claim. |
| `authenticator` | Existing | Earlier migration (pre-existing) | The role PostgREST uses to connect to the database. Can switch to `dk_data_no_anon`, `api_user`, `analyst`. Not exercised by this feature. |
| `analyst` | Existing | Earlier migration (pre-existing) | Reserved for a future tier with broader access. Not used by this feature. |
| `web_anon` | Existing (pending drop) | Earlier migration | Being dropped by migration 218, guarded by this feature's pre-flight check. |

## Grants added by migration 228

### Schema USAGE grants to `api_user`

| Schema | USAGE | SELECT on tables | DEFAULT PRIVILEGES | EXECUTE on functions |
|---|---|---|---|---|
| `mol_silver` | ✓ | ✓ (all existing) | ✓ (new tables) | `resolve_molecule`, `resolve_drug_product`, `resolve_company`, `resolve_target` |
| `mol_gold` | ✓ | ✓ | ✓ | — |
| `mol_api` | ✓ | ✓ | ✓ | — |
| `hcs_silver` | ✓ | ✓ | ✓ | `resolve_provider`, `resolve_facility` |
| `hcs_gold` | ✓ | ✓ | ✓ | — |
| `ind_silver` | ✓ | ✓ | ✓ | `resolve_condition` |
| `ind_gold` | ✓ | ✓ | ✓ | — |
| `hcp_silver` | ✓ | ✓ | ✓ | `resolve_researcher` |
| `hcp_gold` | ✓ | ✓ | ✓ | — |
| `ip_silver` | ✓ | ✓ | ✓ | `resolve_patent`, `resolve_trademark` |
| `ip_gold` | ✓ | ✓ | ✓ | — |
| `mart` | ✓ | ✓ | ✓ | — |
| `scoring` | ✓ | ✓ | ✓ | — |

### Privileges explicitly NOT granted

- INSERT, UPDATE, DELETE, TRUNCATE on any table
- CREATE on any schema
- DDL on any object
- USAGE on `staging`, `application`, `public`, `agents`, `hcs_agents`, `mol_agents`, `xenon`, `meta` (intentionally off-limits)

## JWT payload (in-memory only)

Lifecycle: minted on the hot path, sent as `Authorization: Bearer <token>`, validated by PostgREST, discarded. Never persisted.

| Claim | Type | Example | Source |
|---|---|---|---|
| `sub` | string | `"blai"` | `ConsumerConfig.alias` |
| `role` | string | `"api_user"` | `TIER_TO_ROLE[consumer.tier]` |
| `iss` | string | `"metering-proxy"` | constant in `jwt_mint.JWT_ISSUER` |
| `iat` | int (unix epoch) | `1745432000` | `int(time.time())` at mint |
| `exp` | int (unix epoch) | `1745432060` | `iat + 60` |

Signed with `HS256` using the shared `JWT_SECRET`. Header is the standard PyJWT default: `{"alg": "HS256", "typ": "JWT"}`.

## Consumer configuration (existing, unchanged)

This feature does NOT modify the shape of `consumers.yaml`. The existing `ConsumerConfig` dataclass (in `src/dk_data/metering_proxy/auth.py`) continues to own:

| Field | Type | Source | Notes |
|---|---|---|---|
| `name` | string | `consumers.yaml` | Full consumer name, e.g. `"behavior-labs-ai"` |
| `alias` | string | `consumers.yaml` | Short alias used in JWT `sub` claim, e.g. `"blai"` |
| `allowed_schemas` | list[string] | `consumers.yaml` | Per-consumer schema allowlist enforced in proxy before JWT mint |
| `rpm_limit` | int | `consumers.yaml` | Rate limit — unchanged by this feature |
| `tier` | string | `consumers.yaml` | Drives JWT `role` claim via `TIER_TO_ROLE` mapping |
| `api_keys` | list[string] | `consumers.yaml` | Raw API keys — unchanged by this feature (hashing is a separate issue) |
| `max_in_flight` | int | `consumers.yaml` | Concurrency cap — unchanged by this feature |

## Tier → Role mapping (in code, not persisted)

| Consumer `tier` | JWT `role` claim | Notes |
|---|---|---|
| `unlimited` | `api_user` | Internal/platform tier |
| `high` | `api_user` | BehaviorLabs, Carbon-5 |
| `standard` | `api_user` | DK-OS and similar |

Defined in `src/dk_data/metering_proxy/jwt_mint.py:TIER_TO_ROLE`. Any tier not in the map causes `JWTMintError` at request time, which the proxy translates to a 500 (misconfiguration). A unit test enforces every tier currently in `consumers.yaml` is in the map.

## State transitions

### Happy path

```
client                                        metering-proxy                    PostgREST                  Postgres
  │                                                 │                                │                        │
  │  GET /mol_silver/molecules                      │                                │                        │
  │  Authorization: Bearer dk_data_blai_xxx         │                                │                        │
  │ ───────────────────────────────────────────────>│                                │                        │
  │                                                 │ validate_key → ConsumerConfig  │                        │
  │                                                 │ check_schema_access → OK       │                        │
  │                                                 │ rate_limit check → OK          │                        │
  │                                                 │ concurrency_guard → slot taken │                        │
  │                                                 │ jwt_mint.mint(alias="blai",    │                        │
  │                                                 │               tier="high")     │                        │
  │                                                 │  → HS256 encode (~50 μs)       │                        │
  │                                                 │ JWT_MINTED_TOTAL.inc()         │                        │
  │                                                 │                                │                        │
  │                                                 │ GET /mol_silver/molecules      │                        │
  │                                                 │ Authorization: Bearer <jwt>    │                        │
  │                                                 │ ──────────────────────────────>│                        │
  │                                                 │                                │ verify signature OK    │
  │                                                 │                                │ SET LOCAL ROLE api_user│
  │                                                 │                                │ SELECT ...             │
  │                                                 │                                │ ───────────────────────>
  │                                                 │                                │                        │
  │                                                 │                                │<───────────────── rows │
  │                                                 │<──────────────────── 200 JSON  │                        │
  │ <─────────────────────────────── 200 + x-consumer: blai + body                   │                        │
```

### Startup failure path

```
container start
  │
  │ lifespan() → jwt_mint.load_secret_at_startup()
  │   → os.getenv("JWT_SECRET") → "" (or too short)
  │   → raise JWTMintError
  │
  │ FastAPI lifespan fails
  │ container exits non-zero
  │ kubelet restarts container
  │ readiness probe never flips to ready
  │ no traffic routed to pod
  │ operator sees CrashLoopBackOff + structured error in logs
```

### Self-test failure path (signature mismatch)

```
container start
  │
  │ lifespan() → jwt_mint.load_secret_at_startup() → OK
  │ self_test_jwt_round_trip()
  │   → mint JWT with proxy's JWT_SECRET
  │   → GET http://localhost:3000/health with Bearer <jwt>
  │   → PostgREST verifies signature with PGRST_JWT_SECRET (which is a DIFFERENT value)
  │   → PostgREST returns 401 signature verification failed
  │   → self_test raises
  │
  │ readiness stays false
  │ pod does not receive traffic
  │ operator sees structured "jwt secret mismatch" log line
  │ operator fixes Doppler → new secret propagates → pod restarts → self-test passes
```

## Invariants

1. **I-1**: For every request that reaches PostgREST via the metering proxy, there is exactly one `metering_proxy_jwt_minted_total` increment.
2. **I-2**: For every request that FAILS in the proxy (bad key, disallowed schema, rate-limited, concurrency-shed), there is zero `metering_proxy_jwt_minted_total` increment.
3. **I-3**: No forwarded request carries both the raw API key AND the minted JWT in headers — the raw key is stripped before the JWT is added.
4. **I-4**: The signing secret exists in exactly two places: the metering-proxy container env (`JWT_SECRET`) and the PostgREST container env (`PGRST_JWT_SECRET`). Both are sourced from the same k8s secret key.
5. **I-5**: The `dk_data_no_anon` role has zero grants and therefore executes zero successful queries.
