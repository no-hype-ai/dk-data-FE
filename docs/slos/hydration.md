# Hydration SLO

**Scope**: pre-staged (feature/005) and live-fetcher hydration paths. One SLO per
source, keyed by the `source` label on the canonical metrics.

**Plan reference**: `plan.md` §C.6.

## Statement

> For each declared source, 95% of hydration runs complete within the source's
> declared `sla_seconds`. An alert fires after **three consecutive** samples
> breach this threshold (≈ 15 min at a 5 min evaluation window), to absorb
> single-run noise from network hiccups and WAL-throttle pauses.

- **Service**: `dk-data-fe` hydration (pre-staged + live-fetcher).
- **SLI (Service Level Indicator)**: p95 of `dk_hydration_phase_seconds` summed
  across all phases per `(source)`. Per-phase p95 is also tracked but the SLO is
  on the end-to-end sum.
- **SLO (Service Level Objective)**: p95 ≤ `sla_seconds` where `sla_seconds` is
  declared per-source in `deploy/hydrate/sources.yaml` (feature/005 / §D.2). A
  global default of `3600` (1 h) applies to sources without an explicit value.
- **Error budget window**: rolling 30 days. Budget = 5% of scheduled runs.
- **Freshness companion SLO**: `time() - dk_source_last_success_timestamp ≤
  max(sla_seconds, 24h)`. Three consecutive breaches → `HydrationSourceStale`
  warning; one breach > 7 d → critical.

## Metrics the SLO rides on

| Metric | Type | Purpose |
|---|---|---|
| `dk_hydration_phase_seconds{source,schema,table,phase}` | Histogram | Per-phase latency; p95 roll-up drives the duration SLO. |
| `dk_artifact_bytes_total{source,kind}` | Counter | Throughput context for triage (is the source pulling bytes at all?). |
| `dk_source_last_success_timestamp{source}` | Gauge | Drives the freshness companion SLO. |

All three are declared in `src/dk_data/observability/metrics.py`. Emission sites
land with the feature/005-prestaged-hydration follow-up PR; until then these
panels show `No data` and alerts stay green by virtue of no breaching samples.

## Dashboards

- `grafana/dashboards/applications/dk-data-fe-hydration.json` —
  `dk-data-fe-hydration` — per-source phase latency, bytes moved, freshness.
- `grafana/dashboards/applications/dk-data-fe-source-registry.json` —
  `dk-data-fe-source-registry` — aggregate freshness buckets, stale-source
  count, per-source ranking.

## Worked example

**Source**: `uspto_patents`, `sla_seconds = 1800` (30 min).

The hydration pipeline emits histogram observations per `(source, schema, table,
phase)` each run. The dashboard aggregates across `(schema, table)` and
computes p95 over a 5 min window:

```promql
# per-source end-to-end p95
histogram_quantile(
  0.95,
  sum by (source, le) (rate(dk_hydration_phase_seconds_bucket{source="uspto_patents"}[5m]))
)
```

SLO breach condition (used by the PrometheusRule that follows this PR):

```promql
# fires when p95 exceeds the declared sla_seconds for THREE consecutive evals
(
  histogram_quantile(
    0.95,
    sum by (source, le) (rate(dk_hydration_phase_seconds_bucket[5m]))
  )
  > on (source) group_left()
  dk_source_sla_seconds  # optional companion gauge (feature/005 follow-up)
) > bool 0
```

Until `dk_source_sla_seconds` exists, use a static threshold per source:

```yaml
# alerts/hydration.yaml (follow-up PR)
- alert: HydrationP95Breach
  expr: |
    histogram_quantile(
      0.95,
      sum by (source, le) (rate(dk_hydration_phase_seconds_bucket[5m]))
    ) > 1800
  for: 15m  # three consecutive 5m samples
  labels:
    severity: warning
    source: "{{ $labels.source }}"
  annotations:
    summary: "Hydration p95 for {{ $labels.source }} exceeds SLA (1800s)."
    runbook: "docs/runbooks/hydration-slo-breach.md"  # to be written
```

### Freshness example

If `uspto_patents` last succeeded 26 h ago:

```promql
(time() - dk_source_last_success_timestamp{source="uspto_patents"}) / 3600
# = 26  → yellow threshold on the source-registry stat panel
```

If it stays > 24 h for three evals → `HydrationSourceStale` warning. If it
crosses 168 h (7 d) → critical.

## Why three consecutive breaches?

Hydration is batch-shaped, not request-shaped. A single overrun from a
pg_restore under WAL pressure is not an incident — three in a row is. The
`for: 15m` clause in the PrometheusRule enforces this without extra state.

## Review cadence

Re-check declared `sla_seconds` quarterly against actual p95 trends. Sources
whose p95 runs at < 50% of SLA for two quarters should have their SLA tightened;
sources that chronically breach at < 10% of samples without user impact should
have their SLA loosened (document why in the source-registry PR).

## Related

- `plan.md` §C.6 — metric & SLO definition.
- `plan.md` §C.3 — dead-letter queue backs the breach workflow.
- `plan.md` §D.2 — per-source `sources.yaml` where `sla_seconds` will live.
- `src/dk_data/observability/metrics.py` — metric declarations.
