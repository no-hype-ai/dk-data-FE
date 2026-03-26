# Data Model: Data Source Grafana Dashboard

**Feature**: 017-grafana-datasource-dashboard
**Date**: 2026-03-26

---

## New Prometheus Metrics

### 0. `dk_data_source_staleness_hours` — Emission Only (Gauge Already Defined)

| Attribute | Value |
|---|---|
| Type | Gauge (pre-existing definition at `observability/metrics.py:126`) |
| Labels | `source_id`, `source_name` |
| Unit | hours |
| Source | `meta.data_sources.last_successful_refresh` — compute `(now - last_successful_refresh).total_seconds() / 3600` per active source |
| Emit location | `src/dk_data/services/data_platform/metrics.py` — add to `refresh_metrics_from_database_sync()` |
| Cadence | Every 5 minutes |
| Status | **Definition exists, zero `.set()` calls in codebase — confirmed by grep. Emission is a Phase A task.** |
| Blocker | Without emission: freshness heatmap shows "No data"; `$source` variable has no options; all variable-scoped panels unfiltered |

### 1. `dk_data_source_table_size_bytes`

| Attribute | Value |
|---|---|
| Type | Gauge |
| Labels | `source_id`, `source_name` |
| Unit | bytes |
| Source | `meta.data_sources.table_size_bytes` (already populated in DB) |
| Emit location | `src/dk_data/observability/metrics.py` — added to `record_data_source_refresh()` |
| Cadence | Per successful ingestion run (event-driven via source ingestion jobs) |
| Related metric | `dk_data_source_row_count` (same labels, same emit point) |

### 2. `dk_pipeline_duplicate_fetches_total`

| Attribute | Value |
|---|---|
| Type | Counter |
| Labels | `source` |
| Unit | count (cumulative) |
| Source | Dedup branch in `src/dk_data/services/data_platform/raw_ingestion.py:196–201` |
| Emit location | At the point where `response_body_hash` match is detected and insert is skipped |
| Cadence | Event-driven — incremented once per detected duplicate fetch |
| Dashboard use | Duplicate detection rate = `rate(dk_pipeline_duplicate_fetches_total[5m])` per source |

### 3. `dk_silver_unprocessed_total`

| Attribute | Value |
|---|---|
| Type | Gauge |
| Labels | `source` |
| Unit | count |
| Source | `SELECT COUNT(*) FROM bronze.{table} WHERE processed_to_silver = FALSE` per source |
| Emit location | `src/dk_data/services/data_platform/metrics.py` — `refresh_metrics_from_database_sync()` |
| Cadence | Every 5 minutes |
| Helper function | `set_silver_unprocessed(source: str, count: int)` — mirrors `set_bronze_unprocessed()` |
| Existing parallel | `dk_bronze_unprocessed_total` (same pattern, bronze layer) |

### 4. `dk_gold_unprocessed_total`

| Attribute | Value |
|---|---|
| Type | Gauge |
| Labels | `source` |
| Unit | count |
| Source | Silver records pending gold aggregation (column TBD at implementation: `needs_gold_aggregation = TRUE` or `last_gold_sync IS NULL`) |
| Emit location | `src/dk_data/services/data_platform/metrics.py` — `refresh_metrics_from_database_sync()` |
| Cadence | Every 5 minutes |
| Helper function | `set_gold_unprocessed(source: str, count: int)` |
| Fallback | If no `needs_gold_aggregation` column exists: emit `silver.molecules COUNT(*) - gold.molecule_profile COUNT(*)` |

---

## Recording Rules

Stored as `PrometheusRule` CRD at `k8s/apps/infrastructure/base/recording-rules.yaml`.

| Recorded metric | Expression | Interval | Purpose |
|---|---|---|---|
| `job:dk_pipeline_records_processed:rate5m` | `rate(dk_pipeline_records_processed_total[5m])` by `(source)` | 5m | Ingestion volume stacked area chart — 30-day range |
| `job:dk_pipeline_duration_seconds_p95:5m` | `histogram_quantile(0.95, rate(dk_pipeline_duration_seconds_bucket[5m]))` by `(source)` | 5m | Fetch duration p95 trend — 30-day range |
| `job:dk_pipeline_duration_seconds_p50:5m` | `histogram_quantile(0.50, rate(dk_pipeline_duration_seconds_bucket[5m]))` by `(source)` | 5m | Fetch duration median trend — 30-day range |
| `job:dk_data_source_table_size_bytes:last` | `last_over_time(dk_data_source_table_size_bytes[10m])` by `(source_id, source_name)` | 5m | Storage size trend — 30-day range |

---

## Dashboard Panels — Metric Binding

| Panel | Type | Primary metric | Labels used |
|---|---|---|---|
| Freshness heatmap | State timeline / table | `dk_data_source_staleness_hours` | `source_id`, `source_name` |
| Ingestion volume | Stacked area | `job:dk_pipeline_records_processed:rate5m` | `source` |
| Fetch duration p50/p95 | Time series | `job:dk_pipeline_duration_seconds_p50:5m`, `job:dk_pipeline_duration_seconds_p95:5m` | `source` |
| Error rate by source | Bar chart | `increase(dk_bronze_ingestion_errors_total[24h])` | `source`, `error_type` |
| Duplicate detection rate | Time series | `rate(dk_pipeline_duplicate_fetches_total[5m])` | `source` |
| Medallion flow (Sankey) | netsage-sankey-panel v1.1.4 | 4 instant queries merged into 3-row table: `(raw→bronze, raw_unprocessed)`, `(bronze→silver, bronze_unprocessed)`, `(silver→gold, silver_unprocessed)` via Transformations > Merge. Fallback when silver/gold metrics absent: uses `dk_layer_record_count{layer="silver|gold"}` (total counts, not source-filtered) | `source` (no effect on fallback metric) |
| Storage growth — row count | Time series | `dk_data_source_row_count` | `source_id`, `source_name` |
| Storage growth — bytes | Time series | `job:dk_data_source_table_size_bytes:last` | `source_id`, `source_name` |
| API requests per consumer | Bar chart | `increase(dk_data_metering_requests_total[1h])` | `consumer`, `schema` |
| Response bytes per consumer | Time series | `rate(dk_data_metering_response_bytes_total[5m])` | `consumer`, `schema` |
| Rate limit rejections | Bar chart | `increase(dk_data_metering_rate_limit_rejections_total[1h])` | `consumer` |

---

## Dashboard Variables

| Variable | Type | Query | Purpose |
|---|---|---|---|
| `datasource` | Datasource | type = prometheus | Global datasource selector |
| `source` | Query | `label_values(dk_data_source_staleness_hours, source_name)` | Per-source drill-down filter. Values are human-readable source name strings (e.g., `"euipo_trademarks"`). These match the `source` label value on all pipeline metrics — confirmed by `api/routes/monitoring.py:146`. Panels on metrics with `source_name` label filter as `{source_name=~"$source"}`; panels on metrics with `source` label filter as `{source=~"$source"}`. Exception: `dk_layer_record_count` (fallback in Sankey) has no `source` label and is unaffected by this variable. |

---

## File Locations

### New files
```
monitoring/dashboards/datasource-health.json        # new dashboard
monitoring/rules/dk-data-recording-rules.yaml       # Grafana provisioning format (if needed)
k8s/apps/infrastructure/base/recording-rules.yaml  # PrometheusRule CRD
```

### Modified files
```
src/dk_data/observability/metrics.py                # 4 new metrics + updated record_data_source_refresh()
src/dk_data/services/data_platform/metrics.py       # 2 new helpers + extended refresh_metrics_from_database_sync()
src/dk_data/services/data_platform/raw_ingestion.py # duplicate counter emission
k8s/apps/infrastructure/base/kustomization.yaml     # add recording-rules.yaml resource
```

### Migrated files (move, no content changes)
```
src/dk_data/monitoring/grafana/dashboards/cms-pipeline-health.json      → monitoring/dashboards/
src/dk_data/monitoring/grafana/dashboards/data-platform-overview.json   → monitoring/dashboards/
src/dk_data/monitoring/grafana/dashboards/external-datasources.json     → monitoring/dashboards/
src/dk_data/monitoring/grafana/dashboards/pipeline-health.json          → monitoring/dashboards/
src/dk_data/monitoring/grafana/dashboards/sqlmesh-transformations.json  → monitoring/dashboards/
```

### Deleted directories
```
src/dk_data/monitoring/grafana/dashboards/   # removed after migration
src/dk_data/monitoring/grafana/             # removed if empty
src/dk_data/monitoring/                     # removed if empty
```
