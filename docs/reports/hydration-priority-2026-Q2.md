# Hydration Priority — 2026 Q2

**Feature**: 002-external-integration-foundation (US-7, T140)
**Date**: 2026-04-13
**Status**: Template — to be filled after 2 weeks of production adapter traffic (T139)

## Purpose

This report ranks methods that are falling through to an upstream
source, using 14 days of `app=adapter-telemetry` telemetry. It
produces the Q2 prioritized ingestion list for T141 — which Tier-1
sources to ingest first based on real consumer demand, not the initial
plan.md guesses.

## Source query

```logql
topk(50,
  sum by (method, extra_upstream) (
    count_over_time(
      {app="adapter-telemetry", outcome=~"fallthrough_.*"} | json [14d]
    )
  )
)
```

## Ranked list (fill in after 2 weeks of telemetry)

| Rank | Method | Upstream | 14d count | Volume/day | Tier |
|---|---|---|---|---|---|
| 1 | TBD | TBD | TBD | TBD | TBD |

## Volume → action matrix

| 14d volume | Free upstream | Paid upstream | Action |
|---|---|---|---|
| > 140,000 (10k/day) | any | commercial review | Ingest immediately |
| 14,000 – 140,000 | any | review | Ingest in Q2 |
| 1,400 – 14,000 | any | defer | Document |
| < 1,400 | accept fallthrough | accept fallthrough | Leave as-is |

## Initial hypothesis (pre-telemetry — REPLACE on real data)

Based on the brief's hypothesis (plan.md Hydration Roadmap, Tier 1),
the following are the EXPECTED top hydration candidates. Compare this
list to the telemetry-driven list after 2 weeks; the delta is the
lesson learned.

1. **SEC EDGAR** — company financials, annual/quarterly filings
2. **BioRxiv / MedRxiv** — preprints (~2 weeks ahead of PubMed)
3. **Semantic Scholar** — citation network + paper metadata
4. **DailyMed** — FDA drug labels at full fidelity
5. **UMLS / RxNorm full** — medical terminology with NIH license
6. **FDA Orange Book** — drug approvals + bioequivalence

Each needs a source shim in `src/dk_data/ingestion/sources/`, a
SQLMesh silver model, and at minimum a placeholder row in
`meta.backfill_state` before the next run of
`build_model_lineage.py` (T142).

## Sign-off

Once filled in, this document gates T141 (actually ingesting the
top sources). It must be reviewed by the dk-data on-call engineer
and the product owner before any new source lands.

- dk-data on-call: `________________` on `__________`
- Product owner: `________________` on `__________`

## Related

- `grafana/dashboards/dk-data-adapter-telemetry.json` — source of the LogQL query
- `docs/runbooks/adapter-fallthrough-spike.md` — alerting on spikes
- `plan.md` Hydration Roadmap — the initial hypothesis
- T141 — ingestion work for the top sources
- T142 — update build_model_lineage.py for each new source
- T143 — ind-terminology subdomain
