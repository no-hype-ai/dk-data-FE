# Implementation Plan

**Branch**: `feature/002-external-integration-foundation`
**Date**: 2026-04-13
**Spec**: [spec.md](./spec.md)

## Summary

**Primary requirement**: Consolidate every consuming app's access to dk-data behind a single typed client package with authentication, telemetry, and auto-hydration — and close every anonymous access path so the gateway is the only way in.

**Technical approach**: Ship a TS + Python client package (`@datakinetic/dk-data-client` / `dk-data-client`) with OpenAPI-generated types, two-tier cache (in-process + Redis/SQLite), three fallback modes (strict/upstream/hydrate), and typed error classes. In dk-data-FE, land four sequenced SQL migrations (215 rename, 216 missing views, 217 resolve grants, 218 drop anonymous role) plus a FastAPI JWT dependency at router level, metrics emission wire-up, metering-proxy key provisioning, and cronjob cleanup. Consumer apps migrate file-by-file starting with the admin client (smallest blast radius) and ending with ground-truth/trials-predictor. Hydration priority for Phase 7 is driven by client telemetry, not planning-time guesses.

## Technical Context

| Dimension | Value |
|---|---|
| Language/Version | Python 3.11+ (dk-data-FE, trials-predictor, Python client) / TypeScript 5.x (behavior-labs-ai, ground-truth-charlie, TS client) |
| Primary Dependencies | FastAPI, psycopg2-binary, SQLMesh ≥0.90, PostgREST v12.2.3, JWT (HS256), Pydantic, structlog, OpenTelemetry SDK, Prometheus client library (Python prometheus_client), pytest + responses |
| Storage | PostgreSQL 16.4 via CloudNativePG (single shared cluster, tenant `dk_data`), PgBouncer for fetchers, direct for SQLMesh/procedures, Redis for client L2 cache in production |
| Testing Framework | pytest + responses (dk-data-FE); Vitest + MSW (TS client); real CNPG postgres for integration, no DB mocks |
| Target Platform | Kubernetes (K3s single-node), ArgoCD GitOps, GHCR SHA-pinned images, Doppler secrets, Traefik ingress |
| Project Type | Monorepo-adjacent — dk-data-FE warehouse + separate client package repo + consumer-app repos |
| Performance Goals | `client.molecules.resolve()` p99 ≤ 200 ms; `client.molecules.getProfile()` p99 ≤ 500 ms cached; L1 hit ratio ≥ 30% per handler; L2 hit ratio ≥ 60% steady-state |
| Constraints | WAL ceiling: no single SQL txn > 2 GB (`[WALMX]`); PgBouncer transaction mode breaks session-scoped advisory locks; connections via `build_dsn()` only (`[DSN]`); ArgoCD-only k8s changes (`[GITOP]`); JWT secret ≥ 256 bits; no `pg_stat_statements` available |
| Scale/Scope | 5 active consuming apps × ~1000 calls/min steady state = ~7.2M telemetry events/day; 163 cronjobs total; 78 metrics in codebase (40 live, 38 dead); 5 Grafana dashboards with 307 total panels; 14 `mol_api` views + 2 functions; 11 silver-hub resolve functions; 4 migrations to land (215–218) |

## Constitution Check

*No `.dk/memory/constitution.md` present — gate skipped. Principle tags from `.dk/memory/tags.md` remain authoritative.*

| Tag | Applies | Notes |
|---|---|---|
| `[IDMPT]` | YES | Migrations 215–218 and 220 are idempotent/resumable; client `hydrate` mode writes through idempotent ingestion endpoints |
| `[GITOP]` | YES | All k8s changes (configmap edits, cronjob deletions, annotations) flow through ArgoCD |
| `[SECRT]` | YES | Consumer API keys and `JWT_SECRET` via Doppler — never in YAML manifests |
| `[TESTE]` | YES | Client and migrations require pytest + Vitest integration tests (US-14) |
| `[WALMX]` | YES | Migrations 215–218 and 220 are metadata-only (no bulk DML) — no WAL concern |
| `[DSN]` | YES | All new Python code uses `build_dsn()`; CI check continues to enforce |
| `[SVANT]` | N/A | No new silver models in this initiative (only api/mol_api/ip_api views) |
| `[CARRY]` | N/A | Same — no silver model changes |
| `[JOBLK]` | N/A | No new cross-pod coordination |
| `[PGBOU]` | YES | FastAPI auth dependency uses existing dk-data-fe pod env config |
| `[ZVAL]` | YES (NEW activation candidate) | US-15 adds router-level JWT dep and Pydantic bodies on new resolve wrapper routes |
| `[VERSN]` | YES (NEW activation candidate) | Client package SemVer; FastAPI `/data-platform` surface already unversioned — consider adding `/v1/` prefix in a follow-up |
| `[RBAC]` | YES (NEW activation candidate) | US-2 + US-15: every request requires a JWT role claim matched against `analyst` / `api_user` |
| `[NOLOG]` | YES | Client telemetry events MUST NOT log tokens or secrets (assert in adapter test suite) |
| `[BRKR]` | YES | Client retry/backoff on 429/5xx via typed retry policy |
| `[AUDIT]` | YES (NEW activation candidate) | Metering proxy audit log captures every request (FR-015) |

**New tag activations proposed for this feature**: `[ZVAL]`, `[VERSN]`, `[RBAC]`, `[AUDIT]`. Added to `.dk/memory/decisions.md`.

## Project Structure

```
dk-data-FE/                          # Warehouse repo
├── src/dk_data/
│   ├── api/
│   │   ├── dependencies/
│   │   │   └── auth.py              # NEW (US-15): verify_jwt FastAPI dep
│   │   └── routes/
│   │       └── data_platform.py     # UPDATE: router-level Depends(verify_jwt); 7 new resolve wrappers
│   ├── ingestion/utils/
│   │   └── build_model_lineage.py   # UPDATE: _SKIP_SCHEMAS += mol_api, ip_api; new IND_SUBDOMAINS['ind-terminology']
│   ├── observability/
│   │   └── metrics.py               # UPDATE: delete dead metrics OR wire up emissions
│   ├── services/data_platform/
│   │   ├── metrics.py               # UPDATE: new helpers for cms_* and batch job metrics
│   │   └── pipeline_monitoring.py   # UPDATE: wire record_pipeline_processing_duration()
│   └── sql/
│       ├── migrations/
│       │   ├── 215_ci_views_domain_relocate.sql     # NEW (US-6)
│       │   ├── 216_missing_mol_api_views.sql        # NEW (US-4)
│       │   ├── 217_resolve_function_grants.sql     # NEW (US-5)
│       │   ├── 218_drop_web_anon.sql               # NEW (US-2)
│       │   ├── 218_drop_web_anon_rollback.sql      # NEW (US-2 rollback)
│       │   └── 220_align_source_naming.sql         # NEW (US-20)
│       └── post_sqlmesh/
│           ├── 043_api_materialized_views.sql     # UPDATE: strip web_anon grants
│           ├── 055_postgrest_hub_grants.sql       # UPDATE: strip web_anon block
│           └── 061_ci_api_views.sql               # SUPERSEDED by 215 — leave aliases only
├── grafana/dashboards/
│   ├── dk-data-adapter-telemetry.json  # NEW (hydration heat map)
│   └── [existing 5 dashboards]          # UPDATE: metric references, label selectors
├── k8s/apps/
│   ├── postgrest/base/configmap.yaml    # UPDATE: unset PGRST_DB_ANON_ROLE; add ip_api to PGRST_DB_SCHEMAS
│   ├── postgrest/base/deployment.yaml   # UPDATE: remove stale HTTP-probe comment
│   ├── metering-proxy/base/configmap.yaml  # UPDATE: provision api_keys, scope internal, add ground-truth/trials-predictor
│   ├── metering-proxy/base/deployment.yaml # UPDATE: add prometheus.io/scrape annotations
│   ├── batch-api/base/deployment.yaml       # UPDATE: same
│   ├── observability/base/                  # NEW: servicemonitor-dk-data.yaml (if using Prom Operator)
│   ├── cronjobs/base/                       # DELETE: 25 YAML files (23 redundant + 2 dead)
│   └── infrastructure/base/db-init-job.yaml # UPDATE: remove web_anon creation + grants
├── docs/
│   ├── runbooks/
│   │   ├── rotate-jwt-secret.md             # NEW
│   │   ├── rollback-web-anon-drop.md        # NEW
│   │   ├── metering-proxy-401-debug.md      # NEW
│   │   ├── adapter-fallthrough-spike.md     # NEW
│   │   └── dashboard-no-data.md             # NEW
│   ├── consumer-onboarding.md               # NEW
│   ├── architecture.md                      # UPDATE: auth flow diagram
│   └── data-catalog.md                      # NEW: endpoint → schema → owner mapping
├── tests/
│   ├── migrations/
│   │   ├── test_215_rename.py               # NEW
│   │   ├── test_216_missing_views.py        # NEW
│   │   ├── test_217_resolve_grants.py       # NEW
│   │   └── test_218_drop_web_anon.py        # NEW
│   ├── api/
│   │   └── test_data_platform_auth.py       # NEW (US-15)
│   └── observability/
│       └── test_metric_coverage.py          # NEW (US-12 Fix 12.7)
├── README.md                                # UPDATE: adapter, auth, env vars
└── CLAUDE.md                                # UPDATE: unprefixed-schema carve-out table (US-19)

dk-data-client/                    # NEW separate repo (TS + Python)
├── typescript/
│   ├── src/
│   │   ├── client.ts              # DkDataClient main class
│   │   ├── modules/
│   │   │   ├── molecules.ts       # molecules module
│   │   │   ├── companies.ts
│   │   │   ├── conditions.ts
│   │   │   ├── publications.ts
│   │   │   ├── patents.ts
│   │   │   ├── providers.ts
│   │   │   └── catalog.ts
│   │   ├── cache/
│   │   │   ├── l1.ts              # in-process LRU
│   │   │   └── l2.ts              # Redis adapter (prod) / file adapter (dev)
│   │   ├── fallback/
│   │   │   ├── strict.ts
│   │   │   ├── upstream.ts
│   │   │   └── hydrate.ts
│   │   ├── errors.ts              # 7 typed error classes
│   │   ├── telemetry.ts           # Loki event emission
│   │   ├── types.ts               # GENERATED from OpenAPI
│   │   └── version.ts
│   ├── tests/                     # Vitest + MSW
│   ├── package.json
│   └── tsconfig.json
├── python/
│   ├── dk_data_client/
│   │   ├── client.py
│   │   ├── modules/
│   │   ├── cache/
│   │   ├── fallback/
│   │   ├── errors.py
│   │   ├── telemetry.py
│   │   └── models.py              # GENERATED from OpenAPI (Pydantic)
│   ├── tests/                     # pytest
│   └── pyproject.toml
└── .github/workflows/
    ├── typegen.yml                # Scrape dk-data-FE OpenAPI → regenerate types
    ├── test.yml                    # Unit + integration against ephemeral dk-data
    └── release.yml                 # Semver publish to npm + PyPI

[consuming app repos — separate]
behavior-labs-ai/
├── apps/admin/lib/dk-data/postgrest-client.ts  # DELETE or shim
├── apps/api/src/competitive-intel/sources/dk-data-fe.client.ts  # UPDATE
└── apps/api/src/research/agents/*.agent.ts     # UPDATE (4 agents)

ground-truth-charlie/
├── src/lib/adapters/pubmed-adapter.ts          # REPLACE with client call
└── src/lib/adapters/openalex-adapter.ts        # REPLACE with client call

trials-predictor/
└── app/backend/sqlmesh_project/macros/identifier_utils.py  # UPDATE
```

## Phase 0 — Research

### Client cache L2 backend

- **Decision**: Redis in production, file-backed store (SQLite) in developer environments.
- **Rationale**: Redis is already deployed in the cluster; no new infra. Cross-pod cache sharing is required for multi-replica consumer deployments. SQLite keeps dev simple.
- **Alternatives considered**: Redis everywhere (works but forces devs to run Redis locally); Memcached (no persistence, worse for multi-pod coordination); in-process only (no L2 means every pod rehits dk-data → destroys the point of caching).

### Client telemetry sink

- **Decision**: Direct push from client to cluster Loki via HTTP. If Loki ingestion path does not accept JSON events from external apps, fall back to metering-proxy-mediated telemetry (proxy forwards to Loki).
- **Rationale**: Reuses existing observability stack; one event per call preserves causality for debugging. Direct push is the simpler path; proxy-mediated is the fallback if capacity/auth requires it.
- **Alternatives considered**: OpenTelemetry collector sidecar (heavier; another moving part); batched log ship via file rotation (adds latency); Prometheus-only (counter metrics, not event-shaped).
- **Verification required in Phase 1**: can external apps POST to Loki? Confirm retention + capacity for ~7M events/day.

### Auto-fallback write-back endpoint for `hydrate` mode

- **Decision**: v0.1 ships with `strict` and `upstream` modes only. `hydrate` mode ships in v1.0 after ingestion endpoints are verified idempotent.
- **Rationale**: Avoid coupling the client launch to an unverified write path. Strict + upstream cover all current consumer needs; hydrate is an optimization.
- **Alternatives considered**: Ship hydrate in v0.1 (requires blocking on ingestion endpoint audit first); never ship hydrate (misses the biggest lever for dk-data growth).

### TypeScript HTTP client

- **Decision**: Native `fetch` (Node ≥18), with `undici` as fallback for older runtimes.
- **Rationale**: No external dep for modern runtimes; smallest surface. `undici` fallback covers the legacy long tail.
- **Alternatives considered**: `axios` (unnecessary dep); `ky` (thin wrapper over fetch — nice but not needed); `node-fetch` (mostly deprecated now).

### Python HTTP client

- **Decision**: `httpx` (async-first, connection pooling, trio-compatible).
- **Rationale**: Matches the async patterns in dk-data-FE's FastAPI code; supports retries via `tenacity` (`[BRKR]` tag).
- **Alternatives considered**: `requests` (sync-only; blocks async consumers); `aiohttp` (older; less ergonomic).

### Migration sequencing

- **Decision**: 215 rename → 216 missing views → 217 resolve grants → 218 drop web_anon → 220 align source naming.
- **Rationale**: `mol_api.publications` (216) UNIONs `mol_api.pubmed_publications` and `mol_api.openalex_publications`, which only exist after 215 relocates them. 218 runs last so prior migrations can still touch `web_anon` during the transition window. 220 is independent and can ship in Phase 6.25.
- **Alternatives considered**: Do rename + missing views in one migration (larger blast radius, harder rollback); do drop first and build views against the new state (breaks existing consumers for ~1 day).

### FastAPI JWT dependency pattern

- **Decision**: Router-level `dependencies=[Depends(verify_jwt)]` applied to the `/data-platform` router.
- **Rationale**: Single line, covers all 34 existing routes without per-route edits, hard to bypass.
- **Alternatives considered**: Per-route decorator (repetitive, easy to forget on new routes); middleware (runs before path matching, harder to carve out exceptions); gateway-only auth (leaves FastAPI bypassable from inside the cluster).

### Client type generation pipeline

- **Decision**: CI job scrapes PostgREST OpenAPI + FastAPI `/docs/openapi.json` from an ephemeral dk-data-FE instance, runs `openapi-typescript` and `datamodel-code-generator`, commits generated files.
- **Rationale**: Kills hand-written types; minor dk-data changes auto-propagate. Ephemeral CI instance avoids dependency on prod state.
- **Alternatives considered**: Re-enable PostgREST OpenAPI in production (security concern — currently `disabled`); hand-write types (the failure mode this initiative is trying to prevent).
- **Verification required**: CI job spin-up time; OpenAPI completeness for all mol_api views after migration 215 runs.

### Adapter v0.1 → v0.2 lifecycle (drift audit F-D017)

- **Decision**: Adapter v0.1 ships in Phase 3 against the **pre-migration** PostgREST surface (current `mol_api` + silver layer). v0.2 ships immediately after migration 216 lands on production — CI regenerates types against the new surface and publishes.
- **Rationale**: Decouples adapter shipment from migration landing. Consumers get a working client on day 1 of Phase 3 without waiting for Phase 4.
- **Fingerprint check behavior**:
  - v0.1: `client.serverInfo()` logs a **warning** (not an error) if the dk-data schema fingerprint does not match the client's compile-time fingerprint. Warn-only preserves v0.1 consumer operation during the ≤ 7-day transition window.
  - v0.2+: fingerprint check can escalate to error on major version bumps.
- **Transition window**: 7 days target from migration 216 landing → all consumers on v0.2. If a consumer lags, the warn-only fingerprint means they keep working (degraded features, not outage).
- **Alternatives considered**: Gate adapter release on Phase 4 (delays Phase 3 unnecessarily); throw on fingerprint mismatch (flag-day break).

### `drug_label_sections` investigation for US-4 boxed warnings

- **Decision**: Source `mol_api.boxed_warnings` and `mol_api.contraindications` from inline columns on `mol_silver.drug_labels` (verified: `drug_label_sections` table does not exist; `boxed_warning` is an inline column).
- **Rationale**: Verified against `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql`. Earlier LOINC-code-based plan was wrong.
- **Alternatives considered**: Create a new `drug_label_sections` table (unnecessary when the data is already flat in `drug_labels`); LOINC-based extraction (source data is not structured by LOINC).

### Agents schema collision (US-18)

- **Decision**: Document as intentionally separate in Phase 6.25; defer consolidation to a follow-up initiative.
- **Rationale**: Consolidation requires auditing which cluster services write to each of the three `agents`/`mol_agents`/`hcs_agents` schemas. That audit is out of scope for the current initiative; documenting preserves knowledge without gating the critical path.
- **Alternatives considered**: Consolidate now (large scope expansion); ignore (collision repeats).

## Hydration Roadmap (preserved from brief Section 12)

Phase 8 ingestion priority is telemetry-driven (US-7), but the candidate inventory below is the starting point. The tier structure reflects effort + licensing complexity + downstream value, not commitment order.

### Tier 1 — already fetched by consuming apps, must centralize ASAP

| Source | Data | Used by | Effort | Priority |
|---|---|---|---|---|
| SEC EDGAR | Company financials, 10-K/10-Q | behavior-labs CI | Low (free API, `api.sec_filings` view exists) | P0 |
| Press releases | Company announcements | behavior-labs CI | Medium (multi-source aggregation) | P0 |
| BioRxiv / MedRxiv | Preprints | ground-truth | Low (free API) | P0 |
| Semantic Scholar | Academic graph + citations | ground-truth | Low (free API w/ key) | P0 |
| Europe PMC | EU publications | ground-truth | Low (free API) | P1 |
| DailyMed | Structured FDA labels | ground-truth | Medium (SPL XML parsing) | P1 |
| OpenFDA adverse events | FAERS structured | ground-truth (dedup with mol_gold) | Partial | P1 |
| UMLS / SNOMED CT | Medical terminology | trials-predictor | High (license required) | P0 |
| RxNorm (full release) | Drug normalization | trials-predictor | Low (free) | P0 |

### Tier 2 — not currently fetched, obvious gaps

FDA Orange Book, Purple Book, NDC Directory, drug shortages, recalls/483s/warning letters, Open Payments (Sunshine Act), CMS Medicare Part D prescriber, CMS NPI Registry, AACT (CT.gov full DB), NIH RePORTER, ICD-10/11, MeSH, WHO ATC, OpenTargets, DGIdb, ChEMBL bioactivity audit, UniProt, ClinVar, USPTO assignments, patent litigation (PACER subset).

### Tier 3 — conference abstracts (high value, awkward sourcing)

ASCO, AACR, ASH, ESMO, AHA, EULAR. Each per-society scraper; single conference adapter framework.

### Tier 4 — commercial / paid (build vs buy decisions)

Medi-Span / Red Book, AdisInsight, Cortellis, Pharmaprojects, Citeline, BioMedTracker, GlobalData, IQVIA / Symphony Health. Default: buy nothing until telemetry justifies.

### Tier 5 — real-world evidence (out of scope for 2026 unless forced)

Optum / Truven / Marketscan, Flatiron, TriNetX, All of Us / UK Biobank.

### Coverage / freshness gaps on existing sources

| Existing source | Gap | Action |
|---|---|---|
| `mol_raw.pubchem` | Last refresh date? | Verify cron |
| `mol_raw.chembl_*` | Coverage audit | Row counts vs upstream |
| `mol_raw.clinicaltrials` | Daily refresh? | Verify schedule |
| `mol_raw.faers` | Quarterly drops applied? | Verify FDA release calendar |
| `hcs_raw.cms_*` | Current year loaded? | Verify |
| `ip_silver.patents` | USPTO weekly drops? | Verify |
| `mol_gold.*` aggregations | Last build? | US-8 row-count verification + alerting |

## Phase 1 — Design

See sibling artifacts:

- **`data-model.md`**: Canonical entities (Consuming App, Client Package, Molecule, Molecule Profile, Silver Hub, Resolve Operation, Consumer Credential, Gateway Token, Metric, Dashboard, Lineage Edge, Data Source, Cronjob) with fields and relationships
- **`contracts/`**: The client package's public API (TS + Python signatures), the warehouse's PostgREST + FastAPI contract changes, the metering-proxy auth flow
- **`quickstart.md`**: Developer setup for the client package, for adding a new consumer, and for rotating the JWT signing secret

## Complexity Tracking

| Area | Complexity | Justification | Approved |
|---|---|---|---|
| Sequenced migrations 215–218 | Order-dependent (216 depends on 215; 218 depends on all prior) | Required because `mol_api.publications` UNIONs newly-relocated views; drop-role-last is safety margin | Autonomous (dk.auto) |
| Rollback migration for 218 | Separate file | `DROP ROLE` is one-way; rollback is restore + re-grant minimum | Autonomous (dk.auto) |
| Four new migrations + one rollback | Higher than typical (most features have 1-2) | Each migration is single-purpose and small; combining them would complicate rollback | Autonomous (dk.auto) |
| Client package in two languages | Doubled implementation | Three consumers need TS, two need Python; phasing leaves trials-predictor stranded | Autonomous (dk.auto) |
| Per-resource cache TTL table | More complex than single TTL | Identifiers are immutable (30 days), trials change daily (6h), resolution queue must be live (never cache) — one TTL does not fit | Autonomous (dk.auto) |
| FastAPI router-level auth dep vs per-route | Router-level chosen | Single line of code, applies to all 34 routes, bypass-proof for new routes | Autonomous (dk.auto) |
| Deprecated alias window (30 days telemetry-gated) | Not immediate drop | Prevents flag-day break; gated on observable condition (no calls to legacy name) | Autonomous (dk.auto) |
