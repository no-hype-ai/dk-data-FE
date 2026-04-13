# Runbook: Grafana panel shows "No data"

**Feature**: 002-external-integration-foundation, US-12
**Last verified**: 2026-04-13

A Grafana panel showing "No data" usually means one of: Prometheus isn't scraping the right endpoint, the metric isn't being emitted, the query references a metric that doesn't exist, or the label selector doesn't match what the metric actually exposes. This runbook walks through the four causes in priority order.

## Symptoms

- A panel that used to render now shows "No data"
- A new panel never rendered any data
- Some panels render, others don't, on the same dashboard
- An alert that depends on a metric never fires

## Step 1 — Is the metric actually being scraped?

Check Prometheus targets:

```
https://prometheus.behaviorlabs.ai/targets
```

Find the `dk-data-platform` job and verify all three endpoints are UP:

- `job-trigger:8000/metrics`
- `dk-data-metering-proxy:3001/metrics`
- (no separate batch-api — see B005)

If any are DOWN:
- **`job-trigger:8000` DOWN**: pod is crashing or the prometheus.io annotation is missing. Check `kubectl -n dk-data-prod logs deployment/job-trigger`.
- **`metering-proxy:3001` DOWN**: this is exactly the bug T014 fixed. The annotation used to point at port 9090 which nothing listened on. Verify `k8s/apps/metering-proxy/base/deployment-patch.yaml` has `prometheus.io/port: "3001"`. If it still says 9090, deploy the T014 fix.

## Step 2 — Is the metric defined in code?

```bash
grep -rn "<metric_name>" src/dk_data/observability/metrics.py
```

If no match, the metric is referenced by the dashboard but doesn't exist in code. Two possibilities:
- The dashboard is stale (the metric was renamed or removed). Update the dashboard query or delete the panel.
- The metric was planned but never implemented. Add the definition to `metrics.py`.

The CI metric coverage check (T113, see `tests/observability/test_metric_coverage.py`) is supposed to catch this — if you're seeing it in production, the CI check has either not been added or has been bypassed.

## Step 3 — Is the metric being emitted?

A metric can be defined in `metrics.py` but never `.inc()`'d / `.set()` / `.observe()` anywhere in the running code. This is the "dead metric" pattern that motivated US-12 in the first place — pre-feature-002 there were 38 such dead metrics.

```bash
# Find every code call site that emits the metric
grep -rn "<METRIC_OBJECT_NAME>\.\(inc\|set\|observe\|labels\)" src/dk_data/
```

If grep returns no results, the metric is dead — the helper function exists but nothing calls it. Wire up a call site in the relevant code path. Reference the spec for examples (US-12 Fix 12.4 wired up the `BATCH_JOB_*` metrics; T108 wires up `dk_pipeline_processing_duration_seconds` from the SQLMesh transform entry point).

## Step 4 — Does the label selector match?

Even when a metric is emitted, a label mismatch will silently drop it from a query.

```bash
# Inspect what labels the metric is actually emitted with
curl -s http://job-trigger:8000/metrics | grep "<metric_name>{"
# Example output:
#   dk_pipeline_jobs_total{job_name="bronze_ingest",status="success"} 42
```

Now compare against what the dashboard queries:

```promql
# Dashboard panel
sum by (job_name) (rate(dk_pipeline_jobs_total{job="dk-data-platform",environment="prod"}[5m]))
```

The dashboard filters by `environment="prod"` but the actual metric doesn't have an `environment` label. Result: the filter excludes everything → "No data".

Fix one of:
- Remove the unused filter from the dashboard query
- Add the label to the metric (and to the Prometheus scrape config relabeling)

## Step 5 — Is the scrape job named correctly?

Every dashboard filters by `job="dk-data-platform"`. If the Prometheus scrape config uses a different job name (e.g., `job_name: dk-data-platform-prod`), the filter excludes all targets.

```bash
# In Prometheus
promtool query series 'dk_pipeline_jobs_total' http://prometheus-svc:9090
# Look at the `job=` label in the output
```

If the label is something other than `dk-data-platform`, either:
- Update the dashboard queries (one-shot fix per panel — annoying)
- Update the Prometheus scrape config to relabel `job` to `dk-data-platform` (one fix, all panels work)

The latter is the right move. T016 covers the scrape job naming verification.

## Common false positives

- **Time range too narrow**: Check the dashboard's time picker. A 5-minute window won't show a metric that ticks once an hour.
- **Browser caching the panel JSON**: hard refresh (Cmd+Shift+R)
- **Loki vs Prometheus data source confusion**: dashboards mix both. Verify the panel's data source matches the metric type (counters/gauges → Prometheus, log events → Loki).

## Related

- T014 (metering-proxy port fix), T016 (scrape job naming), T113 (CI coverage check), T114 (dashboard smoke test)
- US-12 (metric endpoints discoverable + every panel renders)
- B004 (T017 stale audit), B005 (T015 N/A — no batch-api)
- `src/dk_data/observability/metrics.py` (canonical metric registry)
- `grafana/dashboards/*.json` (5 dashboards)
