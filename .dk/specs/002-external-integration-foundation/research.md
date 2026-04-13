# Research Decisions — external-integration-foundation

## R-01: Client cache L2 backend

**Decision**: Redis in production, file-backed store (SQLite) in developer environments.

**Rationale**: Redis is already deployed in the cluster for other services — no new infrastructure cost. Cross-pod cache sharing is a hard requirement for multi-replica consumer deployments. SQLite keeps dev simple: no external dep, no setup.

**Alternatives considered**:
- Redis everywhere: forces every developer to run Redis locally, adds setup friction
- Memcached: no persistence, worse multi-pod coordination, no pub/sub
- In-process only: every pod rehits dk-data; negates the point of an L2 cache
- DynamoDB-style cloud cache: unnecessary cloud dependency

## R-02: Client telemetry sink

**Decision**: Direct push from client to cluster Loki via HTTP. Fallback: metering-proxy-mediated if the direct path is infeasible.

**Rationale**: Reuses the existing observability stack (verified: Grafana + Loki + Mimir are deployed). Per-call events preserve causality for debugging. Direct push is the simpler architecture.

**Alternatives considered**:
- OpenTelemetry collector sidecar: adds deployment complexity; heavier runtime
- Batched log file rotation: adds latency between event and observability; doesn't fit cloud-native pattern
- Prometheus-only (counters, no events): loses per-call detail needed for the hydration heat map

**Verification required in Phase 1**:
- Can external apps POST to cluster Loki? (Auth, network path)
- Does Loki have headroom for ~7M events/day?

## R-03: Auto-fallback `hydrate` mode timing

**Decision**: v0.1 ships with `strict` and `upstream` modes only. `hydrate` mode ships in v1.0 after dk-data ingestion endpoints are audited for idempotency.

**Rationale**: Avoid coupling the client launch to an unverified write path. Two modes cover every current consumer need. `hydrate` is the biggest growth lever but also the riskiest code path.

**Alternatives considered**:
- Ship all three modes in v0.1: requires blocking on ingestion endpoint audit
- Never ship hydrate: misses the biggest automatic-growth mechanism

## R-04: TypeScript HTTP client

**Decision**: Native `fetch` (Node ≥18), with `undici` as a fallback for older runtimes.

**Rationale**: No external dep for modern runtimes; smallest surface; matches the platform's direction.

**Alternatives considered**:
- `axios`: unnecessary dep
- `ky`: thin wrapper over fetch — nice but adds a dep for no value
- `node-fetch`: mostly deprecated now that Node has native fetch

## R-05: Python HTTP client

**Decision**: `httpx` (async-first, connection pooling, trio-compatible).

**Rationale**: Matches the async patterns in dk-data-FE's FastAPI code. Supports retries via `tenacity` (already required by `[BRKR]` tag). Sync + async interfaces work for both one-off scripts and long-running services.

**Alternatives considered**:
- `requests`: sync-only; blocks any async consumer
- `aiohttp`: older; less ergonomic API; worse docs
- `urllib3` raw: too low-level

## R-06: Migration sequencing

**Decision**: 215 (CI view rename) → 216 (missing views) → 217 (resolve function grants) → 218 (drop web_anon). Migration 220 (source naming alignment) is independent and can ship in Phase 6.25.

**Rationale**: `mol_api.publications` (216) is `UNION ALL mol_api.pubmed_publications, mol_api.openalex_publications` — both only exist after 215 relocates them from `api.*`. Dropping web_anon last gives prior migrations room to touch it during the transition window.

**Alternatives considered**:
- Combine rename + missing views in one migration: larger blast radius, harder rollback
- Drop web_anon first, rebuild against new state: breaks every consumer for 1+ day
- Reverse order: breaks the publications view dependency

## R-07: FastAPI JWT dependency pattern

**Decision**: Router-level `dependencies=[Depends(verify_jwt)]` on the `/data-platform` router.

**Rationale**: Single line; covers all 34 existing routes without per-route edits; new routes added under the router are auto-protected.

**Alternatives considered**:
- Per-route decorator: repetitive, easy to forget on new routes
- Middleware: runs before path matching, hard to carve out exceptions (e.g., OpenAPI docs)
- Gateway-only auth: leaves FastAPI bypassable from inside the cluster

## R-08: Client type generation pipeline

**Decision**: CI job scrapes PostgREST OpenAPI + FastAPI `/docs/openapi.json` from an ephemeral dk-data-FE instance; runs `openapi-typescript` and `datamodel-code-generator`; commits the generated files to the client repo.

**Rationale**: Eliminates hand-written types. Minor dk-data changes auto-propagate to consumers on the next client release. Ephemeral CI instance keeps CI independent of production state.

**Alternatives considered**:
- Re-enable PostgREST OpenAPI in production: `PGRST_OPENAPI_MODE` is currently `disabled` for a security reason
- Hand-write types: the exact failure mode this initiative is preventing
- Generate from SQL DDL: brittle, misses FastAPI routes

**Verification required**:
- CI job spin-up time is acceptable (<3 min per PR)
- OpenAPI completeness covers all `mol_api` views after migration 215

## R-09: `drug_label_sections` investigation for US-4

**Decision**: Source `mol_api.boxed_warnings` and `mol_api.contraindications` from inline columns on `mol_silver.drug_labels`. The `mol_silver.drug_label_sections` table does NOT exist — the earlier LOINC-code plan was wrong.

**Rationale**: Verified against `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql`. `boxed_warning` is a direct column on the `drug_labels` table, and `contraindications` is a sibling field on the same row. No new table is needed.

**Alternatives considered**:
- Create a new `drug_label_sections` table: unnecessary normalization when data is already flat
- LOINC-based extraction: source data is not structured by LOINC code

## R-10: Agents schema collision (US-18)

**Decision**: Document the three `agents`/`mol_agents`/`hcs_agents` schemas as intentionally separate in Phase 6.25. Defer consolidation to a follow-up initiative.

**Rationale**: Consolidation requires auditing which cluster services write to each schema — an audit that's out of scope for this initiative. Documentation preserves knowledge without gating the critical path.

**Alternatives considered**:
- Consolidate now: large scope expansion, blocks the critical path
- Ignore: collision repeats, same failure mode as `molecule_profile` vs `molecule_profiles`

## R-11: Metering proxy API key format

**Decision**: `dk_data_{alias}_{16-char random suffix}` — matches the pattern documented in the metering proxy's `consumers.yaml` comment.

**Rationale**: Existing pattern; no need to reinvent. Alias is human-readable for log attribution; random suffix is unpredictable.

**Alternatives considered**:
- UUID: longer, less human-friendly
- HMAC-signed tokens: unnecessary complexity; API keys are opaque bearer tokens

## R-12: Rollback restoration depth for migration 218

**Decision**: Rollback restores only the minimum grants: USAGE on `api` schema + SELECT on `api.health` + SELECT on `api.data_catalog`. No broader grants.

**Rationale**: Restoring the legacy broad grants (from migrations 086, 092, 117, 136, 043, 055, 061) re-opens every hole the lockdown closed. If the minimum rollback is insufficient, the operator's next step is a forward-fix (provision the missing consumer credential), not a deeper rollback.

**Alternatives considered**:
- Restore all `api` schema grants: still too broad
- Full restoration of all legacy grants: completely undoes US-2
- Skip rollback entirely: operationally unacceptable for a security change
