# Tasks: Platform Hardening

**Input**: Design documents from `/specs/012-platform-hardening/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-views.sql, quickstart.md

**Tests**: Included per FR-014 requirement (unit tests for new code).

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Branch preparation and verification of existing state

- [x] T001 Verify current branch is `012-platform-hardening` and up-to-date with main

**Checkpoint**: Branch ready for implementation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No shared foundational tasks — each user story is self-contained. Proceed directly to user story phases.

**Checkpoint**: Foundation ready — user story implementation can begin

---

## Phase 3: User Story 1 — Fix CronJob Container Image (Priority: P1) MVP

**Goal**: Fix the Dockerfile multi-stage build bug so all CronJob pods can import `dk_data` at runtime. Resolves GitHub Issue #88.

**Independent Test**: Build the container image, run `python -c "import dk_data"` inside it, and trigger any CronJob — should not produce `ModuleNotFoundError`.

### Tests for User Story 1

- [x] T002 [P] [US1] Create container image smoke tests in tests/test_dockerfile.py — verify dk_data importable, entry points accessible, no redundant source copy

### Implementation for User Story 1

- [x] T003 [US1] Fix Dockerfile — remove redundant `COPY --from=builder /build/src/dk_data /app/dk_data` (line 26) and `ENV PYTHONPATH=/app` (line 29) in Dockerfile
- [x] T004 [P] [US1] Fix absolute imports in src/dk_data/ingestion/fetch_data.py — replace `sys.path.insert()` with `from dk_data.ingestion.fetchers import ...`
- [x] T005 [P] [US1] Fix absolute imports in src/dk_data/ingestion/fetch_molecules.py — already uses absolute dk_data.* imports (no-op)

**Checkpoint**: Container image builds successfully; `python -c "import dk_data"` works inside container; all CronJob entry points resolve without ModuleNotFoundError

---

## Phase 4: User Story 2 — Downstream API Views (Priority: P2)

**Goal**: Create 6 API views (company_pipeline, molecule_targets, trial_publication_features, sider_side_effects, bioactivity, patents) for behavior-labs-ai integration. Resolves GitHub Issue #81.

**Independent Test**: Query each view endpoint via PostgREST with an authenticated token — should return valid JSON (empty array or data). Unauthenticated requests should return 401.

### Tests for User Story 2

- [x] T006 [P] [US2] Create API view contract tests in tests/test_api_views_contract.py — verify column names and types for all 6 views per contracts/api-views.sql

### Implementation for User Story 2

- [x] T007 [US2] Create migration for new backing tables in src/dk_data/sql/migrations/065_downstream_tables.sql — mol_gold.company_pipeline, mol_gold.trial_publication_features, mol_silver.targets per data-model.md
- [x] T008 [US2] Add 6 API views and GRANTs to k8s/base/db-init-job.yaml — company_pipeline, molecule_targets, trial_publication_features, sider_side_effects, bioactivity, patents per contracts/api-views.sql

**Checkpoint**: All 6 API views exist in db-init-job.yaml; migration creates 3 new backing tables; authenticated PostgREST queries return valid schema

---

## Phase 5: User Story 3 — Data Sources: UniProt, PDB, ORCID (Priority: P3)

**Goal**: Integrate UniProt, PDB, and ORCID into the ingestion pipeline using the BaseFetcher pattern, with CronJobs, loaders, validators, and catalog registration. Resolves GitHub Issues #42, #50, #51.

**Independent Test**: Trigger each source's CronJob, verify records land in raw tables, confirm sources appear in data catalog.

### Tests for User Story 3

- [x] T009 [P] [US3] Create UniProt fetcher tests in tests/test_uniprot_fetcher.py — mock HTTP responses, verify fetch() stores data in raw.uniprot
- [x] T010 [P] [US3] Create PDB fetcher tests in tests/test_pdb_fetcher.py — mock HTTP responses, verify fetch() stores data in raw.pdb
- [x] T011 [P] [US3] Create ORCID fetcher tests in tests/test_orcid_fetcher.py — mock HTTP responses, verify fetch() stores data in raw.orcid

### Implementation for User Story 3

- [x] T012 [US3] Create ORCID raw table migration in src/dk_data/sql/migrations/066_orcid_raw_table.sql — raw.orcid per data-model.md (UniProt and PDB raw tables already exist from migration 028)
- [x] T013 [P] [US3] Create UniProt fetcher in src/dk_data/ingestion/fetchers/uniprot.py — BaseFetcher subclass, fetch from UniProt REST API, store in raw.uniprot
- [x] T014 [P] [US3] Create PDB fetcher in src/dk_data/ingestion/fetchers/pdb.py — BaseFetcher subclass, fetch from RCSB PDB search API, store in raw.pdb
- [x] T015 [P] [US3] Create ORCID fetcher in src/dk_data/ingestion/fetchers/orcid.py — BaseFetcher subclass, fetch from ORCID public API, store in raw.orcid
- [x] T016 [P] [US3] Create UniProt loader in src/dk_data/ingestion/sources/uniprot.py — parse UniProt JSON, Pydantic validation, INSERT ON CONFLICT into raw.uniprot
- [x] T017 [P] [US3] Create PDB loader in src/dk_data/ingestion/sources/pdb.py — parse PDB JSON, Pydantic validation, INSERT ON CONFLICT into raw.pdb
- [x] T018 [P] [US3] Create ORCID loader in src/dk_data/ingestion/sources/orcid.py — parse ORCID JSON, Pydantic validation, INSERT ON CONFLICT into raw.orcid
- [x] T019 [US3] Add 3 validators to src/dk_data/ingestion/utils/validators.py — UniProt accession, PDB ID, ORCID iD format validators
- [x] T020 [US3] Register fetchers in src/dk_data/ingestion/fetchers/__init__.py — add UniProtFetcher, PDBFetcher, ORCIDFetcher
- [x] T021 [US3] Register sources in src/dk_data/ingestion/sources/__init__.py — add uniprot, pdb, orcid loaders
- [x] T022 [US3] Add to FETCHERS dict in src/dk_data/ingestion/fetch_data.py — register uniprot, pdb, orcid
- [x] T023 [P] [US3] Add 3 data source entries to src/dk_data/sql/seed_data_sources.sql — uniprot, pdb, orcid
- [x] T024 [P] [US3] Add 3 batch job entries to src/dk_data/sql/seed_batch_jobs.sql — fetch-uniprot, fetch-pdb, fetch-orcid
- [x] T025 [US3] Add 3 SOURCE_METADATA entries to src/dk_data/scripts/catalog_refresh.py — uniprot, pdb, orcid
- [x] T026 [P] [US3] Create CronJob manifest k8s/base/ingestion/cronjob-fetch-uniprot.yaml — weekly schedule, dk-data-secrets
- [x] T027 [P] [US3] Create CronJob manifest k8s/base/ingestion/cronjob-fetch-pdb.yaml — weekly schedule, dk-data-secrets
- [x] T028 [P] [US3] Create CronJob manifest k8s/base/ingestion/cronjob-fetch-orcid.yaml — weekly schedule, dk-data-secrets
- [x] T029 [US3] Register 3 CronJobs in k8s/base/kustomization.yaml — add cronjob-fetch-uniprot, cronjob-fetch-pdb, cronjob-fetch-orcid

**Checkpoint**: All 3 fetchers import via `from dk_data.ingestion.fetchers import UniProtFetcher, PDBFetcher, ORCIDFetcher`; CronJob manifests validate; sources appear in seed SQL

---

## Phase 6: User Story 4 — Dependency Management (Priority: P4)

**Goal**: Pin all dependency versions with upper bounds and generate a uv lock file for reproducible installations. Resolves GitHub Issue #20.

**Independent Test**: Delete `.venv`, run `uv sync`, freeze, recreate, freeze again — diffs should be empty.

### Implementation for User Story 4

- [x] T030 [US4] Update pyproject.toml — add upper version bounds to all dependencies (e.g., `psycopg2-binary>=2.9.9,<3.0`)
- [x] T031 [US4] Generate uv.lock — run `uv lock` to create lock file from pyproject.toml
- [x] T032 [US4] Update CI workflow in .github/workflows/ci.yaml — add lock file consistency check (`uv lock --check`)

**Checkpoint**: `uv sync` installs reproducible versions; CI validates lock file freshness

---

## Phase 7: User Story 5 — Doppler Secret Documentation (Priority: P5)

**Goal**: Document all secrets with name, purpose, format, and source. Add startup validation. Resolves GitHub Issue #57.

**Independent Test**: Run secret validation in container — should log warnings for missing secrets without crashing.

### Tests for User Story 5

- [x] T033 [P] [US5] Create secret validation tests in tests/test_secret_check.py — verify warnings for missing secrets, success for present secrets, empty-value handling

### Implementation for User Story 5

- [x] T034 [US5] Create secret reference documentation in docs/DOPPLER_SECRETS.md — all secrets from research.md R5 with name, purpose, format, required-by, how to obtain
- [x] T035 [US5] Create startup validation module in src/dk_data/ingestion/utils/secret_check.py — validate_secrets() checks env vars, logs clear errors for missing/empty

**Checkpoint**: `docs/DOPPLER_SECRETS.md` lists all 13+ secrets; `validate_secrets()` logs warnings for any missing secrets

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all user stories

- [x] T036 Run full test suite — `pytest tests/ -q` — verify all new and existing tests pass (64 new tests pass, 466 total pass)
- [x] T037 Validate Kustomize manifests — `kubectl kustomize k8s/overlays/staging --enable-helm` and prod overlay
- [x] T038 Run quickstart.md verification steps — Docker build, import check, entry point verification

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: N/A — no shared blockers
- **US1 (Phase 3)**: Can start immediately — no prerequisites
- **US2 (Phase 4)**: Independent of US1 — can start in parallel
- **US3 (Phase 5)**: Independent of US1/US2 — can start in parallel (T012 ORCID migration has no blockers)
- **US4 (Phase 6)**: Independent — can start in parallel
- **US5 (Phase 7)**: Independent — can start in parallel
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories. **MVP — fixes all ingestion pipelines.**
- **US2 (P2)**: No dependencies on other stories. New tables are created by migration 065; views reference them.
- **US3 (P3)**: No dependencies on other stories. Uses existing BaseFetcher pattern, existing raw tables (UniProt/PDB), new ORCID table (T012).
- **US4 (P4)**: No dependencies on other stories. Operates on pyproject.toml and CI config.
- **US5 (P5)**: No dependencies on other stories. Documentation and utility module only.

### Within Each User Story

- Tests written first (where applicable)
- Migrations before views/fetchers that depend on them
- Fetchers/loaders before registration tasks
- Registration tasks before CronJob manifests
- CronJob manifests before kustomization.yaml registration

### Parallel Opportunities

**Within US1**:
- T004 and T005 (import fixes) can run in parallel — different files

**Within US2**:
- T006 (tests) can run in parallel with T007 (migration)

**Within US3** (maximum parallelism):
- T009, T010, T011 (3 test files) — all parallel
- T013, T014, T15 (3 fetchers) — all parallel
- T016, T17, T018 (3 loaders) — all parallel
- T023, T024 (seed SQL) — parallel
- T026, T027, T028 (3 CronJob manifests) — all parallel

**Within US5**:
- T033 (tests) can run in parallel with T034 (docs)

**Across Stories**:
- All 5 user stories can execute in parallel since they touch different files

---

## Parallel Example: User Story 3

```bash
# Launch all 3 fetcher tests together:
Task: "Create UniProt fetcher tests in tests/test_uniprot_fetcher.py"
Task: "Create PDB fetcher tests in tests/test_pdb_fetcher.py"
Task: "Create ORCID fetcher tests in tests/test_orcid_fetcher.py"

# Launch all 3 fetchers together:
Task: "Create UniProt fetcher in src/dk_data/ingestion/fetchers/uniprot.py"
Task: "Create PDB fetcher in src/dk_data/ingestion/fetchers/pdb.py"
Task: "Create ORCID fetcher in src/dk_data/ingestion/fetchers/orcid.py"

# Launch all 3 loaders together:
Task: "Create UniProt loader in src/dk_data/ingestion/sources/uniprot.py"
Task: "Create PDB loader in src/dk_data/ingestion/sources/pdb.py"
Task: "Create ORCID loader in src/dk_data/ingestion/sources/orcid.py"

# Launch all 3 CronJob manifests together:
Task: "Create CronJob manifest k8s/base/ingestion/cronjob-fetch-uniprot.yaml"
Task: "Create CronJob manifest k8s/base/ingestion/cronjob-fetch-pdb.yaml"
Task: "Create CronJob manifest k8s/base/ingestion/cronjob-fetch-orcid.yaml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 3: US1 — Fix Dockerfile + imports (T002-T005)
3. **STOP and VALIDATE**: Build image, run import check, trigger a CronJob
4. Deploy to staging — all ingestion pipelines unblocked

### Incremental Delivery

1. US1 → Container fix deployed → All CronJobs functional (MVP)
2. US2 → API views available → behavior-labs-ai unblocked
3. US3 → 3 new data sources → Molecule platform coverage complete
4. US4 → Lock file → Reproducible builds
5. US5 → Secret docs → Operational readiness

### Parallel Team Strategy

With multiple developers:

1. All stories can start simultaneously (no cross-story blockers)
   - Developer A: US1 (Dockerfile) + US4 (dependencies) — small scope
   - Developer B: US2 (API views) + US5 (secrets) — medium scope
   - Developer C: US3 (data sources) — largest scope
2. Polish phase after all stories complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- US1 is the MVP — fixes the critical CronJob failure blocking all pipelines
- US3 has the most tasks (21) due to 3 parallel data source implementations
- Total: 38 tasks across 8 phases
