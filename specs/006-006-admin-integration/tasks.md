# Tasks: Admin App Integration Fix

**Input**: Design documents from `/specs/006-006-admin-integration/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not requested - skipping test tasks.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Infrastructure project**: `k8s/base/`, `k8s/overlays/`
- **Admin App** (separate repo): `/Users/nicholas/Code/behavior-labs-ai/apps/admin/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify environment and prepare for implementation

- [x] T001 Verify current branch is `006-006-admin-integration` and up to date
- [x] T002 [P] Read current `k8s/base/db-init-job.yaml` and identify all `DO $$...$$` blocks (lines 85, 126, 140, 297)
- [x] T003 [P] Verify staging cluster is accessible via kubectl (namespace exists per ArgoCD)
- [x] T004 [P] Verify production cluster is accessible via kubectl (namespace exists per ArgoCD)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core fixes that MUST be complete before deployment

**⚠️ CRITICAL**: db-init escaping fix must be complete before any deployment

- [x] T005 Create backup of current `k8s/base/db-init-job.yaml` before modifications
- [x] T006 Identify all heredoc sections containing `DO $$...$$` blocks in db-init-job.yaml (Steps 4, 7, 11)

**Checkpoint**: Ready to implement db-init fix

---

## Phase 3: User Story 1 & 4 - Production Database Initialization + Pod Recovery (Priority: P1) 🎯 MVP

**Goal**: Fix db-init heredoc escaping so roles and views are created without SQL errors, enabling PostgREST pods to recover.

**Independent Test**: Deploy to staging, verify PostgREST logs show "Schema cache loaded X Relations" where X >= 5, and `/health` returns 200 OK.

### Implementation for User Story 1 & 4

- [x] T007 [US1] Fix role creation heredoc in Step 4 of `k8s/base/db-init-job.yaml` - changed to `DO $role$`
- [x] T008 [US1] Fix permission grant heredoc in Step 7 of `k8s/base/db-init-job.yaml` - changed to `DO $perm$`
- [x] T009 [US1] Fix permission grant heredoc in Step 10 of `k8s/base/db-init-job.yaml` - no DO blocks (direct GRANTs)
- [x] T010 [US1] Fix cross-database isolation heredoc in Step 11 of `k8s/base/db-init-job.yaml` - changed to `DO $iso$`
- [x] T011 [US1] Test db-init locally using docker to verify SQL syntax is valid before deployment
- [ ] T012 [US1] Deploy fixed db-init to staging: `kubectl delete job db-init -n dk-data-staging && kubectl apply -k k8s/overlays/staging`
- [ ] T013 [US1] Verify staging db-init Job completes with exit code 0, check logs for no SQL errors
- [ ] T014 [US1] Verify staging PostgREST logs show "Schema cache loaded N Relations" where N >= 5
- [ ] T015 [US1] Test staging `/health` endpoint returns 200 OK via port-forward
- [ ] T016 [US4] Deploy fixed db-init to production: `kubectl delete job db-init -n dk-data-prod && kubectl apply -k k8s/overlays/prod`
- [ ] T017 [US4] Verify production db-init Job completes with exit code 0
- [ ] T018 [US4] Verify production PostgREST logs show "Schema cache loaded N Relations" where N >= 5
- [ ] T019 [US4] Verify all PostgREST pods in production show 1/1 Running status
- [ ] T020 [US4] Delete CrashLoopBackOff pod if it doesn't auto-recover: `kubectl delete pod <pod-name> -n dk-data-prod`
- [ ] T021 [US4] Test production `/health` endpoint returns 200 OK

**Checkpoint**: Production db-init working, all PostgREST pods healthy. MVP complete.

---

## Phase 4: User Story 2 - Compass API Views (Priority: P2)

**Goal**: Create api.molecules and api.resolution_queue views expected by Admin App Compass features.

**Independent Test**: Call `GET /molecules` and `GET /resolution_queue` with valid JWT and receive 200 OK responses.

### Implementation for User Story 2

- [x] T022 [US2] Add api.molecules view definition to Step 9 of `k8s/base/db-init-job.yaml` using placeholder pattern from data-model.md
- [x] T023 [US2] Add api.resolution_queue view definition to Step 9 of `k8s/base/db-init-job.yaml` using placeholder pattern from data-model.md
- [x] T024 [US2] Update api.data_sources view in Step 9 of `k8s/base/db-init-job.yaml` to include additional columns (id, record_count, error_message)
- [x] T025 [US2] Add GRANT statements in Step 10 of `k8s/base/db-init-job.yaml`: web_anon SELECT on api.molecules, api.data_sources
- [x] T026 [US2] Add GRANT statements in Step 10 of `k8s/base/db-init-job.yaml`: analyst, api_user SELECT on api.resolution_queue
- [x] T027 [US2] Add explicit REVOKE in Step 10 of `k8s/base/db-init-job.yaml`: resolution_queue from web_anon
- [x] T028 [US2] Update verification section in Step 12 of `k8s/base/db-init-job.yaml` to expect 7+ API views
- [ ] T029 [US2] Deploy updated db-init to staging and verify new views are created
- [ ] T030 [US2] Test `/molecules` endpoint in staging with JWT returns 200 OK
- [ ] T031 [US2] Test `/resolution_queue` endpoint in staging with analyst JWT returns 200 OK
- [ ] T032 [US2] Test `/resolution_queue` endpoint in staging without auth returns 401/403
- [ ] T033 [US2] Deploy to production and verify all Compass views exist

**Checkpoint**: Compass API views available. Admin App can now access /molecules, /data_sources, /resolution_queue endpoints.

---

## Phase 5: User Story 3 - Graceful Service Degradation (Priority: P3)

**Goal**: Document patterns for Admin App resilience when dk-data is unavailable.

**Independent Test**: Admin App shows "dk-data: offline" badge when dk-data is unavailable.

**Note**: Implementation is in Admin App repository (`/Users/nicholas/Code/behavior-labs-ai`), not dk-data-fe. This phase documents patterns only.

### Documentation for User Story 3

- [x] T034 [US3] Document PostgREST client health check caching pattern in `specs/006-006-admin-integration/admin-app-patterns.md`
- [x] T035 [US3] Document service status badge component pattern in `specs/006-006-admin-integration/admin-app-patterns.md`
- [x] T036 [US3] Document health proxy endpoint pattern in `specs/006-006-admin-integration/admin-app-patterns.md`
- [x] T037 [US3] Create GitHub issue in behavior-labs-ai repo for Admin App graceful degradation implementation (issue #469)

**Checkpoint**: Patterns documented for Admin App team to implement.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [ ] T038 Run quickstart.md verification commands to validate all success criteria
- [ ] T039 Update checklists/requirements.md to mark completed items
- [ ] T040 [P] Commit all changes with descriptive commit message
- [ ] T041 Create PR from feature branch to staging
- [ ] T042 Verify ArgoCD syncs staging deployment successfully
- [ ] T043 Create PR from staging to main for production deployment

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Story 1 & 4 (Phase 3)**: Depends on Foundational - BLOCKS Phase 4
- **User Story 2 (Phase 4)**: Depends on Phase 3 completion (db-init must work first)
- **User Story 3 (Phase 5)**: Can run in parallel with Phase 4 (documentation only)
- **Polish (Phase 6)**: Depends on all desired phases being complete

### User Story Dependencies

```
US1 (db-init fix) ──┬──► US4 (pod recovery) ──► US2 (Compass views)
                    │
                    └──► US3 (graceful degradation - docs only)
```

- **User Story 1 (P1)**: Must complete first - fixes fundamental db-init issue
- **User Story 4 (P1)**: Depends on US1 - pod recovery after db-init fix
- **User Story 2 (P2)**: Depends on US1/US4 - views require working db-init
- **User Story 3 (P3)**: Documentation only, can proceed in parallel

### Within Each Phase

- Staging deployment before production deployment
- Verification after each deployment
- Fix issues before moving to next step

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 can run in parallel
- **Phase 3**: Staging tasks sequential; production tasks sequential after staging verified
- **Phase 4**: T022, T023, T024 can be developed together (same file, sequential edits)
- **Phase 5**: T034, T035, T036 can run in parallel (same file, different sections)
- **Phase 6**: T040 is parallel (different file from deployment)

---

## Parallel Example: Phase 1 Setup

```bash
# Launch verification tasks in parallel:
Task: "Read current k8s/base/db-init-job.yaml and identify all DO blocks"
Task: "Verify staging cluster is accessible via kubectl"
Task: "Verify production cluster is accessible via kubectl"
```

---

## Implementation Strategy

### MVP First (User Story 1 & 4 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 & 4 (db-init fix + pod recovery)
4. **STOP and VALIDATE**: Test db-init completes, PostgREST healthy
5. Deploy to production - Admin App may still show 503 for Compass (views don't exist yet)

### Incremental Delivery

1. Complete Setup + Foundational → Ready for fixes
2. Add User Story 1 & 4 → Production healthy → **MVP deployed**
3. Add User Story 2 → Compass views exist → Admin App Compass works
4. Add User Story 3 → Patterns documented → Admin App team can implement resilience

### Critical Path

```
T007 → T008 → T009 → T010 → T011 → T012 → T013 → T014 → T015 → T016 → T017 → T018 → T019
                                                                              ↓
T022 → T023 → T024 → T025 → T026 → T027 → T028 → T029 → T030 → T031 → T032 → T033
```

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- User Stories 1 & 4 are combined in Phase 3 as they're tightly coupled
- User Story 3 (Admin App changes) is documentation-only in this repo
- Staging deployment must succeed before production deployment
- Commit after each logical group of tasks
- Stop at any checkpoint to validate story independently
