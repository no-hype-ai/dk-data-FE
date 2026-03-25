# Tasks: Platform Stabilization

**Input**: Design documents from `/specs/010-platform-stabilization/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/backup-cronjob.yaml, contracts/ci-pipeline.yaml

**Tests**: Included in Phase 6 (US4) — test coverage is an explicit user story requirement.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dev dependency configuration

- [x] T001 Add pytest-cov>=6.0.0 and responses>=0.25.0 to dev dependencies, add [tool.pytest.ini_options] addopts (--cov=src/dk_data, --cov-report=term-missing, --cov-report=xml, --cov-fail-under=15), and add [tool.coverage.run] (source, branch=true, omit) in pyproject.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No cross-cutting foundational tasks required — all user stories are independent.

**Skipped** — proceed directly to user story phases.

---

## Phase 3: User Story 1 - Restore Data Ingestion Pipelines (Priority: P1) MVP

**Goal**: Fix broken ingestion by resolving DNS, configuring registry auth, and establishing proper image promotion from staging to production.

**Independent Test**: Verify job-trigger pod reaches Running state, all 5 CronJobs complete successfully, and the promote-to-prod workflow tags images correctly.

### Implementation for User Story 1

- [ ] T002 [US1] Patch CoreDNS ConfigMap to forward external DNS queries to 8.8.8.8 in k3d cluster (kubectl edit configmap coredns -n kube-system, add forward . 8.8.8.8 block)
- [ ] T003 [US1] Add GHCR_USERNAME and GHCR_PASSWORD to Doppler dk-data-fe project (staging + prod configs) and verify ghcr-credentials imagePullSecret is created via DopplerSecret
- [x] T004 [US1] Replace hardcoded image tag with placeholder (image: ghcr.io/data-kinetic/dk-data-fe/job-trigger:latest) in k8s/base/ingestion/job-trigger-deployment.yaml
- [x] T005 [P] [US1] Add images transformer (name: ghcr.io/data-kinetic/dk-data-fe/job-trigger, newTag: staging-PLACEHOLDER) in k8s/overlays/staging/kustomization.yaml
- [x] T006 [P] [US1] Add images transformer (name: ghcr.io/data-kinetic/dk-data-fe/job-trigger, newTag: prod-PLACEHOLDER) in k8s/overlays/prod/kustomization.yaml
- [x] T007 [US1] Replace sed-based image update with kustomize edit set image targeting STAGING overlay only in .github/workflows/build-push.yaml
- [x] T008 [US1] Create auto-promotion workflow: validate staging health, get latest staging tag, crane tag to prod-{sha}, kustomize edit set image on prod overlay, commit and push in .github/workflows/promote-to-prod.yaml

**Checkpoint**: Job-trigger pod is Running, CronJobs pull images and execute successfully, staging builds auto-promote to production.

---

## Phase 4: User Story 2 - Protect Data from Loss (Priority: P1)

**Goal**: Implement automated PostgreSQL backups to MinIO with verified integrity and automated retention cleanup.

**Independent Test**: Trigger a manual backup job, verify .dump file appears in MinIO with correct tags (checksum, object count), then restore to a temp database and verify data.

### Implementation for User Story 2

- [x] T009 [US2] Create backup shell script ConfigMap with pg_dump -Fc -Z6, SHA256 checksum, pg_restore --list verification (object count >= 10), mc upload with tags, and retention cleanup (mc find --older-than 7d/30d) in k8s/base/backup/pg-backup-configmap.yaml
- [x] T010 [P] [US2] Create MinIO credential secret template referencing MINIO_ACCESS_KEY and MINIO_SECRET_KEY from Doppler in k8s/base/backup/minio-credentials.yaml
- [x] T011 [US2] Create daily backup CronJob (schedule: 0 2 * * *, BACKUP_TYPE=daily, activeDeadlineSeconds: 3600, backoffLimit: 2, requests: 512Mi/250m, limits: 2Gi/1000m) mounting configmap script in k8s/base/backup/pg-backup-daily.yaml
- [x] T012 [P] [US2] Create weekly backup CronJob (schedule: 0 3 * * 0, BACKUP_TYPE=weekly, activeDeadlineSeconds: 7200, backoffLimit: 2) mounting configmap script in k8s/base/backup/pg-backup-weekly.yaml
- [x] T013 [P] [US2] Create backup verification CronJob (schedule: 0 4 * * 1, runs pg_restore --list on latest daily backup) in k8s/base/backup/pg-backup-verify.yaml
- [x] T014 [US2] Add MinIO egress rule (to: namespaceSelector infra, port 9000/TCP) to dk-data-egress NetworkPolicy in k8s/base/networkpolicy.yaml
- [x] T015 [US2] Add backup/ directory resources (pg-backup-configmap.yaml, minio-credentials.yaml, pg-backup-daily.yaml, pg-backup-weekly.yaml, pg-backup-verify.yaml) to k8s/base/kustomization.yaml

**Checkpoint**: Daily and weekly backup CronJobs run on schedule, .dump files appear in MinIO at postgres-backups/{namespace}/{type}/, verification job confirms integrity, expired backups are cleaned up.

---

## Phase 5: User Story 3 - Eliminate Security Vulnerabilities (Priority: P1)

**Goal**: Remove hardcoded credentials from source control and standardize database naming across all environments.

**Independent Test**: Run `grep -rn "postgrest_secret_change_me" src/` and `grep -rn "edwards_tavr" docker-compose.yml src/dk_data/sql/` — both should return zero matches.

### Implementation for User Story 3

- [x] T016 [US3] Parameterize credentials in src/dk_data/sql/init_database.sql: replace PASSWORD 'postgrest_secret_change_me' with PASSWORD :'AUTHENTICATOR_PASSWORD', remove \connect edwards_tavr line, add DO $$ block that raises exception if default password detected
- [x] T017 [P] [US3] Change default database name from edwards_tavr to dk_data in POSTGRES_DB environment variable in docker-compose.yml

**Checkpoint**: Zero hardcoded credentials in source, all environments reference dk_data as database name, init script rejects default/placeholder passwords.

---

## Phase 6: User Story 4 - Establish Test Safety Net (Priority: P2)

**Goal**: Create a baseline test suite achieving >=15% coverage with import tests, model validation, API endpoint tests, and mocked fetcher tests.

**Independent Test**: Run `pytest tests/ -v --cov=src/dk_data --cov-report=term-missing --cov-fail-under=15` — all tests pass and coverage meets threshold.

### Implementation for User Story 4

- [x] T018 [P] [US4] Create import smoke tests covering all top-level dk_data submodules (fetchers, models, services, sql) to verify no import errors in tests/test_imports.py
- [x] T019 [P] [US4] Create Pydantic model instantiation and validation tests (valid data, missing required fields, type coercion) for core models in tests/test_pydantic_models.py
- [x] T020 [P] [US4] Create FastAPI job-trigger endpoint tests using TestClient (health endpoint, trigger endpoint, error responses) in tests/test_fastapi_endpoints.py
- [x] T021 [P] [US4] Create mocked HTTP fetcher tests using responses library (happy path, HTTP errors, timeout handling) for BaseFetcher subclasses in tests/test_fetchers.py
- [x] T022 [US4] Add coverage reporting to CI: upload coverage.xml as artifact, add MishaKav/pytest-coverage-comment action for PR comments in .github/workflows/ci.yaml

**Checkpoint**: pytest runs 4 new test files, all pass, coverage report shows >=15%, CI pipeline reports coverage on PRs.

---

## Phase 7: User Story 5 - Reduce Repository Bloat (Priority: P2)

**Goal**: Remove 182MB of raw CSV data from git tracking to reduce clone times and CI overhead.

**Independent Test**: Run `git status src/dk_data/data/raw/` — should show no tracked files; `grep "data/raw" .gitignore` confirms the ignore entry exists.

### Implementation for User Story 5

- [x] T023 [US5] Add src/dk_data/data/raw/ entry to .gitignore
- [x] T024 [US5] Remove raw CSV files from git tracking via git rm --cached (preserves local copies)

**Checkpoint**: Raw CSV files are untracked, .gitignore prevents re-addition, repository clone no longer includes 182MB of data files.

---

## Phase 8: User Story 6 - Enable Platform Observability (Priority: P3)

**Goal**: Activate the existing observability infrastructure (ServiceMonitor, PrometheusRule) by installing required CRDs and uncommenting disabled resources.

**Independent Test**: Run `kubectl get servicemonitors -n dk-data-staging` and `kubectl get prometheusrules -n dk-data-staging` — both return resources.

### Implementation for User Story 6

- [ ] T025 [US6] Install prometheus-operator-crds Helm chart (CRDs only, no operator deployment) in kube-system namespace
- [x] T026 [US6] Uncomment ServiceMonitor (service-monitor.yaml) and PrometheusRule (alert-rules.yaml) resources in k8s/base/kustomization.yaml

**Checkpoint**: ServiceMonitor and PrometheusRule resources are created in cluster, Prometheus/Alloy can discover and scrape dk-data metrics.

---

## Phase 9: User Story 7 - Clean Up Issue Tracker (Priority: P3)

**Goal**: Close ~15 resolved issues and consolidate duplicates so the backlog accurately reflects pending work.

**Independent Test**: Run `gh issue list --state open --limit 100 | wc -l` — count should decrease by ~15 from the starting 50.

### Implementation for User Story 7

- [x] T027 [US7] Review and close ~15 resolved GitHub issues with evidence citations (commit SHA, PR link, or code reference) via gh issue close with --comment
- [x] T028 [US7] Consolidate duplicate/overlapping issues: close lower-priority duplicate with cross-reference to surviving issue via gh issue close with --comment

**Checkpoint**: Open issue count is ~35, every closed issue has an evidence-based comment, no duplicate issues remain.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation across all user stories

- [ ] T029 Run quickstart.md verification steps 1-7 end-to-end on staging cluster
- [x] T030 Verify all CI checks pass on feature branch pull request

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 3)**: Depends on Setup — K8s operational tasks, can start immediately
- **US2 (Phase 4)**: Depends on Setup — independent of US1
- **US3 (Phase 5)**: Depends on Setup — independent of US1, US2
- **US4 (Phase 6)**: Depends on Setup (T001 provides dev deps) — independent of US1-US3
- **US5 (Phase 7)**: Depends on Setup — independent of all other stories
- **US6 (Phase 8)**: Depends on Setup — independent of all other stories
- **US7 (Phase 9)**: Depends on Setup — independent of all other stories
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories. Operational prerequisite for verifying US2 (backups need running DB with data from pipelines).
- **US2 (P1)**: No hard dependencies. Logical to implement after US1 (so pipelines are running and there's data worth backing up).
- **US3 (P1)**: No dependencies on other stories. Can be done in parallel with US1/US2.
- **US4 (P2)**: Depends on T001 (pyproject.toml dev deps). No dependencies on other stories.
- **US5 (P2)**: No dependencies. Fully independent git operation.
- **US6 (P3)**: No dependencies on other stories. T026 edits k8s/base/kustomization.yaml (also edited by T015) — sequence T015 before T026.
- **US7 (P3)**: No dependencies. Fully independent GitHub CLI operation.

### Within Each User Story

- T002 → T003 → T004 → T005/T006 (parallel) → T007 → T008 (US1: DNS → auth → base → overlays → CI → promotion)
- T009 → T010 (parallel with T009) → T011 → T012/T013 (parallel) → T014 → T015 (US2: script → secrets → CronJobs → network → kustomize)
- T016 → T017 (parallel with T016) (US3: SQL → docker-compose)
- T018/T019/T020/T021 (all parallel) → T022 (US4: test files → CI config)
- T023 → T024 (US5: gitignore → git rm)
- T025 → T026 (US6: CRDs → uncomment resources)
- T027 → T028 (US7: close resolved → consolidate duplicates)

### Parallel Opportunities

- **Within US1**: T005 + T006 (staging/prod overlays, different files)
- **Within US2**: T012 + T013 (weekly/verify CronJobs, different files); T010 parallel with T009
- **Within US3**: T016 + T017 (SQL + docker-compose, different files)
- **Within US4**: T018 + T019 + T020 + T021 (all 4 test files, no dependencies)
- **Across stories**: US1, US2, US3 can all start in parallel (all P1); US4, US5 can start in parallel (both P2); US6, US7 can start in parallel (both P3)

---

## Parallel Example: User Story 4

```bash
# Launch all test file tasks in parallel (different files, no dependencies):
Task: "Create import smoke tests in tests/test_imports.py"
Task: "Create Pydantic model validation tests in tests/test_pydantic_models.py"
Task: "Create FastAPI endpoint tests in tests/test_fastapi_endpoints.py"
Task: "Create mocked fetcher tests in tests/test_fetchers.py"

# Then sequentially:
Task: "Add coverage reporting to .github/workflows/ci.yaml"
```

## Parallel Example: User Story 2

```bash
# Launch secret template in parallel with backup script:
Task: "Create backup script ConfigMap in k8s/base/backup/pg-backup-configmap.yaml"
Task: "Create MinIO credential secret template in k8s/base/backup/minio-credentials.yaml"

# Then daily CronJob, then weekly + verify in parallel:
Task: "Create daily backup CronJob in k8s/base/backup/pg-backup-daily.yaml"
Task: "Create weekly backup CronJob in k8s/base/backup/pg-backup-weekly.yaml"
Task: "Create backup verification CronJob in k8s/base/backup/pg-backup-verify.yaml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 3: US1 - Restore Pipelines (T002-T008)
3. **STOP and VALIDATE**: Verify all 5 CronJobs run, job-trigger is Running, images promote correctly
4. This alone unblocks the entire data platform

### Incremental Delivery

1. **Sprint 1 (P1 stories)**: Setup → US1 (pipelines) → US3 (security) → US2 (backups)
   - Recommended order: fix pipelines first (highest impact), then security (quick win), then backups (needs running DB)
2. **Sprint 2 (P2 stories)**: US4 (tests) → US5 (repo bloat)
   - Tests first (enables safe iteration), then repo cleanup
3. **Sprint 3 (P3 stories)**: US6 (observability) → US7 (issue cleanup) → Polish
   - Observability enables monitoring of all prior work, issue cleanup reflects completed state

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup (T001) together
2. Once Setup is done:
   - Developer A: US1 (Restore Pipelines) → US2 (Backups)
   - Developer B: US3 (Security) → US4 (Tests)
   - Developer C: US5 (Repo Bloat) → US6 (Observability) → US7 (Issue Cleanup)
3. Stories complete and integrate independently
4. Polish phase after all stories merge

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- T002, T003, T025 are operational/cluster tasks (kubectl, Doppler, Helm) not code file changes
- T027, T028 are GitHub CLI operations, not code changes
- T015 and T026 both modify k8s/base/kustomization.yaml — execute T015 (US2) before T026 (US6) to avoid conflicts
- Commit after each task or logical group within a story
- Stop at any checkpoint to validate story independently
