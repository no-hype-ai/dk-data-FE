# Tasks: Observability Dashboard & Metrics Fix

**Input**: Design documents from `/specs/026-observability-dashboard-metrics-fix/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the spec. No test tasks generated.

**Organization**: Tasks grouped by user story priority. Phase A (dashboard query fixes) can deliver immediate value with zero code changes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Verify cluster access and baseline state before making changes.

- [ ] T001 Verify cluster access: connect VPN, establish SSH tunnel, fetch fresh kubeconfig per specs/026-observability-dashboard-metrics-fix/quickstart.md
- [ ] T002 Run baseline metric count: query Mimir for all dk_*/batch_*/cms_* metrics and record current counts (expected: ~25 metrics with data, ~50 missing)
- [ ] T003 Export all 9 current dk-data dashboard JSON definitions from Grafana API for backup and consolidation reference

**Checkpoint**: Cluster accessible, baseline recorded, dashboard JSONs exported.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Directory restructure and CRD cleanup that all subsequent phases depend on.

**CRITICAL**: Complete before any dashboard consolidation or alert deduplication.

- [X] T004 Rename monitoring/dashboards/ to grafana/dashboards/ via `git mv monitoring/dashboards grafana/dashboards`
- [X] T005 Rename monitoring/alerts/ to grafana/alerts/ via `git mv monitoring/alerts grafana/alerts`
- [X] T006 Delete monitoring/provisioning/grafana-data-platform.yaml and remove empty monitoring/ directory
- [X] T007 [P] Delete k8s/apps/infrastructure/base/alert-rules.yaml
- [X] T008 [P] Delete k8s/apps/infrastructure/base/recording-rules.yaml
- [X] T009 [P] Delete k8s/apps/infrastructure/base/service-monitor.yaml
- [X] T010 Update k8s/apps/infrastructure/base/kustomization.yaml — remove references to alert-rules.yaml, recording-rules.yaml, service-monitor.yaml
- [X] T011 [P] Delete k8s/apps/metering-proxy/base/servicemonitor.yaml
- [X] T012 Update k8s/apps/metering-proxy/base/kustomization.yaml — remove reference to servicemonitor.yaml
- [ ] T013 Validate kustomize output: run `kubectl kustomize k8s/base/` and confirm zero PrometheusRule, ServiceMonitor, or PodMonitor resources in output

**Checkpoint**: Directory structure matches org standard (`grafana/dashboards/`, `grafana/alerts/`). All orphaned CRDs deleted. Kustomize clean.

---

## Phase 3: User Story 1 — API Health Dashboard (Priority: P1) MVP

**Goal**: Fix the DK Data API dashboard so all 12 panels show live data by adding HTTP request instrumentation to job-trigger.

**Independent Test**: Open DK Data API dashboard in Grafana; confirm Request Rate, Latency P50/P95, Error Rate, and Requests by Endpoint panels show non-zero values.

### Implementation

- [X] T014 [US1] Add `prometheus-fastapi-instrumentator` to pyproject.toml dependencies in src/pyproject.toml
- [X] T015 [US1] Integrate prometheus-fastapi-instrumentator into the FastAPI app in src/dk_data/ingestion/batch/api.py — add `Instrumentator().instrument(app).expose(app)` or equivalent to emit `http_requests_total` and `http_request_duration_seconds_bucket` metrics
- [ ] T016 [US1] Verify the job-trigger /metrics endpoint now includes http_requests_total and http_request_duration_seconds_bucket by curling the endpoint locally or via kubectl exec
- [ ] T017 [US1] Build and deploy updated job-trigger image to dk-data-staging, verify metrics appear in Mimir within 60 seconds

**Checkpoint**: HTTP request metrics flowing to Mimir. API dashboard panels showing live data.

---

## Phase 4: User Story 2 — PostgREST SLO Dashboard Fix (Priority: P1)

**Goal**: Fix all 10 PostgREST SLO dashboard panels by correcting the Traefik service name pattern.

**Independent Test**: Open PostgREST SLO dashboard; confirm Availability, Latency P95, Request Rate, Error Budget, and Requests by Status Code panels show values.

### Implementation

- [X] T018 [US2] In Grafana UI, edit PostgREST SLO dashboard: replace `service=~"dk-data-prod-postgrest.*"` with `service=~"dk-data-prod-dk-data-metering-proxy.*"` across all 10 panels
- [ ] T019 [US2] Verify all 10 panels render with live data after the query fix
- [ ] T020 [US2] Export corrected PostgREST SLO dashboard JSON from Grafana API and save to grafana/dashboards/ (for later consolidation in Phase 8)

**Checkpoint**: PostgREST SLO dashboard fully functional (10/10 panels).

---

## Phase 5: User Story 3 — Kubernetes Resource Panel Fixes (Priority: P1)

**Goal**: Fix all kube_* metric panels that use wrong namespace label.

**Independent Test**: Open DK Data Platform Overview dashboard; confirm Running Pod Counts, Pod Restarts, CronJob Timeline, Job Trigger Readiness, and PostgREST Readiness panels show correct values matching kubectl output.

### Implementation

- [X] T021 [P] [US3] In Grafana UI, edit DK Data Platform Overview dashboard: change `namespace="dk-data-prod"` to `exported_namespace="dk-data-prod"` for all kube_* metric panels (Running Pod Counts, Pod Restarts, CronJob Execution Timeline, Job Trigger Readiness, PostgREST Readiness)
- [X] T022 [P] [US3] In Grafana UI, edit DK Data API dashboard: fix any kube_* panels using wrong namespace label
- [ ] T023 [US3] Verify all Kubernetes resource panels across all dk-data dashboards display correct values by comparing with `kubectl get pods -n dk-data-prod` and `kubectl get cronjobs -n dk-data-prod`
- [ ] T024 [US3] Export corrected dashboard JSONs from Grafana API for later consolidation

**Checkpoint**: All Kubernetes resource panels working across all dashboards.

---

## Phase 6: User Story 4 — Metric Name Mismatch Fixes (Priority: P2)

**Goal**: Fix 3 dashboard panels that reference wrong metric names.

**Independent Test**: Open Pipeline & Sources and Transformations dashboards; confirm Entity Resolution Queue, Quarantine Count, and Clinical Trials panels show data.

### Implementation

- [X] T025 [P] [US4] In Grafana UI, edit Pipeline & Sources dashboard: change `dk_resolution_queue_size` to `dk_resolution_queue_pending_total` in Entity Resolution Queue panel
- [X] T026 [P] [US4] In Grafana UI, edit Pipeline & Sources dashboard: change `dk_data_quarantine_queue_size` to `dk_quarantine_count` in Quarantine Count panel
- [X] T027 [P] [US4] In Grafana UI, edit Transformations dashboard: change `dk_clinical_trials_by_phase` to `sum by (status)(dk_clinical_trials_total)` in Clinical Trials panel
- [X] T028 [US4] Export corrected dashboard JSONs from Grafana API for later consolidation

**Checkpoint**: All metric name mismatches resolved. 3 additional panels showing data.

---

## Phase 7: User Story 5 — Pipeline & Source Metrics Instrumentation (Priority: P2)

**Goal**: Populate ~25 missing DB-backed gauge metrics and wire CronJob event metrics through the database.

**Independent Test**: Query Mimir for dk_layer_record_count, dk_raw_unprocessed_total, dk_bronze_unprocessed_total, dk_source_health_status — all should return non-zero series. After a CronJob completes, dk_pipeline_records_processed_total should show data.

### Implementation — DB-backed gauges (job-trigger)

- [X] T029 [US5] Extend refresh_metrics_from_database_sync() in src/dk_data/services/data_platform/metrics.py — add query for dk_data_source_table_size_bytes using pg_total_relation_size() per source table
- [X] T030 [P] [US5] Extend refresh_metrics_from_database_sync() — add query for dk_data_source_staleness_hours computing (NOW() - last_refresh_timestamp) / 3600 per source
- [X] T031 [P] [US5] Extend refresh_metrics_from_database_sync() — add query for dk_layer_record_count aggregating COUNT(*) per medallion layer (raw, bronze, silver, gold)
- [X] T032 [P] [US5] Extend refresh_metrics_from_database_sync() — add query for dk_table_record_count with COUNT(*) per individual table across all schemas
- [X] T033 [P] [US5] Extend refresh_metrics_from_database_sync() — add queries for backlog gauges: dk_raw_unprocessed_total (COUNT WHERE processed_to_bronze=FALSE), dk_bronze_unprocessed_total (COUNT WHERE processed_to_silver=FALSE), dk_silver_unprocessed_total, dk_gold_unprocessed_total
- [X] T034 [P] [US5] Extend refresh_metrics_from_database_sync() — add query for dk_molecules_by_lifecycle_stage (COUNT GROUP BY lifecycle_stage from mol_silver.molecules)
- [X] T035 [P] [US5] Extend refresh_metrics_from_database_sync() — add query for dk_silver_identifier_mappings_total (COUNT GROUP BY identifier_type from mol_silver.identifier_mappings)
- [X] T036 [P] [US5] Extend refresh_metrics_from_database_sync() — extend dk_source_health_status to cover ALL source tables (currently partial), update dk_source_last_sync_timestamp for all sources

### Implementation — CronJob event metrics via database

- [X] T037 [US5] Modify CronJob entry point in src/dk_data/ingestion/main.py to INSERT a row into meta.batch_job_runs on job completion for scheduled CronJob executions (currently only API-triggered jobs record here)
- [X] T038 [US5] Extend refresh_metrics_from_database_sync() in src/dk_data/services/data_platform/metrics.py — add queries that read meta.batch_job_runs to populate: dk_pipeline_records_processed_total (SUM records_processed), dk_pipeline_runs_total (COUNT by status), dk_pipeline_duration_seconds (from completed_at - started_at), dk_pipeline_errors_total (COUNT WHERE status=failure)
- [ ] T039 [US5] Verify /metrics endpoint response time stays under 2 seconds after adding all new queries (benchmark with curl timing)
- [ ] T040 [US5] Deploy updated job-trigger to staging, trigger a test CronJob, and verify new metrics appear in Mimir within 2 minutes

**Checkpoint**: 65+ of 75 metrics now have data in Mimir. Pipeline, source health, and backlog metrics all populated.

---

## Phase 8: User Story 6 — Recording Rules Fix (Priority: P2)

**Goal**: Make all 4 Mimir recording rules produce non-empty results.

**Independent Test**: Query Mimir ruler API (/prometheus/api/v1/rules) and confirm all 4 recording rules have non-empty lastEvaluation results.

### Implementation

- [ ] T041 [US6] Verify the source metrics for recording rules now exist in Mimir after Phase 7 (dk_pipeline_records_processed_total, dk_pipeline_duration_seconds_bucket, dk_data_source_table_size_bytes)
- [ ] T042 [US6] If source metrics exist: confirm recording rules in Mimir ConfigMap (mimir-recording-rules in dk-alchemy) reference the correct metric names. If names differ, update the ConfigMap data-platform.yaml group to match canonical names
- [ ] T043 [US6] Query Mimir ruler API to verify all 4 recording rules produce non-empty results: job:dk_pipeline_records_processed:rate5m, job:dk_pipeline_duration_seconds_p95:5m, job:dk_pipeline_duration_seconds_p50:5m, job:dk_data_source_table_size_bytes:last

**Checkpoint**: All recording rules producing data. Pipeline & Sources dashboard recording-rule-backed panels working.

---

## Phase 9: User Story 7 — Monitoring Directory Restructure (Priority: P2)

**Goal**: Complete the org-standard restructure per issue #145 (directory rename done in Phase 2, this phase handles alert consolidation).

**Independent Test**: Run org standards-check.yaml and confirm grafana/dashboards/ and grafana/alerts/ pass Tier 2 gate.

### Implementation

- [X] T044 [US7] Consolidate grafana/alerts/job-trigger.yaml and grafana/alerts/postgrest.yaml into a single grafana/alerts/dk-data.yaml
- [X] T045 [US7] Fix all alert rules in grafana/alerts/dk-data.yaml: set datasourceUid to "mimir", add noDataState and execErrState fields, set folder to "Alerts"
- [X] T046 [US7] Delete grafana/alerts/job-trigger.yaml, grafana/alerts/postgrest.yaml, and grafana/alerts/README.md after consolidation
- [X] T047 [US7] Validate grafana/alerts/dk-data.yaml format is correct Grafana provisioning YAML (apiVersion: 1, groups with rules, relativeTimeRange present)

**Checkpoint**: Single consolidated alert file with correct field values. Directory structure passes standards gate.

---

## Phase 10: User Story 9 — Dashboard Consolidation 9→4 (Priority: P2)

**Goal**: Consolidate 9 overlapping dashboards into 4 purpose-driven dashboards with zero panel duplication.

**Independent Test**: Open each of the 4 consolidated dashboards and verify every panel that was functional in the original dashboards still shows data.

### Implementation

- [X] T048 [US9] Build grafana/dashboards/dk-data-platform-status.json by merging panels from exported dk-data-platform-status, dk-data-overview, dk-data-cronjobs, and data-platform-overview dashboards. Deduplicate panels that appear in multiple sources.
- [X] T049 [P] [US9] Build grafana/dashboards/dk-data-api-services.json by merging panels from exported dk-data-api, job-trigger-overview, postgrest-overview, and dk-data-postgrest-slo dashboards. Include SLO availability, error budget, side-by-side job-trigger + PostgREST metrics.
- [X] T050 [P] [US9] Build grafana/dashboards/dk-data-pipeline-sources.json by merging panels from exported dk-data-pipeline, dk-data-sources, datasource-health, and external-datasources dashboards. Include medallion Sankey, source freshness, ingestion volume, fetch duration.
- [X] T051 [P] [US9] Build grafana/dashboards/dk-data-transformations.json by merging panels from exported sqlmesh-transformations and pipeline-health dashboards. Include SQLMesh model row counts, transformation duration, entity resolution.
- [X] T052 [US9] Resolve metric name discrepancies across all 4 consolidated dashboards: standardize http_requests_total (not http_server_*), dk_quarantine_count (not dk_data_quarantine_queue_size), dk_resolution_queue_pending_total (not dk_resolution_queue_size), dk_clinical_trials_total with sum by status (not dk_clinical_trials_by_phase)
- [X] T053 [US9] Set __metadata.folder to "Applications" on all 4 consolidated dashboard JSONs
- [X] T054 [US9] Delete the original 9+ source dashboard JSON files from grafana/dashboards/ that have been consolidated (keep cms-pipeline-health.json on hold)
- [ ] T055 [US9] Import all 4 consolidated dashboards into Grafana via API and verify every panel renders with live data

**Checkpoint**: Exactly 4 dk-data dashboards. Zero panel duplication. All panels showing data.

---

## Phase 11: User Story 11 — Alert Rule Deduplication (Priority: P2)

**Goal**: Deduplicate alert rules from 3 sources into a single consolidated file with net-new rules added.

**Independent Test**: Review grafana/alerts/dk-data.yaml — each alert condition appears exactly once with canonical metric name.

### Implementation

- [X] T056 [US11] Audit all 3 alert sources per dk-alchemy #449 overlap analysis: identify duplicates to drop, metric name conflicts to resolve, and net-new rules to add
- [X] T057 [US11] Update grafana/alerts/dk-data.yaml — drop duplicate alerts (DataSourceStale, DataSourceCriticallyStale, APIHighErrorRate, MoleculeQuarantineHigh, JobTriggerNotReady, latency duplicates) that are covered by existing rules
- [X] T058 [US11] Update grafana/alerts/dk-data.yaml — resolve metric name discrepancies in remaining alerts to use canonical names from T052
- [X] T059 [US11] Add net-new alert rules to grafana/alerts/dk-data.yaml in correct Grafana provisioning YAML format: APIUnavailable, BatchJobFailed, CronJobMissedSchedule, MoleculeFetchFailed, MoleculeTransformStale, BronzeToSilverBacklog, EntityResolutionQueueHigh, PodHighMemory, dk-data-postgrest-high-error-rate, dk-data-postgrest-high-latency
- [X] T060 [US11] Replace dk-data-oomkill alert with service-specific dk-data-job-trigger-pod-restarts and dk-data-postgrest-pod-restarts rules
- [X] T061 [US11] Add CMS pipeline source failure alerts from monitoring/alerts/cms-pipeline-source-failures.yaml (33 rules) into grafana/alerts/dk-data.yaml or a separate grafana/alerts/dk-data-cms.yaml

**Checkpoint**: Single consolidated alert file with no duplicates, canonical metric names, and all net-new rules added.

---

## Phase 12: User Story 12 — CMS Agent Metrics (Priority: P2)

**Goal**: Wire CMS agent enrichment jobs to emit execution metrics.

**Independent Test**: After an agent job runs, verify cms_agent_executions_total and cms_agent_cost_usd show data in Mimir.

### Implementation

- [X] T062 [US12] Add record_agent_run() calls to each of the 7 CMS agent CronJob entry points (agent-contact-verification, agent-equipment-inventory, agent-idn-hierarchy, agent-publication-evidence, agent-referral-network, agent-service-line-inference, agent-staffing-decomposition) in their respective Python entry modules
- [X] T063 [US12] Add record_gold_view_refresh() calls to the cms-gold-refresh CronJob entry point to populate cms_gold_view_last_refresh_timestamp, cms_gold_view_record_count, and cms_gold_refresh_duration_seconds
- [ ] T064 [US12] Extend refresh_metrics_from_database_sync() to read agent run data from the database and populate cms_agent_* metrics if agents write results to a table
- [ ] T065 [US12] Deploy to staging and verify CMS agent metrics appear in Mimir after an agent job runs

**Checkpoint**: CMS agent and gold refresh metrics populated.

---

## Phase 13: User Story 8 — Alloy Out-of-Order Errors (Priority: P3)

**Goal**: Eliminate recurring err-mimir-sample-out-of-order errors in Alloy logs.

**Independent Test**: Tail Alloy logs for 10 minutes, confirm zero out-of-order error messages.

### Implementation

- [ ] T066 [US8] Update Mimir configuration in dk-alchemy to add `-ingester.out-of-order-time-window=5m` to the Mimir StatefulSet args (this is a dk-alchemy change, not dk-data-FE)
- [ ] T067 [US8] After Mimir config is deployed, monitor Alloy logs for 30 minutes: `kubectl logs -n infra daemonset/alloy --tail=500 | grep "out-of-order"` — confirm zero matches

**Checkpoint**: Clean Alloy logs with no out-of-order errors.

---

## Phase 14: User Story 10 — Uplift Caller Workflow (Priority: P3)

**Goal**: Create the thin caller workflow for Grafana sync (deferred until shared workflow exists).

**Independent Test**: Merge a change to grafana/ on main; verify uplift workflow triggers and opens PR in dk-alchemy.

### Implementation

- [X] T068 [US10] Create .github/workflows/grafana-uplift.yaml as a thin caller of the shared reusable workflow in data-kinetic/.github (workflow implementation lives there). Configure to trigger on push to main when grafana/** files change. Exclude cms-pipeline-health.json.
- [ ] T069 [US10] Test the workflow by pushing a test change to grafana/ on a branch and verifying the workflow runs (dry-run mode if available)

**Checkpoint**: Uplift caller workflow in place. Triggers when grafana/ files change on main.

---

## Phase 15: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup.

- [ ] T070 Run full metric count against Mimir: verify at least 65 of 75 defined metrics have non-zero series (SC-017)
- [ ] T071 Verify both job-trigger pods report up=1 in Mimir (SC-008). If job-trigger-796f468dd-hxgp9 still reports up=0, investigate pod health and network on k3s-slave-1
- [ ] T072 Run `kubectl kustomize k8s/base/` and verify clean output with no monitoring CRDs (SC-006)
- [ ] T073 Verify grafana/dashboards/ contains exactly 4 dashboard JSON files (+ cms-pipeline-health.json on hold) (SC-011)
- [ ] T074 Search all dashboard JSON and alert YAML files for deprecated metric names (dk_resolution_queue_size, dk_data_quarantine_queue_size, dk_clinical_trials_by_phase, http_server_request_duration_seconds_count) — confirm zero matches (SC-012)
- [ ] T075 Update GitHub issue #199 with resolution summary and close
- [ ] T076 Update GitHub issue #145 with resolution summary and close

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS dashboard consolidation and alert work
- **US1 (Phase 3)**: Depends on Phase 2 — code change, independent of other stories
- **US2 (Phase 4)**: Depends on Phase 2 — Grafana UI only, can run in parallel with US1
- **US3 (Phase 5)**: Depends on Phase 2 — Grafana UI only, can run in parallel with US1/US2
- **US4 (Phase 6)**: Depends on Phase 2 — Grafana UI only, can run in parallel with US1/US2/US3
- **US5 (Phase 7)**: Depends on Phase 2 + US1 (HTTP metrics need to be wired first for full coverage)
- **US6 (Phase 8)**: Depends on Phase 7 (recording rules need source metrics populated)
- **US7 (Phase 9)**: Depends on Phase 2 (directory rename already done, alert consolidation next)
- **US9 (Phase 10)**: Depends on Phase 4/5/6 (need corrected dashboard exports) + Phase 9 (alerts consolidated)
- **US11 (Phase 11)**: Depends on Phase 9 (alert file exists in grafana/alerts/)
- **US12 (Phase 12)**: Depends on Phase 7 (refresh function extended)
- **US8 (Phase 13)**: Independent — dk-alchemy config change
- **US10 (Phase 14)**: Depends on Phase 10 (dashboards in grafana/ directory). Blocked on external dependency (shared workflow).
- **Polish (Phase 15)**: Depends on all phases complete

### Parallel Opportunities

**Immediate parallel (after Phase 2)**:
- US1 (HTTP instrumentation) + US2 (PostgREST SLO fix) + US3 (namespace fix) + US4 (metric name fix) — all independent

**After Phase 7 (metrics instrumentation)**:
- US6 (recording rules) + US9 (dashboard consolidation) + US23 (CMS agents) — all independent

**Always independent**:
- US8 (Alloy errors) — dk-alchemy config, no dk-data-FE dependency

---

## Parallel Example: Phases 3-6 (all P1/P2 quick wins)

```
# These can all run in parallel after Phase 2:
Task: "Add prometheus-fastapi-instrumentator to job-trigger" (US1)
Task: "Fix PostgREST SLO service name in Grafana UI" (US2)
Task: "Fix namespace→exported_namespace in Grafana UI" (US3)
Task: "Fix metric name mismatches in Grafana UI" (US4)
```

---

## Implementation Strategy

### MVP First (Phases 1-6)

1. Complete Phase 1: Setup (verify access)
2. Complete Phase 2: Foundational (restructure + CRD cleanup)
3. Complete Phases 3-6 in parallel: HTTP metrics + dashboard query fixes
4. **STOP and VALIDATE**: ~35 additional panels now showing data (up from 35 to ~70)
5. Deploy and demo

### Full Delivery (Phases 7-15)

6. Phase 7: Metrics instrumentation (~25 more panels)
7. Phases 8-12 in parallel: Recording rules, consolidation, alerts, CMS agents
8. Phase 13-14: Infrastructure fixes + uplift workflow
9. Phase 15: Final validation — 65/75 metrics, 4 dashboards, clean alerts

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Grafana UI edits (Phases 4-6) are immediately visible but not persistent — export JSON after each fix
- Dashboard consolidation (Phase 10) creates the persistent Git-managed versions
- CMS agent metrics (Phase 12) depend on understanding agent entry point code — may require investigation
- Alloy out-of-order fix (Phase 13) is a dk-alchemy change, not dk-data-FE
- Uplift workflow (Phase 14) is blocked on external dependency (shared workflow in data-kinetic/.github)
