# Runbook: Adapter telemetry shows a fallthrough spike

**Feature**: 002-external-integration-foundation, US-7
**Last verified**: 2026-04-13

The dk-data client (`packages/dk-data-client/`) emits a structured telemetry event for every call. Each event has an `outcome` field — `hit`, `miss`, `stale`, `fallthrough_upstream`, `fallthrough_hydrate`, or `error`. A sudden increase in the `fallthrough_*` outcomes means consumers are routing around dk-data and hitting upstream APIs (PubChem, FDA, ClinicalTrials.gov, etc.) directly via the client's fallback path. That's expensive, slow, and indicates dk-data is missing data its consumers want.

This runbook walks through diagnosing a fallthrough spike and deciding whether to ingest the missing source.

## Symptoms

- Loki query shows `outcome="fallthrough_upstream" OR outcome="fallthrough_hydrate"` count rising
- The "Adapter Hydration Heat Map" Grafana dashboard (`dk-data-adapter-telemetry`) shows a spike on a specific method
- A consuming app's latency p99 climbs because every fallthrough call goes to a slow upstream API
- Upstream API rate-limit alarms fire (PubChem 429, FDA OpenFDA quota exceeded, etc.)

## Step 1 — Identify the fallthrough method

Open the heat map dashboard and look at the "Top fallthrough methods" panel. Or query Loki directly:

```logql
sum by (method) (
  rate({app="adapter-telemetry"} | json | outcome=~"fallthrough_.*" [1h])
)
```

The top method is the one to focus on. Common cases:

- `molecules.getProfile` → upstream PubChem / FDA → dk-data lacks the molecule entirely
- `molecules.getClinicalTrials` → upstream ClinicalTrials.gov → trials not yet ingested for the molecule
- `molecules.getSafety` → upstream FAERS → safety signals not in `mol_gold.safety_signals`
- `publications.search` → upstream Europe PMC / Semantic Scholar → those sources are not yet ingested

## Step 2 — Determine the cause

There are three causes for a fallthrough:

### Cause A: dk-data has the data but the cache key doesn't match

Rare. Indicates the client cache is computing the wrong key for the request. Check the `args_hash` in the telemetry event — if two requests with the same logical arguments produce different `args_hash` values, the client cache key normalization is broken. File a bug against `packages/dk-data-client/`.

### Cause B: dk-data has the silver/gold tables but they're empty

Common right after a deploy or a failed nightly transform. The silver/gold tables exist but are empty, so the client gets a 200 with empty results, treats it as a miss, and falls through.

```bash
# Check row counts for the gold tables that back the failing method
psql -h $PROD_POSTGRES_HOST -U postgres -d dk_data -c "
  SELECT COUNT(*) AS row_count, NOW() - MAX(computed_at) AS staleness
  FROM mol_gold.competitive_landscape;"

# Same for the relevant silver hubs
psql ... -c "SELECT COUNT(*) FROM mol_silver.molecules;"
```

If row counts are zero or staleness is > 24h, the SQLMesh transform job has failed. Check the `cronjob-mol-transform-gold-ext` cron history:

```bash
kubectl -n dk-data-prod get jobs.batch | grep mol-transform-gold-ext
kubectl -n dk-data-prod logs job/<latest-failed-job>
```

Fix the transform, re-run it, and the fallthroughs should subside as the cache fills.

### Cause C: dk-data doesn't have the source at all

The most interesting case. The fallthrough is telling you which source consumers actually want. Check the hydration roadmap (plan.md Hydration Roadmap section) — is this source listed in Tier 1 or Tier 2?

If yes → prioritize ingesting it. The fallthrough volume justifies the build.

If no → it's a new candidate. Add it to the roadmap with the observed volume as evidence.

## Step 3 — Decide: ingest, build-vs-buy, or accept the fallthrough

| Volume | Source type | Action |
|---|---|---|
| > 10K / day | Free public API | Ingest immediately (Tier 1 priority bump) |
| > 10K / day | Paid commercial | Build-vs-buy review with cost/value table |
| 1K – 10K / day | Free | Schedule for next ingestion sprint |
| 1K – 10K / day | Paid | Document, defer until the volume justifies the cost |
| < 1K / day | Any | Accept the fallthrough; revisit if it grows |

## Step 4 — Hard limits

If the fallthrough is hitting upstream rate limits and breaking consumers:

```python
# In the consuming app, switch the fallback mode to "strict" temporarily
# to fail fast instead of cascading retries through upstream.
client = DkDataClient(..., fallback_mode="strict")
```

This buys time to ingest the source without burning the upstream quota.

## Step 5 — Close the loop

Once the missing source is ingested into dk-data:

1. The next adapter call for that method gets a `hit` outcome instead of `fallthrough_*`
2. The heat map reverts to baseline
3. Document the resolution in `.dk/memory/lessons.md` (if the fallthrough revealed a hydration roadmap gap)

## Related

- `grafana/dashboards/dk-data-adapter-telemetry.json` (heat map)
- `packages/dk-data-client/typescript/src/telemetry.ts` (event emitter)
- Plan.md "Hydration Roadmap" section
- US-7 (telemetry-driven hydration prioritization)
