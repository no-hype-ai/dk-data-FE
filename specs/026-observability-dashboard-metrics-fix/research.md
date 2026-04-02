# Research: Observability Dashboard & Metrics Fix

**Date**: 2026-04-02 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## R1: How CronJob metrics reach Mimir (OTEL vs Prometheus mismatch)

**Decision**: CronJob pods write execution results to `meta.batch_job_runs` table; the job-trigger's `refresh_metrics_from_database_sync()` reads them and exposes as Prometheus gauges/counters on `/metrics`.

**Rationale**: CronJob pods currently use `setup_telemetry()` which configures OTEL to push **traces** (not Prometheus metrics) to Alloy. The metric update functions (`record_pipeline_processing()`, etc.) use `prometheus_client` which updates in-process registry objects — but CronJob pods don't expose `/metrics`, so these values are never scraped. The database approach:
- Reuses existing `meta.batch_job_runs` table (schema already has `records_processed`, `status`, `started_at`, `completed_at`, `error_message`, `k8s_job_name`)
- Doesn't require a push gateway or Prometheus-to-OTEL bridge
- Works for short-lived pods that exit before a scrape can occur
- Is consistent with how API-triggered jobs already record results

**Alternatives considered**:
1. **Add prometheus-to-OTEL metric bridge in CronJob pods**: Adds dependency, complex configuration, metrics may not push before pod exits
2. **Push to job-trigger API before exit**: Requires adding an internal API endpoint, network calls from CronJob pods, failure handling
3. **Prometheus push gateway**: Another infrastructure component to maintain, single point of failure

## R2: Extending `refresh_metrics_from_database_sync()` performance

**Decision**: Batch queries per schema, use a single DB connection, add 5-second total timeout. Expect ~15 queries (grouped by schema) completing in <1s total.

**Rationale**: The function currently runs ~8 queries in <200ms. Adding ~7 more queries (table sizes, layer counts, backlogs, mappings) is feasible within a 2-second budget. PostgreSQL `pg_total_relation_size()` is an O(1) catalog lookup. `COUNT(*) WHERE processed_to_X = FALSE` can use existing indexes (`idx_raw_*_processed`).

**Alternatives considered**:
1. **Background refresh on timer**: Decouples from scrape, but adds complexity and stale data risk
2. **Materialized views for counts**: Fast reads but requires refresh scheduling
3. **Redis cache**: Overkill for ~15 simple queries

## R3: HTTP request instrumentation for job-trigger

**Decision**: Use `prometheus-fastapi-instrumentator` library (already a pattern in the ecosystem).

**Rationale**: The library auto-instruments all FastAPI endpoints, emitting `http_requests_total` (Counter with method, handler, status labels) and `http_request_duration_seconds` (Histogram). It integrates with the existing `prometheus_client` registry that the `/metrics` endpoint already serves. Zero manual middleware needed.

**Alternatives considered**:
1. **Manual Starlette middleware**: More control but more code to maintain
2. **OpenTelemetry HTTP auto-instrumentation**: Already active but emits `http_server_request_duration_seconds` (OTEL convention) not `http_requests_total` (Prometheus convention). Dashboard queries currently use the Prometheus naming.

**Note**: The job-trigger already has OTEL auto-instrumentation producing `http_server_duration_milliseconds` metrics in Mimir. The dashboards reference `http_requests_total` (Prometheus convention). The canonical metric resolution (FR-019) must decide: update dashboards to use OTEL metric names, or add Prometheus-convention metrics alongside OTEL. **Recommendation**: Add `prometheus-fastapi-instrumentator` since it directly produces the metric names dashboards expect.

## R4: Dashboard consolidation approach

**Decision**: Use existing 11 dashboard JSONs as source panels. Merge by copying panel JSON blocks from source dashboards into 4 new consolidated files. Deduplicate by panel title + query expression.

**Rationale**: The 11 dashboards in `monitoring/dashboards/` are well-structured with correct `${datasource}` variable substitution and `{"__metadata": {}, "dashboard": {}}` wrapper format. The content is correct; only the arrangement needs changing.

**Process**:
1. Export current dashboards from Grafana (may have newer edits than Git)
2. Map each panel to its target consolidated dashboard
3. Build 4 new JSON files, deduplicating panels that appear in multiple sources
4. Verify no panel lost, no metric reference changed

## R5: Alloy out-of-order error resolution

**Decision**: Configure Mimir with `-ingester.out-of-order-time-window=5m`.

**Rationale**: Both Alloy DaemonSet pods scrape kube-state-metrics (cluster-wide service). Mimir rejects out-of-order samples by default. Setting a 5-minute out-of-order window allows both pods' samples to be ingested even with slight timestamp differences. This is a Mimir-side config change (in dk-alchemy), not an Alloy topology change.

**Alternatives considered**:
1. **Add `hashmod` relabeling to Alloy**: Each Alloy pod only scrapes a subset of targets. More complex, requires maintaining hash ring config.
2. **Deduplicate at query time**: Mimir supports deduplication via `--querier.max-query-lookback`, but doesn't prevent ingestion errors in logs.

## R6: Metric canonical name resolution

**Decision**: Resolve during implementation based on what's actually emitted. Preliminary mapping:

| Concept | Dashboard currently uses | Actually emitted | Canonical choice |
|---------|------------------------|-----------------|-----------------|
| HTTP request count | `http_requests_total` | Not emitted (will be after FR-001) | `http_requests_total` (add via instrumentator) |
| HTTP latency | `http_request_duration_seconds_bucket` | `http_server_duration_milliseconds_bucket` (OTEL) | `http_request_duration_seconds_bucket` (add via instrumentator) |
| Quarantine count | `dk_data_quarantine_queue_size` (dashboard) | `dk_quarantine_count` (code) | `dk_quarantine_count` (fix dashboard query) |
| Resolution queue | `dk_resolution_queue_size` (dashboard) | `dk_resolution_queue_pending_total` (code) | `dk_resolution_queue_pending_total` (fix dashboard query) |
| Clinical trials by phase | `dk_clinical_trials_by_phase` (dashboard) | `dk_clinical_trials_total{status=...}` (code) | `dk_clinical_trials_total` with `sum by (status)` (fix dashboard query) |
