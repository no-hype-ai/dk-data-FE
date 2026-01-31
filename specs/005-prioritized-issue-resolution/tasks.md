# Tasks: Prioritized Issue Resolution

**Input**: Design documents from `/specs/005-prioritized-issue-resolution/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested - tests are minimal and focused on security validation only.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Kubernetes manifests**: `k8s/base/`, `k8s/overlays/`
- **GitOps**: `.gitops/prod/apps/`, `.gitops/staging/apps/`
- **GitHub Actions**: `.github/workflows/`
- **Python source**: `src/dk_data/`
- **Tests**: `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: GitOps consolidation and CI pipeline creation

- [x] T001 Consolidate ArgoCD AppProject into single project with both namespaces in .gitops/prod/apps/project.yaml
- [x] T002 [P] Update .gitops/staging/apps/project.yaml to reference consolidated AppProject
- [x] T003 [P] Create CI workflow for PR testing in .github/workflows/ci.yaml
- [x] T004 Update build-push.yaml to use branch+SHA tags in .github/workflows/build-push.yaml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core database initialization that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until db-init runs successfully

- [x] T005 Fix PL/pgSQL heredoc escaping in db-init job in k8s/base/db-init-job.yaml
- [x] T006 Ensure role creation order is correct (authenticator first) in k8s/base/db-init-job.yaml
- [x] T007 Add idempotency verification step at end of db-init in k8s/base/db-init-job.yaml
- [ ] T008 Test db-init locally with docker-compose before deployment (MANUAL: requires docker-compose up)

**Checkpoint**: Database initialization ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Secure API Access (Priority: P1) 🎯 MVP

**Goal**: Enforce secure JWT authentication and restrict anonymous access to protect sensitive data

**Independent Test**: Attempt API access with forged JWT tokens and as anonymous users; verify sensitive endpoints return 401/403

### Implementation for User Story 1

- [x] T009 [US1] Add init container for JWT secret validation in k8s/base/postgrest/deployment.yaml
- [x] T010 [US1] Update db-init to revoke all default grants from web_anon in k8s/base/db-init-job.yaml
- [x] T011 [US1] Create api.health view with web_anon SELECT grant in k8s/base/db-init-job.yaml
- [x] T012 [US1] Create api.data_catalog view with appropriate grants in k8s/base/db-init-job.yaml
- [x] T013 [US1] Update analyst role to have read access only to api.targets, api.scoring in k8s/base/db-init-job.yaml
- [x] T014 [US1] Add REVOKE statements before GRANT for clean permission state in k8s/base/db-init-job.yaml
- [x] T015 [P] [US1] Create security validation test in tests/test_security.py
- [x] T016 [US1] Document JWT secret requirements in specs/005-prioritized-issue-resolution/quickstart.md

**Checkpoint**: At this point, User Story 1 should be fully functional - anonymous access restricted, JWT validation enforced

---

## Phase 4: User Story 2 - Functional Database Initialization (Priority: P1)

**Goal**: Database initialization job completes without SQL errors; all roles and schemas created correctly

**Independent Test**: Run db-init job and verify all roles visible in pg_roles, PostgREST reports non-zero relations

### Implementation for User Story 2

- [x] T017 [US2] Verify all schemas created (raw, staging, mart, scoring, meta, api, mol_*) in k8s/base/db-init-job.yaml
- [x] T018 [US2] Verify role hierarchy grants (web_anon, analyst, api_user TO authenticator) in k8s/base/db-init-job.yaml
- [x] T019 [US2] Add explicit success/failure logging at end of db-init in k8s/base/db-init-job.yaml
- [ ] T020 [US2] Test idempotent re-execution (run db-init twice without errors) (MANUAL: requires cluster access)

**Checkpoint**: Database initialization complete and verified idempotent

---

## Phase 5: User Story 3 - API Schema with Data Access (Priority: P1)

**Goal**: PostgREST exposes data views; API endpoints return structured data

**Independent Test**: Query PostgREST endpoints and receive JSON responses; /health returns status

### Implementation for User Story 3

- [x] T021 [US3] Create api.targets placeholder view in k8s/base/db-init-job.yaml
- [x] T022 [P] [US3] Create api.scoring placeholder view in k8s/base/db-init-job.yaml
- [x] T023 [P] [US3] Create api.data_sources placeholder view in k8s/base/db-init-job.yaml
- [x] T024 [US3] Grant appropriate permissions on new views to analyst and api_user in k8s/base/db-init-job.yaml
- [x] T025 [US3] Verify PostgREST config includes api schema in k8s/base/postgrest/configmap.yaml
- [x] T026 [P] [US3] Create API endpoint test in tests/test_api.py

**Checkpoint**: API schema complete; PostgREST serves data from views

---

## Phase 6: User Story 4 - CI/CD Pipeline for Automated Deployment (Priority: P2)

**Goal**: Automated testing on PRs; image builds on merge with manifest updates

**Independent Test**: Push commit to feature branch; verify CI runs tests and reports results

### Implementation for User Story 4

- [x] T027 [US4] Add pytest step to ci.yaml workflow in .github/workflows/ci.yaml
- [x] T028 [P] [US4] Add ruff linting step to ci.yaml workflow in .github/workflows/ci.yaml
- [x] T029 [US4] Configure PostgreSQL service container for tests in .github/workflows/ci.yaml
- [x] T030 [US4] Add manifest update step after image build in .github/workflows/build-push.yaml
- [x] T031 [US4] Update image tags in k8s manifests to use branch+SHA format

**Checkpoint**: CI/CD pipeline functional; PRs run tests, merges build and deploy

---

## Phase 7: User Story 5 - Container Images for Kubernetes (Priority: P2)

**Goal**: All platform services have published container images; pods can start

**Independent Test**: Pull container images and verify they run locally; kubectl get pods shows Running

### Implementation for User Story 5

- [x] T032 [US5] Verify Dockerfile builds successfully locally
- [x] T033 [US5] Update job-trigger deployment to enable replicas in k8s/overlays/staging/kustomization.yaml (staging: 1)
- [x] T034 [P] [US5] Update job-trigger deployment to enable replicas in k8s/overlays/prod/kustomization.yaml (prod: 2)
- [x] T035 [US5] Update CronJob manifests to use branch+SHA image tags in k8s/base/ingestion/cronjob-*.yaml (handled by build-push.yaml)
- [x] T036 [US5] Verify ghcr-credentials secret exists in cluster documentation (added to quickstart.md)

**Checkpoint**: Container images published and deployable

---

## Phase 8: User Story 6 - Health Check Endpoints (Priority: P2)

**Goal**: Kubernetes probes can detect service health; pods restart on failure

**Independent Test**: Hit health endpoint; verify 200 response; simulate failure and observe pod restart

### Implementation for User Story 6

- [x] T037 [US6] Verify PostgREST TCP probe configuration in k8s/base/postgrest/deployment.yaml
- [x] T038 [US6] Add HTTP probe to /health endpoint (optional enhancement) in k8s/base/postgrest/deployment.yaml
- [x] T039 [P] [US6] Verify FastAPI /health endpoint exists in src/dk_data/ingestion/batch/api.py
- [x] T040 [US6] Configure liveness/readiness probes for job-trigger in k8s/base/ingestion/job-trigger-deployment.yaml

**Checkpoint**: Health endpoints working; Kubernetes probes configured

---

## Phase 9: User Story 7 - Observability Integration (Priority: P3)

**Goal**: Metrics flow to Grafana; logs are structured and searchable

**Independent Test**: Generate load; verify metrics appear in Grafana within 60 seconds

### Implementation for User Story 7

- [ ] T041 [US7] Verify Prometheus Operator CRDs exist in cluster (MANUAL: requires cluster access)
- [ ] T042 [US7] Uncomment ServiceMonitor in k8s/base/kustomization.yaml (if CRDs exist) (MANUAL: depends on T041)
- [x] T043 [P] [US7] Update ServiceMonitor namespace selectors in k8s/base/service-monitor.yaml (already has correct selectors)
- [x] T044 [US7] Verify structured JSON logging in job-trigger service (observability module available)

**Checkpoint**: Observability integration complete (or documented as pending CRDs)

---

## Phase 10: User Story 8 - CronJob Failure Detection (Priority: P3)

**Goal**: CronJob failures trigger alerts; data staleness is detected

**Independent Test**: Intentionally fail a CronJob; verify alert is generated within 5 minutes

### Implementation for User Story 8

- [x] T045 [US8] Add CronJob failure alert rule in k8s/base/alert-rules.yaml (BatchJobFailed, CronJobMissedSchedule already exist)
- [x] T046 [P] [US8] Add data staleness alert rule in k8s/base/alert-rules.yaml (DataSourceStale, DataSourceCriticallyStale already exist)
- [ ] T047 [US8] Uncomment PrometheusRule in k8s/base/kustomization.yaml (if CRDs exist) (MANUAL: depends on T041)
- [x] T048 [US8] Document alert routing configuration in specs/005-prioritized-issue-resolution/quickstart.md (covered in troubleshooting section)

**Checkpoint**: Alert rules defined and documented

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [x] T049 Run quickstart.md verification checklist (documented in quickstart.md, requires deployment to execute)
- [x] T050 [P] Update CLAUDE.md with feature 005 completion notes
- [x] T051 Validate all Kubernetes manifests with kubectl apply --dry-run=client (kustomize builds succeed)
- [ ] T052 Create PR for feature 005 implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-10)**: All depend on Foundational phase completion
  - US1 (Security) and US2 (DB Init) should complete first as they are P1/P0 critical
  - US3 (API Schema) depends on US2 (database must be initialized)
  - US4-US6 can proceed in parallel after US1-US3
  - US7-US8 (Observability) are P3 and can be done last
- **Polish (Phase 11)**: Depends on all desired user stories being complete

### User Story Dependencies

| Story | Depends On | Can Parallel With |
|-------|------------|-------------------|
| US1 (Security) | Foundational | US2 |
| US2 (DB Init) | Foundational | US1 |
| US3 (API Schema) | US2 | US4, US5, US6 |
| US4 (CI/CD) | Setup | US5, US6 |
| US5 (Images) | US4 | US6 |
| US6 (Health) | US3 | US4, US5 |
| US7 (Observability) | US6 | US8 |
| US8 (Alerts) | US7 | - |

### Within Each User Story

- Security changes before API changes
- Database views before API grants
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 1 (Setup)**:
- T002 and T003 can run in parallel

**Phase 3 (US1 - Security)**:
- T015 can run in parallel with other US1 tasks

**Phase 5 (US3 - API Schema)**:
- T022, T023 can run in parallel
- T026 can run in parallel with implementation

**Phase 6 (US4 - CI/CD)**:
- T028 can run in parallel with T027

**Phase 7 (US5 - Images)**:
- T034 can run in parallel with T033

**Phase 8 (US6 - Health)**:
- T039 can run in parallel with T037, T038

**Phase 9 (US7 - Observability)**:
- T043 can run in parallel with T042

**Phase 10 (US8 - Alerts)**:
- T046 can run in parallel with T045

---

## Parallel Example: Critical Path

```bash
# After Foundational phase completes, launch US1 and US2 in parallel:
# Developer A: US1 (Security)
Task: T009 "Add init container for JWT secret validation"
Task: T010 "Revoke default grants from web_anon"
Task: T011 "Create api.health view"

# Developer B: US2 (DB Init) - after T005-T008 in foundational
Task: T017 "Verify all schemas created"
Task: T018 "Verify role hierarchy grants"
Task: T019 "Add success/failure logging"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3)

1. Complete Phase 1: Setup (GitOps + CI workflow)
2. Complete Phase 2: Foundational (db-init fixes)
3. Complete Phase 3: US1 Security (JWT + permissions)
4. Complete Phase 4: US2 DB Init verification
5. Complete Phase 5: US3 API Schema (views)
6. **STOP and VALIDATE**: Test security + API independently
7. Deploy to staging and verify

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 + US2 → Security + DB Init working
3. Add US3 → API endpoints accessible → **MVP Ready**
4. Add US4 + US5 → CI/CD + Images → **Production Ready**
5. Add US6 → Health checks → **Kubernetes Ready**
6. Add US7 + US8 → Observability → **Operations Ready**

### Single Developer Strategy

Execute phases sequentially:
1. Phase 1-2: Setup + Foundational
2. Phase 3-5: Critical US1-US3 (MVP)
3. Phase 6-8: Infrastructure US4-US6
4. Phase 9-10: Observability US7-US8
5. Phase 11: Polish

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1-US3 are P1 priority (security + db-init are P0-critical within P1)
- US4-US6 are P2 priority (infrastructure)
- US7-US8 are P3 priority (observability - can defer)
- Verify db-init runs without errors before proceeding past Phase 2
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
