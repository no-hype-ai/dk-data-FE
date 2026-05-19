# Tasks: Observability & Platform Governance

**Input**: Design documents from `/specs/013-observability-governance/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-views.sql, quickstart.md

**Tests**: Included per FR-016 requirement (unit tests for all new code paths).

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Branch preparation and verification of existing state

- [x] T001 Verify current branch is `013-observability-governance` and up-to-date with main

**Checkpoint**: Branch ready for implementation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No shared foundational tasks — each user story is self-contained. Proceed directly to user story phases.

**Checkpoint**: Foundation ready — user story implementation can begin

---

## Phase 3: User Story 1 — Deploy ServiceMonitors and Verify Metrics Scraping (Priority: P1) MVP

**Goal**: Verify existing Prometheus instrumentation is emitting all 10 metric families, fix any label mismatches in ServiceMonitor/PrometheusRule manifests, and ensure CronJob pod templates have the labels required by PodMonitors. Resolves GitHub Issue #91 (tasks 1-3, 5).

**Independent Test**: Port-forward to job-trigger pod on port 8000, curl `/metrics`, confirm all 10 metric families are present. After deployment, query Prometheus for `http_requests_total{namespace="dk-data"}`.

### Tests for User Story 1

- [x] T002 [P] [US1] Create metrics endpoint verification test in tests/test_metrics_endpoint.py — mock the prometheus_client registry, verify all 10 metric families are registered with correct names, types, and labels per src/dk_data/observability/metrics.py

### Implementation for User Story 1

- [x] T003 [US1] Verify and fix ServiceMonitor labels in k8s/base/service-monitor.yaml — ensure `release: mimir` metadata label is present on all ServiceMonitor/PodMonitor resources, verify service selectors match actual Service labels (`app: postgrest`, `app: job-trigger`), update PostgREST ServiceMonitor path from `/` to `/health` if `/` does not serve Prometheus format
- [x] T004 [P] [US1] Verify PrometheusRule labels in k8s/base/alert-rules.yaml — ensure `prometheus: mimir` metadata label is present, verify all alert expressions reference correct metric names and namespace patterns
- [x] T005 [P] [US1] Audit CronJob pod template labels — verify all CronJob manifests in k8s/base/ingestion/ include `app.kubernetes.io/component: batch-job` label matching the PodMonitor selector; add label if missing
- [x] T006 [US1] Validate kustomize manifests include service-monitor.yaml and alert-rules.yaml — verify k8s/base/kustomization.yaml lists both resources, run `kubectl kustomize k8s/overlays/staging --enable-helm` to confirm no errors

**Checkpoint**: All ServiceMonitor/PodMonitor/PrometheusRule manifests have correct labels; CronJob pods have required labels; kustomize validates cleanly

---

## Phase 4: User Story 2 — Add PostgREST Observability (Priority: P2)

**Goal**: Add PostgREST availability monitoring via health endpoint probing so outages trigger alerts and uptime appears in dashboards. Resolves GitHub Issue #91 (task 4).

**Independent Test**: Deploy the probe configuration, query Prometheus for `probe_success{job="dk-data-postgrest"}`, confirm it returns 1 when PostgREST is healthy.

### Implementation for User Story 2

- [x] T007 [US2] Update PostgREST ServiceMonitor in k8s/base/service-monitor.yaml — change the `dk-data-postgrest` ServiceMonitor endpoint path from `/` to a valid health check path; if PostgREST does not serve Prometheus format at any path, replace with a Probe CRD targeting the `/health` endpoint (requires blackbox-exporter in cluster) or add a blackbox probe module configuration
- [x] T008 [US2] Verify the `APIUnavailable` alert rule in k8s/base/alert-rules.yaml fires when PostgREST probe fails — confirm the alert expression references the correct metric name from the probe approach chosen in T007

**Checkpoint**: PostgREST availability is monitored via health probing; `APIUnavailable` alert expression matches probe metric

---

## Phase 5: User Story 3 — Implement Audit Trail (Priority: P3)

**Goal**: Implement two-layer audit logging — FastAPI middleware on job-trigger + PostgreSQL audit function for PostgREST — and expose a queryable audit log endpoint. Resolves GitHub Issue #17.

**Independent Test**: Make an authenticated API request, query `api.audit_log`, confirm the access event was recorded with timestamp, user role, endpoint, and response status.

### Tests for User Story 3

- [x] T009 [P] [US3] Create audit middleware tests in tests/test_audit_middleware.py — test AuditLoggingMiddleware captures request_id, method, path, user_role (from JWT), status_code, response_time_ms; test async write to database; test that health/metrics endpoints are excluded from auditing
- [x] T010 [P] [US3] Create API view contract tests for api.audit_log in tests/test_api_views_governance.py — verify column names and types match contracts/api-views.sql; verify `api_user` role has SELECT access; verify `web_anon` and `analyst` roles do NOT have access

### Implementation for User Story 3

- [x] T011 [US3] Create audit log table migration in src/dk_data/sql/migrations/067_audit_log_table.sql — CREATE TABLE meta.api_audit_log per data-model.md with all columns, indexes, and append-only constraints (REVOKE UPDATE, DELETE); include PostgreSQL audit trigger function that captures `current_setting('request.jwt.claims')` for PostgREST API view access
- [x] T012 [US3] Create AuditLoggingMiddleware in src/dk_data/api/middleware.py — add new middleware class after RequestTrackingMiddleware; capture request_id, method, path, query_params, user_role, user_sub (from JWT), ip_address (from X-Forwarded-For), user_agent, status_code, response_time_ms; write audit entries asynchronously; skip /health and /metrics paths
- [x] T013 [US3] Register AuditLoggingMiddleware in src/dk_data/ingestion/batch/api.py — add the middleware to the FastAPI app middleware stack in the correct order (after RequestTrackingMiddleware, before CacheControlMiddleware)
- [x] T014 [US3] Add api.audit_log view and GRANTs to k8s/base/db-init-job.yaml — CREATE VIEW api.audit_log per data-model.md; GRANT SELECT to api_user only; REVOKE ALL from web_anon, analyst, readonly

**Checkpoint**: Authenticated API requests produce audit log entries; PostgREST API view queries trigger PostgreSQL audit function; `api.audit_log` view returns entries for `api_user` role only

---

## Phase 6: User Story 4 — Automated Database Migration Runner (Priority: P4)

**Goal**: Build a lightweight Python migration runner that tracks applied migrations in `meta.schema_migrations`, supports baseline mode, and integrates into the K8s deployment pipeline. Resolves GitHub Issue #9.

**Independent Test**: Run the migration runner, confirm it applies only pending migrations. Run again, confirm "no pending migrations."

### Tests for User Story 4

- [x] T015 [P] [US4] Create migration runner tests in tests/test_migration_runner.py — test discover_migrations() finds and sorts SQL files by numeric prefix; test compute_checksum() produces consistent SHA-256 hashes; test apply_migration() executes SQL and records in tracking table; test skip logic for already-applied migrations; test --baseline mode marks without executing; test halt on failure behavior

### Implementation for User Story 4

- [x] T016 [US4] Create schema_migrations table migration in src/dk_data/sql/migrations/068_schema_migrations.sql — CREATE TABLE meta.schema_migrations per data-model.md with version, filename, checksum, applied_at, applied_by, execution_time_ms columns; UNIQUE constraint on version
- [x] T017 [US4] Create migration runner script in src/dk_data/scripts/run_migrations.py — implement discover_migrations() to scan src/dk_data/sql/migrations/ directory, sorted by numeric prefix; implement ensure_tracking_table() to create meta.schema_migrations if not exists; implement apply_pending() to execute unapplied migrations in order with checksum verification; implement --baseline flag to mark all as applied without executing; halt on first failure with error report; CLI entry point with --baseline and --dry-run flags
- [x] T018 [US4] Integrate migration runner into k8s/base/db-init-job.yaml — add a final step after schema/role/view creation that runs `python -m dk_data.scripts.run_migrations`; on first deployment to existing databases, use --baseline mode
- [x] T019 [P] [US4] Add api.migration_status view and GRANTs to k8s/base/db-init-job.yaml — CREATE VIEW api.migration_status per data-model.md; GRANT SELECT to api_user only

**Checkpoint**: Migration runner discovers 26+ existing migrations; --baseline marks them as applied; subsequent runs report "no pending migrations"; api.migration_status view shows applied migrations

---

## Phase 7: User Story 5 — PII/PHI Data Classification and Retention Policy (Priority: P5)

**Goal**: Establish data classification for all ~60 tables, define retention periods per classification, extend the purge mechanism to support multi-table retention, and document the classification scheme. Resolves GitHub Issues #18 and #19.

**Independent Test**: Query `api.data_classification`, confirm ORCID tables are classified as "pii" with pii_fields listed. Run extended purge in dry-run mode, confirm it identifies expired data across multiple tables.

### Tests for User Story 5

- [x] T020 [P] [US5] Create data classification tests in tests/test_data_classification.py — verify seed data classifies raw.orcid as 'pii' with pii_fields=['given_names','family_name','credit_name','biography']; verify scoring.* tables are classified as 'confidential'; verify mol_raw.* tables are classified as 'public'; verify retention_days is set for non-perpetual classifications

### Implementation for User Story 5

- [x] T021 [US5] Create data classification table and seed migration in src/dk_data/sql/migrations/069_data_classification.sql — CREATE TABLE meta.data_classification per data-model.md; INSERT seed rows for all database tables with classification levels (public, internal, pii, confidential), pii_fields, retention_days, and retention_policy per research.md R4 inventory
- [x] T022 [P] [US5] Create retention_days column migration in src/dk_data/sql/migrations/070_retention_column.sql — ALTER TABLE meta.data_sources ADD COLUMN IF NOT EXISTS retention_days INTEGER DEFAULT NULL
- [x] T023 [US5] Extend purge mechanism in src/dk_data/scripts/purge_history.py — add a new function purge_by_classification() that reads retention_days from meta.data_classification, identifies tables with non-NULL retention, queries each for records exceeding retention period based on a timestamp column (configurable per table), deletes expired records in batches, and logs results to meta.refresh_log; preserve existing purge_old_history() for backwards compatibility; add --all-tables CLI flag to trigger classification-based purge
- [x] T024 [P] [US5] Create data classification documentation in docs/DATA_CLASSIFICATION.md — document the 4-tier classification scheme (public, internal, pii, confidential) with schema-level breakdown, PII field inventory, retention periods, and purge strategy per research.md R4
- [x] T025 [US5] Add api.data_classification view and GRANTs to k8s/base/db-init-job.yaml — CREATE VIEW api.data_classification per data-model.md; GRANT SELECT to api_user only

**Checkpoint**: All ~60 tables classified in meta.data_classification; raw.orcid identified as PII; purge --all-tables --dry-run shows retention policy enforcement; api.data_classification view returns classifications for api_user

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all user stories

- [x] T026 Run full test suite — `pytest tests/ -q` — verify all new and existing tests pass
- [x] T027 Validate Kustomize manifests — `kubectl kustomize k8s/overlays/staging --enable-helm` and prod overlay
- [x] T028 Run quickstart.md verification steps — metrics endpoint check, kustomize validation, migration runner dry-run

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: N/A — no shared blockers
- **US1 (Phase 3)**: Can start immediately — no prerequisites
- **US2 (Phase 4)**: Depends on US1 (T003 may modify service-monitor.yaml that US2 also modifies)
- **US3 (Phase 5)**: Independent of US1/US2 — can start in parallel
- **US4 (Phase 6)**: Independent of US1/US2/US3 — can start in parallel
- **US5 (Phase 7)**: Independent of US1-US4 — can start in parallel
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories. **MVP — enables all Grafana dashboards.**
- **US2 (P2)**: Depends on US1 (shared file: service-monitor.yaml). Run after US1 tasks T003-T006.
- **US3 (P3)**: No dependencies on other stories. New table, new middleware, new view.
- **US4 (P4)**: No dependencies on other stories. New table, new script, new view.
- **US5 (P5)**: No dependencies on other stories. New table, extended script, new view.

### Within Each User Story

- Tests written first (where applicable)
- Migrations before views/middleware that depend on them
- Core implementation before integration tasks
- API views and GRANTs after backing tables exist

### Parallel Opportunities

**Within US1**:
- T004 and T005 (alert rules + CronJob labels) can run in parallel — different files

**Within US3**:
- T009 and T010 (tests) can run in parallel — different test files

**Within US5**:
- T022 and T024 (retention column + docs) can run in parallel — different files

**Across Stories**:
- US3, US4, US5 can execute in parallel (different files, no cross-dependencies)
- US1 must complete before US2 starts (shared service-monitor.yaml)

---

## Parallel Example: US3 + US4 + US5

```bash
# Launch all 3 test files together:
Task: "Create audit middleware tests in tests/test_audit_middleware.py"
Task: "Create migration runner tests in tests/test_migration_runner.py"
Task: "Create data classification tests in tests/test_data_classification.py"

# Launch all 3 table migrations together:
Task: "Create audit log table migration 067_audit_log_table.sql"
Task: "Create schema_migrations table migration 068_schema_migrations.sql"
Task: "Create data classification migration 069_data_classification.sql"

# Launch independent implementation files:
Task: "Create AuditLoggingMiddleware in src/dk_data/api/middleware.py"
Task: "Create migration runner in src/dk_data/scripts/run_migrations.py"
Task: "Extend purge mechanism in src/dk_data/scripts/purge_history.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 3: US1 — Verify and fix ServiceMonitor/PrometheusRule labels (T002-T006)
3. **STOP and VALIDATE**: Deploy to staging, check Grafana dashboards show data
4. All 3 Grafana dashboards populated — MVP complete

### Incremental Delivery

1. US1 → ServiceMonitors deployed → Grafana dashboards show data (MVP)
2. US2 → PostgREST probing → API availability monitored
3. US3 → Audit trail → Compliance readiness
4. US4 → Migration runner → Reproducible deployments
5. US5 → Data classification → Governance documentation

### Parallel Team Strategy

With multiple developers:

1. All stories can start after US1 completes (US2 depends on US1; US3-5 are independent)
   - Developer A: US1 (ServiceMonitors) + US2 (PostgREST probe) — same files
   - Developer B: US3 (Audit trail) — middleware + migration
   - Developer C: US4 (Migration runner) + US5 (Classification) — scripts + migrations
2. Polish phase after all stories complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- US1 is the MVP — enables all Grafana dashboard panels
- US3 has the most complexity (middleware + PostgreSQL trigger + API view)
- US4 (migration runner) is reusable infrastructure for all future features
- db-init-job.yaml is modified by US3, US4, and US5 — coordinate sequential writes
- Total: 28 tasks across 8 phases
