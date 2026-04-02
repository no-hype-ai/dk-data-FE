# Feature Specification: Observability Dashboard & Metrics Fix

**Feature Branch**: `026-observability-dashboard-metrics-fix`  
**Created**: 2026-04-02  
**Status**: Draft  
**Input**: User description: "Fix dk-data-prod Grafana dashboards and metrics scraping: 60 of 95 panels (~63%) show no data across 9 dk-data dashboards. 24 of 51 unique metrics referenced by dashboards don't exist in Mimir. Full details in GitHub issue #199."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Engineer Views API Health Dashboard (Priority: P1)

A platform engineer opens the DK Data API dashboard to monitor request rates, latency, and error rates for the job-trigger service. Today, 8 of 12 panels show "No data" because the job-trigger service does not emit HTTP request metrics (`http_requests_total`, `http_request_duration_seconds_bucket`). After this fix, the engineer sees live request rate, latency percentiles (P50/P95/P99), error rates, and per-endpoint breakdowns.

**Why this priority**: HTTP request metrics are referenced by 13+ panels across 3 dashboards (DK Data API, DK Data API & Services, DK Data Platform Status). This is the single highest-impact missing metric and blocks meaningful API health monitoring.

**Independent Test**: Deploy the updated job-trigger with HTTP instrumentation, then verify the DK Data API dashboard shows non-zero values for Request Rate, Latency P50, Latency P95, Error Rate, and Requests by Endpoint panels.

**Acceptance Scenarios**:

1. **Given** the job-trigger service is running with HTTP instrumentation, **When** a platform engineer opens the DK Data API dashboard, **Then** all 12 panels display live metric data (no "No data" states).
2. **Given** a request is made to the job-trigger API, **When** the engineer refreshes the dashboard within 60 seconds, **Then** the request appears in the Request Rate and Requests by Endpoint panels.
3. **Given** the job-trigger returns a 5xx error, **When** the engineer views the Error Rate panel, **Then** the error is reflected in the error rate calculation.

---

### User Story 2 - Platform Engineer Views PostgREST SLO Dashboard (Priority: P1)

A platform engineer opens the DK Data PostgREST SLO dashboard to assess API availability, latency, and error budget. Today, all 10 panels show "No data" because they query a Traefik service name (`dk-data-prod-postgrest.*`) that does not exist — the actual service is routed through the metering proxy with a different name. After this fix, the engineer sees real availability percentages, latency SLOs, and error budget burn rate.

**Why this priority**: The PostgREST SLO dashboard is 100% broken (0 of 10 panels working). SLO visibility is critical for understanding production API health and making informed decisions about reliability investments.

**Independent Test**: Update the dashboard queries to use the correct Traefik service name pattern, then verify all 10 panels display live data.

**Acceptance Scenarios**:

1. **Given** PostgREST is serving traffic through the metering proxy, **When** the engineer opens the PostgREST SLO dashboard, **Then** the Availability (1h) and Availability (24h) stat panels show a percentage value.
2. **Given** the dashboard queries use the correct Traefik service name, **When** the engineer views the Requests by Status Code panel, **Then** it displays a breakdown of 2xx, 3xx, 4xx, and 5xx response codes.
3. **Given** PostgREST has been serving traffic for at least 24 hours, **When** the engineer views the Error Budget panel, **Then** it shows remaining error budget as a percentage relative to the 99.9% SLO target.

---

### User Story 3 - Platform Engineer Views Kubernetes Resource Panels (Priority: P1)

A platform engineer uses the DK Data Platform Overview dashboard to check pod counts, deployment readiness, restarts, and CronJob execution timelines. Today, 5 of 9 panels show "No data" because they filter `kube_*` metrics using `namespace="dk-data-prod"` instead of `exported_namespace="dk-data-prod"`. After this fix, all Kubernetes resource panels display correct data.

**Why this priority**: Kubernetes resource visibility (pod status, restarts, CronJob health) is foundational to operational awareness. The fix is a straightforward query label correction affecting multiple dashboards.

**Independent Test**: Update the affected dashboard queries to use `exported_namespace`, then verify panels in DK Data Platform Overview show pod counts, restart trends, and CronJob timelines.

**Acceptance Scenarios**:

1. **Given** dk-data-prod has running pods, **When** the engineer views the Running Pod Counts panel, **Then** it shows the correct count of running pods matching the output of `kubectl get pods -n dk-data-prod`.
2. **Given** a CronJob has executed recently, **When** the engineer views the CronJob Execution Timeline, **Then** the timeline shows the last schedule time for each CronJob.
3. **Given** a pod has restarted, **When** the engineer views the Pod Restarts Over Time panel, **Then** the restart event appears in the time series.

---

### User Story 4 - Platform Engineer Views Metric Name Mismatches Fixed (Priority: P2)

A platform engineer opens the DK Data Pipeline & Sources dashboard to check quarantine queue size, entity resolution queue, and bronze backlog. Today, 3 panels show "No data" because they reference metric names that don't match what the job-trigger actually exports (e.g., `dk_resolution_queue_size` vs. the actual `dk_resolution_queue_pending_total`). After this fix, these panels display the correct values.

**Why this priority**: These are quick wins — the data already exists in Mimir under slightly different metric names. Fixing the dashboard queries requires no code changes to the job-trigger.

**Independent Test**: Update the 3 mismatched metric references in dashboard queries, then verify each panel shows a non-empty value.

**Acceptance Scenarios**:

1. **Given** the job-trigger exports `dk_resolution_queue_pending_total`, **When** the Entity Resolution Queue panel queries the corrected metric name, **Then** it displays the current queue size.
2. **Given** the job-trigger exports `dk_quarantine_count`, **When** the Quarantine Count panel in Pipeline & Sources queries the corrected metric name, **Then** it displays the current quarantine count.
3. **Given** the job-trigger exports `dk_clinical_trials_total` with a `status` label, **When** the Clinical Trials by Phase panel uses a `sum by (status)` aggregation on the correct metric, **Then** it displays trials grouped by status.

---

### User Story 5 - Platform Engineer Views Pipeline & Source Metrics (Priority: P2)

A platform engineer opens the DK Data Pipeline, Sources, and Transformations dashboards to monitor ingestion rates, transform durations, medallion layer counts, and source health. Today, approximately 20 panels across these dashboards show "No data" because the job-trigger does not emit the referenced `dk_*` pipeline metrics. After this fix, the engineer sees live pipeline throughput, layer record counts, source health status, and transform performance.

**Why this priority**: Pipeline observability is essential for detecting stalled ingestion, transform failures, and data freshness issues. However, it requires instrumenting ~20 new metrics in the job-trigger codebase, making it more effort than the query-fix stories.

**Independent Test**: Deploy the updated job-trigger with new pipeline metrics instrumentation, then verify panels in the Pipeline, Sources, and Transformations dashboards display non-zero values.

**Acceptance Scenarios**:

1. **Given** a data source ingestion job completes, **When** the engineer views the Ingestion Rate by Source panel, **Then** it shows the records-per-minute rate for that source.
2. **Given** medallion layers contain data, **When** the engineer views the Medallion Layer Counts panel, **Then** it shows record counts for raw, bronze, silver, and gold layers.
3. **Given** a source health check runs, **When** the engineer views the Source Health Status panel in the Sources dashboard, **Then** each configured source displays a health indicator (healthy, stale, or error).
4. **Given** a transform job completes, **When** the engineer views the SQLMesh Model Row Counts panel, **Then** it shows row counts per model per layer.

---

### User Story 6 - Recording Rules Produce Meaningful Results (Priority: P2)

A platform engineer relies on pre-aggregated recording rules for efficient dashboard queries (ingestion volume rate, fetch duration percentiles, table sizes). Today, all 4 Mimir recording rules evaluate to empty results because their source metrics (`dk_pipeline_records_processed_total`, `dk_pipeline_duration_seconds_bucket`, `dk_data_source_table_size_bytes`) do not exist. After this fix, recording rules produce non-empty aggregations that power the Pipeline & Sources dashboard.

**Why this priority**: Recording rules are dependencies for the Pipeline & Sources dashboard panels. They must be updated to reference metrics that actually exist, or their source metrics must be instrumented first.

**Independent Test**: After instrumenting the source metrics (or updating recording rules to use existing metrics), verify via Mimir API that each recording rule returns non-empty results.

**Acceptance Scenarios**:

1. **Given** the source metrics exist in Mimir, **When** the Mimir ruler evaluates `job:dk_pipeline_records_processed:rate5m`, **Then** it produces at least one non-empty time series.
2. **Given** fetch duration data is being recorded, **When** the Mimir ruler evaluates `job:dk_pipeline_duration_seconds_p95:5m`, **Then** it produces a valid percentile value.

---

### User Story 7 - Restructure Monitoring to Org Standard Layout (Priority: P2)

A platform engineer needs dk-data-FE's monitoring configuration to follow the organization's standard directory layout (`grafana/dashboards/` and `grafana/alerts/`) so that the shared uplift workflow can automatically sync dashboards and alerts to dk-alchemy, which is the single source of truth for what reaches Grafana. Today, monitoring config is in a non-standard `monitoring/` directory, and K8s CRD files (PrometheusRule, ServiceMonitor, PodMonitor) exist that have never worked because there is no Prometheus Operator in the cluster. After this fix, the directory layout passes the Tier 2 standards gate, orphaned CRDs are removed, and alert YAML files are consolidated and corrected.

**Why this priority**: This is a prerequisite for the org's monitoring pipeline to work. Without the correct directory layout, no dashboards or alerts from dk-data-FE can be automatically synced to Grafana via dk-alchemy. This also resolves the orphaned CRD confusion (issue #145).

**Independent Test**: Run the org's `standards-check.yaml` against the repo and confirm `grafana/dashboards/` and `grafana/alerts/` pass the Tier 2 gate. Verify no PrometheusRule, ServiceMonitor, or PodMonitor CRD files remain in any kustomization.

**Acceptance Scenarios**:

1. **Given** the monitoring directory has been restructured, **When** the standards check runs, **Then** it passes the Tier 2 gate for `grafana/dashboards/` and `grafana/alerts/`.
2. **Given** the K8s CRD files have been deleted, **When** an engineer runs `kubectl kustomize k8s/base/`, **Then** the output contains no PrometheusRule, ServiceMonitor, or PodMonitor resources.
3. **Given** alert YAML files have been consolidated, **When** an engineer inspects `grafana/alerts/dk-data.yaml`, **Then** it contains all dk-data alert rules with correct `datasourceUid`, `noDataState`, `execErrState`, and `folder` fields.
4. **Given** the `monitoring/provisioning/` directory contained a non-functional sidecar config, **When** the restructure is complete, **Then** the file and directory no longer exist.

---

### User Story 9 - Consolidate Dashboards from 9 to 4 and Deduplicate Metrics (Priority: P2)

A platform engineer managing dk-data observability finds 9 overlapping dashboards with approximately 45% panel duplication — request rate, error rate, latency, CPU/memory, and pod restarts each appear across 4 to 6 separate dashboards. This creates confusion about which dashboard is authoritative and wastes maintenance effort. After this fix, 9 dashboards are consolidated into 4 purpose-driven dashboards with zero panel duplication, and all metric name discrepancies are resolved to use a single canonical name per concept.

The 4 consolidated dashboards (per dk-alchemy #449):
- **Platform Status** — consolidates dk-data-platform-status, dk-data-platform-overview, and dk-data-cronjobs panels. Deployment readiness, pod counts, restarts, CPU/memory, CronJob timeline, batch failures, data source freshness.
- **API & Services** — consolidates dk-data-api, dk-data-api-services, and dk-data-postgrest-slo. Job-trigger and PostgREST side by side: request rate, error rate, latency, SLO availability, error budget, status codes, Loki errors, Tempo traces.
- **Data Pipeline & Sources** — consolidates dk-data-pipeline, dk-data-pipeline-sources, dk-data-sources, and datasource-health. Source freshness, ingestion volume, fetch duration, error rates, medallion Sankey, storage growth, API consumer metering, external source row counts, entity resolution, quarantine.
- **Transformations** — consolidates dk-data-transformations. SQLMesh model row counts, transformation duration, records processed, pipeline layer duration, clinical trials, entity resolution success rate.

Additionally, metric name discrepancies must be resolved across dashboards and alerts:
- `http_requests_total` vs `http_server_request_duration_seconds_count` — pick one canonical HTTP metric name
- `http_request_duration_seconds_bucket` vs `http_server_request_duration_seconds_bucket` — pick one canonical latency metric
- `dk_quarantine_count` vs `dk_data_quarantine_queue_size` — verify which is actually emitted and standardize
- `dk_resolution_queue_pending_total` vs `dk_resolution_queue_size` — standardize to the emitted name

**Why this priority**: Dashboard consolidation reduces maintenance burden, eliminates confusion about which dashboard to use, and is a prerequisite for the dk-alchemy uplift (fewer files to maintain). Metric deduplication ensures alerts and dashboards query the same canonical metrics.

**Independent Test**: Open each of the 4 consolidated dashboards and verify that every panel that was functional in the original 9 dashboards still displays data. Verify no duplicate panels exist across the 4 dashboards.

**Acceptance Scenarios**:

1. **Given** the 9 dashboards have been consolidated, **When** an engineer lists dk-data dashboards in Grafana, **Then** exactly 4 dashboards exist (Platform Status, API & Services, Data Pipeline & Sources, Transformations).
2. **Given** a panel existed in one of the original 9 dashboards, **When** the engineer opens the corresponding consolidated dashboard, **Then** the same data is visible without loss of information.
3. **Given** metric name discrepancies existed (e.g., two names for HTTP error rate), **When** all dashboards and alerts are reviewed, **Then** each metric concept uses exactly one canonical name across all dashboards and alert rules.
4. **Given** the `data-platform-overview` dashboard contained domain-level business aggregates, **When** consolidation is complete, **Then** those panels are either folded into Platform Status as a summary row or retained as a standalone product metrics view (disposition decided during implementation).

---

### User Story 10 - Uplift Caller Workflow for Grafana Sync (Priority: P3)

A platform engineer merges monitoring changes to dk-data-FE's main branch and expects them to automatically propagate to dk-alchemy (and then to Grafana) via the org's shared uplift workflow. Today, no uplift caller workflow exists in dk-data-FE. After this fix, a thin caller workflow in `.github/workflows/grafana-uplift.yaml` triggers the shared reusable workflow on merge to main, which opens a PR in dk-alchemy with the transformed dashboard and alert files.

**Why this priority**: This depends on the shared uplift workflow existing in `data-kinetic/.github` first (external dependency). The dk-data-FE side is a thin caller file — low effort but blocked until the shared workflow is ready.

**Independent Test**: Merge a monitoring change to main and verify that the uplift workflow triggers and opens a PR in dk-alchemy with the correct file transforms applied.

**Acceptance Scenarios**:

1. **Given** the shared uplift workflow exists in `data-kinetic/.github`, **When** a change to `grafana/` is merged to main in dk-data-FE, **Then** the uplift caller workflow triggers automatically.
2. **Given** the uplift workflow runs, **When** it processes dashboard JSON files, **Then** it opens a PR in dk-alchemy with datasource UID, folder, and format transforms applied.
3. **Given** `cms-pipeline-health.json` is excluded from the uplift, **When** the workflow runs, **Then** only non-excluded dashboards are included in the dk-alchemy PR.

---

### User Story 11 - Resolve Alert Rule Overlaps and Deduplicate (Priority: P2)

A platform engineer reviewing alert rules finds three sources of alert definitions with overlapping coverage: K8s PrometheusRule CRDs (12 rules, never evaluated), Grafana provisioning YAML files in `monitoring/alerts/` (6 rules), and existing rules in dk-alchemy's `grafana/alerts/dk-data.yaml` (10 rules). Several alerts cover the same condition with different metric names or thresholds. After this fix, a single consolidated `grafana/alerts/dk-data.yaml` exists with no duplicates, correct metric names, and one canonical threshold per condition.

**Why this priority**: Duplicate alerts with different metric names create confusion about which is authoritative. Consolidation is required before the uplift workflow can sync alerts without creating conflicts in dk-alchemy.

**Independent Test**: Review the consolidated alert file and verify each alert condition appears exactly once with the correct canonical metric name.

**Acceptance Scenarios**:

1. **Given** the alert overlap analysis from dk-alchemy #449 is applied, **When** an engineer reviews `grafana/alerts/dk-data.yaml`, **Then** duplicate alerts are removed and only one rule exists per condition (e.g., one data-source-stale rule, one error-rate-high rule).
2. **Given** metric name discrepancies existed between alert sources, **When** alerts are consolidated, **Then** each alert uses the canonical metric name that is actually emitted by the instrumented services.
3. **Given** net-new alert rules exist in the CRD and monitoring/alerts sources that have no equivalent in dk-alchemy, **When** consolidation is complete, **Then** those rules are added to the consolidated file in Grafana provisioning YAML format with correct `datasourceUid`, `noDataState`, `execErrState`, and `folder` fields.

---

### User Story 8 - Resolve Alloy Out-of-Order Sample Errors (Priority: P3)

A platform engineer reviewing Alloy logs sees recurring `err-mimir-sample-out-of-order` errors every ~60 seconds caused by both Alloy DaemonSet pods scraping the same cluster-wide services (e.g., kube-state-metrics). After this fix, duplicate scraping is eliminated or Mimir is configured to accept out-of-order samples, and error logs are clean.

**Why this priority**: The errors cause some metric samples to be dropped for shared services. While most pod-level metrics are unaffected (they're node-local), cluster-wide service metrics like kube-state-metrics may have gaps.

**Independent Test**: After applying the fix, monitor Alloy logs for 10 minutes and confirm zero `err-mimir-sample-out-of-order` errors.

**Acceptance Scenarios**:

1. **Given** Alloy is running as a 2-pod DaemonSet, **When** both pods scrape kube-state-metrics, **Then** Mimir does not reject any samples with out-of-order errors.
2. **Given** the fix is deployed, **When** an engineer tails Alloy logs for 10 minutes, **Then** no `non-recoverable error` messages related to out-of-order samples appear.

---

### Edge Cases

- What happens when the job-trigger pod restarts mid-scrape? Counters reset to zero; dashboards should use `rate()` or `increase()` functions that handle counter resets gracefully.
- What happens when a new data source is added but its metrics are not yet registered? Dashboard panels for that source should show "No data" only for the new source, not break existing panels.
- What happens when only one of two job-trigger pods is healthy (up=1, up=0)? Dashboards should still display data from the healthy pod; alerts should fire for the unhealthy pod.
- How do dashboards behave during a Mimir restart? Panels show "No data" temporarily but recover automatically once Mimir is back. No manual intervention should be required.
- What happens when kube-state-metrics is temporarily unavailable? Kubernetes resource panels show stale data (last known values) rather than "No data", depending on the query range.
- What happens if the shared uplift workflow in `data-kinetic/.github` does not exist yet? The directory restructure (`monitoring/` → `grafana/`) proceeds regardless; the uplift caller workflow is created but will not trigger until the shared workflow is available. Dashboard updates continue to be applied manually via the Grafana UI in the interim.
- What happens to dashboard JSON files during the `monitoring/` → `grafana/` rename? Git tracks the rename; no content changes are made to the JSON files themselves during the move. Alert YAML files are consolidated and field-corrected as a separate step.
- What happens when a CronJob pod exits before its metrics are persisted? If using the database-write approach (FR-007b option b), the CronJob MUST write metric events to the database before exiting. If using the job-trigger API approach (option c), the CronJob MUST call the API synchronously before the process terminates.
- What happens when a transform job starts before its upstream layer is complete (e.g., Silver starts before Bronze finishes)? The transform reads stale data and produces incomplete results. The dashboard MUST show the dependency chain status so engineers can identify when jobs run out of order.

## Clarifications

### Session 2026-04-02

- Q: Where should the ~20 new pipeline/source metrics originate — centralized in job-trigger, distributed in CronJob pods, or hybrid? → A: Hybrid — job-trigger polls the database for slow-changing gauges (row counts, health status, staleness); CronJob pods emit event-driven counters during execution via OTEL push (ingestion rates, transform durations, failure counts). This aligns with the existing architecture where CronJob pods already push via OTEL to Alloy.
- Q: Should orphaned monitoring CRDs (ServiceMonitors, PodMonitors, PrometheusRules) be removed or integrated? → A: ~~Integrate via Alloy operator blocks~~ **Revised**: Delete all K8s CRD files and adopt the org-standard `grafana/` directory + dk-alchemy uplift workflow pattern (per issue #145). The CRDs never worked (no Prometheus Operator), and the org standard is for each product repo to own monitoring config in `grafana/dashboards/` and `grafana/alerts/`, uplifted to dk-alchemy via a shared reusable workflow.
- Q: How should Grafana dashboard fixes be applied — UI edits, Git-provisioned JSON, or both? → A: Both — apply fixes immediately in the Grafana UI for urgent visibility, then backport the corrected dashboard JSON to the Git repository for persistence via the grafana-github-webhook provisioning pipeline.
- Investigation: Full platform audit revealed 75 metrics defined in code but only ~25 reaching Mimir. Root causes: (1) `refresh_metrics_from_database_sync()` doesn't query all DB-backed gauges it should (missing table sizes, layer counts, backlogs, staleness), (2) CronJob pods don't call existing metric update functions (`record_pipeline_processing()`, `record_agent_run()`, etc.) — the functions exist but are never invoked, (3) CronJob OTEL setup pushes traces only, not Prometheus metrics — fundamental mismatch between metric definitions (prometheus_client) and collection path (OTEL traces). Recommended fix: CronJob pods write events to `meta.batch_job_runs` table; job-trigger refresh function reads and exposes them. 11 dashboard JSON files in `monitoring/dashboards/` are well-structured and should be used as basis for consolidation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The job-trigger service MUST emit HTTP request count metrics with labels for method, path, and status code.
- **FR-002**: The job-trigger service MUST emit HTTP request duration histogram metrics with labels for method and path.
- **FR-003**: All 4 consolidated dk-data Grafana dashboards MUST display live data for every panel (no "No data" states for panels whose source metrics exist).
- **FR-004**: The PostgREST SLO dashboard MUST query the correct Traefik service name that matches the production routing path.
- **FR-005**: All dashboard panels referencing `kube_*` metrics MUST use the `exported_namespace` label (not `namespace`) when filtering by the dk-data namespace.
- **FR-006**: Dashboard panels MUST reference the exact metric names exported by the job-trigger (no name mismatches between dashboard queries and actual metric names).
- **FR-007**: Pipeline metrics MUST be emitted using a hybrid approach: the job-trigger service MUST emit slow-changing gauge metrics by periodically polling the database; CronJob pods MUST emit event-driven counter and histogram metrics during execution. Specifically:
  - **Job-trigger DB-backed gauges** (extend `refresh_metrics_from_database_sync()`): medallion layer record counts (`dk_layer_record_count`), per-table record counts (`dk_table_record_count`), table sizes (`dk_data_source_table_size_bytes` via `pg_total_relation_size`), staleness hours (`dk_data_source_staleness_hours`), source health status (`dk_source_health_status`), unprocessed backlogs per layer (`dk_raw_unprocessed_total` via `COUNT(*) WHERE processed_to_bronze = FALSE`, `dk_bronze_unprocessed_total` via `COUNT(*) WHERE processed_to_silver = FALSE`, `dk_silver_unprocessed_total`, `dk_gold_unprocessed_total`), molecules by lifecycle stage (`dk_molecules_by_lifecycle_stage`), silver identifier mappings count (`dk_silver_identifier_mappings_total`).
  - **CronJob event counters** (call existing metric update functions in CronJob entry points): `dk_pipeline_records_processed_total`, `dk_pipeline_processing_duration_seconds`, `dk_pipeline_errors_total`, `dk_bronze_records_ingested_total`, `dk_bronze_ingestion_errors_total`, `dk_bronze_ingestion_duration_seconds`, `dk_silver_records_transformed_total`, `dk_silver_transformation_errors_total`, `dk_pipeline_duplicate_fetches_total`, `dk_pipeline_runs_total`, `dk_pipeline_duration_seconds`, `dk_gold_aggregation_duration_seconds`, `dk_resolution_requests_total`, `dk_resolution_latency_seconds`.
- **FR-007a**: The existing `refresh_metrics_from_database_sync()` function in `src/dk_data/services/data_platform/metrics.py` MUST be extended to query and populate ALL database-backed gauge metrics that are currently defined in `src/dk_data/observability/metrics.py` but return 0 series in Mimir. Currently only ~25 of 75 defined metrics reach Mimir; the remaining ~50 are defined but never populated.
- **FR-007b**: CronJob pod entry points (`src/dk_data/ingestion/main.py` and transform scripts) MUST write execution results (records processed, duration, status, errors) to the `meta.batch_job_runs` table on job completion. The job-trigger's `refresh_metrics_from_database_sync()` function MUST read these records and populate the corresponding Prometheus counters and histograms on each `/metrics` scrape. This avoids the OTEL/Prometheus mismatch since CronJob pods push only traces via OTEL, not Prometheus metrics.
- **FR-008**: The job-trigger service MUST emit entity resolution and quarantine metrics that match the names referenced by dashboard panels.
- **FR-009**: Mimir recording rules MUST reference metrics that exist in the time-series database and produce non-empty aggregation results.
- **FR-010**: The metrics collection pipeline MUST NOT produce recurring out-of-order sample rejection errors.
- **FR-011**: All orphaned K8s monitoring CRD files (PrometheusRule, ServiceMonitor, PodMonitor) MUST be deleted from the repository and removed from kustomization references.
- **FR-014**: The monitoring directory MUST be restructured from `monitoring/` to the org-standard `grafana/dashboards/` and `grafana/alerts/` layout to pass the Tier 2 standards gate.
- **FR-015**: Alert YAML files MUST be consolidated into a single `grafana/alerts/dk-data.yaml` with correct `datasourceUid` (mimir), `noDataState`, `execErrState`, and `folder` (Alerts) fields.
- **FR-016**: The non-functional `monitoring/provisioning/` directory and its contents MUST be deleted.
- **FR-017**: A thin uplift caller workflow (`.github/workflows/grafana-uplift.yaml`) MUST be created to call the shared reusable workflow in `data-kinetic/.github` on merge to main, once that shared workflow exists.
- **FR-012**: The metrics scraping system MUST collect data from all healthy job-trigger pods without gaps.
- **FR-013**: Dashboard query fixes MUST be applied in two phases: first directly in the Grafana UI for immediate visibility, then backported to the Git-managed dashboard JSON files for persistence via the grafana-github-webhook provisioning pipeline.
- **FR-022**: The transformation pipeline MUST be monitored across the full medallion chain: raw→bronze (06:00-07:30 UTC), bronze→silver (08:00-10:30 UTC), silver→gold (12:00-14:00 UTC). Each layer transition MUST have metrics for duration, records processed, error count, and unprocessed backlog. The Transformations dashboard MUST show the current state of each layer transition and whether transform jobs completed successfully.
- **FR-023**: CMS agent enrichment jobs (7 agents) MUST emit execution metrics by calling the existing `record_agent_run()` function: records enriched, records quarantined, LLM cost per run, execution status, and execution count.
- **FR-024**: The 11 existing dashboard JSON files in `monitoring/dashboards/` (pipeline-health, external-datasources, sqlmesh-transformations, cms-pipeline-health, datasource-health, job-trigger-overview, postgrest-overview, data-platform-overview, dk-data-cronjobs, dk-data-overview, sqlmesh-lineage) MUST be used as the basis for the 4 consolidated dashboards. These dashboards are well-structured and reference the correct metric names — they need metrics to be populated, not rewritten from scratch.
- **FR-018**: The 9 existing dk-data dashboards MUST be consolidated into 4 purpose-driven dashboards (Platform Status, API & Services, Data Pipeline & Sources, Transformations) with zero panel duplication across dashboards (per dk-alchemy #449).
- **FR-019**: All metric name discrepancies MUST be resolved to a single canonical name per concept across all dashboards and alert rules (e.g., one HTTP request counter name, one latency histogram name, one quarantine gauge name).
- **FR-020**: Alert rules from all three sources (PrometheusRule CRDs, `monitoring/alerts/` YAML, existing dk-alchemy rules) MUST be deduplicated into a single consolidated `grafana/alerts/dk-data.yaml` with no overlapping conditions.
- **FR-021**: Net-new alert rules not covered by existing dk-alchemy rules MUST be added to the consolidated alert file in Grafana provisioning YAML format (APIUnavailable, BatchJobFailed, CronJobMissedSchedule, MoleculeFetchFailed, MoleculeTransformStale, BronzeToSilverBacklog, EntityResolutionQueueHigh, PodHighMemory, PostgREST-specific error/latency rules).

### Key Entities

- **Dashboard Panel**: A single visualization within a Grafana dashboard. Has a title, type (stat, timeseries, table, etc.), and one or more metric queries. The panel either shows data or shows "No data" depending on whether its queries return results.
- **Metric**: A named time series emitted by an application or infrastructure component, scraped by Alloy, stored in Mimir, and queried by Grafana. Each metric has a name, labels, and a value type (counter, gauge, histogram).
- **Recording Rule**: A pre-computed aggregation evaluated periodically by the Mimir ruler. Takes a source metric expression, computes a result, and stores it as a new metric name for efficient dashboard queries.
- **ServiceMonitor / PodMonitor**: Kubernetes custom resources that declare scrape targets. Only useful when a Prometheus Operator or compatible component is running to consume them. In this cluster, these are orphaned and will be deleted (no Prometheus Operator exists).
- **PrometheusRule**: A Kubernetes custom resource declaring alert and recording rules. Orphaned in this cluster — alert logic will be migrated to Grafana-native alert YAML files in `grafana/alerts/`.
- **Uplift Workflow**: A shared reusable GitHub Actions workflow (in `data-kinetic/.github`) that copies and transforms monitoring config from product repos into dk-alchemy on merge to main. Each product repo has a thin caller workflow that invokes it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All panels in the 4 consolidated dk-data dashboards display live metric data (no "No data" states for panels whose source metrics exist), verified by opening each dashboard and confirming every panel renders.
- **SC-002**: The PostgREST SLO dashboard shows availability, latency, and error budget values for all 10 panels (up from 0 currently).
- **SC-003**: All Kubernetes resource panels (pod counts, restarts, CronJob timelines, deployment replicas) across all dk-data dashboards display correct values matching `kubectl` output.
- **SC-004**: Zero recurring `err-mimir-sample-out-of-order` errors in Alloy logs over a 30-minute observation window after deployment.
- **SC-005**: All 4 Mimir recording rules produce non-empty results, verified via the Mimir ruler API (`/prometheus/api/v1/rules`).
- **SC-006**: No orphaned monitoring CRD files remain in the repository; `kubectl kustomize k8s/base/` output contains zero PrometheusRule, ServiceMonitor, or PodMonitor resources.
- **SC-009**: The `grafana/dashboards/` and `grafana/alerts/` directories exist and pass the org's Tier 2 standards gate.
- **SC-010**: A single consolidated `grafana/alerts/dk-data.yaml` contains all dk-data alert rules with correct field values.
- **SC-007**: The job-trigger `/metrics` endpoint exports at least 70 unique metric names (up from 54 currently), covering HTTP request, pipeline, source health, and transformation metrics.
- **SC-008**: Both job-trigger pods report `up=1` in Mimir, confirming full scrape coverage across all cluster nodes.
- **SC-011**: Exactly 4 dk-data dashboards exist in `grafana/dashboards/` (down from 9), with zero duplicate panels across them.
- **SC-012**: Each metric concept (HTTP request count, HTTP latency, quarantine count, resolution queue, etc.) uses exactly one canonical name across all dashboards and alert rules — verified by searching all dashboard JSON and alert YAML files for conflicting metric names.
- **SC-013**: The consolidated `grafana/alerts/dk-data.yaml` contains all net-new alert rules from the overlap analysis, with no duplicate conditions and correct Grafana provisioning format fields.
- **SC-014**: Medallion layer backlog gauges (`dk_raw_unprocessed_total`, `dk_bronze_unprocessed_total`, `dk_silver_unprocessed_total`, `dk_gold_unprocessed_total`) return non-zero values in Mimir when unprocessed records exist, verified by comparing with direct database `COUNT(*) WHERE processed_to_X = FALSE` queries.
- **SC-015**: After a transform CronJob completes (e.g., `mol-transform-bronze`), the corresponding pipeline event metrics (`dk_pipeline_records_processed_total`, `dk_pipeline_duration_seconds`) are visible in Mimir within 2 minutes.
- **SC-016**: The CMS agent metrics (`cms_agent_executions_total`, `cms_agent_records_enriched_total`, `cms_agent_cost_usd`) show data in Mimir after an agent job runs.
- **SC-017**: At least 65 of the 75 defined metrics in `src/dk_data/observability/metrics.py` have non-zero series in Mimir (up from ~25 currently), verified via the Mimir label values API.

## Assumptions

- The org standard for monitoring delivery is `grafana/dashboards/` + `grafana/alerts/` in each product repo, uplifted to dk-alchemy via a shared reusable workflow (per issue #145). K8s CRDs (PrometheusRule, ServiceMonitor, PodMonitor) are NOT the delivery mechanism — there is no Prometheus Operator in the cluster. All CRD files will be deleted.
- The uplift caller workflow (`.github/workflows/grafana-uplift.yaml`) depends on the shared reusable workflow in `data-kinetic/.github` existing first. If the shared workflow is not yet available, the caller workflow creation is deferred but the directory restructure proceeds regardless.
- `cms-pipeline-health.json` dashboard is excluded from the uplift until 016 CMS PUF sources are ported to main (tracked in issue #144).
- Pipeline metrics use a hybrid instrumentation approach: the job-trigger handles slow-changing database-backed gauges via its existing `refresh_metrics_from_database_sync()` function (called on each `/metrics` scrape); CronJob pods record event-driven counters during execution. **Critical finding**: CronJob pods currently push only OTEL traces (not Prometheus metrics) to Alloy. The metric update functions (`record_pipeline_processing()`, `record_cms_source_sync()`, etc.) update in-process `prometheus_client` registry objects, but CronJob pods don't expose a `/metrics` endpoint. The recommended approach is for CronJob pods to write metric events to the `meta.batch_job_runs` table (which already exists) and have the job-trigger's refresh function read and expose them. This avoids adding a Prometheus-to-OTEL bridge or a push gateway.
- 75 metrics are defined in `src/dk_data/observability/metrics.py` but only ~25 currently have data in Mimir. The remaining ~50 are defined with proper Prometheus types (Counter, Gauge, Histogram) and helper update functions, but the code paths that invoke those functions are either missing or unreachable. The implementation must wire the existing update functions into the correct code paths, not redefine the metrics.
- The Traefik service name for production PostgREST traffic is `dk-data-prod-dk-data-metering-proxy-3001@kubernetes` (routed via metering proxy). If a direct PostgREST Ingress is preferred instead, dashboard queries and routing must both be updated.
- Dashboard panels for metrics that have no active data sources (e.g., a data source that has never been ingested) are acceptable to show "No data" — the 90/95 target accounts for this.
- The Alloy out-of-order error fix will be applied at the Mimir configuration level (accepting out-of-order samples within a time window) rather than restructuring the Alloy DaemonSet scraping topology.
- Dashboard consolidation (9→4) follows the plan in dk-alchemy #449. The consolidated dashboard JSON files are authored in dk-data-FE's `grafana/dashboards/` and uplifted to dk-alchemy. The 5 existing dk-alchemy dashboards (dk-data-api, dk-data-pipeline, dk-data-platform-status, dk-data-postgrest-slo, dk-data-sources) are superseded and will be deleted from dk-alchemy as part of the consolidation.
- The disposition of `data-platform-overview.json` (standalone product metrics dashboard vs. fold into Platform Status as a summary row) is an open question to be decided during implementation.
- Alert overlap resolution follows the analysis in dk-alchemy #449. Duplicate alerts are dropped, and net-new rules are added in Grafana provisioning YAML format.
