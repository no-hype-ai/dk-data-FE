# dk-data Architecture

**Feature**: 002-external-integration-foundation
**Last verified**: 2026-04-13

This document explains how dk-data is structured end-to-end, with a particular focus on the authentication flow after feature 002 (US-2, US-3, US-15). For command-level and make-target details, see `README.md`. For consumer onboarding, see `docs/consumer-onboarding.md`. For the silver-hub data model, see `CLAUDE.md` and the runbooks under `docs/runbooks/`.

## Layered overview

```
                ┌────────────────────────────────────────────────┐
                │            External consumers                 │
                │  behavior-labs-ai    ground-truth-charlie      │
                │  trials-predictor    internal notebooks        │
                └───────────────────────┬────────────────────────┘
                                        │
                          (HTTPS Bearer <API_KEY>)
                                        │
                ┌───────────────────────▼────────────────────────┐
                │     Traefik ingress (k8s)                      │
                │     host: data.behaviorlabs.ai                 │
                └───────────────────────┬────────────────────────┘
                                        │
                ┌───────────────────────▼────────────────────────┐
                │     Metering proxy  (port 3001)                │
                │  - validates API key against consumers.yaml    │
                │  - enforces per-consumer schema allowlist      │
                │  - enforces per-consumer rate limit            │
                │  - mints HS256 JWT with role=analyst|api_user  │
                │  - emits structured telemetry                  │
                │  - serves /metrics on the same port (T014)     │
                └─────────┬─────────────────────────┬────────────┘
                          │                         │
           ┌──────────────▼─────────┐     ┌─────────▼───────────┐
           │  PostgREST (port 3000) │     │ FastAPI data-platform│
           │  - Accept-Profile:     │     │ (port 8000)          │
           │    mol_silver/ip_api…  │     │ - /rpc/resolve_*     │
           │  - JWT verify (HS256)  │     │ - require_auth       │
           │  - switches PG role    │     │   (rbac.py)          │
           │    to analyst/api_user │     │ - JWTService reads   │
           │  - TCP probes          │     │   JWT_SECRET_KEY     │
           │    (no web_anon)       │     │   → JWT_SECRET       │
           └──────────────┬─────────┘     └─────────┬───────────┘
                          │                         │
                          └─────────────┬───────────┘
                                        │
                ┌───────────────────────▼────────────────────────┐
                │     PgBouncer (transaction mode)               │
                │  - pools for authenticator role                │
                │  - POSTGRES_HOST_DIRECT bypasses for SQLMesh   │
                │    and PL/pgSQL jobs (advisory locks need      │
                │    session mode)                               │
                └───────────────────────┬────────────────────────┘
                                        │
                ┌───────────────────────▼────────────────────────┐
                │     PostgreSQL 16 (port 5432)                  │
                │                                                │
                │  Domains:  mol_*   hcs_*   ind_*   hcp_*  ip_* │
                │            raw → bronze → silver → gold → api │
                │                                                │
                │  Infra:    meta   staging   xenon   agents     │
                │            (see CLAUDE.md for carve-outs)      │
                └────────────────────────────────────────────────┘
```

## Auth flow (after feature 002)

```
┌─────────┐                                                      ┌──────────┐
│consumer │                                                      │ Postgres │
└────┬────┘                                                      └────▲─────┘
     │                                                                │
     │ 1. GET /molecules?select=id,canonical_name                      │
     │    Authorization: Bearer <DK_DATA_API_KEY>                      │
     │                                                                 │
     ├──▶┌────────────────┐                                            │
     │   │metering-proxy  │                                            │
     │   └──────┬─────────┘                                            │
     │          │                                                      │
     │          │ 2. bcrypt-verify key against consumers.yaml          │
     │          │    lookup consumer_id, tier, allowed_schemas         │
     │          │                                                      │
     │          │ 3. enforce rate limit (per-consumer token bucket)    │
     │          │                                                      │
     │          │ 4. enforce schema allowlist from Accept-Profile      │
     │          │    header OR from inferred target                   │
     │          │                                                      │
     │          │ 5. mint HS256 JWT                                    │
     │          │    { "role": "analyst",                              │
     │          │      "sub": "behavior-labs-ai",                      │
     │          │      "iat": ..., "exp": now+5min,                    │
     │          │      "aud": "dk-data" }                              │
     │          │                                                      │
     │          │ 6. forward to PostgREST or FastAPI                   │
     │          │    with Authorization: Bearer <minted-JWT>           │
     │          │                                                      │
     │          ▼                                                      │
     │   ┌────────────────┐                                            │
     │   │   PostgREST    │                                            │
     │   └──────┬─────────┘                                            │
     │          │                                                      │
     │          │ 7. verify JWT signature (PGRST_JWT_SECRET)           │
     │          │                                                      │
     │          │ 8. SET LOCAL role = <jwt.role>                       │
     │          │                                                      │
     │          │ 9. query via authenticator → analyst                 │
     │          ├──────────────────────────────────────────────────────▶
     │          │                                                      │
     │◀─────────┤                                                      │
     │ rows     │                                                      │
     │ (JSON)   │                                                      │
     │                                                                 │
```

**Key facts**:

- The metering proxy is the ONLY entry point. Nothing talks to PostgREST or FastAPI directly except the proxy itself.
- Consumers never see a JWT. They hold an API key; the proxy mints a fresh JWT for every request.
- The JWT is short-lived (5 min) and scoped with `aud: dk-data`. If a JWT leaks, the worst case is 5 minutes of unauthorized access, bounded to whatever the consumer's tier can read.
- The shared HS256 signing secret is held in three places, all synced from Doppler: `JWT_SECRET` (env), k8s `dk-data-secrets` Secret, `PGRST_JWT_SECRET` (env). See `docs/runbooks/rotate-jwt-secret.md`.
- There is no anonymous access. `web_anon` was dropped in migration 218. Any request without a valid `Authorization` header gets a 401 before it reaches any data.
- PostgREST health probes are TCP only (`tcpSocket: {port: 3000}`) — no HTTP probe, no `api.health` carve-out. The previous comment in `k8s/apps/postgrest/base/deployment.yaml` claiming HTTP probes was stale and has been removed (T085).

## Schema switching via `Accept-Profile`

PostgREST exposes multiple schemas via `PGRST_DB_SCHEMAS`. A client selects the target schema per request with the `Accept-Profile` header:

```
GET /molecules
Accept-Profile: mol_silver
```

The allowed schemas (as of feature 002) are:

```
api, mol_api, mol_silver, mol_gold,
ip_api, ip_silver,
hcs_silver, hcs_gold,
ind_silver, ind_gold,
hcp_silver, hcp_gold,
mol_agents, hcs_agents, agents,
mart, scoring, targeting, xenon
```

If a consumer requests a schema that is in `PGRST_DB_SCHEMAS` but NOT in their `allowed_schemas` in `consumers.yaml`, the metering proxy returns 403 before the request ever reaches PostgREST. See `docs/consumer-onboarding.md` for per-consumer allowlist guidance.

## Write path — ingestion

Ingestion is a separate side of the system. The metering proxy and PostgREST only handle reads; writes happen via:

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ job-trigger      │───▶│ k8s CronJob      │───▶│ fetcher / loader │
│ (port 8000)      │    │ batch.Job        │    │ (per source)     │
└──────────────────┘    └──────────────────┘    └────────┬─────────┘
                                                          │
                                                          ▼
                                                  ┌──────────────┐
                                                  │ PostgreSQL   │
                                                  │ raw.*        │
                                                  └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │ SQLMesh      │
                                                  │ run          │
                                                  └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │ bronze/silver│
                                                  │ /gold tables │
                                                  └──────────────┘
```

Cronjobs and ad-hoc ingestion runs go through `POSTGRES_HOST_DIRECT` (bypassing PgBouncer) because SQLMesh and PL/pgSQL procedures rely on session-scoped features (advisory locks, LISTEN/NOTIFY, `CREATE TEMP TABLE ... ON COMMIT DROP`) that PgBouncer transaction mode does not support.

The `meta.backfill_state` orchestrator (introduced in feature 002) runs as a single CronJob on a 10-minute cadence and processes one source per tick, sequentially. This replaces a previous fan-out design that was too easy to overrun API rate limits.

## Observability

Three concerns, three signal paths:

| Signal | Path | Where to look |
|---|---|---|
| Metrics | FastAPI `/metrics` (port 8000) and metering-proxy `/metrics` (port 3001) | Prometheus scrape → Grafana dashboards |
| Logs | `stdout` / `stderr` from every pod | Loki → Grafana Explore |
| Telemetry | Client-side structured events emitted by `packages/dk-data-client/` | Loki (`app=adapter-telemetry`) → Adapter Hydration Heat Map |

The three-way binding principle (`.dk/memory/principles.md` §6) requires every metric to be *defined* (in `src/dk_data/observability/metrics.py`), *emitted* (at least one production call site), and *consumed* (by a dashboard panel or alert) in the same PR that introduces it.

## Related

- `README.md` — quick start, make targets, env var reference
- `CLAUDE.md` — schema reference, silver hub architecture
- `docs/consumer-onboarding.md` — provisioning a new consumer
- `docs/data-catalog.md` — endpoint → schema → owner mapping
- `docs/runbooks/` — per-incident debugging runbooks
- `.dk/memory/principles.md` — project principles (plan-before-code, three-way binding, etc.)
