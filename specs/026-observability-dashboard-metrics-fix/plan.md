# Implementation Plan: Observability Dashboard & Metrics Fix

**Branch**: `026-observability-dashboard-metrics-fix` | **Date**: 2026-04-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/026-observability-dashboard-metrics-fix/spec.md`

## Summary

Fix dk-data-prod's broken observability stack: 60 of 95 dashboard panels show no data, 50 of 75 defined metrics never reach Mimir, and monitoring config uses non-standard patterns. The implementation extends the existing `refresh_metrics_from_database_sync()` to populate all DB-backed gauges, wires CronJob metric events through the database to the job-trigger's `/metrics` endpoint, consolidates 9 dashboards into 4, restructures `monitoring/` → `grafana/`, deletes orphaned K8s CRDs, deduplicates alert rules, and fixes the Alloy out-of-order sample errors.

## Technical Context

**Language/Version**: Python 3.11+ (job-trigger FastAPI service, CronJob pods)
**Primary Dependencies**: FastAPI, prometheus-client, psycopg2-binary, structlog, OpenTelemetry SDK, SQLMesh
**Storage**: PostgreSQL 16.4 (CloudNativePG cluster, `postgresql.infra.svc.cluster.local:5432`, database `dk_data`). Schemas: `raw`, `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `hcs_bronze`, `hcs_silver`, `hcs_gold`, `ip_bronze`, `ip_silver`, `ind_bronze`, `ind_silver`, `meta`, `api`, `staging`
**Testing**: pytest (existing test suite), manual Grafana dashboard verification, Mimir API queries
**Target Platform**: Kubernetes (k3s cluster), Grafana 10.x, Mimir 2.14.1, Alloy (Grafana Agent)
**Project Type**: Single backend service + infrastructure config
**Performance Goals**: All dashboard panels render within 5s; `/metrics` endpoint responds within 2s (including DB queries); scrape interval 30s
**Constraints**: No new infrastructure components; use existing Alloy, Mimir, Grafana stack; no Prometheus Operator available; CronJob pods cannot expose HTTP endpoints (short-lived)
**Scale/Scope**: 128 CronJobs, 75 defined metrics, 4 consolidated dashboards, ~30 alert rules, 100+ data sources

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. GitOps Deployment Model | **PASS** | All changes via Git (dashboard JSON, alert YAML, kustomize). No manual `kubectl apply`. |
| II. Environment Parity | **PASS** | Monitoring changes apply to both staging and prod via kustomize overlays. |
| III. Observability by Default | **FIXING** | This feature's entire purpose — populating 50 dead metrics, fixing broken dashboards, wiring CronJob metrics. |
| IV. Specification-Driven Development | **PASS** | Full speckit workflow: spec → clarify → plan → tasks. |
| V. Medallion Architecture Integrity | **PASS** | Backlog metrics enforce layer boundaries (processed_to_bronze/silver flags). No cross-layer shortcuts. |
| VI. No Dead Infrastructure | **FIXING** | Deleting orphaned CRDs (PrometheusRule, ServiceMonitor), removing dead provisioning config, eliminating 50 defined-but-unpopulated metrics. |

**Gate result**: PASS (2 principles actively being fixed by this feature, 4 already compliant).

**Post-Phase 1 re-check**:
- Constitution Principle III (Observability): All 75 metrics will be populated → fully compliant after implementation.
- Constitution Principle VI (No Dead Infrastructure): All orphaned CRDs deleted, `monitoring/` renamed to `grafana/`, provisioning doc removed → fully compliant.

## Project Structure

### Documentation (this feature)

```text
specs/026-observability-dashboard-metrics-fix/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── metrics-api.md   # Metrics endpoint contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/dk_data/
├── observability/
│   ├── metrics.py                          # 75 metric definitions (MODIFY: no new metrics needed, wire existing)
│   └── __init__.py                         # setup_telemetry() for OTEL (READ ONLY)
├── services/data_platform/
│   ├── metrics.py                          # refresh_metrics_from_database_sync() (MODIFY: extend DB queries)
│   ├── database_metrics.py                 # Async DB metric queries (READ ONLY)
│   └── pipeline_monitoring.py              # Pipeline run tracking (READ ONLY)
├── ingestion/
│   ├── main.py                             # CronJob entry point (MODIFY: add metric event recording)
│   ├── batch/
│   │   ├── api.py                          # /metrics endpoint (MODIFY: ensure refresh covers all gauges)
│   │   └── job_runner.py                   # Job execution (MODIFY: record pipeline events to DB)
│   └── initial_backfill.py                 # Backfill entry (READ ONLY)
├── metering_proxy/
│   └── metrics.py                          # Metering proxy metrics (READ ONLY)
└── sql/migrations/
    └── XXX_metric_events_table.sql         # NEW: metric events table if needed

grafana/                                    # NEW directory (renamed from monitoring/)
├── dashboards/
│   ├── dk-data-platform-status.json        # Consolidated dashboard 1
│   ├── dk-data-api-services.json           # Consolidated dashboard 2
│   ├── dk-data-pipeline-sources.json       # Consolidated dashboard 3
│   └── dk-data-transformations.json        # Consolidated dashboard 4
└── alerts/
    └── dk-data.yaml                        # Consolidated alert rules

k8s/
├── apps/infrastructure/base/
│   ├── kustomization.yaml                  # MODIFY: remove CRD references
│   ├── alert-rules.yaml                    # DELETE
│   ├── recording-rules.yaml                # DELETE
│   └── service-monitor.yaml                # DELETE
└── apps/metering-proxy/base/
    ├── kustomization.yaml                  # MODIFY: remove servicemonitor reference
    └── servicemonitor.yaml                 # DELETE

monitoring/                                 # DELETE entire directory after rename

.github/workflows/
└── grafana-uplift.yaml                     # NEW: thin caller workflow
```

**Structure Decision**: This feature modifies existing source files (primarily `metrics.py` and `main.py`) rather than creating new modules. The main structural change is the `monitoring/` → `grafana/` directory rename and K8s CRD file deletions.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Constitution III/VI: Dashboard fixes applied via Grafana UI before Git (FR-013) | Broken dashboards are a production visibility gap — immediate fix via UI restores engineer access to metrics within minutes. Git backport follows in same feature branch (T020, T024, T028 export; T048-T055 consolidate). | Git-first would require building consolidated dashboards before any panel works, delaying visibility by days. Two-phase approach is explicitly scoped: UI edits are temporary, Git is the durable source. |

## Implementation Phases

### Phase A: Quick Wins — Dashboard Query Fixes (P1, no code changes)

**Goal**: Fix 25+ broken panels immediately by correcting queries in Grafana UI.

1. **Fix PostgREST SLO dashboard** (US2): Change `service=~"dk-data-prod-postgrest.*"` → `service=~"dk-data-prod-dk-data-metering-proxy.*"` across all 10 panels
2. **Fix namespace label mismatches** (US3): Change `namespace="dk-data-prod"` → `exported_namespace="dk-data-prod"` for all `kube_*` metric queries in Platform Overview and affected panels
3. **Fix metric name mismatches** (US4): `dk_resolution_queue_size` → `dk_resolution_queue_pending_total`, `dk_data_quarantine_queue_size` → `dk_quarantine_count`, `dk_clinical_trials_by_phase` → `sum by (status)(dk_clinical_trials_total)`

**Verification**: Open each fixed dashboard in Grafana, confirm panels show data.
**Backport**: Export corrected dashboard JSON from Grafana API for Phase C.

### Phase B: Metrics Instrumentation (P1-P2, code changes)

**Goal**: Get 65+ of 75 defined metrics populating in Mimir.

#### B1: Extend `refresh_metrics_from_database_sync()` (job-trigger)

Add DB queries to `src/dk_data/services/data_platform/metrics.py` for:
- `dk_data_source_table_size_bytes` — `SELECT pg_total_relation_size(...)` per source table
- `dk_data_source_staleness_hours` — `SELECT EXTRACT(EPOCH FROM (NOW() - last_refresh)) / 3600`
- `dk_source_health_status` — already partially implemented, extend to all sources
- `dk_layer_record_count` — aggregate `COUNT(*)` per medallion layer (raw, bronze, silver, gold)
- `dk_table_record_count` — per-table counts across all schemas
- `dk_raw_unprocessed_total` — `COUNT(*) FROM raw.* WHERE processed_to_bronze = FALSE`
- `dk_bronze_unprocessed_total` — `COUNT(*) FROM bronze.* WHERE processed_to_silver = FALSE`
- `dk_silver_unprocessed_total`, `dk_gold_unprocessed_total` — analogous queries
- `dk_molecules_by_lifecycle_stage` — query `mol_silver.molecules` grouped by stage
- `dk_silver_identifier_mappings_total` — `COUNT(*)` by identifier_type

#### B2: Wire CronJob metric events through database

Since CronJob pods can't expose `/metrics` (short-lived, OTEL pushes traces only), the pattern is:
1. CronJob pods write execution results to `meta.batch_job_runs` (already happens for API-triggered jobs)
2. Extend CronJob entry points (`src/dk_data/ingestion/main.py`) to also write to `meta.batch_job_runs` for scheduled runs
3. Extend `refresh_metrics_from_database_sync()` to read `meta.batch_job_runs` and populate:
   - `dk_pipeline_records_processed_total` — from `records_processed` column
   - `dk_pipeline_duration_seconds` — from `completed_at - started_at`
   - `dk_pipeline_runs_total` — count by status (success/failure)
   - `dk_pipeline_errors_total` — count where status = 'failure'
   - `batch_job_duration_seconds` — already works for API-triggered; extend to scheduled
   - CMS agent metrics — from agent-specific columns or a new `meta.agent_runs` table

#### B3: Add HTTP request instrumentation to job-trigger

Add Prometheus HTTP middleware to the FastAPI app:
- Use `prometheus-fastapi-instrumentator` or manual middleware
- Emits `http_requests_total` and `http_request_duration_seconds_bucket`
- Labels: method, path, status_code

#### B4: Fix recording rules

Update Mimir recording rules ConfigMap to reference metrics that now exist after B1/B2.

### Phase C: Monitoring Restructure & Consolidation (P2)

**Goal**: Adopt org standard, consolidate dashboards, deduplicate alerts.

#### C1: Directory restructure (issue #145)

1. `git mv monitoring/dashboards grafana/dashboards`
2. `git mv monitoring/alerts grafana/alerts`
3. Delete `monitoring/provisioning/grafana-data-platform.yaml`
4. Delete empty `monitoring/` directory

#### C2: K8s CRD cleanup

1. Delete `k8s/apps/infrastructure/base/alert-rules.yaml`
2. Delete `k8s/apps/infrastructure/base/recording-rules.yaml`
3. Delete `k8s/apps/infrastructure/base/service-monitor.yaml`
4. Update `k8s/apps/infrastructure/base/kustomization.yaml` — remove 3 references
5. Delete `k8s/apps/metering-proxy/base/servicemonitor.yaml`
6. Update `k8s/apps/metering-proxy/base/kustomization.yaml` — remove reference

#### C3: Dashboard consolidation (dk-alchemy #449)

Consolidate 11 dashboard JSONs in `monitoring/dashboards/` into 4 in `grafana/dashboards/`:
- **Platform Status** ← dk-data-platform-status + dk-data-overview + dk-data-cronjobs + data-platform-overview
- **API & Services** ← dk-data-api + job-trigger-overview + postgrest-overview + dk-data-postgrest-slo
- **Data Pipeline & Sources** ← dk-data-pipeline + dk-data-sources + datasource-health + external-datasources
- **Transformations** ← sqlmesh-transformations + pipeline-health (+ sqlmesh-lineage panels where useful)

Exclude `cms-pipeline-health.json` (blocked on #144).

#### C4: Alert rule deduplication

1. Consolidate `monitoring/alerts/job-trigger.yaml` + `postgrest.yaml` + CRD alert logic → `grafana/alerts/dk-data.yaml`
2. Fix fields: `datasourceUid: mimir`, add `noDataState`, `execErrState`, set `folder: Alerts`
3. Drop duplicates per dk-alchemy #449 overlap analysis
4. Add net-new rules: APIUnavailable, BatchJobFailed, CronJobMissedSchedule, etc.
5. Resolve metric name discrepancies to canonical names

### Phase D: Infrastructure Fixes (P3)

#### D1: Fix Alloy out-of-order errors

Configure Mimir to accept out-of-order samples: add `-ingester.out-of-order-time-window=5m` to Mimir config (dk-alchemy change).

#### D2: Fix job-trigger pod on k3s-slave-1

Investigate why `job-trigger-796f468dd-hxgp9` reports `up=0`. Check pod health, network connectivity, and metrics endpoint accessibility.

#### D3: Create uplift caller workflow

Create `.github/workflows/grafana-uplift.yaml` as thin caller of shared workflow in `data-kinetic/.github` (deferred until shared workflow exists).

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `refresh_metrics_from_database_sync()` becomes slow with 50+ DB queries | Medium | High (blocks scrape) | Batch queries, use single connection, add query timeout, consider caching |
| Dashboard consolidation loses panels from originals | Low | Medium | Panel-by-panel audit checklist before/after |
| CronJob DB writes add latency to job completion | Low | Low | Writes are small (1 row per job run), use existing connection |
| Metric name canonical resolution breaks existing alerts | Medium | High | Test alert queries against Mimir before deploying changes |
| Shared uplift workflow doesn't exist yet | High | Low | Directory restructure proceeds anyway; manual sync interim |
