# Quickstart: Data Source Grafana Dashboard

**Feature**: 017-grafana-datasource-dashboard

---

## Prerequisites

Before the dashboard shows full data, four prerequisites must be in place:

| # | Prerequisite | Where | Blocks |
|---|---|---|---|
| 1 | `netsage-sankey-panel` installed on Grafana | `GF_INSTALL_PLUGINS` env var or Grafana Operator | Medallion flow panel |
| 2 | PrometheusRule recording rules deployed | `k8s/apps/infrastructure/base/recording-rules.yaml` | 30-day query performance |
| 3 | 4 new Python metrics added and emitting | `observability/metrics.py` + callers | Duplicate, storage, silver/gold backlog panels |
| 4 | `data-platform` Grafana team and folder permissions configured | Grafana provisioning | Access control |

---

## Step 1 — Add Grafana Plugin

Add to the Grafana deployment environment (or Helm values):

```yaml
env:
  GF_INSTALL_PLUGINS: "netsage-sankey-panel"
```

Verify after restart:
```bash
# Port-forward to Grafana and check
curl http://localhost:3000/api/plugins/netsage-sankey-panel | jq '.name'
```

---

## Step 2 — Deploy Recording Rules

```bash
# Apply the PrometheusRule CRD
kubectl apply -f k8s/apps/infrastructure/base/recording-rules.yaml -n dk-data-prod

# Verify it was picked up by Mimir ruler
kubectl get prometheusrules -n dk-data-prod | grep recording

# After ~5 minutes, verify recorded metrics exist
kubectl exec -n infra deploy/mimir -- wget -qO- \
  'http://localhost:9009/prometheus/api/v1/query?query=job:dk_pipeline_records_processed:rate5m' \
  | jq '.data.result | length'
```

---

## Step 3 — Add New Metrics to Python

Four metrics must be added. See `specs/017-grafana-datasource-dashboard/contracts/new-metrics.md` for the exact Python definitions and emit locations.

Summary of changes:
- `src/dk_data/observability/metrics.py` — add 4 metric definitions
- `src/dk_data/services/data_platform/metrics.py` — add staleness emission + 2 helpers + extend `refresh_metrics_from_database_sync()` (staleness, silver unprocessed, gold unprocessed queries)
- `src/dk_data/services/data_platform/raw_ingestion.py` — add duplicate counter increment

**Important**: `dk_data_source_staleness_hours` is defined but never emitted. Adding staleness emission to `refresh_metrics_from_database_sync()` is required for the freshness heatmap and the `$source` dashboard variable to function.

Verify metrics are emitting:
```bash
# Port-forward to the job-trigger or batch-api /metrics endpoint
kubectl port-forward -n dk-data-prod deploy/job-trigger 8080:8080
curl -s http://localhost:8080/metrics | grep dk_data_source_table_size_bytes
curl -s http://localhost:8080/metrics | grep dk_pipeline_duplicate_fetches_total
```

---

## Step 4 — Migrate Orphaned Dashboards

```bash
# Move the 5 orphaned files to the canonical location
mv src/dk_data/monitoring/grafana/dashboards/*.json monitoring/dashboards/

# Remove the now-empty directory tree
rm -rf src/dk_data/monitoring/grafana/dashboards/
rmdir src/dk_data/monitoring/grafana/ 2>/dev/null || true
rmdir src/dk_data/monitoring/ 2>/dev/null || true
```

---

## Step 5 — Deploy Dashboard

Commit `monitoring/dashboards/datasource-health.json` to the branch and merge. The Grafana provisioning sidecar picks it up on next deployment.

Verify in Grafana:
1. Navigate to Dashboards → Data Platform folder
2. Confirm `datasource-health` dashboard is present
3. Confirm all 8 row sections are visible
4. Set time range to 24h — all panels with existing metrics should show data
5. Panels for `dk_pipeline_duplicate_fetches_total`, `dk_silver_unprocessed_total`, `dk_gold_unprocessed_total` will show "No data" until Step 3 changes are deployed

---

## Panel-by-Panel Data Readiness Checklist

| Panel | Metric | Ready at deploy? |
|---|---|---|
| Freshness heatmap | `dk_data_source_staleness_hours` | ⏳ After Step 3 — metric is defined but never emitted; emission must be added to `refresh_metrics_from_database_sync()` |
| Ingestion volume | `dk_pipeline_records_processed_total` | ✅ Yes (uses recording rule for 30d) |
| Fetch duration | `dk_pipeline_duration_seconds` | ✅ Yes (uses recording rule for 30d) |
| Error rate by source | `dk_bronze_ingestion_errors_total` | ✅ Yes |
| Duplicate detection | `dk_pipeline_duplicate_fetches_total` | ⏳ After Step 3 (new metric) |
| Medallion flow | `dk_raw/bronze/silver/gold_unprocessed_total` | ⏳ Raw+bronze ready; silver+gold after Step 3 |
| Storage — row count | `dk_data_source_row_count` | ✅ Yes |
| Storage — bytes | `dk_data_source_table_size_bytes` | ⏳ After Step 3 (new metric) |
| API consumer usage | `dk_data_metering_*` | ✅ Yes (metering proxy ServiceMonitor active) |
