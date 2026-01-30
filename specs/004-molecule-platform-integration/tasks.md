# Tasks: Molecule Platform Integration

**Input**: Design documents from `/specs/004-molecule-platform-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Not explicitly requested — test tasks omitted. Validation is via `ruff check`, `kustomize build`, `docker build`, and credential scans.

**Organization**: Tasks grouped by user story. Since this is a code integration feature (selective merge from `Philipp-working`), foundational tasks are heavier than typical greenfield development.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Prepare integration branch and verify source branch is accessible

- [x] T001 Verify branch `004-molecule-platform-integration` is checked out from `staging` and `origin/Philipp-working` is fetched
- [x] T002 List all files on `origin/Philipp-working` that will be selectively checked out — verify against plan.md §3.1–3.3

---

## Phase 2: Foundational (Selective Code Checkout + Fixes)

**Purpose**: Bring all application code from `Philipp-working` into the integration branch and fix all import/config issues. MUST complete before any user story work.

**CRITICAL**: No user story work can begin until this phase is complete.

### Selective Checkout

- [x] T003 Checkout `src/dk_data/models/` from `origin/Philipp-working` (6 packages: `__init__.py`, `application/`, `bronze/`, `data_platform/`, `gold/`, `silver/`, plus domain files `competitive_graph.py`, `coverage.py`, `indication.py`, `lifecycle.py`)
- [x] T004 [P] Checkout `src/dk_data/core/` from `origin/Philipp-working` (`__init__.py`, `config.py`, `feature_flags.py`, `logging.py`)
- [x] T005 [P] Checkout `src/dk_data/data/` from `origin/Philipp-working` (`__init__.py` + 18 `load_*.py` files)
- [x] T006 Checkout `src/dk_data/services/` from `origin/Philipp-working` (3 packages: `auth/`, `data_platform/`, `external_apis/`, `ground_truth/`, plus `__init__.py`)
- [x] T007 [P] Checkout `src/dk_data/api/` from `origin/Philipp-working` (`__init__.py`, `dependencies.py`, `errors.py`, `errors/`, `middleware.py`, `middleware/`, `routes/`)
- [x] T008 [P] Checkout molecule ingestion CLIs from `origin/Philipp-working`: `src/dk_data/ingestion/fetch_molecules.py`, `src/dk_data/ingestion/transform_molecules.py`, `src/dk_data/ingestion/run_molecule_pipeline.py`
- [x] T009 [P] Checkout SQL migrations from `origin/Philipp-working`: `src/dk_data/sql/migrations/` (files 020–051)
- [x] T010 [P] Checkout SQLMesh config and models from `origin/Philipp-working`: `src/dk_data/sqlmesh/` (config.yaml + models/molecules/ bronze/silver/gold)
- [x] T011 [P] Checkout specs and docs from `origin/Philipp-working`: `specs/012-dk-data-platform/`, `docs/DATA_LOADERS.md`, `docs/MEDALLION_ARCHITECTURE.md`

### Import Path Fixes

- [x] T012 Fix all bare module imports in `src/dk_data/api/` — replace `from api.` with `from dk_data.api.`, `from services.` with `from dk_data.services.`, `from models.` with `from dk_data.models.`, `from core.` with `from dk_data.core.`
- [x] T013 [P] Fix all bare module imports in `src/dk_data/services/` — same pattern as T012
- [x] T014 [P] Fix all bare module imports in `src/dk_data/data/` — same pattern
- [x] T015 [P] Fix all bare module imports in `src/dk_data/ingestion/fetch_molecules.py`, `transform_molecules.py`, `run_molecule_pipeline.py` — same pattern
- [x] T016 [P] Fix all bare module imports in `src/dk_data/models/` — same pattern

### Config & Dependency Fixes

- [x] T017 Update `src/dk_data/core/config.py` — change database default from `edwards_tavr` to `dk_data`, change port default from `5432` to `5433`, ensure all config reads from env vars
- [x] T018 [P] Update `src/dk_data/sqlmesh/config.yaml` — change database from `edwards_tavr` to `dk_data`, remove hardcoded password (use env var or `.env` file), update port to `5433`
- [x] T019 [P] Redirect `src/dk_data/core/logging.py` — ensure it delegates to `dk_data.observability` module instead of duplicating structlog setup
- [x] T020 Add `httpx>=0.25.0` and `pyjwt>=2.8.0` to `pyproject.toml` dependencies, then run `uv lock`
- [x] T021 Run `ruff check src/` and fix all lint errors across all newly checked-out files — iterate until zero errors

**Checkpoint**: All application code is in the branch, imports resolve, `ruff check` passes. No runtime validation yet.

---

## Phase 3: User Story 4 — Database Schema Initialization (Priority: P1) 🎯 MVP

**Goal**: Molecule database schemas, tables, roles, and grants are automatically created during deployment via the db-init Job.

**Independent Test**: Deploy to fresh namespace → all 6 molecule schemas exist → init job is idempotent (run twice without error) → existing TAVR schemas unaffected.

### Implementation for User Story 4

- [x] T022 [US4] Extend `k8s/base/db-init-job.yaml` — add molecule schemas (`mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_app`, `mol_api`) with `CREATE SCHEMA IF NOT EXISTS`
- [x] T023 [US4] Extend `k8s/base/db-init-job.yaml` — add `CREATE EXTENSION IF NOT EXISTS pg_trgm` for fuzzy text matching
- [x] T024 [US4] Extend `k8s/base/db-init-job.yaml` — add role grants: `GRANT USAGE ON SCHEMA mol_api TO web_anon, analyst, api_user` + `GRANT SELECT ON ALL TABLES` + `ALTER DEFAULT PRIVILEGES` for mol_api
- [x] T025 [US4] Extend `k8s/base/db-init-job.yaml` — add full-privilege grants on `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_app` for `api_user` role (used by ingestion services)
- [x] T026 [US4] Verify idempotency — review the entire db-init SQL block to confirm every statement uses `IF NOT EXISTS`, `CREATE OR REPLACE`, or `DO $$ ... $$` guard blocks

**Checkpoint**: `kustomize build k8s/overlays/staging | grep -c "mol_"` returns schema references. Init SQL is idempotent.

---

## Phase 4: User Story 5 — Kubernetes Deployment (Priority: P1)

**Goal**: Molecule platform components deploy via dk-alchemy ArgoCD workflow with CronJobs, ConfigMap, and updated PostgREST config.

**Independent Test**: `kustomize build` for both overlays includes molecule CronJobs, ConfigMap, and updated PostgREST schemas.

### Implementation for User Story 5

- [x] T027 [P] [US5] Create `k8s/base/ingestion/cronjob-mol-fetch-daily.yaml` — daily 2 AM UTC, sources: clinicaltrials,openfda_labels, GHCR image, dk-data-secrets, imagePullSecrets, resources 256Mi/512Mi, per contracts/cronjob-manifests.yaml
- [x] T028 [P] [US5] Create `k8s/base/ingestion/cronjob-mol-fetch-weekly.yaml` — Sunday 3 AM UTC, sources: openfda_faers,chembl,pubchem, same pattern as T027
- [x] T029 [P] [US5] Create `k8s/base/ingestion/cronjob-mol-transform.yaml` — daily 6 AM UTC, layer: all, resources 512Mi/1Gi, per contracts/cronjob-manifests.yaml
- [x] T030 [P] [US5] Create `k8s/base/ingestion/molecule-pipeline-config.yaml` — ConfigMap with BATCH_SIZE, FETCH_MODE, TRANSFORM_LAYERS, ENABLE_FETCH, ENABLE_TRANSFORM, ENABLE_RESOLUTION, ENTITY_RESOLUTION_THRESHOLD=0.80, LOG_LEVEL
- [x] T031 [US5] Update `k8s/base/kustomization.yaml` — add 4 new resources: `ingestion/cronjob-mol-fetch-daily.yaml`, `ingestion/cronjob-mol-fetch-weekly.yaml`, `ingestion/cronjob-mol-transform.yaml`, `ingestion/molecule-pipeline-config.yaml`
- [x] T032 [US5] Update `k8s/base/postgrest/configmap.yaml` — change `PGRST_DB_SCHEMAS` from `"api"` to `"api,mol_api"`
- [x] T033 [US5] Update `k8s/overlays/staging/kustomization.yaml` — add patches for molecule CronJob resources if staging-specific overrides needed (e.g., lower batch size, debug log level)
- [x] T034 [US5] Update `k8s/overlays/prod/kustomization.yaml` — add patches for molecule CronJob resources with production resource limits (mol-transform: 1Gi/2Gi memory)
- [x] T035 [US5] Validate `kustomize build k8s/overlays/staging` — confirm output includes all 3 molecule CronJobs, ConfigMap, updated PGRST_DB_SCHEMAS, extended db-init
- [x] T036 [US5] Validate `kustomize build k8s/overlays/prod` — same validation as T035 for production overlay

**Checkpoint**: Both overlays render correctly with all molecule K8s resources.

---

## Phase 5: User Story 1 — Molecule Data Ingestion Pipeline (Priority: P1)

**Goal**: Platform automatically ingests data from 5 core pharmaceutical sources on scheduled basis via CronJobs.

**Independent Test**: Trigger a molecule fetch job → data appears in mol_raw and mol_bronze layers for at least one source.

### Implementation for User Story 1

- [x] T037 [US1] Wire molecule routers into `src/dk_data/ingestion/batch/api.py` — add try/except import block for `dk_data.api.routes` routers (data_platform, monitoring, data_sources, onboarding, alerts) with `app.include_router()` prefix `/api/v1`, log warning on ImportError
- [x] T038 [US1] Add molecule job commands to `src/dk_data/ingestion/batch/job_runner.py` — extend `JOB_COMMANDS` dict in `LocalJobRunner` with: `fetch-clinicaltrials`, `fetch-openfda-labels`, `fetch-openfda-faers`, `fetch-chembl`, `fetch-pubchem`, `mol-bronze-transform`, `mol-silver-transform`, `mol-gold-aggregate`, `mol-pipeline-full` — all using `python -m dk_data.ingestion.*` paths
- [x] T039 [US1] Verify `src/dk_data/ingestion/fetch_molecules.py` — confirm CLI accepts `--source` argument, sources map to correct external API clients, graceful skip on unavailable sources
- [x] T040 [US1] Verify external API client rate limiting in `src/dk_data/services/external_apis/base_client.py` — confirm rate limits match research.md (ClinicalTrials 3/sec, OpenFDA 40/min, ChEMBL 10/sec, PubChem 5/sec)
- [x] T041 [US1] Verify deduplication logic — confirm `response_body_hash` check in raw ingestion service prevents duplicate bronze entries

**Checkpoint**: `/jobs` endpoint lists molecule jobs. `fetch_molecules.py` CLI is importable and accepts `--source` flag.

---

## Phase 6: User Story 2 — Medallion Data Transformation (Priority: P1)

**Goal**: Raw source data automatically transforms through bronze → silver → gold layers with entity resolution.

**Independent Test**: Run transform pipeline → silver-layer molecules have cross-source identifiers linked → gold aggregations populated.

### Implementation for User Story 2

- [x] T042 [US2] Verify `src/dk_data/ingestion/transform_molecules.py` — confirm CLI accepts `--layer` argument (bronze, silver, gold, all), invokes correct service classes
- [x] T043 [US2] Verify entity resolution confidence threshold in `src/dk_data/services/data_platform/identifier_resolver.py` or `fuzzy_matcher.py` — confirm threshold is configurable via `ENTITY_RESOLUTION_THRESHOLD` env var, default 0.80
- [x] T044 [US2] Verify `needs_review` flag logic in silver transformation — molecules matched below 0.80 confidence must have `needs_review=TRUE` in `mol_silver.molecules`
- [x] T045 [US2] Verify SQLMesh model definitions in `src/dk_data/sqlmesh/models/molecules/` — confirm bronze (13 models), silver (12 models), gold (6 models) reference correct `mol_*` schemas

**Checkpoint**: `transform_molecules.py` CLI is importable. SQLMesh models reference correct schemas.

---

## Phase 7: User Story 8 — TAVR Functionality Preservation (Priority: P1)

**Goal**: Existing TAVR API endpoints and batch jobs continue working identically after integration.

**Independent Test**: `/health` returns 200, `/jobs` lists TAVR jobs, existing CronJobs unchanged.

### Implementation for User Story 8

- [x] T046 [US8] Verify `/health` endpoint in `src/dk_data/ingestion/batch/api.py` — confirm health check function is unchanged, DB_CONFIG still reads from env vars
- [x] T047 [US8] Verify all existing TAVR `JOB_COMMANDS` in `src/dk_data/ingestion/batch/job_runner.py` are preserved — `fetch-cms-all`, `fetch-cms-hospitals`, `fetch-cms-inpatient`, `fetch-acc-tvc`, `fetch-hrsa`, `catalog-refresh`, `sqlmesh-run`, `check-freshness`, `purge-history`
- [x] T048 [US8] Verify existing K8s CronJobs `cronjob-cms-all.yaml` and `cronjob-refresh.yaml` are unchanged in `k8s/base/ingestion/`
- [x] T049 [US8] Verify existing PostgREST deployment reads `PGRST_DB_SCHEMAS` from ConfigMap — confirm `api` schema is still first in the list

**Checkpoint**: All existing TAVR endpoints and jobs are preserved. Zero regressions in base manifests.

---

## Phase 8: User Story 7 — Secrets and Credential Security (Priority: P1)

**Goal**: Zero hardcoded credentials in all integrated source code.

**Independent Test**: `grep -rn` for passwords/keys/tokens in new code returns zero matches. All secret refs use `dk-data-secrets`.

### Implementation for User Story 7

- [x] T050 [US7] Scan all new source files for hardcoded credentials — `grep -rn "password\|secret\|api_key\|token" src/dk_data/{api,core,data,models,services}/ --include="*.py"` — fix any matches that are actual hardcoded values (not env var reads)
- [x] T051 [US7] Verify `src/dk_data/core/config.py` `DatabaseSettings.password` default is empty string or `None`, not `"postgres"` — fix if needed
- [x] T052 [US7] Verify `src/dk_data/sqlmesh/config.yaml` does not contain hardcoded password — replace with env var reference or `.env` file pattern
- [x] T053 [US7] Verify all 3 new CronJob manifests reference `dk-data-secrets` for database credentials (not hardcoded env values)
- [x] T054 [US7] Verify `src/dk_data/services/external_apis/` clients read API keys from env vars and handle missing keys gracefully (skip source, don't crash)

**Checkpoint**: Zero hardcoded credentials. All secrets via env vars backed by Doppler.

---

## Phase 9: User Story 3 — Molecule Search and Profile API (Priority: P2)

**Goal**: Analysts can search molecules by name/identifier and retrieve comprehensive profiles via API.

**Independent Test**: Call molecule search endpoint with a known name → structured profile response returned.

### Implementation for User Story 3

- [x] T055 [US3] Verify `src/dk_data/api/routes/data_platform.py` — confirm `/search` POST endpoint accepts `MoleculeSearchRequest` (query, threshold, limit), returns `MoleculeSearchResult[]`
- [x] T056 [US3] Verify `src/dk_data/api/routes/data_platform.py` — confirm `/molecules/{id}` GET endpoint returns `MoleculeProfileResponse` with aggregated properties, identifiers, trial counts, safety events
- [x] T057 [US3] Verify fuzzy search uses `pg_trgm` similarity — confirm `mol_api.molecule_search` function or equivalent query uses `similarity()` function with configurable threshold
- [x] T058 [US3] Verify PostgREST views exist in migration files for `mol_api` schema — confirm `mol_api.molecule_profiles`, `mol_api.safety_signals`, `mol_api.competitive_landscapes` views are defined in SQL migrations

**Checkpoint**: Molecule search and profile routes are wired and reference correct database objects.

---

## Phase 10: User Story 6 — Pipeline Monitoring and Alerting (Priority: P2)

**Goal**: Prometheus metrics scraped from molecule CronJobs, alert rules fire on failure/staleness.

**Independent Test**: Alert rules render in PrometheusRule manifest. PodMonitor targets molecule CronJobs.

### Implementation for User Story 6

- [x] T059 [US6] Extend `k8s/base/alert-rules.yaml` — add alert group `molecule-pipeline` with rules: `MoleculeFetchFailed` (CronJob failure), `MoleculeTransformStale` (no successful transform in 48h), `BronzeToSilverBacklog` (unprocessed bronze records > threshold)
- [x] T060 [US6] Extend `k8s/base/service-monitor.yaml` — add PodMonitor for molecule CronJobs (label selector `app.kubernetes.io/component: ingestion`, `app in (mol-fetch-daily, mol-fetch-weekly, mol-transform)`)
- [x] T061 [US6] Verify `src/dk_data/services/data_platform/pipeline_monitoring.py` uses `dk_data.observability.metrics` for Prometheus counters/gauges — not a parallel metrics setup
- [x] T062 [US6] Verify molecule API monitoring route in `src/dk_data/api/routes/monitoring.py` — confirm `/api/v1/monitoring/pipeline-health` and `/api/v1/monitoring/data-freshness` endpoints exist

**Checkpoint**: PrometheusRule includes molecule alerts. PodMonitor targets mol CronJobs.

---

## Phase 11: Docker & CI Validation

**Purpose**: Ensure container image builds and CI pipeline works with all new code.

### Implementation

- [x] T063 Verify `Dockerfile` at repo root — confirm `pip install .` picks up all new deps from `pyproject.toml` (no changes to Dockerfile needed if `pyproject.toml` is correct)
- [x] T064 Run `docker build -t dk-data-fe-test .` — confirm image builds successfully with all new Python packages
- [x] T065 Run `docker run --rm dk-data-fe-test python -c "import dk_data; from dk_data.api.routes import data_platform_router; print('OK')"` — confirm all new modules are importable
- [x] T066 Verify `.github/workflows/build-push.yaml` — confirm it triggers on `staging` branch (already configured)

**Checkpoint**: Docker image builds. All new modules importable. CI unchanged.

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, env documentation, and GitHub issue creation for deferred work.

- [x] T067 Update `.env.example` — add molecule-specific variables: `OPENFDA_API_KEY`, `CHEMBL_API_KEY`, `DRUGBANK_API_KEY` (all optional), `BATCH_SIZE`, `ENTITY_RESOLUTION_THRESHOLD`, `FETCH_MODE`
- [x] T068 Final `ruff check src/` — confirm zero errors across all files
- [x] T069 Final `kustomize build k8s/overlays/staging` — confirm valid output, count resources
- [x] T070 Final `kustomize build k8s/overlays/prod` — confirm valid output, count resources
- [x] T071 Final credential scan — `grep -rn "password.*=" src/dk_data/ --include="*.py" | grep -v "getenv\|environ\|env_var\|os.get\|Optional\|Field\|#\|password:"` — confirm zero real hardcoded credentials
- [x] T072 [P] Create GitHub issue: "Enable DrugBank data source (requires API key)" with label `data-source`, referencing plan.md §FR-003
- [x] T073 [P] Create GitHub issue: "Enable UniProt data source" with label `data-source`
- [x] T074 [P] Create GitHub issue: "Enable OpenAlex data source" with label `data-source`
- [x] T075 [P] Create GitHub issue: "Enable BindingDB data source" with label `data-source`
- [x] T076 [P] Create GitHub issue: "Enable SIDER data source" with label `data-source`
- [x] T077 [P] Create GitHub issue: "Enable Orange Book data source" with label `data-source`
- [x] T078 [P] Create GitHub issue: "Enable USPTO Patents data source" with label `data-source`
- [x] T079 [P] Create GitHub issue: "Enable EMA data source" with label `data-source`
- [x] T080 [P] Create GitHub issue: "Enable TDC ADMET data source" with label `data-source`
- [x] T081 [P] Create GitHub issue: "Enable PDB (Protein Data Bank) data source" with label `data-source`
- [x] T082 [P] Create GitHub issue: "Enable ORCID data source for KOL identification" with label `data-source`
- [x] T083 Create GitHub issue: "Frontend integration — React onboarding wizard + dashboard (feature 005)" with label `enhancement`, referencing deferred scope from spec.md §Constraints
- [x] T084 Run quickstart.md verification checklist — confirm all 8 items pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US4 Database Init (Phase 3)**: Depends on Phase 2 — provides schemas for all other stories
- **US5 K8s Deployment (Phase 4)**: Depends on Phase 2 — CronJobs reference code from checkout
- **US1 Ingestion (Phase 5)**: Depends on Phase 2 — verifies ingestion code and API wiring
- **US2 Transformation (Phase 6)**: Depends on Phase 2 — verifies transform code and SQLMesh
- **US8 TAVR Preservation (Phase 7)**: Depends on Phase 5 (T037–T038 modify shared files)
- **US7 Secrets (Phase 8)**: Depends on Phase 2 — scans all checked-out code
- **US3 Search API (Phase 9)**: Depends on Phase 2 — verifies API routes
- **US6 Monitoring (Phase 10)**: Depends on Phase 4 (needs CronJob manifests to add monitors)
- **Docker & CI (Phase 11)**: Depends on Phases 2–9 (needs all code + manifests)
- **Polish (Phase 12)**: Depends on all previous phases

### User Story Dependencies

- **US4 (Database)**: Foundational only — no cross-story dependencies
- **US5 (K8s)**: Foundational + US4 (db-init must include molecule schemas)
- **US1 (Ingestion)**: Foundational only — code verification
- **US2 (Transform)**: Foundational only — code verification
- **US8 (TAVR)**: US1 (shares api.py and job_runner.py modifications)
- **US7 (Secrets)**: Foundational only — scans all code
- **US3 (Search API)**: Foundational only — code verification
- **US6 (Monitoring)**: US5 (needs CronJob manifests for PodMonitor selectors)

### Parallel Opportunities

Within Phase 2 (Foundational):
- T003–T011 (selective checkouts) — all [P] tasks write to different directories
- T012–T016 (import fixes) — all [P] tasks modify different packages
- T017–T019 (config fixes) — all [P] tasks modify different files

Within Phase 4 (US5):
- T027–T030 (CronJob + ConfigMap creation) — all [P] tasks create different files

Within Phase 12 (Polish):
- T072–T082 (GitHub issues) — all [P] tasks are independent

Cross-phase parallelism:
- After Phase 2 completes, Phases 3–9 can proceed in parallel (different files, independent stories)

---

## Parallel Example: Phase 2 Foundational

```
# Launch all selective checkouts in parallel:
T003: Checkout src/dk_data/models/
T004: Checkout src/dk_data/core/
T005: Checkout src/dk_data/data/
T006: Checkout src/dk_data/services/
T007: Checkout src/dk_data/api/
T008: Checkout ingestion CLI modules
T009: Checkout SQL migrations
T010: Checkout SQLMesh models
T011: Checkout specs and docs

# Then launch all import fixes in parallel:
T012: Fix imports in api/
T013: Fix imports in services/
T014: Fix imports in data/
T015: Fix imports in ingestion CLIs
T016: Fix imports in models/
```

---

## Parallel Example: Phase 4 K8s Manifests

```
# Launch all CronJob + ConfigMap creation in parallel:
T027: Create cronjob-mol-fetch-daily.yaml
T028: Create cronjob-mol-fetch-weekly.yaml
T029: Create cronjob-mol-transform.yaml
T030: Create molecule-pipeline-config.yaml

# Then sequentially:
T031: Update kustomization.yaml (depends on T027–T030)
T032: Update PostgREST configmap
```

---

## Implementation Strategy

### MVP First (US4 + US5 + US1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (selective checkout + fixes)
3. Complete Phase 3: US4 — Database schemas ready
4. Complete Phase 4: US5 — K8s manifests ready
5. Complete Phase 5: US1 — Ingestion pipeline wired
6. **STOP and VALIDATE**: `kustomize build` + `docker build` + `ruff check`
7. Deploy to staging if ready

### Full Delivery

1. MVP (Phases 1–5) → Deploy to staging
2. Add Phase 6: US2 (Transform) → Verify pipeline end-to-end
3. Add Phase 7: US8 (TAVR) → Regression check
4. Add Phase 8: US7 (Secrets) → Security validation
5. Add Phase 9: US3 (Search API) → API consumer value
6. Add Phase 10: US6 (Monitoring) → Operational readiness
7. Add Phase 11: Docker & CI → Build validation
8. Add Phase 12: Polish → GitHub issues, final checks
9. Commit, push, create PR to staging

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- This is a **code integration** feature — most tasks are selective checkouts, verification, and wiring rather than greenfield development
- Credential scan tasks (T050–T054, T071) are critical — the source branch has known hardcoded defaults that must be removed
- SQLMesh config (T018, T052) is a known risk — hardcoded `password: postgres` must be replaced
- GitHub issues (T072–T083) track 11 deferred data sources + 1 deferred frontend feature

---

## Completion Summary

**Status**: ✅ ALL 84 TASKS COMPLETE

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: Setup | T001-T002 | ✅ Complete |
| Phase 2: Foundational | T003-T021 | ✅ Complete |
| Phase 3: US4 Database | T022-T026 | ✅ Complete |
| Phase 4: US5 K8s | T027-T036 | ✅ Complete |
| Phase 5: US1 Ingestion | T037-T041 | ✅ Complete |
| Phase 6: US2 Transform | T042-T045 | ✅ Complete |
| Phase 7: US8 TAVR | T046-T049 | ✅ Complete |
| Phase 8: US7 Secrets | T050-T054 | ✅ Complete |
| Phase 9: US3 Search API | T055-T058 | ✅ Complete |
| Phase 10: US6 Monitoring | T059-T062 | ✅ Complete |
| Phase 11: Docker/CI | T063-T066 | ✅ Complete |
| Phase 12: Polish | T067-T084 | ✅ Complete |

**Completed**: 2026-01-30
