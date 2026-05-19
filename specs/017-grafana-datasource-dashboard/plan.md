# Implementation Plan: Data Source Grafana Dashboard

**Branch**: `017-grafana-datasource-dashboard` | **Date**: 2026-03-26 | **Spec**: [spec.md](./spec.md)

## Summary

Build a dedicated Data Source Health Dashboard in Grafana covering 8 sections: per-source freshness, ingestion volume, fetch duration, error rate, duplicate detection, medallion pipeline flow (Sankey), storage growth, and API consumer usage. The feature includes four new Prometheus metrics, PrometheusRule recording rules for 30-day query performance, a Sankey plugin installation, and consolidation of 5 orphaned dashboard files into the canonical `monitoring/dashboards/` path. The dashboard JSON is built against existing Mimir data for 6 of 8 panels; 2 panels (duplicate detection, storage bytes) require new metric instrumentation before they show live data.

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: prometheus-client (existing), psycopg2-binary (existing), Grafana (cluster-managed), Mimir (cluster-managed), netsage-sankey-panel (new Grafana plugin)
**Storage**: PostgreSQL 16.4 via CloudNativePG (`meta.data_sources`, `bronze.*`, `silver.*`, `gold.*`)
**Testing**: pytest (existing test suite)
**Target Platform**: Kubernetes cluster (dk-data-prod / dk-data-staging namespaces); Grafana provisioning sidecar
**Project Type**: Single project — Python instrumentation changes + JSON dashboard artifact + Kubernetes YAML
**Performance Goals**: Dashboard loads in ≤5 seconds for any query range 24h–30d; achieved via PrometheusRule recording rules pre-aggregating high-cardinality counters and histograms at 5-minute intervals
**Constraints**: Access restricted to `data-platform` Grafana team (viewer); all panels degrade gracefully to "No data" rather than zero; no PostgreSQL direct queries in dashboard (Mimir only)
**Scale/Scope**: 26 active data sources; 4 new metrics; 1 new dashboard JSON; 1 new PrometheusRule CRD; 5 files migrated

---

## Constitution Check

Constitution file is a blank template — no project-specific gates defined. No violations to evaluate.

Standard quality gates applied:
- No implementation without failing test first: applies to Python metric changes
- All new metrics must have corresponding unit tests verifying they are registered and emit correct types
- Dashboard JSON must pass schema validation against existing dashboard structure before commit

---

## Project Structure

### Documentation (this feature)

```text
specs/017-grafana-datasource-dashboard/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — decisions and rationale
├── data-model.md        # Phase 1 output — metrics, panels, file locations
├── quickstart.md        # Phase 1 output — deployment guide
├── contracts/
│   ├── new-metrics.md   # Python metric definitions and emit locations
│   └── recording-rules.yaml  # PrometheusRule CRD contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code

```text
src/dk_data/observability/
└── metrics.py                              # +4 new metric definitions, updated record_data_source_refresh()

src/dk_data/services/data_platform/
├── metrics.py                              # +2 new helpers, extended refresh_metrics_from_database_sync()
└── raw_ingestion.py                        # +duplicate counter increment at dedup branch

monitoring/
├── dashboards/
│   ├── datasource-health.json              # NEW — the main dashboard artifact
│   ├── cms-pipeline-health.json            # MIGRATED from src/dk_data/monitoring/grafana/dashboards/
│   ├── data-platform-overview.json         # MIGRATED
│   ├── external-datasources.json           # MIGRATED
│   ├── pipeline-health.json                # MIGRATED
│   └── sqlmesh-transformations.json        # MIGRATED
└── rules/                                  # NEW directory (optional Grafana provisioning format)

k8s/apps/infrastructure/base/
├── recording-rules.yaml                    # NEW — PrometheusRule CRD
└── kustomization.yaml                      # MODIFIED — add recording-rules.yaml resource

src/dk_data/monitoring/                     # DELETED after migration
```

---

## Implementation Phases

### Phase A — Instrumentation (Python, unblocks 2 panels)

**Deliverables**: 4 new metrics emitting to Mimir; all 8 dashboard panels have backing data.

1. Add metric definitions to `src/dk_data/observability/metrics.py`:
   - `DATA_SOURCE_TABLE_SIZE_BYTES` (Gauge, labels: `source_id`, `source_name`)
   - `DK_PIPELINE_DUPLICATE_FETCHES` (Counter, label: `source`)
   - `DK_SILVER_UNPROCESSED` (Gauge, label: `source`)
   - `DK_GOLD_UNPROCESSED` (Gauge, label: `source`)

2. Extend `record_data_source_refresh()` — add `table_size_bytes: Optional[int] = None` parameter; set `DATA_SOURCE_TABLE_SIZE_BYTES` when provided.

3. Add helpers to `src/dk_data/services/data_platform/metrics.py`:
   - `set_silver_unprocessed(source: str, count: int)`
   - `set_gold_unprocessed(source: str, count: int)`

4. Extend `refresh_metrics_from_database_sync()` — add silver and gold unprocessed queries alongside the existing bronze query block (line 438).

5. Emit duplicate counter in `raw_ingestion.py` — at the hash-match dedup branch (lines 196–201), import `DK_PIPELINE_DUPLICATE_FETCHES` and call `.labels(source=source_name).inc()`.

6. Write unit tests covering: metric registration, type assertions, and that emit functions call `.set()`/`.inc()` without raising.

---

### Phase B — Recording Rules (Kubernetes, unblocks 30-day performance)

**Deliverables**: `PrometheusRule` CRD deployed; recorded metrics visible in Mimir after 5 minutes.

1. Create `k8s/apps/infrastructure/base/recording-rules.yaml` using the contract at `contracts/recording-rules.yaml`.

2. Add `recording-rules.yaml` to `k8s/apps/infrastructure/base/kustomization.yaml` resources list.

3. Verify Mimir ruler picks up the rule and recorded metrics emit (see quickstart.md Step 2 for verification commands).

---

### Phase C — Dashboard File Consolidation (no code changes)

**Deliverables**: `src/dk_data/monitoring/grafana/dashboards/` deleted; 5 files in `monitoring/dashboards/`.

1. Move 5 JSON files from `src/dk_data/monitoring/grafana/dashboards/` to `monitoring/dashboards/`.
2. Delete now-empty `src/dk_data/monitoring/grafana/` directory tree.
3. Verify no references to the old path exist in any YAML, Python, or CI file.

---

### Phase D — Grafana Plugin (cluster configuration)

**Deliverables**: `netsage-sankey-panel` installed and available in Grafana.

1. Add `GF_INSTALL_PLUGINS=netsage-sankey-panel` to the Grafana deployment environment (location depends on cluster's Grafana management method — Helm values, Grafana Operator CR, or Kustomize patch).
2. Verify plugin is active via `/api/plugins/netsage-sankey-panel` endpoint.

---

### Phase E — Dashboard JSON (the main artifact)

**Deliverables**: `monitoring/dashboards/datasource-health.json` — a complete, provisionable Grafana dashboard.

Dashboard structure (8 row sections):

| Row | Panel(s) | Metric(s) | Notes |
|---|---|---|---|
| 1. Freshness | State timeline heatmap, 26-cell grid | `dk_data_source_staleness_hours` | Green <4h, yellow 4–24h, red >24h |
| 2. Ingestion Volume | Stacked area chart | `job:dk_pipeline_records_processed:rate5m` | 26 series by source |
| 3. Fetch Duration | Time series (p50 + p95) | `job:dk_pipeline_duration_seconds_p50:5m`, `p95` | Per source, line chart |
| 4. Error Rate | Bar chart (24h) | `increase(dk_bronze_ingestion_errors_total[24h])` | Sorted descending |
| 5. Duplicate Detection | Time series | `rate(dk_pipeline_duplicate_fetches_total[5m])` | "No data" until Phase A |
| 6. Medallion Flow | netsage-sankey-panel | `dk_raw/bronze/silver/gold_unprocessed_total` | 4 nodes; silver+gold fallback to layer counts until Phase A |
| 7. Storage Growth | Dual time series | `dk_data_source_row_count`, `job:dk_data_source_table_size_bytes:last` | Bytes panel "No data" until Phase A |
| 8. API Consumer | Bar chart + time series | `dk_data_metering_requests_total`, `response_bytes_total`, `rate_limit_rejections_total` | metering proxy ServiceMonitor already active |

Dashboard metadata:
```json
{
  "__metadata": {
    "folder": "Data Platform",
    "tags": ["dk-data", "data-platform", "datasource-health", "auto-provisioned"],
    "version": "1.0.0",
    "maintainer": "data-platform-team"
  }
}
```

Access: Grafana folder `Data Platform` restricted to `data-platform` team with Viewer permission.

Dashboard variables:
- `datasource`: Prometheus datasource selector
- `source`: `label_values(dk_data_source_staleness_hours, source_name)` — scopes all per-source panels

FR-012 compliance: All panels configured with `noValue: "No data"` in `fieldConfig.defaults` and `nullValueMode: "null"`.

---

## Complexity Tracking

No constitutional violations. No unusual patterns introduced. The Sankey plugin is the only non-standard dependency — justified because it was explicitly chosen in clarification Q1 and no built-in panel type supports directional flow visualization between nodes.
