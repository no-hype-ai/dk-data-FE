# Research: Data Source Grafana Dashboard

**Feature**: 017-grafana-datasource-dashboard
**Date**: 2026-03-26

---

## Decision 1: Sankey Plugin

**Decision**: `netsage-sankey-panel` v1.1.4 (June 2025) for the medallion flow panel.

**Rationale**: Purpose-built for Sankey diagrams with the simplest data model — exactly 3 columns `(source, target, value)` in table format. Grafana 7.0+ compatible, tested through Grafana 12. Actively maintained by the netsage-project org.

**Alternatives considered and rejected**:
- `volkovlabs-echarts-panel` — **discontinued Sept 2025** (Volkov Labs ceased operations). Must not be used.
- Built-in Grafana panels — bar-gauge or stat panels per layer could show backlog counts but cannot express directionality between layers.

**Installation in Kubernetes**: Set `GF_PLUGINS_PREINSTALL=netsage-sankey-panel` on the Grafana deployment (env var or Grafana Operator CR `spec.config.plugins.GF_PLUGINS_PREINSTALL`). The plugin will be fetched from the Grafana Plugin Catalog on startup.

⚠️ **Feb 2026 note**: Plugin installation via grafana.com website is being removed Feb 2026 — the Plugin Catalog (in-product) and `GF_PLUGINS_PREINSTALL` env var remain the correct installation paths.

**Panel data format**: Exactly 3 columns required — `source` (text), `target` (text), `value` (numeric, no NULLs). For the raw→bronze→silver→gold flow, the query must produce 3 rows: `(raw, bronze, raw_unprocessed_value)`, `(bronze, silver, bronze_unprocessed_value)`, `(silver, gold, silver_unprocessed_value)`. This requires a `Union` or `Transformations > Merge` step combining the 4 separate PromQL instant queries into a single table.

---

## Decision 2: Recording Rules Format and Placement

**Decision**: PrometheusRule CRD at `k8s/apps/infrastructure/base/recording-rules.yaml`, matching the existing pattern in `alert-rules.yaml` (`apiVersion: monitoring.coreos.com/v1`).

**Rationale**: The cluster already uses PrometheusRule CRD for alert rules (confirmed in `k8s/apps/infrastructure/base/alert-rules.yaml:1`). Recording rules follow the same CRD format — same `apiVersion`, different `record:` key instead of `alert:`. Mimir's ruler component picks up PrometheusRule CRDs via the same `prometheus: mimir` label selector.

**Metrics requiring recording rules** (high cardinality + used in time-series panels with 30-day range):
- `rate(dk_pipeline_records_processed_total[5m])` by source — counter with 26 label values, used in stacked area chart
- `histogram_quantile(0.95, rate(dk_pipeline_duration_seconds_bucket[5m]))` by source — histogram, expensive over 30d
- `dk_data_source_row_count` and `dk_data_source_table_size_bytes` by source — gauges, lighter but still benefit from pre-aggregation for trend panels

**Recording rule naming convention**: `job:metric:aggregation` e.g. `job:dk_pipeline_records_processed:rate5m`

**Recording interval**: 5 minutes — matches metric emit cadence and Prometheus scrape default.

---

## Decision 3: New Metrics — Where to Add and Emit

### `dk_data_source_table_size_bytes` (Gauge)
- **Add to**: `src/dk_data/observability/metrics.py` alongside `DATA_SOURCE_ROW_COUNT` (line 120)
- **Emit in**: `record_data_source_refresh()` (line 478) — add optional `table_size_bytes: Optional[int] = None` parameter; query `meta.data_sources.table_size_bytes` or use `pg_total_relation_size()` if available
- **Cadence**: Called per source on each successful ingestion run — effectively per-source-run, not on a fixed schedule

### `dk_pipeline_duplicate_fetches_total` (Counter)
- **Add to**: `src/dk_data/observability/metrics.py` alongside other pipeline counters
- **Emit in**: `src/dk_data/services/data_platform/raw_ingestion.py` — the dedup check at lines 196–201 checks `WHERE response_body_hash = $1` and skips insert if found. Increment the counter immediately after the existing duplicate-detected branch.

### `dk_silver_unprocessed_total` (Gauge)
- **Add to**: `src/dk_data/observability/metrics.py` alongside `DK_BRONZE_UNPROCESSED` (line 261)
- **Emit in**: `src/dk_data/services/data_platform/metrics.py` `refresh_metrics_from_database_sync()` — add alongside the existing bronze unprocessed queries (line 438). Query: `SELECT COUNT(*) FROM bronze.{table} WHERE processed_to_silver = FALSE` for each source.
- **Add helper**: `set_silver_unprocessed(source: str, count: int)` alongside existing `set_bronze_unprocessed()`
- **Cadence**: Every 5 minutes via whatever scheduled call invokes `refresh_metrics_from_database_sync()`

### `dk_gold_unprocessed_total` (Gauge)
- **Add to**: `src/dk_data/observability/metrics.py`
- **Emit in**: `src/dk_data/services/data_platform/metrics.py` `refresh_metrics_from_database_sync()` — emit after `GoldAggregationService.refresh_all()` context or alongside silver queries. Gold service is at `src/dk_data/services/data_platform/gold_aggregation.py` (`GoldAggregationService`). Query: `SELECT COUNT(*) FROM silver.molecules WHERE needs_gold_aggregation = TRUE OR last_gold_sync IS NULL` (column existence to be verified at implementation time; fallback: total silver count minus gold profile count from `gold.molecule_profile`).
- **Add helper**: `set_gold_unprocessed(source: str, count: int)`
- **Cadence**: Every 5 minutes

---

## Decision 4: Dashboard Access Control

**Decision**: Grafana folder-level permissions — `data-platform` team, Viewer role.

**Implementation**: In Grafana provisioning, folders are configured via `apiVersion: 1, folders:` YAML (same provisioning path as dashboards). A folder named `Data Platform` with `orgId: 1` and `team: data-platform, permission: View` restricts access. The dashboard JSON `__metadata.folder` field must match this folder name.

**Existing pattern**: Current dashboards use `"folder": "Applications"` (dk-data-overview.json) — the new dashboard uses a new `"Data Platform"` folder restricted to the team.

---

## Decision 5: Dashboard File Consolidation

**Decision**: Migrate 5 files from `src/dk_data/monitoring/grafana/dashboards/` to `monitoring/dashboards/` and delete the empty directory.

**Evidence**: `src/dk_data/monitoring/grafana/dashboards/` is referenced by no YAML, Python, or CI file outside of `specs/`. The files are not being provisioned to any Grafana instance. `monitoring/dashboards/` is the canonical location per dk-template pattern (referenced in `.datakinetic/dk-data-prod.md`).

**Files to move**:
1. `cms-pipeline-health.json`
2. `data-platform-overview.json`
3. `external-datasources.json`
4. `pipeline-health.json`
5. `sqlmesh-transformations.json`

---

## Decision 6: `record_data_source_refresh` table_size_bytes Source

**Decision**: Query `meta.data_sources.table_size_bytes` directly rather than using `pg_total_relation_size()`.

**Rationale**: The column already exists and is the authoritative value. It's populated via `catalog_refresh.py` (or equivalent). Using a direct `pg_total_relation_size()` call in `record_data_source_refresh` would require knowing the actual table name per source, which is not part of the current function signature. Reading from `meta.data_sources` by `source_id` keeps the logic consistent with how row counts are managed.

**Implementation**: The `record_data_source_refresh()` function receives `source_id` and `source_name` — add a DB query to fetch `table_size_bytes` from `meta.data_sources WHERE source_id = $1`, or extend the function signature with an optional `table_size_bytes` parameter so callers can pass it directly.
