# Task Breakdown — external-integration-foundation

**Branch**: `feature/002-external-integration-foundation`
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

## Task Format

```
- [ ] [ID] [P?] [Story?] Description — `file/path.ext`
```

- `[ID]`: Sequential (T001, T002, ...)
- `[P]`: Parallelizable (different files, no dependencies)
- `[US#]`: User story reference
- File paths in backticks

---

## Phase 1 — Setup & Verification

*Everything that must be true before any breaking change. Run sequentially.*

**Artifact rule (drift audit D13):** Every Phase 1 verification task MUST produce a dated report at `docs/reports/<task-id>-<short-name>.md` showing: command run, output excerpt, timestamp, pass/fail verdict, runner's name. Checking the box without the artifact is NOT acceptable — SC-028 enforces this at the go/no-go gate (T169).

- [ ] T001 Verify `mol_gold.{molecule_profile, safety_signals, lifecycle_stages, competitive_landscape, company_pipeline}` row counts > 0 on production — `docs/runbooks/verify-gold-backfill.md` (US-8)
- [ ] T002 Verify k8s probes are TCP-only: confirm the `startupProbe`, `livenessProbe`, and `readinessProbe` blocks in `postgrest/base/deployment.yaml` all use `tcpSocket: {port: 3000}` (not `httpGet`) — `k8s/apps/postgrest/base/deployment.yaml`
- [ ] T003 Verify Loki ingestion path accepts JSON events from external apps — `docs/runbooks/verify-loki-ingestion.md` (US-17, US-1)
- [ ] T004 Verify Loki retention + capacity for ~7M events/day — `docs/runbooks/verify-loki-ingestion.md` (US-17)
- [ ] T005 Verify `mol_silver.drug_labels` inline columns: `boxed_warning`, `contraindications` — read `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql` (US-4)
- [ ] T006 Audit `internal` metering-proxy consumer: list every cluster service currently authenticating as `internal`, build explicit allowlist — `k8s/apps/metering-proxy/base/configmap.yaml` (US-3)
- [ ] T007 Verify FastAPI `/data-platform/*` has no current auth — grep `src/dk_data/api/routes/data_platform.py` for `Depends(verify_jwt)` (US-15)
- [ ] T008 Audit metric emission gaps against dashboards — produce `docs/reports/metric-coverage-audit.md` (US-12)
- [ ] T009 Verify parent `cronjob-fetch-chembl-activities.yaml` accepts `--fiscal-year` from orchestrator; verify parent `cronjob-fetch-pubchem.yaml` handles range partitioning — `k8s/apps/cronjobs/base/` (US-20)

### Phase 1b — Cluster capacity & stability audit (CRITICAL, from post-dk.auto audit)

- [ ] T001a [CRITICAL] Audit `PGRST_DB_POOL` sizing: current value + projected load from 5 consumers × 2–5 replicas after US-2. Raise if < 30. Document in `docs/reports/capacity-audit-2026-Q2.md` — `k8s/apps/postgrest/base/configmap.yaml`, `docs/reports/capacity-audit-2026-Q2.md`
- [ ] T001b [CRITICAL] Connection pool capacity audit: measure current steady-state connections per tenant (`dk_data`, `behavior_labs`, `litellm`) against shared `max_connections=200`. Estimate +50–200 new connections from adapter fleet. Raise `max_connections` or add PgBouncer capacity if headroom < 20% — `docs/reports/capacity-audit-2026-Q2.md`
- [ ] T001c Verify adapter connection routing: confirm all consumer→dk-data reads go through metering-proxy → PostgREST, NOT direct adapter→PostgreSQL. Add network policy if needed — `k8s/apps/metering-proxy/base/networkpolicy.yaml`
- [ ] T001d [HIGH] Consumer audit for `hcs_silver` dependency via `web_anon`: query `pg_stat_activity` for last 30 days, identify which internal/carbon-5/dk-os services read `hcs_silver` or `hcs_gold`. Document dependencies. If any legitimate usage found, provision API key BEFORE migration 218 runs — `docs/reports/hcs-silver-consumer-audit.md` (US-2, US-3)
- [ ] T002a [HIGH] Concurrent load test: on staging, simulate Phase 2 peak — SQLMesh transform job + backfill orchestrator + 10K adapter calls/min + metering proxy JWT minting. Measure query p99, CPU, connection pool. Alert if any exceeds 70% saturation — `tests/load/phase2_concurrent.py`
- [ ] T004b REMOVED — Loki retention + PVC size are infrastructure-repo concerns (k8s/apps/loki/ does not exist in dk-data-FE). File as a request to the infra team with required parameters: 30-day retention, PVC ≥ 200 GB, expected volume ~7M events/day × 500 bytes.
- [ ] T004c [HIGH] Loki push rate limit test: load test HTTP push endpoint at 500 events/sec burst (5 consumers × 100 events/sec peak). If <5K events/sec sustained, document batching requirement for adapter v1.1 — `tests/load/loki_push.py`

---

## Phase 2 — Foundational (pre-lockdown prerequisites)

*No breaking changes. Blocks Phase 3 and beyond. Parallelizable where marked.*

### Phase 2a — Dev hygiene + metrics infra

- [x] T010 [P] Sync `src/dk_data/postgrest.conf` `db-schemas` to match k8s production — `src/dk_data/postgrest.conf` (US-9)
- [x] T011 [P] Sync `docker-compose.yml` `PGRST_DB_SCHEMAS` to match k8s production (add `mol_api`, `ip_api`, `hcs_agents`, `mol_agents`, `agents`) — `docker-compose.yml` (US-9)
- [x] T012 [P] Add `mol_api` and `ip_api` to the `_SKIP_SCHEMAS` set in the lineage builder (search for the existing `_SKIP_SCHEMAS` assignment) — `src/dk_data/ingestion/utils/build_model_lineage.py` (US-11)
- [x] T013 [P] Document resolve-function lineage limitation as code comment — `src/dk_data/ingestion/utils/build_model_lineage.py` (US-11)
- [ ] T014 [P] Add `prometheus.io/scrape` annotation to metering-proxy deployment — `k8s/apps/metering-proxy/base/deployment.yaml` (US-12 Fix 12.1)
- [ ] T015 [P] Add `prometheus.io/scrape` annotation to batch-api deployment — `k8s/apps/batch-api/base/deployment.yaml` (US-12 Fix 12.1)
- [ ] T016 [P] Verify Prometheus scrape job name is `dk-data-platform` (matches all 5 dashboards) — `k8s/apps/observability/**/*.yaml` (US-12 Fix 12.6)
- [x] T017 [P] **ALREADY COMPLETE (blocker B004)** — verified `src/dk_data/api/routes/monitoring.py` `report_job_completion` handler already calls `mark_job_success` + `record_job_records` on success, `increment_job_failure` on failure, and `record_job_duration` unconditionally. All 4 corresponding metrics (`BATCH_JOB_LAST_SUCCESS_TIMESTAMP`, `BATCH_JOB_RECORDS_PROCESSED`, `BATCH_JOB_FAILURES_TOTAL`, `BATCH_JOB_DURATION_SECONDS`) are emitted by their respective helpers in `src/dk_data/observability/metrics.py` lines 586–601. The brief's claim that the endpoint was "partially broken" was based on a stale snapshot — the code was already correct when this feature spec was written.
- [ ] T018 [P] Create CronJob `cronjob-build-model-lineage.yaml` (schedule `*/30 * * * *`, 5-min timeout) — `k8s/apps/cronjobs/base/cronjob-build-model-lineage.yaml` (US-11)

### Phase 2b — Consumer gateway hardening (MUST land before T030)

- [ ] T019 Provision metering-proxy API keys for 5 consumers (behavior-labs-ai, carbon-5, dk-os, ground-truth-charlie, trials-predictor) via Platform API — `k8s/apps/metering-proxy/base/configmap.yaml` (US-3)
- [ ] T020 Scope `internal` consumer to explicit allowlist (not `["*"]`) — `k8s/apps/metering-proxy/base/configmap.yaml` (US-3)
- [ ] T021 Extend `behavior-labs-ai` consumer allowlist: add `ip_api`, `mol_silver`, `mol_gold`, `ip_silver`, `ip_gold` — `k8s/apps/metering-proxy/base/configmap.yaml` (US-3)
- [ ] T022 Verify metering proxy returns 401 on missing/unknown API keys — `tests/metering-proxy/test_auth.py` (US-3)
- [ ] T023 Verify metering proxy mints valid JWTs with `role: analyst` or `role: api_user` — `tests/metering-proxy/test_jwt_mint.py` (US-3)
- [ ] T024 Verify metering proxy enforces `allowed_schemas` per consumer — `tests/metering-proxy/test_schema_allowlist.py` (US-3)
- [ ] T024a Verify metering proxy writes audit log for every request (FR-015): consumer_id, resource, status, latency_ms, ts. If the proxy currently doesn't audit-log, implement it — `src/dk_data/metering_proxy/app.py`, `tests/metering-proxy/test_audit_log.py` (US-3, FR-015)
- [ ] T024b Verify audit log destination: Loki vs Postgres audit table. Document the choice and wire the sink — `src/dk_data/metering_proxy/audit.py` (US-3, FR-015)
- [ ] T024b1 [MEDIUM] Audit log writes MUST be async (non-blocking hot path); if queue fills, drop oldest + emit alerting metric — `src/dk_data/metering_proxy/audit.py`
- [ ] T024c [HIGH] Measure metering proxy latency distribution: break down JWT mint cost vs PostgREST pass-through vs audit log write. Ensure total p99 fits inside the 200ms SLO budget — `tests/metering-proxy/test_latency_profile.py`
- [ ] T024d [CRITICAL] Metering proxy HA validation: verify deployment has ≥2 replicas AND `PodDisruptionBudget minAvailable: 1` AND passes failover test (kill one replica, verify <5s recovery). After US-2 ships, metering proxy is the ONLY path into dk-data — single point of failure is unacceptable — `k8s/apps/metering-proxy/base/deployment.yaml`, `k8s/apps/metering-proxy/base/pdb.yaml`, `tests/metering-proxy/test_failover.py`
- [ ] T024e [HIGH] Rate limit storage: confirm metering proxy rate-limit counters are in Redis (not per-replica in-memory). If in-memory, a multi-replica deployment would allow N × configured rate. Implement Redis-backed counters if needed — `src/dk_data/metering_proxy/rate_limit.py`
- [ ] T025 Write `docs/runbooks/rotate-jwt-secret.md` — MUST include rolling update procedure: deploy new replicas first with BOTH old + new secret, then remove old secret from original replicas. Zero-downtime requirement — `docs/runbooks/rotate-jwt-secret.md` (US-3, US-16)

### Phase 2c — FastAPI auth (US-15, must land alongside web_anon drop)

- [x] T026 **SCOPE REVISED (blocker B001)** — discovered existing `require_auth` in `src/dk_data/api/middleware/rbac.py` (backed by `JWTService` in `src/dk_data/services/auth/jwt_service.py`). No new `verify_jwt` function needed. Also fixed blocker B002: `JWTService` now reads `JWT_SECRET_KEY` with `JWT_SECRET` fallback so FastAPI, PostgREST, and the metering proxy all use the same signing key — `src/dk_data/services/auth/jwt_service.py`
- [x] T027 Applied `dependencies=[Depends(require_auth)]` at `/data-platform` router level; all 34 routes now protected — `src/dk_data/api/routes/data_platform.py`
- [x] T028 Wrote `tests/test_data_platform_auth.py` with 9 test cases covering missing/malformed/invalid/wrong-secret/expired/wrong-audience → 401 and valid JWT → non-401. All 9 pass — `tests/test_data_platform_auth.py`
- [x] T029 **NOT NEEDED** — existing `tests/conftest.py` loads `.env` which already sets `JWT_SECRET_KEY`. The new test file mints tokens using the live `JWTService`'s actual secret, which is robust to any env configuration.

---

## Phase 3 — Standardized adapter package (US-1, P1)

*Ship client v0.1 against the CURRENT pre-cleanup PostgREST surface. No dependency on Phase 4 migrations.*

### 3a — Package scaffold

- [ ] T030 Create `dk-data-client` repo with TS + Python monorepo structure — `packages/dk-data-client/` (US-1)
- [ ] T031 [P] Write TS package skeleton (`package.json`, `tsconfig.json`, `src/client.ts`) — `packages/dk-data-client/typescript/` (US-1)
- [ ] T032 [P] Write Python package skeleton (`pyproject.toml`, `src/dk_data_client/__init__.py`) — `packages/dk-data-client/python/` (US-1)
- [ ] T033 [P] Create shared type-generation script scraping PostgREST + FastAPI OpenAPI — `packages/dk-data-client/scripts/generate-types.sh` (US-1)
- [ ] T034 [P] GitHub Actions workflow: CI on every PR — type-gen, lint, test — `packages/dk-data-client/.github/workflows/test.yml` (US-1)
- [ ] T035 [P] GitHub Actions release workflow: publish to npm + PyPI on tag — `packages/dk-data-client/.github/workflows/release.yml` (US-1)
- [ ] T035a [MEDIUM] Measure CI job total wall clock: dk-data-FE spin-up + OpenAPI scrape + type-gen + test run. Target ≤ 3 min per PR; if exceeded, cache the dk-data-FE image layer — `packages/dk-data-client/.github/workflows/test.yml`

### 3b — Core implementation (TS)

- [ ] T036 [US1] Implement `DkDataClient` class with config + HTTP transport (native fetch) — `packages/dk-data-client/typescript/src/client.ts`
- [ ] T037 [P] [US1] Implement typed errors (7 classes) — `packages/dk-data-client/typescript/src/errors.ts`
- [ ] T038 [P] [US1] Implement L1 in-process LRU cache — `packages/dk-data-client/typescript/src/cache/l1.ts`
- [ ] T039 [P] [US1] Implement L2 Redis cache adapter — `packages/dk-data-client/typescript/src/cache/l2-redis.ts`
- [ ] T040 [P] [US1] Implement L2 SQLite cache adapter (dev) — `packages/dk-data-client/typescript/src/cache/l2-sqlite.ts`
- [ ] T041 [P] [US1] Implement strict fallback mode — `packages/dk-data-client/typescript/src/fallback/strict.ts`
- [ ] T042 [P] [US1] Implement upstream fallback mode (no write-back in v0.1) — `packages/dk-data-client/typescript/src/fallback/upstream.ts`
- [ ] T043 [P] [US1] Implement telemetry event emission to Loki — `packages/dk-data-client/typescript/src/telemetry.ts`
- [ ] T044 [US1] Implement molecules module (resolve, search, get, getProfile, getSafety, getAdverseEvents, getClinicalTrials, getDrugLabels, getBoxedWarnings, getContraindications, getCompetitiveLandscape, getResolutionQueue) — `packages/dk-data-client/typescript/src/modules/molecules.ts`
- [ ] T045 [P] [US1] Implement companies module — `packages/dk-data-client/typescript/src/modules/companies.ts`
- [ ] T046 [P] [US1] Implement conditions module — `packages/dk-data-client/typescript/src/modules/conditions.ts`
- [ ] T047 [P] [US1] Implement publications module — `packages/dk-data-client/typescript/src/modules/publications.ts`
- [ ] T048 [P] [US1] Implement patents module — `packages/dk-data-client/typescript/src/modules/patents.ts`
- [ ] T049 [P] [US1] Implement providers module — `packages/dk-data-client/typescript/src/modules/providers.ts`
- [ ] T050 [P] [US1] Implement catalog/health module — `packages/dk-data-client/typescript/src/modules/catalog.ts`
- [ ] T051 [US1] Implement `serverInfo()` + version fingerprint check — `packages/dk-data-client/typescript/src/version.ts`

### 3c — Core implementation (Python)

- [ ] T052 [P] [US1] Implement Python `DkDataClient` class with httpx async client — `packages/dk-data-client/python/dk_data_client/client.py`
- [ ] T053 [P] [US1] Port typed errors from TS — `packages/dk-data-client/python/dk_data_client/errors.py`
- [ ] T054 [P] [US1] Implement Python two-tier cache (cachetools LRU + redis/sqlite) — `packages/dk-data-client/python/dk_data_client/cache.py`
- [ ] T055 [P] [US1] Port fallback modes — `packages/dk-data-client/python/dk_data_client/fallback.py`
- [ ] T056 [P] [US1] Implement Python telemetry push to Loki — `packages/dk-data-client/python/dk_data_client/telemetry.py`
- [ ] T057 [P] [US1] Implement Python modules (mirrors TS) — `packages/dk-data-client/python/dk_data_client/modules/`
- [ ] T058 [P] [US1] Implement sync facade (`dk_data_client.sync`) — `packages/dk-data-client/python/dk_data_client/sync.py`

### 3d — Testing

- [ ] T059 [P] [US1] TS unit tests: all modes, all errors, cache TTL — `packages/dk-data-client/typescript/tests/unit/` (US-14)
- [ ] T060 [P] [US1] Python unit tests: same coverage — `packages/dk-data-client/python/tests/unit/` (US-14)
- [ ] T061 [US1] Integration test harness: spin ephemeral dk-data-FE + metering proxy in CI — `packages/dk-data-client/tests/integration/fixtures.py` (US-14)
- [ ] T062 [P] [US1] TS integration tests against ephemeral instance — `packages/dk-data-client/typescript/tests/integration/` (US-14)
- [ ] T063 [P] [US1] Python integration tests against ephemeral instance — `packages/dk-data-client/python/tests/integration/` (US-14)
- [ ] T064 [US1] Contract test: client type fingerprint matches live OpenAPI — `packages/dk-data-client/tests/contract/test_schema_fingerprint.py` (US-14)
- [ ] T065 [US1] Publish `v0.1.0` to internal npm + PyPI registries — `packages/dk-data-client/.github/workflows/release.yml` (US-1)

### 3e — Hydration heat map dashboard

- [ ] T066 [US1] Create `grafana/dashboards/dk-data-adapter-telemetry.json` with panels for hit/miss/fallthrough/error per method + p99 latency + top fallthroughs — `grafana/dashboards/dk-data-adapter-telemetry.json` (US-7)

---

## Phase 4 — Warehouse migrations (P1, sequenced)

*These MUST run in order 215 → 216 → 217 → 218. Cannot parallelize.*

- [ ] T067a [HIGH] Code review of migrations 215–218 + 220 before merge: verify each is DML-free (DDL/DCL only), idempotent (IF NOT EXISTS / CREATE OR REPLACE), wrapped in transactions, has a `SET statement_timeout = '60s'` + `SET lock_timeout = '30s'` guard — checklist in `docs/reviews/migrations-215-220.md`
- [ ] T067 [US6] Write migration `215_ci_views_domain_relocate.sql` — create `ip_api` schema, relocate 10 unprefixed views with deprecated aliases — `src/dk_data/sql/migrations/215_ci_views_domain_relocate.sql`
- [ ] T068 [US6] Add `ip_api` to `PGRST_DB_SCHEMAS` in k8s configmap — `k8s/apps/postgrest/base/configmap.yaml`
- [ ] T068a [HIGH] PostgREST deployment HA validation: verify ≥2 replicas AND `PodDisruptionBudget minAvailable: 1`; measure rolling-update duration on staging; ensure zero-downtime deploy — `k8s/apps/postgrest/base/deployment.yaml`, `k8s/apps/postgrest/base/pdb.yaml`
- [ ] T069 [US6] Add `ip_api` to standalone `postgrest.conf` + `docker-compose.yml` — `src/dk_data/postgrest.conf`, `docker-compose.yml`
- [ ] T070 [US6] Write `tests/migrations/test_215_ci_rename.py` — verify all 10 new views exist, deprecated aliases still return data — `tests/migrations/test_215_ci_rename.py` (US-14)
- [ ] T071 [US4] Write migration `216_missing_mol_api_views.sql` — create boxed_warnings, contraindications, competitive_scores, companies, publications — `src/dk_data/sql/migrations/216_missing_mol_api_views.sql`
- [ ] T072 [US4] Write `tests/migrations/test_216_missing_views.py` — verify views exist, grants present, queries return data — `tests/migrations/test_216_missing_views.py` (US-14)
- [ ] T073 [US5] Write migration `217_resolve_function_grants.sql` — EXECUTE grants on 11 resolve functions — `src/dk_data/sql/migrations/217_resolve_function_grants.sql`
- [ ] T074 [US5] Write `tests/migrations/test_217_resolve_grants.py` — verify every resolve function is callable by analyst + api_user — `tests/migrations/test_217_resolve_grants.py` (US-14)
- [ ] T075 [US5] Add 7 FastAPI wrapper routes: `/data-platform/{conditions,companies,providers,facilities,researchers,patents,trademarks}/resolve` — `src/dk_data/api/routes/data_platform.py`
- [ ] T076 [US5] Write tests for new FastAPI resolve wrappers — `tests/api/test_resolve_wrappers.py` (US-14)

### Phase 4b — web_anon drop (MUST be last)

- [ ] T077 [US2] Write migration `218_drop_web_anon.sql` — dynamic revoke + drop — `src/dk_data/sql/migrations/218_drop_web_anon.sql`
- [ ] T078 [US2] Write rollback migration `218_drop_web_anon_rollback.sql` — restore minimum grants only — `src/dk_data/sql/migrations/218_drop_web_anon_rollback.sql`
- [ ] T079 [US2] Write `docs/runbooks/rollback-web-anon-drop.md` — `docs/runbooks/rollback-web-anon-drop.md` (US-16)
- [ ] T080 [US2] Strip `web_anon` references from init scripts — `scripts/dev-init.sql`, `src/dk_data/sql/init_database.sql`, `.github/workflows/ci.yaml`
- [ ] T081 [US2] Strip `web_anon` grants from `k8s/apps/infrastructure/base/db-init-job.yaml`: search for every `GRANT ... TO web_anon` and `CREATE ROLE web_anon` and remove them. Replace role-creation blocks with `RAISE EXCEPTION 'web_anon is forbidden'` guards — `k8s/apps/infrastructure/base/db-init-job.yaml`
- [ ] T082 [US2] Strip `web_anon` grants from `post_sqlmesh/055_postgrest_hub_grants.sql` (entire `web_anon` block) — `src/dk_data/sql/post_sqlmesh/055_postgrest_hub_grants.sql`
- [ ] T083 [US2] Strip `web_anon` grants from `post_sqlmesh/043_api_materialized_views.sql` — `src/dk_data/sql/post_sqlmesh/043_api_materialized_views.sql`
- [ ] T084 [US2] Strip `web_anon` grants from migrations 061, 086, 092, 117, 136 — 5 files
- [ ] T085 [US2] Delete the stale comment block in `postgrest/base/deployment.yaml` that says "HTTP probes require api.health view to exist and web_anon role to have USAGE on schema api" — the comment contradicts the actual TCP-only probe config that follows it — `k8s/apps/postgrest/base/deployment.yaml`
- [ ] T086 [US2] Unset `PGRST_DB_ANON_ROLE` in k8s configmap — remove the `PGRST_DB_ANON_ROLE: "web_anon"` line from `k8s/apps/postgrest/base/configmap.yaml`
- [ ] T087 [US2] Unset `db-anon-role` in standalone `postgrest.conf` + `docker-compose.yml` — 2 files
- [ ] T088 [US2] Write `tests/migrations/test_218_drop_web_anon.py` — verify role dropped, rollback restores minimum — `tests/migrations/test_218_drop_web_anon.py` (US-14)
- [ ] T088a [HIGH] Run migration 218 on staging with realistic schema/table count; measure execution time and total ACCESS EXCLUSIVE lock duration; document in runbook — `docs/runbooks/rollback-web-anon-drop.md`
- [ ] T088b [HIGH] Document migration 218 lock contention risk: REVOKE ... ON ALL TABLES IN SCHEMA takes ACCESS EXCLUSIVE per table. Run during maintenance window OR with explicit `SET lock_timeout = '30s'` + retry loop. Add alerting hook if lock waits exceed 30s — `docs/runbooks/rollback-web-anon-drop.md`
- [ ] T088c [HIGH] Pre-migration session handling: query `pg_stat_activity WHERE usename = 'web_anon'` immediately before running migration 218. If any sessions exist, force-disconnect via `pg_terminate_backend` (they will be broken by the drop anyway) — `docs/runbooks/rollback-web-anon-drop.md`
- [ ] T089 [US2] Apply migration 218 on **staging**; verify k8s probes still pass; verify `curl /molecules` returns 401; verify admin-app works end-to-end through adapter — `docs/runbooks/rollback-web-anon-drop.md`
- [ ] T089a [US2] After staging verification AND after all consumer migrations (T090–T107) verified, apply migration 218 on **production** via ArgoCD sync; monitor grafana for 401 spikes over 1 hour; run rollback drill if anything regresses — `docs/runbooks/rollback-web-anon-drop.md`

---

## Phase 5 — Consumer migration (US-13, P1)

*Migrate consuming apps in lockstep with Phase 4. Admin first (smallest blast radius).*

### 5a — behavior-labs-ai admin

**Phase 5 REMOVED — consumer-side migration is tracked in each consuming app's own spec (behavior-labs-ai, ground-truth-charlie, trials-predictor).** The work below stays as a reference pointer:

- Admin client migration → behavior-labs-ai spec (T090–T093 equivalent)
- CI client migration → behavior-labs-ai spec (T094–T096 equivalent)
- Research agent migration → behavior-labs-ai spec (T097–T100 equivalent)
- Ground-truth adapter replacement → ground-truth-charlie spec (T101–T105 equivalent)
- Trials-predictor resolve integration → trials-predictor spec (T106–T107 equivalent)

SC-026 (client v0.2 published in this repo) and SC-030 (go/no-go before production web_anon drop) are the observable gates that tie dk-data-FE's Phase 4b rollout to consumer-side readiness. This spec does not implement the consumer work; it just refuses to ship the lockdown until those external specs have confirmed their migrations are done.

---

## Phase 6 — Metrics cleanup (US-12, P1)

*Can run in parallel with Phase 5. Mostly code edits in dk-data-FE.*

**Serialization rule (drift audit D12):** Phase 6 tasks T108–T115 all edit `grafana/dashboards/*.json` or `src/dk_data/observability/metrics.py`. Only one person at a time may touch a given dashboard JSON file — `cms-pipeline-health.json`, `dk-data-pipeline-sources.json`, `dk-data-platform-status.json`, `dk-data-transformations.json`, `dk-data-api-services.json`. Coordinate via a shared doc; rebase downstream tasks after each merge. `metrics.py` edits also need to be serialized to avoid noisy merge conflicts during bulk emission wiring.

- [ ] T108 [P] [US12] Wire `record_pipeline_processing_duration()` into every SQLMesh layer transition — `src/dk_data/ingestion/transform_molecules.py`
- [ ] T109 [P] [US12] Add helper + decorator for `dk_bronze_ingestion_duration_seconds`; wrap base ingestion class — `src/dk_data/ingestion/base.py`, `src/dk_data/services/data_platform/metrics.py`
- [ ] T110 [US12] Wire all 18 `cms_*` metrics from CMS PUF agent code paths (add 15 helpers to `services/data_platform/metrics.py`, call from agent code) — `src/dk_data/agents/cms_puf/**/*.py`, `src/dk_data/services/data_platform/metrics.py`
- [ ] T111 [P] [US12] Delete dead metrics (**after T158 re-audit confirms they are still dead at Phase 6 start time**): `HTTP_REQUESTS_TOTAL`, `HTTP_REQUEST_DURATION_SECONDS`, `DB_QUERY_DURATION_SECONDS` — `src/dk_data/observability/metrics.py`
- [ ] T112 [P] [US12] Wire up or delete the remaining dead `DK_*` metrics from the **re-audit output** (NOT the stale list from the brief — T158 regenerates it at Phase 6 start). The 38-count in the brief is a snapshot; actual count may differ — `src/dk_data/observability/metrics.py`, various call sites
- [ ] T113 [US12] Write `tests/observability/test_metric_coverage.py` — fails CI on dead metrics or undefined dashboard refs — `tests/observability/test_metric_coverage.py` (US-14)
- [ ] T114 [US12] Write dashboard smoke test — `tests/observability/test_dashboard_smoke.py` (US-14)
- [ ] T114a [MEDIUM] Prometheus cardinality check: after US-12 cleanup, calculate estimated cardinality of live metrics. Alert if any metric exceeds 1K cardinality combinations. Add to `tests/observability/test_metric_coverage.py` — `tests/observability/test_metric_cardinality.py`
- [ ] T115 [US12] Manual label-selector audit across all 5 dashboards — document outcomes in `docs/reports/dashboard-audit.md`
- [ ] T116 [US12] Add three-way binding principle to `.dk/memory/principles.md` — `.dk/memory/principles.md`

---

## Phase 7 — Documentation, cronjob cleanup, lessons (US-16, US-20, US-18, US-19)

*Parallel with Phase 5/6. Mostly file authoring and YAML deletion.*

### 7a — Runbooks & docs (US-16)

- [ ] T117 [P] [US16] Write `docs/runbooks/metering-proxy-401-debug.md` — `docs/runbooks/metering-proxy-401-debug.md`
- [ ] T118 [P] [US16] Write `docs/runbooks/adapter-fallthrough-spike.md` — `docs/runbooks/adapter-fallthrough-spike.md`
- [ ] T119 [P] [US16] Write `docs/runbooks/dashboard-no-data.md` — `docs/runbooks/dashboard-no-data.md`
- [ ] T120 [P] [US16] Update `README.md` with adapter usage, auth model, env vars — `README.md`
- [ ] T121 [P] [US16] Write `docs/consumer-onboarding.md` — `docs/consumer-onboarding.md`
- [ ] T122 [P] [US16] Update `docs/architecture.md` with auth flow diagram — `docs/architecture.md`
- [ ] T123 [P] [US16] Write `docs/data-catalog.md` (endpoint → schema → owner mapping) — `docs/data-catalog.md`
- [ ] T124 [P] [US16] Update `.dk/memory/lessons.md` with 7 captured lessons — `.dk/memory/lessons.md`
- [ ] T125 [P] [US19] Add unprefixed-schema carve-out table to `CLAUDE.md` "Active PostgreSQL Schemas" — `CLAUDE.md`
- [ ] T126 [P] [US18] Document the three `agents`/`mol_agents`/`hcs_agents` schemas in CLAUDE.md schema reference — `CLAUDE.md`

### 7b — Cronjob cleanup (US-20 / issue #277)

- [ ] T127a [HIGH / F-D016] Specify consolidated chembl job as **single sequential cronjob** (reverted from fan-out per drift audit D2b). Contract: each cron tick of `cronjob-fetch-chembl-activities.yaml` reads `meta.backfill_state`, finds the next un-backfilled year, fetches that ONE year, updates state, exits. 17 ticks = 17 years complete. After initial backfill, subsequent ticks keep the latest year current. **No parallel dispatch, no new orchestrator feature needed.** Document in `docs/runbooks/chembl-consolidation.md`
- [ ] T127b [HIGH] Idempotency test for the sequential consolidated job: run twice with `meta.backfill_state` pointing at year 2024; verify `mol_raw.chembl` row count is unchanged after second run (INSERT ... ON CONFLICT DO NOTHING enforced) — `tests/cronjobs/test_chembl_idempotency.py`
- [ ] T127c [MEDIUM] Document the sequential dispatch pattern in `docs/runbooks/chembl-consolidation.md` — covers: cron cadence (10 min tick from backfill orchestrator), state progression via `meta.backfill_state.last_year_processed`, per-year WAL budget under 2 GB `[WALMX]`, failure → retry on next tick (resumable via `meta.refresh_state.last_chunk_position`), total wall-clock for initial backfill = 170 min minimum
- [ ] T127d [HIGH] Same sequential pattern for `cronjob-fetch-pubchem.yaml`: each tick processes one of 6 CID ranges (range_1 → range_6), advancing through `meta.backfill_state`. 6 ticks = full backfill. Document in `docs/runbooks/pubchem-consolidation.md`
- [ ] T127 [US20] Delete 17 `cronjob-fetch-chembl-activities-{2010..2026}.yaml` files — `k8s/apps/cronjobs/base/`
- [ ] T128 [US20] Delete 6 `cronjob-fetch-pubchem-range-{1..6}.yaml` files — `k8s/apps/cronjobs/base/`
- [ ] T129 [US20] Delete `cronjob-fetch-cms-puf-all.yaml` and `cronjob-fetch-cms-cost-reports-puf-lines.yaml` — `k8s/apps/cronjobs/base/`
- [ ] T130 [US20] Run `kubectl apply --dry-run=server` to verify 25 fewer files apply cleanly — `k8s/apps/cronjobs/base/`
- [ ] T131 [US20] Write migration `220_align_source_naming.sql` — `src/dk_data/sql/migrations/220_align_source_naming.sql`
- [ ] T132 [US20] Update Python ingestion modules + remaining cronjob YAMLs to use canonical source names — `src/dk_data/ingestion/sources/`, `k8s/apps/cronjobs/base/`
- [ ] T133 [US20] Update `build_model_lineage.py` if subdomain lookup references any old names — `src/dk_data/ingestion/utils/build_model_lineage.py`
- [ ] T134 [US20] Update `consumers.yaml` allowlists if any referenced old source names — `k8s/apps/metering-proxy/base/configmap.yaml`
- [ ] T135 [US20] Add CI check enforcing naming consistency (backfill_state ↔ raw tables ↔ Python modules). **Blocks on T131–T134 complete** — the check must pass on a green state before it can be enforced — `.github/workflows/ci.yaml`
- [ ] T136 [US20] Close GitHub issue [#277](https://github.com/data-kinetic/cd-data-FE/issues/277)

### 7c — US-10 molecule_profile collision

- [ ] T137 [US10] Determine canonical name (`mol_gold.molecule_profile` likely wins — used by conditional `api.molecule_properties` view) — `docs/decisions/molecule-profile-canonical.md`
- [ ] T138 [US10] Drop the non-canonical table; update any references — SQL migration + `src/dk_data/sqlmesh/models/molecules/gold/`

---

## Phase 8 — Telemetry-driven hydration (US-7, P2)

*Runs after adapter has been in prod for ≥ 2 weeks.*

- [ ] T139 [US7] Review hydration heat map after 2 weeks of production traffic — `grafana/dashboards/dk-data-adapter-telemetry.json`
- [ ] T140 [US7] Rank fallthrough_upstream + fallthrough_hydrate counts per method; produce prioritized ingestion list — `docs/reports/hydration-priority-2026-Q2.md`
- [ ] T141 [US7] Ingest top Tier-1 sources based on telemetry (tentative: SEC EDGAR, BioRxiv, Semantic Scholar, DailyMed, UMLS/RxNorm full, FDA Orange Book) — `src/dk_data/ingestion/sources/`
- [ ] T142 [US7] For each new source, add classification to `build_model_lineage.py` and create nodeGraph panel in dashboard — `src/dk_data/ingestion/utils/build_model_lineage.py`, `grafana/dashboards/dk-data-transformations.json`
- [ ] T143 [US7] Create `ind-terminology` subdomain in lineage builder for UMLS/SNOMED/ICD/MeSH/ATC — `src/dk_data/ingestion/utils/build_model_lineage.py`

---

## Phase 9 — Polish & follow-up

- [ ] T144 [P] Add Grafana alert on zero gold-table row counts for >24h — `grafana/dashboards/dk-data-transformations.json` (US-8, US-11)
- [ ] T145 [P] Add `hydrate` fallback mode to client v1.0 (after Phase 4 ingestion endpoints verified idempotent) — `packages/dk-data-client/typescript/src/fallback/hydrate.ts`, `packages/dk-data-client/python/dk_data_client/fallback.py` (US-1)
- [ ] T146 [P] Drop deprecated `api.*` aliases 30 days after last telemetry-verified consumer cutover — new migration file (US-6)
- [ ] T147 [P] Cost/capacity sign-off from infrastructure team — `docs/reports/capacity-signoff.md` (US-17)
- [ ] T148 [P] Update test.architect coverage report — verify `[TESTE]` tag satisfied for new code paths — `docs/reports/test-coverage-2026-04.md`

---

## Phase 10 — Anti-drift controls (inserted post-audit)

*Tasks that prevent the feature branch from drifting relative to main, prevent cross-artifact inconsistency, and prevent implementation-reality divergence during the multi-week rollout.*

### 10a — Adapter version lifecycle

- [ ] T149 [CRITICAL / D1] Adapter v0.2 type regeneration: immediately after migration 216 lands, run type-gen against the updated PostgREST OpenAPI; publish `@datakinetic/dk-data-client` v0.2.0 with the new types. Consumer apps bump via their own PR cycle — `packages/dk-data-client/.github/workflows/release.yml`
- [ ] T150 [D1] Client `serverInfo()` schema fingerprint check must warn on mismatch, NOT throw. Warn-only behavior preserves v0.1 consumers running against post-migration dk-data for the transition window — `packages/dk-data-client/typescript/src/version.ts`, `packages/dk-data-client/python/dk_data_client/client.py`
- [ ] T151 [D1] Document the v0.1 → v0.2 transition window in `docs/consumer-onboarding.md`: expect fingerprint warnings between migration 216 landing and consumer v0.2 upgrade. Target window ≤ 7 days — `docs/consumer-onboarding.md`

### 10b — Backfill orchestrator feature verification

- [ ] T152 [D2 RESOLVED / F-D016] Single-sequential-backfill decision recorded: the consolidated chembl + pubchem cronjobs run ONE per tick via the existing backfill orchestrator; no fan-out feature needed. T127a-d fully cover the implementation. Verify at execution time that `meta.backfill_state` has columns for `last_year_processed` / `last_range_processed` or equivalent; if missing, add them in migration 220 (piggyback on the source-naming alignment) — `src/dk_data/sql/migrations/220_align_source_naming.sql`
- [ ] T152a [D2] Verify `meta.backfill_state` schema supports sequential year/range progression: needs at least `source_name`, `status`, `last_year_processed` (INT, nullable), `last_range_processed` (INT, nullable), `last_run_at` (TIMESTAMPTZ). If columns missing, add in migration 220 — `src/dk_data/sql/migrations/220_align_source_naming.sql`
- [ ] T152b [D2] Update US-20 scope in spec.md to reflect the 25-file deletion holds (17 chembl + 6 pubchem + 2 dead), with the clarification that deleted jobs are replaced by SEQUENTIAL parameterized cronjobs, not parallel fan-out — `spec.md` US-20

### 10c — Pre-migration schema audit

- [ ] T153 [CRITICAL / D3] Before writing migration 216 publications view: read actual column definitions of `mol_api.pubmed_publications` and `mol_api.openalex_publications` (post-215 state in staging). Produce a column-mapping table: (pubmed.column, type) → (openalex.column, type) → (publications.column, type). Document coercions — `docs/reviews/migration-216-column-audit.md`
- [ ] T153a [D3] Update `contracts/migration-ddl.md` publications view DDL with the verified column list from T153 — `contracts/migration-ddl.md`

### 10d — Memory commit discipline

- [ ] T154 [CRITICAL / D4] `.dk/memory/decisions.md` and `.dk/memory/tags.md` edits (D008-D015 + `[ZVAL]`/`[VERSN]`/`[RBAC]`/`[AUDIT]` activations) are global memory. Do NOT land these until feature PR merges. Track as a conditional commit — if feature is cancelled mid-flight, revert memory edits — `.dk/memory/decisions.md`, `.dk/memory/tags.md`
- [ ] T154a [D4] Consider moving feature-scoped decisions into `.dk/specs/002-external-integration-foundation/memory/decisions.md`; only promote to global `.dk/memory/decisions.md` at merge — feature-level memory file

### 10e — Anti-drift process controls

- [ ] T155 [HIGH / D5] Migration renumber-at-merge policy: tasks.md references migrations 215-218, but another feature may land 215 first. **Immediately before merging:** check the highest number in `src/dk_data/sql/migrations/` on main, renumber if needed, update tasks.md, re-run tests — `docs/reviews/migration-renumber-check.md`
- [x] T156 [HIGH / D6] **COMPLETED as part of the drift-fix pass 2026-04-13.** Hardcoded line numbers replaced with semantic anchors in T002 (startupProbe/livenessProbe/readinessProbe blocks), T012 (`_SKIP_SCHEMAS` set), T017 (job_complete handler + `record_job_duration`/`report_job_records`/`inc_job_failures` functions), T081 (`GRANT ... TO web_anon` search), T085 (comment block contradicting TCP-only probes), T086 (`PGRST_DB_ANON_ROLE: "web_anon"` line removal). Remaining task: audit any NEW tasks added after 2026-04-13 to ensure they follow the same convention — `tasks.md`
- [ ] T157 [HIGH / D7] Align L2 cache TTL with actual refresh cadence: gold table transform runs daily at 22:00 UTC, so `competitive_landscape` L2 TTL should be 24h, not 6h. Same for `lifecycle_stages`, `safety_signals`, `molecule_profile`, `company_pipeline`. Update cache TTL table in plan.md Phase 0, contracts/client-package-api.md, and data-model.md — `plan.md`, `contracts/client-package-api.md`, `data-model.md`
- [ ] T158 [HIGH / D8] Re-audit the dead-metrics list at the start of Phase 6 (before T108): grep `src/dk_data/observability/metrics.py` and every call site, regenerate the list. Do NOT trust the 38-metric list from the dk.auto brief — it was snapshotted at audit time — `tests/observability/test_metric_coverage.py`
- [ ] T159 [HIGH / D9] Rebase cadence: rebase `feature/002-external-integration-foundation` onto `main` at least weekly. Identify merge-conflict hotspots up front (data_platform.py, configmap.yaml, metrics.py, deployment.yaml, dashboard JSONs) and coordinate with anyone else editing them — `docs/reviews/rebase-log.md`
- [ ] T160 [HIGH / D10] Pointer to each consuming app's spec: before T089a (production web_anon drop) fires, verify each consumer repo's spec has its migration tasks checked off. Reference the separate specs, do not own them. Capture outcome in `docs/reports/phase-5-coordination.md` — read-only coordination pointer

### 10f — Contract/implementation consistency

- [ ] T161 [MEDIUM / D11] When each migration (215-218, 220) is actually written at T067/T071/T073/T077/T131, diff the written SQL against the corresponding section in `contracts/migration-ddl.md`. If drift: update contracts to match implementation (contracts follow code) — `contracts/migration-ddl.md`
- [ ] T162 [MEDIUM / D12] Serialize dashboard JSON edits: Phase 6 tasks T108-T112 + T115 all touch the same 5 JSON files. Process: one dev at a time touches dashboards; after each merge, downstream tasks rebase — workflow documentation
- [ ] T163 [MEDIUM / D13] Every verification task (T001-T009, T067a, T088a-c) MUST write an artifact to `docs/reports/<task>.md` showing the command run + timestamp + result. Checkbox in tasks.md is NOT sufficient — `docs/reports/`
- [ ] T164 [MEDIUM / D14] CI lint to enforce open-question defaults. Add these checks to the client package CI workflow:
  - Q10 default (TS HTTP): `grep -r "from ['\"]axios['\"]" typescript/src/` → fail on any match; same for `ky`, `node-fetch`, `got`. Only native `fetch` + `undici` allowed.
  - Q10 default (Python HTTP): `grep -r "import requests" python/dk_data_client/` → fail; `aiohttp` → fail. Only `httpx` allowed.
  - Q9 default (cache backend): `grep -r "from ['\"]memcached" typescript/src/ python/dk_data_client/` → fail. Only Redis or SQLite allowed.
  - Q13 default (telemetry): assert `telemetry.emit()` is called at most once per adapter method invocation; no batching logic in v0.1.
  - Q11 default (monorepo): the client package must live in its own repo, not be co-located with dk-data-FE. CI failing if `packages/dk-data-client/` path appears inside dk-data-FE.
  - Generated files regeneration: if `types.ts` or `models.py` is edited by a human (no CI regeneration comment header), fail.
  — `packages/dk-data-client/.github/workflows/lint.yml`
- [ ] T165 [MEDIUM / D15] Document that `mol_raw.chembl` → `mol_raw.chembl_molecules` rename is explicitly OUT OF SCOPE for this initiative. Add guard migration if necessary — `spec.md` Non-Goals section

### 10g — Mid-implementation drift detection

- [ ] T166 [HIGH] Run `/dk.analyze` again when Phase 3 (adapter v0.1) is complete, before Phase 4 starts. Any spec/plan/task inconsistencies get fixed before migration work begins.
- [ ] T167 [HIGH] Run `/dk.analyze` again when Phase 4 (migrations) is complete, before Phase 5 (consumer migration) starts.
- [ ] T168 [HIGH] Run `/dk.analyze` once more when Phase 5 is complete, before Phase 4b production cutover (T089a).

### 10h — Real-time state audit before T089a

- [ ] T169 [CRITICAL] Immediately before T089a (production drop of web_anon):
  - Re-run T001d `pg_stat_activity` audit — confirm no in-flight `web_anon` sessions on prod
  - Re-verify all Phase 1b success criteria (SC-021 through SC-025) still pass
  - Confirm every consumer app's adapter version is verified working via metering proxy
  - Confirm the feature-flag pattern: a KILL SWITCH exists to roll back within 5 minutes
  - Get explicit sign-off from the on-call engineer — `docs/runbooks/phase-4b-go-no-go.md`

---

## Dependencies & Execution Order

```
Phase 1 (Setup & Verification)                [T001–T009, sequential]
   ↓
Phase 2a (Dev hygiene + metrics infra)        [T010–T018, parallelizable]
Phase 2b (Gateway hardening)                   [T019–T025, T019 first then parallel]
Phase 2c (FastAPI auth)                        [T026–T029, sequential]
   ↓
   ├── Phase 3 (Adapter v0.1)                 [T030–T066]
   │      Ships against CURRENT PostgREST surface.
   │      NOT blocked by Phase 4.
   │      T065 (publish v0.1) is the milestone.
   │
   ├── Phase 4a (Migrations 215/216/217)     [T067–T076, HARD SEQUENCED]
   │      215 rename → 216 missing views → 217 resolve grants
   │      CAN run in parallel with Phase 3.
   │
   └── Phase 6 (Metrics cleanup)              [T108–T116]
          Fully parallel with Phase 3 + Phase 4a.
   ↓
Phase 5a (Admin migration)                    [T090–T093, sequential]
   Requires T065 (adapter v0.1 published) + Phase 4a (migrations 215/216/217) complete.
   ↓
Phase 4b (Drop web_anon)                      [T077–T089]
   T077 BLOCKED until T089a's "all consumer migrations verified" gate.
   Actually sequencing: apply 218 on STAGING first (T089), then prod (T089a).
   ↓
Phase 5b–5e (Remaining consumers)             [T094–T107]
   CI client, research agents, ground-truth, trials-predictor.
   5c, 5d, 5e parallel.
   ↓
Phase 4b production (T089a — apply 218 on prod)
   Final breaking change. BLOCKED until Phase 5a–5e complete.
   ↓
Phase 7 (Docs + Cronjobs)                     [T117–T138]
   Parallel with 5 + 6; most [P] tasks.
   ↓
Phase 8 (Telemetry-driven hydration)          [T139–T143]
   Waits ≥ 2 weeks after Phase 5 complete for telemetry warmup.
   ↓
Phase 9 (Polish)                              [T144–T148]
```

### Critical path blockers — the true ordering

**The single hardest constraint: T089a (apply migration 218 on production).** Nothing after it can assume `web_anon` exists. Everything before it must not depend on `web_anon` being gone. This is what drives sequencing.

Explicit blockers:

- **T067 (migration 215 rename)**: blocks on Phase 2 complete
- **T071 (migration 216 missing views)**: blocks on T067 (216 depends on `mol_api.pubmed_publications` existing)
- **T073 (migration 217 resolve grants)**: blocks on Phase 2 complete (parallel with T067, T071)
- **T077 (migration 218 drop web_anon — staging)**: blocks on T067, T071, T073 complete AND T019 (keys provisioned) AND T026–T029 (FastAPI auth) AND T065 (adapter v0.1 published) AND T093 (admin migrated + verified)
- **T089 (apply 218 on staging)**: blocks on T077 + all prior Phase 4a tasks
- **T089a (apply 218 on production)**: blocks on T089 staging green for ≥ 24 hours AND Phase 5 (all consumers migrated and verified in telemetry)
- **Phase 3 (adapter)**: does NOT block on Phase 4. Ships against current PostgREST surface via `Accept-Profile: mol_api`.
- **Phase 6 (metrics)**: fully parallel with Phase 3 + Phase 4a.
- **Phase 7 (docs + cronjobs)**: mostly parallel. T127–T130 (cronjob deletions) are zero-risk and can run any time after Phase 2.

### Parallel execution examples

Most of Phase 3 is `[P]` — once the package scaffold (T030–T035) is done, TS and Python core (T036–T058) run concurrently. Tests (T059–T064) parallelize within each language.

Phase 4 migrations are strictly sequential (215 → 216 → 217 → 218). Do not parallelize.

Phase 5 consumer migrations: 5c, 5d, 5e can run concurrently once 5a (admin) is verified.

Phase 7 documentation is fully parallel.

## Implementation Strategy

- **MVP-first**: Ship adapter v0.1 (Phase 3 complete) in the first week — this is the highest-leverage work per Nick's framing.
- **Don't block adapter on migrations**: Adapter v0.1 ships against the pre-cleanup PostgREST surface via `Accept-Profile: mol_api`. Migrations 215–218 ship in Phase 4 in parallel with consumer migration to the adapter.
- **Lockdown gated by adapter**: Do NOT run migration 218 until every consuming app is verified working through the metering proxy + adapter.
- **Consumer migration in lockstep**: T089 (apply 218 on prod) is the last breaking change. Every consumer must be on the adapter by then.
- **Metrics cleanup is orthogonal**: Phase 6 can run any time after Phase 2 lands. Does not block Phase 3 or Phase 5.
- **Cronjob cleanup and docs are safe**: Phase 7 tasks are pure additions/deletions with no runtime risk. Can run early for morale wins.

## Task Count Summary

| Phase | Tasks | Parallelizable |
|---|---|---|
| Phase 1 (Setup & Verification) | 9 | 0 (sequential verification) |
| Phase 2 (Foundational) | 20 | 13 |
| Phase 3 (Adapter) | 37 | 31 |
| Phase 4 (Migrations) | 23 | 0 (sequenced) |
| Phase 5 (Consumer Migration) | 18 | 9 |
| Phase 6 (Metrics Cleanup) | 9 | 6 |
| Phase 7 (Docs + Cronjobs) | 22 | 17 |
| Phase 8 (Hydration) | 5 | 0 (depends on telemetry lag) |
| Phase 9 (Polish) | 5 | 5 |
| **Total** | **148** | **81** |

## User Story Coverage

| Story | Priority | Tasks |
|---|---|---|
| US-1 (Adapter) | P1 | T030–T066 (37) |
| US-2 (Drop web_anon) | P1 | T077–T089 (13) |
| US-3 (Metering proxy) | P1 | T019–T025 (7) |
| US-4 (Missing views) | P1 | T071–T072 (2) |
| US-5 (Resolve functions) | P1 | T073–T076 (4) |
| US-6 (CI view rename) | P2 | T067–T070, T146 (5) |
| US-7 (Telemetry hydration) | P2 | T139–T143 (5) |
| US-8 (Gold verification) | P1 | T001, T144 (2) |
| US-9 (Config sync) | P2 | T010–T011 (2) |
| US-10 (Profile collision) | P3 | T137–T138 (2) |
| US-11 (DAG updates) | P2 | T012–T013, T018 (3) |
| US-12 (Metrics cleanup) | P1 | T014–T017, T108–T116 (13) |
| US-13 (Consumer migration) | P1 | T090–T107 (18) |
| US-14 (Test coverage) | P2 | T028, T059–T064, T070, T072, T074, T076, T088, T113–T114 (13) |
| US-15 (FastAPI auth) | P1 | T026–T029 (4) |
| US-16 (Docs) | P2 | T025, T079, T117–T124 (10) |
| US-17 (Cost/capacity) | P2 | T003–T004, T147 (3) |
| US-18 (Agents collision) | P3 | T126 (1) |
| US-19 (Naming carve-outs) | P3 | T125 (1) |
| US-20 (Cronjob cleanup) | P2 | T127–T136 (10) |
