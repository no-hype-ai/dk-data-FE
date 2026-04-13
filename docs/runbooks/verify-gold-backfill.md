# Runbook: Verify gold-layer backfill

**Feature**: 002-external-integration-foundation (US-8, T001)
**Last verified**: 2026-04-13

Before the `dk-data-client` starts driving real traffic at gold tables,
every gold table that backs a client method must have row_count > 0 and
a `computed_at` timestamp within the documented freshness SLA. Any gap
here shows up as a client-observed `fallthrough_*` outcome that should
never happen (see `docs/runbooks/adapter-fallthrough-spike.md`).

## Pass criteria

| Table | Minimum rows | Max staleness |
|---|---|---|
| `mol_gold.molecule_profile` | ≥ 100,000 | 24h |
| `mol_gold.safety_signals` | ≥ 10,000 | 24h |
| `mol_gold.lifecycle_stages` | ≥ 100,000 | 24h |
| `mol_gold.competitive_landscape` | ≥ 1,000 | 24h |
| `mol_gold.company_pipeline` | ≥ 500 | 24h |

Minimums are order-of-magnitude guards — the point is "not empty", not
a specific contract on data size.

## Procedure

```bash
# Connect to prod PgBouncer (read-only credentials work)
PGPASSWORD=$PROD_RO_PW psql \
  -h pgbouncer.dk-data-prod.svc \
  -p 6432 \
  -U postgres_ro -d dk_data <<'SQL'

SELECT
    'mol_gold.molecule_profile' AS table_name,
    COUNT(*) AS row_count,
    MAX(computed_at) AS last_refreshed,
    NOW() - MAX(computed_at) AS staleness
FROM mol_gold.molecule_profile
UNION ALL
SELECT
    'mol_gold.safety_signals',
    COUNT(*),
    MAX(computed_at),
    NOW() - MAX(computed_at)
FROM mol_gold.safety_signals
UNION ALL
SELECT
    'mol_gold.lifecycle_stages',
    COUNT(*),
    MAX(computed_at),
    NOW() - MAX(computed_at)
FROM mol_gold.lifecycle_stages
UNION ALL
SELECT
    'mol_gold.competitive_landscape',
    COUNT(*),
    MAX(computed_at),
    NOW() - MAX(computed_at)
FROM mol_gold.competitive_landscape
UNION ALL
SELECT
    'mol_gold.company_pipeline',
    COUNT(*),
    MAX(computed_at),
    NOW() - MAX(computed_at)
FROM mol_gold.company_pipeline
ORDER BY table_name;
SQL
```

Write the command output to `docs/reports/T001-verify-gold-backfill.md`
with the timestamp and operator who ran it — this is the T163 paper
trail.

## Failure modes

### Row count zero on a gold table

The SQLMesh transform that builds the table failed. Check:

```bash
kubectl -n dk-data-prod logs -l job-name=mol-transform-gold-ext --tail=200
kubectl -n dk-data-prod get jobs.batch | grep mol-transform-gold
```

Re-run the specific model:

```bash
kubectl -n dk-data-prod create job --from=cronjob/mol-transform-gold-ext \
  mol-transform-gold-ext-manual-$(date +%s)
```

### Staleness > 24h on a gold table

The cronjob either isn't running or is failing silently. Verify the
CronJob object exists and its last completion:

```bash
kubectl -n dk-data-prod get cronjob mol-transform-gold-ext -o yaml | \
  grep -E 'schedule|lastSuccessfulTime|lastScheduleTime'
```

If the schedule is `@daily` at 22:00 UTC, any staleness > 26h is a bug.
Page the owner and block production migration 218 until the issue is
resolved — stale gold violates the adapter's SC-015 promise.

## Related

- `docs/runbooks/dashboard-no-data.md` — Prometheus metric gaps
- `docs/runbooks/adapter-fallthrough-spike.md` — client-observed gaps
- `grafana/dashboards/dk-data-pipeline-sources.json` — source freshness panels
