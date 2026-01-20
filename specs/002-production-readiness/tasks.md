# Tasks: Production Readiness for dk-data-fe

**Input**: Design documents from `/specs/002-production-readiness/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are NOT included as they were not explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## User Story Summary

| Story | Title | Priority | Dependencies |
|-------|-------|----------|--------------|
| US1 | Secure Secret Management | P1 | Foundational |
| US2 | Codebase Deduplication | P1 | None (can run parallel with US1) |
| US3 | Repository Size Reduction | P1 | US2 (scripts cleaned first) |
| US4 | Observability Integration | P2 | US1 (secrets for OTEL endpoint) |
| US5 | ArgoCD GitOps Deployment | P2 | US1, US2, US3 |
| US6 | API Access Control Hardening | P2 | US1 (JWT secret from Doppler) |
| US7 | Dependency Synchronization | P3 | US4 (OTEL deps added) |
| US8 | Documentation Consolidation | P3 | All others |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, tooling, and backup preparation

- [ ] T001 Create backup branch before any destructive operations using `git branch backup-pre-production-$(date +%Y%m%d)`
- [ ] T002 [P] Install git-filter-repo tool for history rewrite using `brew install git-filter-repo`
- [ ] T003 [P] Install gitleaks for secret scanning using `brew install gitleaks`
- [ ] T004 [P] Configure Doppler CLI with `doppler login` and verify access to dk-infrastructure project
- [ ] T005 [P] Create .gitleaks.toml configuration file at repository root for secret scanning rules
- [ ] T006 Verify dk-alchemy cluster access with `kubectl get nodes` and ArgoCD connectivity

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T007 Run baseline gitleaks scan and document current secret locations using `gitleaks detect --source . -v > /tmp/gitleaks-baseline.txt`
- [ ] T008 [P] Create test directory structure for future tests at tests/contract/, tests/integration/, tests/unit/
- [ ] T009 [P] Document all duplicate file pairs by running `diff -r scripts/ src/dk_data/scripts/` and saving output
- [ ] T010 Verify MinIO bucket access for data file migration at dk-minio/dk-data-fe/

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Secure Secret Management (Priority: P1) 🎯 MVP

**Goal**: Remove all hardcoded credentials and integrate with Doppler for centralized secret management

**Independent Test**: Deploy application and verify: (1) gitleaks scan passes, (2) app fails gracefully without Doppler, (3) app works with Doppler secrets injected

**Implements**: FR-001, FR-002, FR-003, FR-006 | **Success Criteria**: SC-001, SC-006

### Implementation for User Story 1

- [ ] T011 [US1] Add required secrets to Doppler project dk-infrastructure config prod: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, PGRST_JWT_SECRET (256-bit), ANTHROPIC_API_KEY
- [ ] T012 [US1] Create Doppler service token for dk-data-fe-prod and store in temporary secure location
- [ ] T013 [P] [US1] Create DopplerSecret CRD manifest at .gitops/base/secrets/doppler-secret.yaml per contracts/doppler-secret.yaml
- [ ] T014 [P] [US1] Create doppler-token-dk-data-fe Secret manifest at .gitops/base/secrets/doppler-token.yaml (placeholder for CI injection)
- [ ] T015 [US1] Update .gitops/base/kustomization.yaml to include secrets/ directory resources
- [ ] T016 [US1] Remove hardcoded PGRST_DB_URI from .gitops/base/postgrest/secret.yaml, reference DopplerSecret instead
- [ ] T017 [US1] Remove hardcoded PGRST_JWT_SECRET placeholder from .gitops/base/postgrest/secret.yaml
- [ ] T018 [US1] Update .gitops/base/postgrest/deployment.yaml to mount secrets from dk-data-fe-secrets
- [ ] T019 [P] [US1] Update src/dk_data/docker-compose.yml to use environment variable references without defaults for POSTGRES_PASSWORD
- [ ] T020 [P] [US1] Update src/dk_data/docker-compose.yml to use environment variable references without defaults for POSTGREST_PASSWORD
- [ ] T021 [US1] Create .env.example file at repository root documenting required environment variables (no actual values)
- [ ] T022 [US1] Add graceful failure with clear error message when secrets missing in src/dk_data/ingestion/utils/database.py
- [ ] T023 [US1] Run gitleaks scan to verify no secrets remain in current code: `gitleaks detect --source .`

**Checkpoint**: User Story 1 complete - secrets managed via Doppler, no hardcoded credentials

---

## Phase 4: User Story 2 - Codebase Deduplication (Priority: P1)

**Goal**: Establish single canonical location for all scripts and configuration files

**Independent Test**: Verify each script exists in exactly one location, docker-compose mounts only canonical paths, make help shows single Makefile

**Implements**: FR-007, FR-008, FR-011 | **Success Criteria**: SC-003

### Implementation for User Story 2

- [ ] T024 [US2] Compare and identify any differences between duplicate files: `diff scripts/catalog_refresh.py src/dk_data/scripts/catalog_refresh.py`
- [ ] T025 [US2] Merge any unique content from /scripts/ into /src/dk_data/scripts/ ensuring canonical versions are complete
- [ ] T026 [US2] Remove duplicate /scripts/ directory from repository root using `rm -rf scripts/`
- [ ] T027 [P] [US2] Compare SQL files: `diff sql/targeting_tables.sql src/dk_data/sql/targeting_tables.sql`
- [ ] T028 [US2] Remove duplicate /sql/ directory from repository root if it exists
- [ ] T029 [US2] Update src/dk_data/docker-compose.yml volume mount: remove `../../scripts:/app/scripts:ro` line
- [ ] T030 [US2] Update src/dk_data/docker-compose.yml volume mount: change legacy_scripts path to use canonical location only
- [ ] T031 [US2] Move src/dk_data/docker-compose.yml to repository root as docker-compose.yml (FR-022)
- [ ] T032 [US2] Move src/dk_data/docker-compose.prod.yml to repository root as docker-compose.prod.yml
- [ ] T033 [US2] Update volume paths in root docker-compose.yml to reference src/dk_data/ correctly
- [ ] T034 [P] [US2] Remove duplicate Makefile from src/dk_data/Makefile if it exists
- [ ] T035 [US2] Consolidate all make targets into single root Makefile
- [ ] T036 [US2] Add `make help` target to root Makefile showing all available commands
- [ ] T037 [US2] Create CI check script at scripts/check-duplicates.sh to detect future duplicate files
- [ ] T038 [US2] Commit deduplication changes: "chore: consolidate scripts and configs to canonical locations"

**Checkpoint**: User Story 2 complete - single source of truth for all scripts and configs

---

## Phase 5: User Story 3 - Repository Size Reduction (Priority: P1)

**Goal**: Remove large data files and logs from git history to reduce repository size below 10MB

**Independent Test**: Fresh clone completes in <30 seconds, `git count-objects -vH` shows <10MB, no CSV files in /data/

**Implements**: FR-009, FR-010 | **Success Criteria**: SC-002, SC-009

**⚠️ WARNING**: This phase rewrites git history. Coordinate with all team members before proceeding.

### Implementation for User Story 3

- [ ] T039 [US3] Notify all team members of upcoming git history rewrite via team communication channel
- [ ] T040 [US3] Ensure all team members have pushed pending changes and created local backups
- [ ] T041 [US3] Upload existing data files to MinIO: `mc cp --recursive data/raw/ dk-minio/dk-data-fe/raw/`
- [ ] T042 [US3] Verify MinIO upload successful: `mc ls dk-minio/dk-data-fe/raw/`
- [ ] T043 [US3] Remove /data/ directory from git history: `git filter-repo --path data/ --invert-paths --force`
- [ ] T044 [US3] Remove /logs/ directory from git history: `git filter-repo --path logs/ --invert-paths --force`
- [ ] T045 [P] [US3] Update .gitignore to include: /data/, !/data/README.md, /logs/, *.log, *.csv
- [ ] T046 [US3] Create data/README.md explaining where to obtain data files (MinIO location, download instructions)
- [ ] T047 [US3] Create empty logs/.gitkeep to preserve directory structure
- [ ] T048 [US3] Verify repository size reduced: `git count-objects -vH` (target: <10MB)
- [ ] T049 [US3] Force push rewritten history: `git push --force --all` (COORDINATE WITH TEAM)
- [ ] T050 [US3] Force push tags: `git push --force --tags`
- [ ] T051 [US3] Notify team to re-clone or reset their local repositories
- [ ] T052 [US3] Verify fresh clone size and time: clone to temp directory and measure

**Checkpoint**: User Story 3 complete - repository lean and fast to clone

---

## Phase 6: User Story 4 - Observability Integration (Priority: P2)

**Goal**: Instrument all services to send metrics, logs, and traces to dk-alchemy observability stack

**Independent Test**: Deploy application, make API requests, verify metrics in Grafana within 60 seconds, logs in Loki, traces in Tempo

**Implements**: FR-013, FR-014, FR-015, FR-016, FR-017 | **Success Criteria**: SC-004

### Implementation for User Story 4

- [ ] T053 [US4] Add OpenTelemetry dependencies to pyproject.toml: opentelemetry-api, opentelemetry-sdk, opentelemetry-exporter-otlp, opentelemetry-instrumentation-fastapi, opentelemetry-instrumentation-psycopg2, opentelemetry-instrumentation-requests
- [ ] T054 [US4] Add structlog and prometheus-client dependencies to pyproject.toml
- [ ] T055 [US4] Run `uv lock` to update lock file with new dependencies
- [ ] T056 [US4] Create src/dk_data/observability/__init__.py with setup_telemetry() function per research.md
- [ ] T057 [P] [US4] Create src/dk_data/observability/metrics.py with Prometheus metric definitions per data-model.md
- [ ] T058 [P] [US4] Create src/dk_data/observability/logging.py with structured JSON logging configuration
- [ ] T059 [US4] Update src/dk_data/ingestion/batch/api.py to call setup_telemetry("job-trigger") on startup
- [ ] T060 [US4] Add /metrics endpoint to src/dk_data/ingestion/batch/api.py exposing Prometheus metrics
- [ ] T061 [US4] Update src/dk_data/ingestion/batch/job_runner.py to emit job duration and record count metrics
- [ ] T062 [US4] Update all fetchers in src/dk_data/ingestion/fetchers/ to use structured logging with correlation IDs
- [ ] T063 [P] [US4] Create ServiceMonitor manifest at .gitops/base/observability/service-monitor.yaml per contracts/service-monitor.yaml
- [ ] T064 [P] [US4] Create PrometheusRule manifest at .gitops/base/observability/alert-rules.yaml per contracts/alert-rules.yaml
- [ ] T065 [US4] Create Grafana dashboard JSON at .gitops/base/observability/grafana-dashboard.json for data freshness, job status, API health
- [ ] T066 [US4] Update .gitops/base/kustomization.yaml to include observability/ directory resources
- [ ] T067 [US4] Add OTEL_EXPORTER_OTLP_ENDPOINT environment variable to job-trigger deployment at .gitops/base/ingestion/job-trigger-deployment.yaml
- [ ] T068 [US4] Test observability locally using docker-compose with Jaeger all-in-one for trace verification

**Checkpoint**: User Story 4 complete - full observability into platform operations

---

## Phase 7: User Story 5 - ArgoCD GitOps Deployment (Priority: P2)

**Goal**: Restructure for ArgoCD external app pattern following dk-alchemy conventions

**Independent Test**: Push change to main branch, verify ArgoCD syncs within 5 minutes, all apps show healthy in dashboard

**Implements**: FR-018, FR-019, FR-020, FR-021 | **Success Criteria**: SC-005

### Implementation for User Story 5

- [ ] T069 [US5] Create k8s/ directory structure: k8s/postgrest/{base,overlays/{prod,staging}}, k8s/job-trigger/{base,overlays/{prod,staging}}, k8s/cronjobs/{base,overlays/{prod,staging}}
- [ ] T070 [US5] Move .gitops/base/postgrest/* to k8s/postgrest/base/
- [ ] T071 [US5] Move .gitops/base/ingestion/job-trigger-* to k8s/job-trigger/base/
- [ ] T072 [US5] Move .gitops/base/ingestion/cronjob-* and .gitops/base/catalog/* to k8s/cronjobs/base/
- [ ] T073 [P] [US5] Create k8s/postgrest/base/kustomization.yaml listing all PostgREST resources
- [ ] T074 [P] [US5] Create k8s/job-trigger/base/kustomization.yaml listing all job-trigger resources
- [ ] T075 [P] [US5] Create k8s/cronjobs/base/kustomization.yaml listing all cronjob resources
- [ ] T076 [P] [US5] Create k8s/postgrest/overlays/prod/kustomization.yaml with namespace: dk-data-fe-prod and resource patches
- [ ] T077 [P] [US5] Create k8s/postgrest/overlays/staging/kustomization.yaml with namespace: dk-data-fe-staging and smaller resource limits
- [ ] T078 [P] [US5] Create k8s/job-trigger/overlays/prod/kustomization.yaml
- [ ] T079 [P] [US5] Create k8s/job-trigger/overlays/staging/kustomization.yaml
- [ ] T080 [P] [US5] Create k8s/cronjobs/overlays/prod/kustomization.yaml
- [ ] T081 [P] [US5] Create k8s/cronjobs/overlays/staging/kustomization.yaml
- [ ] T082 [US5] Create .gitops/prod/apps/ directory for ArgoCD Application manifests
- [ ] T083 [US5] Create .gitops/staging/apps/ directory for ArgoCD Application manifests
- [ ] T084 [P] [US5] Create .gitops/prod/apps/postgrest-app.yaml ArgoCD Application pointing to k8s/postgrest/overlays/prod
- [ ] T085 [P] [US5] Create .gitops/prod/apps/job-trigger-app.yaml ArgoCD Application pointing to k8s/job-trigger/overlays/prod
- [ ] T086 [P] [US5] Create .gitops/prod/apps/cronjobs-app.yaml ArgoCD Application pointing to k8s/cronjobs/overlays/prod
- [ ] T087 [US5] Create .gitops/prod/apps/kustomization.yaml listing all prod applications
- [ ] T088 [P] [US5] Create .gitops/staging/apps/postgrest-app.yaml for staging environment
- [ ] T089 [P] [US5] Create .gitops/staging/apps/job-trigger-app.yaml for staging environment
- [ ] T090 [P] [US5] Create .gitops/staging/apps/cronjobs-app.yaml for staging environment
- [ ] T091 [US5] Create .gitops/staging/apps/kustomization.yaml listing all staging applications
- [ ] T092 [US5] Update .gitops/argocd/application.yaml to use new external app pattern (or remove if using dk-alchemy bootstrap)
- [ ] T093 [US5] Create NetworkPolicy manifests at k8s/postgrest/base/network-policy.yaml per contracts/network-policy.yaml
- [ ] T094 [US5] Remove old .gitops/base/ and .gitops/overlays/ directories after migration verified
- [ ] T095 [US5] Add bootstrap application to dk-alchemy at .gitops/external/dk-data-fe.yaml (in dk-alchemy repo)
- [ ] T096 [US5] Test ArgoCD sync by pushing a small change and measuring sync time

**Checkpoint**: User Story 5 complete - GitOps deployment via ArgoCD operational

---

## Phase 8: User Story 6 - API Access Control Hardening (Priority: P2)

**Goal**: Restrict API access based on user roles, implement rate limiting

**Independent Test**: Unauthenticated request to /api/targets returns 401, authenticated analyst can access /api/scoring, rate limit triggers 429

**Implements**: FR-003, FR-004, FR-005 | **Success Criteria**: SC-007

### Implementation for User Story 6

- [ ] T097 [US6] Create SQL migration file at src/dk_data/sql/migrations/002_role_restrictions.sql to restrict web_anon permissions
- [ ] T098 [US6] Add SQL to revoke all from web_anon and grant only health, data_catalog endpoints
- [ ] T099 [US6] Add SQL to grant analyst role SELECT on api.targets, api.scoring, api.data_sources
- [ ] T100 [US6] Add SQL to grant api_user role SELECT on ALL TABLES IN SCHEMA api
- [ ] T101 [US6] Document JWT token format and role claim structure in README.md API section
- [ ] T102 [US6] Create IngressRoute manifest at k8s/postgrest/base/ingress-route.yaml per contracts/ingress-route.yaml
- [ ] T103 [P] [US6] Create rate-limit Middleware at k8s/postgrest/base/middleware-rate-limit.yaml (100 req/min per IP)
- [ ] T104 [P] [US6] Create cors-headers Middleware at k8s/postgrest/base/middleware-cors.yaml
- [ ] T105 [P] [US6] Create security-headers Middleware at k8s/postgrest/base/middleware-security.yaml
- [ ] T106 [US6] Update k8s/postgrest/base/kustomization.yaml to include IngressRoute and Middleware resources
- [ ] T107 [US6] Test role restrictions locally: verify anonymous cannot access /targets, analyst can with JWT
- [ ] T108 [US6] Test rate limiting: send >100 requests in 1 minute, verify 429 response

**Checkpoint**: User Story 6 complete - API properly secured with RBAC and rate limiting

---

## Phase 9: User Story 7 - Dependency Synchronization (Priority: P3)

**Goal**: Single source of truth for Python dependencies with locked versions

**Independent Test**: `pip install .` installs all deps including FastAPI, `uv sync` reproduces exact versions, CI fails on lock drift

**Implements**: FR-012, FR-023 | **Success Criteria**: SC-008

### Implementation for User Story 7

- [ ] T109 [US7] Audit pyproject.toml for missing dependencies: check if fastapi, uvicorn, kubernetes are listed
- [ ] T110 [US7] Add missing FastAPI dependencies to pyproject.toml: fastapi, uvicorn, python-multipart
- [ ] T111 [US7] Add kubernetes client dependency to pyproject.toml for K8s job runner mode
- [ ] T112 [US7] Ensure all observability deps from US4 are in main dependencies (not just dev)
- [ ] T113 [US7] Run `uv lock` to regenerate uv.lock with all dependencies
- [ ] T114 [US7] Verify uv.lock is committed: `git add uv.lock`
- [ ] T115 [US7] Create CI workflow at .github/workflows/ci.yaml with dependency verification step
- [ ] T116 [US7] Add lock file drift check to CI: `uv sync --frozen` should succeed
- [ ] T117 [US7] Add ruff linting step to CI workflow
- [ ] T118 [US7] Add gitleaks secret scanning step to CI workflow
- [ ] T119 [US7] Add duplicate file check step to CI using scripts/check-duplicates.sh
- [ ] T120 [US7] Test `pip install .` in clean virtual environment to verify all deps install

**Checkpoint**: User Story 7 complete - reproducible dependency management

---

## Phase 10: User Story 8 - Documentation Consolidation (Priority: P3)

**Goal**: Single authoritative source for each documentation topic

**Independent Test**: Search for "API endpoints" finds exactly one source, README links to all docs, no duplicate quickstart files

**Implements**: FR-024 | **Success Criteria**: SC-010

### Implementation for User Story 8

- [ ] T121 [US8] Audit all markdown files in repository for duplicate content
- [ ] T122 [US8] Merge specs/001-data-layer-postgrest-gitops/quickstart.md content into main README.md if not already present
- [ ] T123 [US8] Create ARCHITECTURE.md at repository root with detailed system architecture
- [ ] T124 [US8] Update README.md with documentation map section listing all docs and their purpose
- [ ] T125 [US8] Add link from README.md to ARCHITECTURE.md for detailed architecture
- [ ] T126 [US8] Add link from README.md to RECOMMENDATIONS.md for improvement roadmap
- [ ] T127 [US8] Update README.md API section with current endpoint documentation
- [ ] T128 [US8] Remove any duplicate documentation files after merging content
- [ ] T129 [US8] Add "Getting Started" section to README.md with clear steps for new developers
- [ ] T130 [US8] Verify documentation accessibility: all docs reachable within 2 clicks from README

**Checkpoint**: User Story 8 complete - clear, consolidated documentation

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, cleanup, and cross-story validation

- [ ] T131 Final gitleaks scan across entire repository: `gitleaks detect --source . -v`
- [ ] T132 [P] Verify repository size: `git count-objects -vH` (must be <10MB)
- [ ] T133 [P] Run duplicate check: `scripts/check-duplicates.sh` (must pass)
- [ ] T134 Run full CI pipeline locally to verify all checks pass
- [ ] T135 [P] Update CLAUDE.md with any new commands or conventions from this feature
- [ ] T136 Deploy to staging environment and run quickstart.md verification checklist
- [ ] T137 Document rollback procedures in case of issues
- [ ] T138 Create PR for production deployment with all changes
- [ ] T139 Final review of all success criteria (SC-001 through SC-010)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-10)**: All depend on Foundational phase completion
  - US1 and US2 can proceed in parallel (no cross-dependencies)
  - US3 depends on US2 (scripts cleaned before history rewrite)
  - US4 depends on US1 (needs Doppler for OTEL endpoint secrets)
  - US5 depends on US1, US2, US3 (needs clean repo structure)
  - US6 depends on US1 (JWT secret from Doppler)
  - US7 depends on US4 (OTEL deps added to pyproject.toml)
  - US8 depends on all others (documents final state)
- **Polish (Phase 11)**: Depends on all user stories being complete

### User Story Dependencies Graph

```
Foundational (Phase 2)
         │
    ┌────┴────┐
    ▼         ▼
   US1       US2
    │         │
    │    ┌────┘
    │    ▼
    │   US3
    │    │
    ├────┼────┬────┐
    ▼    ▼    ▼    ▼
   US4  US5  US6  (US6 also needs US1)
    │
    ▼
   US7
    │
    ▼
   US8 (depends on all)
```

### Parallel Opportunities

**Within Setup (Phase 1)**:
- T002, T003, T004, T005, T006 can all run in parallel

**Within Foundational (Phase 2)**:
- T008, T009, T010 can run in parallel

**After Foundational**:
- US1 and US2 can start simultaneously (different concerns)

**Within US1**:
- T013, T014 can run in parallel (different manifests)
- T019, T020 can run in parallel (same file but different sections)

**Within US4**:
- T057, T058 can run in parallel (different modules)
- T063, T064 can run in parallel (different manifests)

**Within US5**:
- T073-T081 (kustomization files) can all run in parallel
- T084-T086 and T088-T090 (app manifests) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch Doppler setup (sequential - needs token first):
Task T011: "Add required secrets to Doppler..."
Task T012: "Create Doppler service token..."

# Launch manifest creation in parallel:
Task T013: "Create DopplerSecret CRD manifest at .gitops/base/secrets/doppler-secret.yaml"
Task T014: "Create doppler-token-dk-data-fe Secret manifest at .gitops/base/secrets/doppler-token.yaml"

# Launch docker-compose updates in parallel:
Task T019: "Update docker-compose.yml POSTGRES_PASSWORD references"
Task T020: "Update docker-compose.yml POSTGREST_PASSWORD references"
```

## Parallel Example: User Story 5 (GitOps)

```bash
# After directory structure created (T069-T072), launch kustomizations in parallel:
Task T073: "Create k8s/postgrest/base/kustomization.yaml"
Task T074: "Create k8s/job-trigger/base/kustomization.yaml"
Task T075: "Create k8s/cronjobs/base/kustomization.yaml"
Task T076: "Create k8s/postgrest/overlays/prod/kustomization.yaml"
Task T077: "Create k8s/postgrest/overlays/staging/kustomization.yaml"
Task T078: "Create k8s/job-trigger/overlays/prod/kustomization.yaml"
Task T079: "Create k8s/job-trigger/overlays/staging/kustomization.yaml"
Task T080: "Create k8s/cronjobs/overlays/prod/kustomization.yaml"
Task T081: "Create k8s/cronjobs/overlays/staging/kustomization.yaml"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only) - Security Foundation

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete US1: Secure Secret Management ← **Critical security fix**
4. Complete US2: Codebase Deduplication ← **Enables reliable development**
5. Complete US3: Repository Size Reduction ← **Enables fast clones**
6. **STOP and VALIDATE**: All P1 stories complete, core security addressed
7. Deploy MVP to staging

### Incremental Delivery (P2 Stories)

1. Add US4: Observability → Test metrics/logs → Deploy
2. Add US5: GitOps → Test ArgoCD sync → Deploy
3. Add US6: Access Control → Test RBAC → Deploy
4. Each story adds operational capability

### Final Polish (P3 Stories)

1. Add US7: Dependencies → CI now enforces lockfile
2. Add US8: Documentation → Onboarding improved
3. Complete Polish phase → Production ready

### Parallel Team Strategy

With 2-3 developers after Foundational phase:
- **Developer A**: US1 (Secrets) → US4 (Observability) → US7 (Dependencies)
- **Developer B**: US2 (Deduplication) → US3 (Repo Size) → US5 (GitOps)
- **Developer C**: Wait for US1 → US6 (Access Control) → US8 (Documentation)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- **WARNING**: US3 requires git history rewrite - coordinate with entire team before executing
- All manifests reference contracts in specs/002-production-readiness/contracts/
- Use quickstart.md as verification runbook after each phase
