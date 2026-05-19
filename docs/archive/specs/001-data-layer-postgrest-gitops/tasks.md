# Tasks: Data Layer Enhancement with PostgREST and GitOps

**Input**: Design documents from `/specs/001-data-layer-postgrest-gitops/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1, US2, US3, US4) or shared (no label)
- Exact file paths included in descriptions

## Path Conventions

Based on plan.md structure:
- **Source**: `src/dk_data/`
- **SQL**: `src/dk_data/sql/`
- **GitOps**: `.gitops/`
- **Config**: `src/dk_data/` (docker-compose, Makefile)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and directory structure

- [X] T001 Create `.gitops/` directory structure with base/, overlays/, argocd/ subdirectories
- [X] T002 [P] Create `src/dk_data/ingestion/batch/` module directory with `__init__.py`
- [X] T003 [P] Add FastAPI dependency to `src/dk_data/requirements.txt`
- [X] T004 [P] Add kubernetes Python client dependency to `src/dk_data/requirements.txt`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema enhancements that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Enhance `meta.data_sources` table with new columns (topic_tags, column_descriptions, staleness_threshold_hours, table_size_bytes, ai_description, target_tables) in `src/dk_data/sql/init_database.sql`
- [X] T006 Create `meta.table_health` table with health tracking columns in `src/dk_data/sql/init_database.sql`
- [X] T007 Create `meta.batch_jobs` table for job definitions in `src/dk_data/sql/init_database.sql`
- [X] T008 Create `meta.batch_job_runs` table for execution history in `src/dk_data/sql/init_database.sql`
- [X] T009 [P] Add database indexes for catalog performance (GIN index on topic_tags, health lookups) in `src/dk_data/sql/init_database.sql`
- [X] T010 [P] Add validation constraints (health_status enum, null_rate range, run_status enum) in `src/dk_data/sql/init_database.sql`
- [X] T011 Create SQL migration script to apply schema changes to existing databases in `src/dk_data/sql/migrations/001_catalog_health_jobs.sql`

**Checkpoint**: Database schema ready - user story implementation can now begin

---

## Phase 3: User Story 1 - API Consumer Queries Data via REST (Priority: P1) 🎯 MVP

**Goal**: Expose PostgreSQL views through PostgREST with filtering, pagination, and data catalog endpoint

**Independent Test**: Query `/catalog` and `/targets` endpoints with filters, verify JSON responses with pagination headers

### Implementation for User Story 1

- [X] T012 [US1] Create `api.catalog` view joining data_sources with latest table_health in `src/dk_data/sql/api_views.sql`
- [X] T013 [US1] Create `api.jobs` view exposing batch job definitions in `src/dk_data/sql/api_views.sql`
- [X] T014 [US1] Create `api.job_runs` view exposing execution history in `src/dk_data/sql/api_views.sql`
- [X] T015 [US1] Create `api.health` view for system health check in `src/dk_data/sql/api_views.sql`
- [X] T016 [US1] Grant SELECT permissions on new api views to web_anon and api_user roles in `src/dk_data/sql/api_views.sql`
- [X] T017 [US1] Create `calculate_health_status()` SQL function for health determination in `src/dk_data/sql/catalog_functions.sql`
- [X] T018 [US1] Create trigger to update health status on refresh_log inserts in `src/dk_data/sql/catalog_functions.sql`
- [X] T019 [US1] Create `src/dk_data/scripts/catalog_refresh.py` to populate semantic metadata (descriptions, topic_tags)
- [X] T020 [US1] Seed initial batch job definitions (fetch-cms-all, fetch-individual-sources) in `src/dk_data/sql/seed_batch_jobs.sql`
- [X] T021 [US1] Add `catalog-refresh` make target to `src/dk_data/Makefile`
- [X] T022 [US1] Update `api-test` make target to include catalog and jobs endpoint examples in `src/dk_data/Makefile`

**Checkpoint**: API endpoints `/catalog`, `/jobs`, `/job_runs`, `/health` are functional and queryable

---

## Phase 4: User Story 2 - DevOps Engineer Deploys via GitOps (Priority: P2)

**Goal**: Kubernetes manifests compatible with k3s and ArgoCD for GitOps deployment

**Independent Test**: Apply manifests to k3s cluster with `kubectl apply -k .gitops/overlays/dev`, verify pods healthy

### Kustomize Base Manifests

- [X] T023 [P] [US2] Create namespace manifest in `.gitops/base/namespace.yaml`
- [X] T024 [P] [US2] Create PostgREST Deployment in `.gitops/base/postgrest/deployment.yaml`
- [X] T025 [P] [US2] Create PostgREST Service in `.gitops/base/postgrest/service.yaml`
- [X] T026 [P] [US2] Create PostgREST ConfigMap in `.gitops/base/postgrest/configmap.yaml`
- [X] T027 [US2] Create base kustomization.yaml referencing all base resources in `.gitops/base/kustomization.yaml`

### Batch Job Manifests

- [X] T028 [P] [US2] Create CronJob for fetch-cms-all in `.gitops/base/ingestion/cronjob-cms-all.yaml`
- [X] T029 [P] [US2] Create CronJob for catalog refresh in `.gitops/base/catalog/cronjob-refresh.yaml`
- [X] T030 [P] [US2] Create Job Trigger Service Deployment in `.gitops/base/ingestion/job-trigger-deployment.yaml`
- [X] T031 [P] [US2] Create Job Trigger Service in `.gitops/base/ingestion/job-trigger-service.yaml`

### Environment Overlays

- [X] T032 [P] [US2] Create dev overlay kustomization in `.gitops/overlays/dev/kustomization.yaml`
- [X] T033 [P] [US2] Create staging overlay kustomization in `.gitops/overlays/staging/kustomization.yaml`
- [X] T034 [P] [US2] Create prod overlay kustomization with replica patches in `.gitops/overlays/prod/kustomization.yaml`
- [X] T035 [P] [US2] Create prod replicas patch in `.gitops/overlays/prod/patches/replicas.yaml`

### ArgoCD Integration

- [X] T036 [US2] Create ArgoCD Application manifest in `.gitops/argocd/application.yaml`
- [X] T037 [US2] Add README.md with GitOps deployment instructions in `.gitops/README.md`

**Checkpoint**: GitOps deployment works - `kubectl apply -k .gitops/overlays/dev` deploys functional stack

---

## Phase 5: User Story 3 - Developer Runs Full Stack Locally (Priority: P3)

**Goal**: Enhanced docker-compose for complete local development with PostgreSQL, PostgREST, and job trigger

**Independent Test**: Run `docker compose up`, verify all services start within 2 minutes, API responds

### Docker Compose Enhancement

- [X] T038 [US3] Enhance PostgreSQL service with health check in `src/dk_data/docker-compose.yml`
- [X] T039 [US3] Enhance PostgREST service with proper depends_on and health check in `src/dk_data/docker-compose.yml`
- [X] T040 [US3] Add job-trigger service definition to `src/dk_data/docker-compose.yml`
- [X] T041 [US3] Add network and volume definitions for service connectivity in `src/dk_data/docker-compose.yml`
- [X] T042 [US3] Create `src/dk_data/docker-compose.prod.yml` override for production-like settings

### Batch Job API Service

- [X] T043 [US3] Implement job runner module in `src/dk_data/ingestion/batch/job_runner.py`
- [X] T044 [US3] Implement FastAPI job trigger API with `/jobs` and `/jobs/{name}/trigger` in `src/dk_data/ingestion/batch/api.py`
- [X] T045 [US3] Create Dockerfile for job-trigger service in `src/dk_data/ingestion/batch/Dockerfile`
- [X] T046 [US3] Add job-trigger service startup to Makefile `dev` target in `src/dk_data/Makefile`

### Local Development Commands

- [X] T047 [US3] Add `batch-trigger` make target for testing job triggers locally in `src/dk_data/Makefile`
- [X] T048 [US3] Add `catalog-status` make target to show catalog health in `src/dk_data/Makefile`
- [X] T049 [US3] Update `status` make target to include job-trigger service in `src/dk_data/Makefile`

**Checkpoint**: Local stack fully functional with batch job triggering capability

---

## Phase 6: User Story 4 - Role-Based API Access (Priority: P4)

**Goal**: Configure PostgREST with role-based access for authenticated vs anonymous users

**Independent Test**: Anonymous requests get public data, JWT-authenticated requests get additional data

### Database Roles

- [X] T050 [P] [US4] Create `analyst` role with extended permissions in `src/dk_data/sql/init_database.sql`
- [X] T051 [P] [US4] Create restricted views for anonymous access in `src/dk_data/sql/api_views.sql`
- [X] T052 [US4] Configure role switching based on JWT claims in PostgREST config

### PostgREST JWT Configuration

- [X] T053 [US4] Add JWT secret configuration to PostgREST environment in `src/dk_data/docker-compose.yml`
- [X] T054 [US4] Add JWT secret to Kubernetes secrets in `.gitops/base/postgrest/secret.yaml`
- [X] T055 [US4] Document role-based access patterns in `ARCHITECTURE.md`

**Checkpoint**: Role-based access working - anonymous vs authenticated requests return different data

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, and improvements across all stories

- [X] T056 Update `ARCHITECTURE.md` with enhanced data layer documentation
- [X] T057 [P] Add data catalog section to `ARCHITECTURE.md` describing meta schema
- [X] T058 [P] Add GitOps deployment section to `ARCHITECTURE.md` with Kustomize patterns
- [X] T059 [P] Add batch scheduling section to `ARCHITECTURE.md` with CronJob patterns
- [X] T060 [P] Update `src/dk_data/README.md` with new make targets and features
- [X] T061 Run quickstart.md validation - verify all commands work
- [X] T062 Create example API queries document in `docs/api-examples.md`
- [X] T063 Add OpenAPI spec link to PostgREST endpoint documentation

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup ─────────────────────────────────────────────┐
                                                            │
Phase 2: Foundational (BLOCKS ALL) ─────────────────────────┤
                                                            │
        ┌───────────────────────────────────────────────────┘
        │
        ├── Phase 3: US1 (API/Catalog) ──┐
        │                                 │
        ├── Phase 4: US2 (GitOps) ────────┼── Can run in parallel
        │                                 │   after Phase 2
        ├── Phase 5: US3 (Local Dev) ─────┤
        │                                 │
        └── Phase 6: US4 (Auth) ──────────┘
                                          │
Phase 7: Polish ──────────────────────────┘
```

### User Story Dependencies

| Story | Depends On | Can Parallel With |
|-------|------------|-------------------|
| US1 (API) | Phase 2 | US2, US3, US4 |
| US2 (GitOps) | Phase 2 | US1, US3, US4 |
| US3 (Local Dev) | Phase 2, partial US1 (API views) | US2, US4 |
| US4 (Auth) | Phase 2, US1 (views must exist) | US2 |

### Within Each User Story

1. SQL schema/views first
2. Functions and triggers second
3. Application code third
4. Configuration fourth
5. Documentation last

---

## Parallel Execution Examples

### Phase 2 (Foundational) - All schema tasks in parallel:

```bash
# Can run T005, T006, T007, T008 in parallel (different tables)
# Then T009, T010 in parallel (indexes and constraints)
```

### Phase 4 (GitOps) - Manifest creation in parallel:

```bash
# Launch all base manifests together:
Task T023: Create namespace.yaml
Task T024: Create postgrest/deployment.yaml
Task T025: Create postgrest/service.yaml
Task T026: Create postgrest/configmap.yaml

# Launch all overlays together:
Task T032: Create dev overlay
Task T033: Create staging overlay
Task T034: Create prod overlay
```

### Cross-Story Parallelism (after Phase 2):

```bash
# Team can split:
# Developer A: US1 (T012-T022) - API and catalog
# Developer B: US2 (T023-T037) - GitOps manifests
# Developer C: US3 (T038-T049) - Docker compose and batch API
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (database schema)
3. Complete Phase 3: User Story 1 (API/Catalog)
4. **STOP and VALIDATE**: Test `/catalog`, `/jobs`, `/health` endpoints
5. Deploy/demo with just API functionality

### Incremental Delivery

1. Setup + Foundational → Schema ready
2. Add US1 → API working → **MVP!**
3. Add US2 → GitOps deployable → Production-ready
4. Add US3 → Local dev enhanced → Developer experience
5. Add US4 → Auth enabled → Security complete

### Suggested Order for Solo Developer

```
T001-T004 (Setup)
T005-T011 (Foundational)
T012-T022 (US1 - API) ← MVP checkpoint
T038-T049 (US3 - Local Dev) ← Enables testing
T023-T037 (US2 - GitOps) ← Production ready
T050-T055 (US4 - Auth) ← Security
T056-T063 (Polish)
```

---

## Task Summary

| Phase | Task Range | Count | Purpose |
|-------|------------|-------|---------|
| 1: Setup | T001-T004 | 4 | Directory structure |
| 2: Foundational | T005-T011 | 7 | Database schema |
| 3: US1 (API) | T012-T022 | 11 | MVP - API endpoints |
| 4: US2 (GitOps) | T023-T037 | 15 | K8s deployment |
| 5: US3 (Local Dev) | T038-T049 | 12 | Docker compose |
| 6: US4 (Auth) | T050-T055 | 6 | Role-based access |
| 7: Polish | T056-T063 | 8 | Documentation |
| **Total** | | **63** | |

---

## Notes

- [P] tasks = different files, can run in parallel
- [US#] label maps task to user story for traceability
- Commit after each logical group of tasks
- Each story checkpoint should be independently verifiable
- US1 (API) is the MVP - deploy early, iterate often
