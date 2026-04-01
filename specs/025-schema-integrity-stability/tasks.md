# Tasks: Schema Integrity & Platform Stability

**Input**: Design documents from `/specs/025-schema-integrity-stability/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. No tests are generated unless explicitly requested.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new project structure needed — all changes modify existing files. This phase handles prerequisite research only.

- [x] T001 Audit all loaders in `src/dk_data/ingestion/sources/` for ON CONFLICT clauses and verify matching UNIQUE constraints exist in migration files under `src/dk_data/sql/migrations/`
- [x] T002 [P] Audit all 8 affected MCP adapter files in `src/dk_data/services/mcp/adapters/` to confirm current state matches issue descriptions (no build_url overrides, base.py default behavior)

**Checkpoint**: Current state verified — implementation can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration 138 and init script alignment — MUST be complete before any source ingestion can be verified.

**CRITICAL**: No user story verification can happen until the database schema is correct.

- [x] T003 Create migration `src/dk_data/sql/migrations/138_schema_integrity.sql` with: (a) ALTER TABLE `meta.refresh_log` RENAME COLUMN `started_at` TO `refresh_started_at` and `completed_at` TO `refresh_completed_at` (use DO block with NAMED dollar-quoting per dk-canon, e.g. `DO $migrate$ BEGIN ... END $migrate$` — staged `$$` is FORBIDDEN), (b) CREATE UNIQUE INDEX IF NOT EXISTS `uidx_mol_raw_pubchem_cid` ON `mol_raw.pubchem` `((response_body->>'cid'))`, (c) CREATE UNIQUE INDEX IF NOT EXISTS `uidx_mol_raw_chembl_molecules_chembl_id` ON `mol_raw.chembl_molecules` `((response_body->>'molecule_chembl_id'))`, (d) CREATE UNIQUE INDEX IF NOT EXISTS `uidx_mol_raw_who_gho_indicator_code` ON `mol_raw.who_gho` `((response_body->>'IndicatorCode'))`, (e) CREATE TABLE IF NOT EXISTS `mol_raw.cdc_vaccines` with standard envelope schema (BIGSERIAL id, request_id VARCHAR NOT NULL UNIQUE, request_timestamp, api_endpoint, api_version, request_params JSONB, request_headers JSONB, response_status INTEGER, response_headers JSONB, response_body JSONB, response_body_hash VARCHAR, response_size_bytes INTEGER, response_time_ms INTEGER, processed_to_bronze BOOLEAN DEFAULT FALSE, processed_at TIMESTAMPTZ, processing_error TEXT, ingested_at TIMESTAMPTZ DEFAULT NOW(), source_id INTEGER), (f) INSERT INTO `meta.data_sources` (source_name, source_type, is_active) VALUES ('cdc_vaccines', 'api', true) ON CONFLICT (source_name) DO NOTHING — required for ingestion orchestrator to resolve source_id
- [x] T004 [P] Fix `scripts/dev-init.sql` — change ONLY `started_at` to `refresh_started_at` and `completed_at` to `refresh_completed_at` in the `meta.refresh_log` CREATE TABLE statement. Do NOT modify any other part of the file (preserves API views, role grants, and all other schema definitions per dk-canon db-init requirements)
- [x] T005 [P] Verify `src/dk_data/sql/init_database.sql` already uses `refresh_started_at` and `refresh_completed_at` — if not, fix it to match

**Checkpoint**: Database schema is consistent across all init scripts and migrations. ON CONFLICT upserts will work for pubchem, chembl_molecules, who_gho.

---

## Phase 3: User Story 1 — All scheduled ingestion jobs complete without DB errors (Priority: P1) MVP

**Goal**: pubchem, chembl_molecules, who_gho insert >0 records; refresh_log tracks all ingestions; cdc_vaccines table exists.

**Independent Test**: Run `python -m dk_data.ingestion.main pubchem --max-records 100` and verify records_inserted > 0 and `meta.refresh_log` has a new row with non-NULL `refresh_started_at`/`refresh_completed_at`.

### Implementation for User Story 1

- [x] T006 [US1] Verify the pubchem loader ON CONFLICT clause in `src/dk_data/ingestion/sources/pubchem.py` matches the new UNIQUE index expression `(response_body->>'cid')` exactly — fix if mismatched
- [x] T007 [P] [US1] Verify the chembl_molecules loader ON CONFLICT clause in `src/dk_data/ingestion/sources/chembl_molecules.py` matches the new UNIQUE index expression `(response_body->>'molecule_chembl_id')` exactly — fix if mismatched
- [x] T008 [P] [US1] Verify the who_gho loader ON CONFLICT clause in `src/dk_data/ingestion/sources/who_gho.py` matches the new UNIQUE index expression `(response_body->>'IndicatorCode')` exactly — fix if mismatched
- [x] T009 [US1] Verify the refresh_log INSERT in `src/dk_data/ingestion/main.py` (around line 1159) uses column names `refresh_started_at` and `refresh_completed_at` — fix if mismatched
- [x] T010 [US1] Verify the cdc_vaccines fetcher in `src/dk_data/ingestion/fetchers/cdc_vaccines.py` inserts into `mol_raw.cdc_vaccines` with columns matching the table DDL from T003

**Checkpoint**: All 3 previously broken sources (pubchem, chembl_molecules, who_gho) can upsert records. Refresh log tracks every ingestion. cdc_vaccines table ready.

---

## Phase 4: User Story 2 — Ingestion jobs do not crash with OOMKill (Priority: P1)

**Goal**: 5 CronJobs have sufficient memory limits to complete without OOMKill.

**Independent Test**: `kubectl get cronjob fetch-sider -n dk-data -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].resources.limits.memory}'` returns `1Gi`.

### Implementation for User Story 2

- [x] T011 [P] [US2] In `k8s/apps/cronjobs/base/cronjob-fetch-sider.yaml`, change memory request from `256Mi` to `512Mi` and memory limit from `512Mi` to `1Gi`
- [x] T012 [P] [US2] In `k8s/apps/cronjobs/base/cronjob-fetch-cms-imaging-puf.yaml`, change memory request from `256Mi` to `512Mi` and memory limit from `512Mi` to `1Gi`
- [x] T013 [P] [US2] In `k8s/apps/cronjobs/base/cronjob-fetch-cms-pecos.yaml`, change memory request from `256Mi` to `512Mi` and memory limit from `512Mi` to `1Gi`
- [x] T014 [P] [US2] In `k8s/apps/cronjobs/base/cronjob-fetch-hrsa.yaml`, change memory request from `256Mi` to `512Mi` and memory limit from `512Mi` to `1Gi`
- [x] T015 [P] [US2] In `k8s/apps/cronjobs/base/cronjob-fetch-cms-formulary.yaml`, change memory request from `512Mi` to `1Gi` and memory limit from `2Gi` to `4Gi`

**Checkpoint**: All 5 CronJobs have sufficient memory. Deploy to staging and trigger each to verify no OOMKills.

---

## Phase 5: User Story 5 — Schema consistency across all medallion layers (Priority: P1)

**Goal**: Verify all table prefixes are correct and no columns are dropped between raw and bronze layers.

**Independent Test**: For each domain-specific raw table, the corresponding bronze model SELECT list includes all raw columns.

### Implementation for User Story 5

- [x] T016 [US5] Audit all mol_raw domain-specific tables (non-envelope pattern: openalex_ci, orcid, cochrane_reviews, etc.) — compare DDL column lists in migrations against corresponding bronze model SELECT lists in `src/dk_data/sqlmesh/models/molecules/bronze/`. Document any missing columns.
- [x] T017 [P] [US5] Audit all hcs_raw domain-specific tables (cms_nppes, cms_physician_puf, cms_inpatient_puf, cms_outpatient_puf, etc.) — compare DDL column lists in migrations against corresponding bronze model SELECT lists in `src/dk_data/sqlmesh/models/hcs/bronze/`. Document any missing columns.
- [ ] T018 [US5] For each column mismatch found in T016/T017, fix the bronze model SQL to include the missing column(s), using appropriate type casting from the raw table
- [x] T019 [US5] Verify all 238 SQLMesh model files use correct domain prefixes (mol_raw/mol_bronze/mol_silver/mol_gold, hcs_raw/hcs_bronze/hcs_silver/hcs_gold, ind_raw/ind_bronze/ind_silver/ind_gold) — fix any mismatches
- [x] T020 [US5] For each fetcher with domain-specific columns (not envelope pattern), verify INSERT column list matches the raw table DDL. Check fetchers in `src/dk_data/ingestion/fetchers/` against table definitions. Fix any mismatches to use API response field names as authoritative source.

**Checkpoint**: All table prefixes verified. All columns flow from raw to bronze without loss. API field names are authoritative through the pipeline.

---

## Phase 6: User Story 3 — External API fetchers handle endpoint changes (Priority: P2)

**Goal**: cochrane, openfda_faers, and imgt fetchers either work or fail with clear messages.

**Independent Test**: Run each fetcher with `--max-records 10` and verify either data returned or a clear structured error (not a generic 404/403).

### Implementation for User Story 3

- [x] T021 [US3] In `src/dk_data/ingestion/fetchers/cochrane.py`, replace the fetch logic with an early return that sets status to `source_unavailable` and includes message: "Cochrane Library API (/api/search) has been removed. Requires Wiley institutional API license. No free endpoint available." Preserve the existing function signature and return format.
- [x] T022 [P] [US3] In `src/dk_data/ingestion/fetchers/openfda_faers.py`, find the open-ended query with `TO 99991231` (around line 107) and replace `99991231` with `datetime.now().strftime('%Y%m%d')`. Add `from datetime import datetime` import if not present. This fixes the 403 Forbidden error from the FDA API. IMPORTANT: Leave the year-partitioned query on ~line 150 (`{year}0101 TO {year}1231`) unchanged — it is correct as-is.
- [x] T023 [P] [US3] In `src/dk_data/ingestion/fetchers/imgt.py`, add HTTP response status checking after the download attempt. If the response status is not 200, return a structured error dict with `status: 'source_unavailable'`, `error: f'IMGT endpoint returned HTTP {status_code}'`, and `url: <the attempted URL>`. Keep existing logic for successful downloads.

**Checkpoint**: openfda_faers returns data. cochrane returns clear unavailable message. imgt either returns data or clear error.

---

## Phase 7: User Story 4 — MCP data-tool adapters return useful responses (Priority: P3)

**SUPERSEDED by PR #190** (merged to staging 2026-04-01, SHA 1c74b90). PR #190 implemented all MCP adapter fixes with a different architecture (standalone BaseMCPTool + router.py + 19 tests). All T024-T033 reverted from this branch to avoid conflicts.

- [x] T024-T033 — DROPPED: Fully covered by PR #190 (feat(mcp): MCP data-tool adapter layer + base_tool fixes)

**Checkpoint**: Verified PR #190 covers B1-B3 cross-cutting fixes, all 5 build_url overrides, all 3 bulk-only messages, router, and tests.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and cleanup across all work packages. Includes dk-canon feature branch checklist.

- [x] T034 Run full validation per `specs/025-schema-integrity-stability/quickstart.md` — apply migration, test all affected sources, verify refresh_log, test MCP adapters
- [ ] T035 [P] Verify no regressions: run `cd src && pytest tests/ -v` to ensure existing tests still pass
- [x] T036 [P] Run `kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null` and `kubectl kustomize k8s/overlays/prod --enable-helm > /dev/null` to verify K8s manifests are valid after CronJob changes
- [ ] T037 Run the dk-canon staging validation script: `./scripts/validate-staging-ingestion.sh` (phases 1-3) after deploying to staging. Verify: (a) job-trigger pod running, (b) meta.data_sources has >= 22 active sources including cdc_vaccines, (c) CronJobs deployed, (d) single-source manual runs succeed for pubmed/epo_ops/uniprot, (e) incremental fetch works
- [x] T038 [P] dk-canon feature branch checklist — verify all 10 items: (1) kustomize staging builds, (2) kustomize prod builds, (3) no `:latest` image tags in k8s/, (4) Doppler project is `dk-data-fe`, (5) POSTGRES_* env vars before PGRST_DB_URI in CronJob YAMLs, (6) PostgREST health probes use `/health`, (7) API views exist in dev-init.sql (api.health, api.data_catalog, api.targets, api.scoring, api.data_sources), (8) CI workflows present (.github/workflows/build-push.yaml, ci.yaml), (9) all SQL uses named dollar-quoting (no staged `$$`), (10) no hardcoded secrets in any file

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — audit/verification only
- **Foundational (Phase 2)**: No dependency on Phase 1 — can start immediately (but Phase 1 informs T003)
- **US1 (Phase 3)**: Depends on Phase 2 (migration must exist before verifying loaders match)
- **US2 (Phase 4)**: No dependency on Phase 2 — CronJob YAMLs are independent
- **US5 (Phase 5)**: No dependency on Phase 2 — audit of SQLMesh models is independent
- **US3 (Phase 6)**: No dependency on other phases — fetcher fixes are standalone
- **US4 (Phase 7)**: No dependency on other phases — MCP adapter fixes are standalone
- **Polish (Phase 8)**: Depends on all user story phases being complete. T037 requires staging deployment. T038 can run locally.

### Parallel Opportunities

**Phases that can run simultaneously**:
- Phase 2 (Migration) + Phase 4 (CronJob memory) + Phase 5 (Column audit) + Phase 6 (Fetcher fixes) + Phase 7 (MCP adapters)
- Phase 3 must wait for Phase 2

**Within phases**:
- Phase 4: All 5 CronJob tasks (T011-T015) are fully parallel
- Phase 5: T016 and T017 are parallel (mol vs hcs audit)
- Phase 6: T022 and T023 are parallel (openfda + imgt)
- Phase 7: T025-T029 are parallel (5 adapter overrides), T030-T032 are parallel (3 bulk-only)

---

## Parallel Example: Phase 4 (CronJob Memory)

```
# All 5 CronJob tasks can launch simultaneously:
Task T011: "cronjob-fetch-sider.yaml — 512Mi/1Gi"
Task T012: "cronjob-fetch-cms-imaging-puf.yaml — 512Mi/1Gi"
Task T013: "cronjob-fetch-cms-pecos.yaml — 512Mi/1Gi"
Task T014: "cronjob-fetch-hrsa.yaml — 512Mi/1Gi"
Task T015: "cronjob-fetch-cms-formulary.yaml — 1Gi/4Gi"
```

## Parallel Example: Phase 7 (MCP Adapters)

```
# After T024 (base_tool), all adapter overrides can launch simultaneously:
Task T025: "fda_drugs.py build_url"
Task T026: "pdb_structures.py build_url"
Task T027: "orcid.py build_url"
Task T028: "cms_part_d_spending.py build_url"
Task T029: "hta_decisions.py build_url"
Task T030: "ema.py bulk-only"
Task T031: "cochrane.py bulk-only"
Task T032: "ttd.py bulk-only"
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2 Only)

1. Complete Phase 2: Migration 138 + init script alignment
2. Complete Phase 3: Verify loaders match new UNIQUE indexes
3. Complete Phase 4: CronJob memory bumps
4. **STOP and VALIDATE**: All ingestion jobs should run without DB errors or OOMKills
5. Deploy to staging and trigger affected CronJobs

### Incremental Delivery

1. Phase 2 + 3 + 4 → Core ingestion fixed → Deploy (MVP!)
2. Phase 5 → Column audit complete → Confidence in data integrity
3. Phase 6 → Fetcher coverage expanded → 2-3 more sources ingesting
4. Phase 7 → MCP adapters fixed → Analyst tooling improved
5. Phase 8 → Full validation → Ready for prod

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All SQL migrations must be idempotent (IF NOT EXISTS / IF EXISTS patterns)
- CronJob memory changes are YAML-only — no code changes needed
- MCP adapter fixes require understanding the base adapter pattern in `adapters/base.py`
- The column audit (Phase 5) may generate additional fix tasks — these should be completed before Phase 8
