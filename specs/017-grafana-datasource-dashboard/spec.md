# Feature Specification: Data Source Grafana Dashboard

**Feature Branch**: `017-grafana-datasource-dashboard`
**Created**: 2026-03-26
**Status**: Draft
**Input**: User description: "Data Source Grafana Dashboard — dedicated health and telemetry dashboard covering per-source freshness, ingestion volume, fetch durations, error rates, duplicate detection, medallion pipeline flow, storage growth, and API consumer usage."

## Clarifications

### Session 2026-03-26

- Q: What panel type should be used for the medallion pipeline flow visualization? → A: Sankey diagram (requires Grafana plugin installation)
- Q: Where should the dashboard JSON file be placed, and should orphaned dashboards be consolidated? → A: `monitoring/dashboards/` (canonical dk-template location); migrate the 5 orphaned files from `src/dk_data/monitoring/grafana/dashboards/` as part of this feature
- Q: Who can access the dashboard? → A: Restricted to `data-platform` team — view-only for team members, no access for other authenticated users
- Q: At what cadence should the four new Prometheus gauges emit? → A: Every 5 minutes
- Q: What is the performance requirement for query ranges beyond 24h, and are recording rules required? → A: Recording rules required — pre-aggregate key metrics so 30-day queries meet the 5-second load target

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Data Health at a Glance (Priority: P1)

An on-call engineer opens the dashboard during an incident and immediately identifies which of the 26 data sources are stale, erroring, or lagging — without querying Prometheus directly or reading logs.

**Why this priority**: Fastest path to incident triage. A freshness heatmap + error rate panel together form the minimum viable view for on-call use. Everything else is supporting detail.

**Independent Test**: Deploy only the freshness heatmap and error-rate panels; an engineer can open the dashboard and identify a stale or failing source within 30 seconds.

**Acceptance Scenarios**:

1. **Given** all 26 sources are healthy, **When** the engineer opens the dashboard, **Then** the freshness heatmap shows all cells green with staleness under threshold.
2. **Given** one source has not refreshed for 6+ hours, **When** the engineer views the heatmap, **Then** that source cell appears red and is immediately visible without scrolling.
3. **Given** a source has generated errors in the last 24 hours, **When** the engineer views the error-rate panel, **Then** that source appears in the bar chart sorted by error count descending.
4. **Given** all metrics are unavailable (scrape failure), **When** the engineer opens the dashboard, **Then** panels display a "No data" state rather than stale cached values.

---

### User Story 2 - Pipeline Volume and Flow Monitoring (Priority: P2)

A data engineer reviews ingestion trends and medallion pipeline backlogs to identify throughput regressions, sudden volume drops, or growing backlogs between pipeline layers.

**Why this priority**: Volume drops and layer backlogs are leading indicators of data quality problems. Important for daily ops reviews but not required for basic incident triage.

**Independent Test**: Deploy only the ingestion volume chart and medallion flow panel; an engineer can confirm data is flowing through all four layers and spot a backlog at a specific layer.

**Acceptance Scenarios**:

1. **Given** a source stops ingesting records, **When** the engineer views the ingestion volume chart, **Then** a visible gap or drop appears for that source within one scrape interval.
2. **Given** bronze-to-silver transformation is backlogged, **When** the engineer views the medallion flow panel, **Then** the bronze backlog count is visually elevated relative to other layers.
3. **Given** the time range is adjusted to the last 7 days, **When** the engineer reviews ingestion volume, **Then** per-source trends are distinguishable without overlap or label clipping.

---

### User Story 3 - Fetch Performance and Duplicate Efficiency (Priority: P3)

A platform engineer monitors per-source fetch durations and duplicate detection rates to identify API slowdowns, rate-limiting patterns, and bandwidth waste from redundant fetches.

**Why this priority**: Proactive optimization signal. Valuable for capacity planning and cost reduction but not needed for immediate incident response.

**Independent Test**: Deploy only the fetch duration and duplicate rate panels; an engineer can identify which sources have the highest p95 fetch times and which have elevated duplicate fetch rates.

**Acceptance Scenarios**:

1. **Given** an external API is rate-limiting a source, **When** the engineer views fetch duration trends, **Then** a sustained upward trend or spike is visible for that source.
2. **Given** response-body hashing is active for a source, **When** duplicate rates are above 50%, **Then** that source is highlighted in the duplicate detection panel.
3. **Given** response-body hashing is not yet populated for a source, **When** the engineer views the duplicate panel, **Then** that source shows "No data" rather than a misleading zero.

---

### User Story 4 - Storage Growth and Consumer Usage (Priority: P4)

A platform owner tracks per-source row count growth and API consumer usage patterns for capacity planning and cost attribution.

**Why this priority**: Long-horizon planning signal. Useful for quarterly reviews but low urgency for day-to-day operations.

**Independent Test**: Deploy only the storage growth and consumer usage panels; a platform owner can view row count trends per source and identify which consumers drive the highest request volume.

**Acceptance Scenarios**:

1. **Given** a source table is growing faster than expected, **When** the platform owner views the storage growth panel, **Then** that source's row count trend line diverges upward from the baseline.
2. **Given** a consumer is consistently hitting rate limits, **When** the platform owner views the consumer usage panel, **Then** rate limit rejections appear as a distinct segment of that consumer's request count.
3. **Given** no metering proxy data is available, **When** the platform owner views the consumer panel, **Then** a clear "data source unavailable" notice appears rather than empty charts.

---

### Edge Cases

- What happens when a data source has never successfully refreshed (no staleness metric emitted yet)? The freshness heatmap must render that source as a distinct "unknown" state rather than green.
- What happens when fewer than 26 sources are reporting metrics (e.g., a new source not yet instrumented)? The heatmap must show only sources with active metric labels, not phantom entries.
- How does the medallion flow panel behave when only raw-layer counts are available and bronze/silver/gold are missing? It must degrade gracefully, showing only the layers with data.
- What happens if the time range selected is shorter than the scrape interval? Panels must indicate sparse data rather than interpolate false continuity.
- What if duplicate detection metrics are entirely absent (hashing not yet deployed)? The duplicate rate panel must show an explicit placeholder rather than zero.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST display a per-source freshness status grid for all active data sources using staleness-hours values, with clear green/yellow/red thresholds. **Instrumentation prerequisite**: `dk_data_source_staleness_hours` is defined in `src/dk_data/observability/metrics.py:126` but is never emitted — no `.set()` call exists anywhere in the codebase. Emitting this metric is a Phase A task: extend `refresh_metrics_from_database_sync()` in `src/dk_data/services/data_platform/metrics.py` to query `SELECT source_id, source_name, last_successful_refresh FROM meta.data_sources WHERE is_active = TRUE` and emit `DATA_SOURCE_STALENESS_HOURS.labels(source_id=str(row['source_id']), source_name=row['source_name']).set((now - row['last_successful_refresh']).total_seconds() / 3600)` for each active source. Until this is deployed, the freshness panel and the `$source` variable both show "No data".
- **FR-002**: The dashboard MUST show ingestion volume over time broken down by source, with support for at least a 7-day lookback window.
- **FR-003**: The dashboard MUST display fetch duration trends per source, showing at minimum the median and p95 latency over the selected time range. Source-level duration data is sourced from `dk_pipeline_duration_seconds` (labels: `layer`, `source`), not `batch_job_duration_seconds` which carries only a `job_name` label and cannot be broken down by source.
- **FR-004**: The dashboard MUST show error counts per source for a configurable window (default: last 24 hours), sorted to surface highest-error sources first. Source-level error data is sourced from `dk_bronze_ingestion_errors_total` (labels: `source`, `error_type`); `dk_pipeline_errors_total` is explicitly excluded as it carries only `layer` and `error_type` labels and cannot be queried by source.
- **FR-005**: The dashboard MUST display duplicate fetch rates per source. A new Prometheus counter `dk_pipeline_duplicate_fetches_total` (label: `source`) must be added to `src/dk_data/observability/metrics.py` and incremented in `src/dk_data/services/data_platform/raw_ingestion.py` at the point where an incoming response hash matches an existing `response_body_hash` and the fetch is skipped. The hash column and dedup logic already exist; only the metric emission is missing. Until this counter is present in Mimir, the panel MUST display a "not available" state rather than zero.
- **FR-006**: The dashboard MUST visualize record flow across raw, bronze, silver, and gold layers using a Sankey diagram panel. The required plugin is `netsage-sankey-panel` v1.1.4 — `volkovlabs-echarts-panel` was discontinued Sept 2025 and must not be used. Plugin installation is a prerequisite task for this panel. Backlog counts (unprocessed records) are available for raw (`dk_raw_unprocessed_total`, label: `source`) and bronze (`dk_bronze_unprocessed_total`, label: `source`). No equivalent unprocessed metrics exist for silver or gold; two new Prometheus gauges must be added to `src/dk_data/observability/metrics.py` and populated by their respective transformation jobs: `dk_silver_unprocessed_total` (label: `source`) and `dk_gold_unprocessed_total` (label: `source`). Until these metrics exist, the silver and gold stages MUST fall back to displaying total record counts from `dk_layer_record_count` (label: `layer`, confirmed present at `observability/metrics.py:249`) rather than backlog counts, with a visible label indicating the distinction. Note: in fallback mode the Sankey panel shows aggregate layer totals across all sources — the `$source` variable filter has no effect on `dk_layer_record_count` because it carries no `source` label. This is acceptable degradation behavior.
- **FR-007**: The dashboard MUST show per-source row count and storage size trends over time for capacity planning purposes. Row count is sourced from the existing `dk_data_source_row_count` Prometheus metric. Storage size in bytes is sourced from a new Prometheus gauge `dk_data_source_table_size_bytes` (labels: `source_id`, `source_name`) that must be added to `src/dk_data/observability/metrics.py` and populated by the same job that currently writes `dk_data_source_row_count`; the underlying value already exists as `meta.data_sources.table_size_bytes` in the database.
- **FR-008**: The dashboard MUST display API consumer usage metrics including requests per consumer, response sizes, and rate limit rejections when metering proxy data is available.
- **FR-009**: The dashboard MUST be deployable alongside existing dashboards without modifying or breaking them. Access MUST be restricted to the `data-platform` Grafana team with viewer permissions; no other authenticated users should have access by default. Dashboard folder permissions must be set accordingly in the provisioning configuration.
- **FR-010**: The dashboard MUST support a global time range selector that applies to all time-series panels simultaneously.
- **FR-011**: The dashboard MUST include a variable filter for source name so operators can drill into a single source across all panels.
- **FR-012**: All panels MUST display a "No data" state rather than zero or empty when the underlying metric has no data points in the selected range.
- **FR-013**: The new dashboard JSON MUST be placed at `monitoring/dashboards/datasource-health.json`, which is the canonical dk-template provisioning location. The 5 existing dashboard files currently at `src/dk_data/monitoring/grafana/dashboards/` (`cms-pipeline-health.json`, `data-platform-overview.json`, `external-datasources.json`, `pipeline-health.json`, `sqlmesh-transformations.json`) MUST be moved to `monitoring/dashboards/` as part of this feature, and the `src/dk_data/monitoring/grafana/dashboards/` directory MUST be removed. These files are currently unreferenced by any provisioning configuration and are not reaching Grafana.

### Key Entities

- **Data Source**: One of the 26 active ingestion sources; identified by `source_id` and `source_name` labels on metrics. Has freshness, row count, error rate, fetch duration, and duplicate rate attributes.
- **Pipeline Layer**: One of raw, bronze, silver, or gold. Raw and bronze layers have both a total record count and an unprocessed (backlog) count available as Prometheus metrics. Silver and gold layers currently have only total record counts; backlog metrics for these layers are new requirements of this feature (see FR-006).
- **API Consumer**: An authenticated caller of the PostgREST API layer; identified by consumer label on metering proxy metrics. Has request count, response size, and rate limit rejection attributes.
- **Dashboard Panel**: A single visualization unit (heatmap cell, time-series chart, bar chart) bound to one or more metric queries. Has a defined time range, variable bindings, and a no-data behavior.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An on-call engineer can identify all stale or erroring data sources within 30 seconds of opening the dashboard, without any additional queries or navigation.
- **SC-002**: The freshness heatmap correctly reflects the status of all 26 active sources with no false-green or phantom entries when viewed against live metric data.
- **SC-003**: All 8 dashboard sections (freshness, volume, fetch duration, errors, duplicates, medallion flow, storage, consumer usage) are accessible within a single scrollable dashboard view.
- **SC-004**: Panels gracefully degrade to a "No data" or "Unavailable" state for any metric section where source data has not been emitted, with no misleading zeros or interpolated values.
- **SC-005**: The dashboard loads within 5 seconds on a standard browser connection for any supported query range (24 hours through 30 days) across all 26 sources. Meeting this target for ranges beyond 24 hours requires Prometheus recording rules that pre-aggregate the high-cardinality time-series panels (ingestion volume, fetch duration, storage growth). Recording rules must be defined and deployed as part of this feature.
- **SC-006**: The source-name variable filter correctly scopes all time-series and bar chart panels to the selected source without requiring manual panel edits.
- **SC-007**: The dashboard JSON passes validation against the existing dashboard schema used by other dashboards in the repository and can be provisioned without manual Grafana UI steps.

## Assumptions

- Mimir (or compatible Prometheus-compatible long-term storage) is the active query backend for all dashboard panels; no direct PostgreSQL queries are needed in the dashboard. Mimir must support recording rules (or an equivalent pre-aggregation mechanism) for SC-005 to be achievable at 30-day query ranges.
- The metering proxy metrics for API consumer usage are available via the same Prometheus scrape path as other platform metrics. If they are not yet scraped, FR-008 and SC-003 (consumer section) will require a prerequisite scrape configuration change before those panels can display data.
- `response_body_hash` deduplication is fully implemented in `raw_ingestion.py`. What is absent is the Prometheus counter `dk_pipeline_duplicate_fetches_total` that records when a duplicate is detected — this is a new metric required by FR-005, not a future schema change.
- Dashboard provisioning follows the same GitOps pattern as existing dashboards: JSON files committed to the repository are picked up by the Grafana provisioning sidecar on next deployment.
- Green/yellow/red freshness thresholds are: green < 4 hours, yellow 4–24 hours, red > 24 hours. These are adjustable via dashboard variables if needed.
- The 26 active sources correspond to `meta.data_sources WHERE is_active = TRUE`. `dk_data_source_staleness_hours` is currently defined but not emitted (see FR-001). Once emission is added in Phase A, all active sources will appear as label values. Until then, the `$source` variable returns no options and the freshness panel shows "No data".
- This feature requires four new Prometheus metrics to be instrumented before all panels can display live data:
  1. `dk_data_source_table_size_bytes` (gauge, labels: `source_id`, `source_name`) — reads from `meta.data_sources.table_size_bytes`; emitted every 5 minutes; required by FR-007
  2. `dk_pipeline_duplicate_fetches_total` (counter, label: `source`) — emitted in `raw_ingestion.py` at the dedup branch on each detected duplicate; event-driven, not scheduled; required by FR-005
  3. `dk_silver_unprocessed_total` (gauge, label: `source`) — emitted by the silver transformation job every 5 minutes; required by FR-006
  4. `dk_gold_unprocessed_total` (gauge, label: `source`) — emitted by the gold aggregation job every 5 minutes; required by FR-006
- `batch_job_duration_seconds` is intentionally not used in this dashboard — it has no `source` label. Per-source fetch duration panels use `dk_pipeline_duration_seconds` exclusively.
- `dk_pipeline_errors_total` is intentionally not used in this dashboard — it has no `source` label. Per-source error panels use `dk_bronze_ingestion_errors_total` exclusively.
- The dashboard variable `$source` is populated from `label_values(dk_data_source_staleness_hours, source_name)`, yielding human-readable source name strings (e.g., `"euipo_trademarks"`). All pipeline metrics that carry a `source` label (e.g., `dk_bronze_ingestion_errors_total`, `dk_pipeline_duration_seconds`, `dk_pipeline_duplicate_fetches_total`, `dk_raw_unprocessed_total`, `dk_bronze_unprocessed_total`) use the same string as their `source` label value. This is confirmed by the ingestion path: `api/routes/monitoring.py` calls `record_data_source_refresh(job_name, source_name, ...)` and ingestion jobs emit pipeline counters using the same `source_name` string. Panel queries filtering by `{source=~"$source"}` will therefore correctly scope to the selected source.
