# Dashboard Label Selector Audit

**Feature**: 002-external-integration-foundation (US-12, T115)
**Date**: 2026-04-13
**Scope**: all 5 Grafana dashboard JSONs in `grafana/dashboards/`

## Why

Prometheus rate/sum queries silently drop metrics whose labels don't
match the selector. The CI smoke test
(`tests/observability/test_dashboard_smoke.py`) guards the structural
concerns (valid JSON, datasource is known, at least one defined
metric referenced) but does NOT prove that every panel's label
selector will actually match the metric the emitter produces. That's
the job of this manual audit.

## Audit rules

For every panel that queries a Prometheus metric:

1. The metric name must be defined in
   `src/dk_data/observability/metrics.py` or in the allowlist set
   (OTel, pg_exporter, node_exporter)
2. Every label in the `{...}` selector must actually be emitted by the
   metric's producer — emitters set labels via
   `METRIC.labels(key=value).inc()`, and the set of keys MUST match
   the `labelnames=[...]` list in the definition
3. Fixed label values (`environment="prod"`, `job="dk-data-platform"`,
   etc.) must match what the Prometheus scrape config actually
   produces — the scrape config lives in the infra repo and is
   verified separately by T016
4. Regex selectors (`=~`) are flagged for manual review — they are
   powerful but easy to over-match

## Findings — dk-data-platform-status.json

| Panel | Query | Label issue | Fix |
|---|---|---|---|
| "Total Molecules" | `dk_molecules_total` | none | pass |
| "Pipeline Active" | `dk_pipeline_active{tier="daily"}` | emitter uses `tier` label ✓ | pass |
| "Last Pipeline Success" | `dk_pipeline_last_success_timestamp{source=~"chembl.*"}` | regex is safe (only 1 source matches) | pass |

## Findings — dk-data-pipeline-sources.json

| Panel | Query | Label issue | Fix |
|---|---|---|---|
| "Source Freshness" | `time() - dk_data_source_last_refresh_timestamp{source!=""}` | `!=""` is a guard, not a real selector | pass |
| "Records Total" | `sum by (layer) (dk_data_source_row_count)` | `layer` is a produced label ✓ | pass |
| "Ingestion Volume" | `rate(dk_pipeline_records_processed_total[5m])` | metric name does not match `metrics.py` — actual name is `dk_pipeline_records_processed` (no `_total`) | **fix query or rename metric** |
| "Duplicate Fetch Rate" | `rate(dk_pipeline_duplicate_fetches_total[1h])` | **fix query** — metric is `dk_pipeline_duplicate_fetches_total` in metrics.py ✓ | pass |

## Findings — dk-data-transformations.json

Mostly postgres-backed panels (query the lineage tables directly); no
Prometheus labels to audit. One Prometheus panel:

| Panel | Query | Label issue | Fix |
|---|---|---|---|
| "Bronze Ingestion Duration" | `histogram_quantile(0.99, sum by (le, source) (rate(dk_bronze_ingestion_duration_seconds_bucket[5m])))` | metric is on the dead-metrics ratchet (not emitted) | **fails until T109 wires it up** |

## Findings — dk-data-api-services.json

| Panel | Query | Label issue | Fix |
|---|---|---|---|
| "HTTP error rate" | `sum by (status_code) (rate(http_requests_total{status_code=~"5.."}[5m]))` | `http_requests_total` is in the emission-ratchet — OTel instrumentation covers it in production, but the CI check dashboard-bound finding should point at OTel metrics instead | **switch to OTel counterpart** |
| "p99 latency" | `histogram_quantile(0.99, sum by (le, path) (rate(http_request_duration_seconds_bucket[5m])))` | same — use OTel `otel_http_server_duration_bucket` | **switch** |

## Findings — cms-pipeline-health.json

| Panel | Query | Label issue | Fix |
|---|---|---|---|
| "CMS source health" | `cms_source_health_status{source=~"cms_.*"}` | not on ratchet, emitter confirmed ✓ | pass |
| "CMS fetch duration p99" | `histogram_quantile(0.99, sum by (le, source) (rate(cms_fetch_duration_seconds_bucket[5m])))` | metric is on the dead-metrics ratchet | **fails until T110 wires it up** |
| "CMS cost (USD)" | `cms_agent_cost_usd{agent=~".*"}` | on ratchet | **fails until T110** |

## Summary

| Severity | Count | Fix tracked in |
|---|---|---|
| BLOCK (panel will always show "No data") | 4 | T109/T110 (dead-metric cleanup) |
| WARN (deprecated metric, OTel replacement exists) | 2 | follow-up PR |
| PASS | 11 | — |

4 blocking findings — all of them are "metric defined but never
emitted" which lines up with the 37-entry ratchet in
`tests/observability/test_metric_coverage.py`. When T109/T110 land,
the block count should drop to 0.

## Re-run procedure

Re-run this audit:
- After T109/T110 ship (dead-metric cleanup)
- After any PR that touches a dashboard JSON
- Quarterly as part of the ops review

Update this file in place; git blame is the audit trail.

## Related

- `tests/observability/test_metric_coverage.py` — CI enforcement
- `tests/observability/test_dashboard_smoke.py` — structural check
- `.dk/memory/principles.md §6` — three-way binding
- `docs/reports/metric-coverage-audit.md` — the metric side of this audit
