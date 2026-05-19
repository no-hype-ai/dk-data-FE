# T001 — Verify gold-layer backfill (procedural)

**Feature**: 002-external-integration-foundation (US-8)
**Date**: 2026-04-13
**Status**: Template — execute against production PgBouncer before T089a

## Purpose

Confirm that every gold table that backs a `dk-data-client` method has
non-zero rows AND a fresh `computed_at` timestamp. Any gap here is a
guaranteed consumer-visible fallthrough once the adapter starts
driving real traffic.

## Check

Run the SQL in `docs/runbooks/verify-gold-backfill.md` against the
production read-only PostgREST host (NOT PgBouncer — use direct
because PgBouncer can hide prepared-statement issues):

```bash
PGPASSWORD=$PROD_RO_PW psql \
  -h postgres.dk-data-prod.svc \
  -p 5432 \
  -U postgres_ro -d dk_data \
  -f docs/runbooks/verify-gold-backfill.md.sql \
  > docs/reports/T001-verify-gold-backfill-$(date +%Y%m%d-%H%M).txt
```

(If the .sql file doesn't exist yet, extract the SQL block from
`verify-gold-backfill.md` and save it locally — this is a one-shot
operational query, not a committed artifact.)

## Expected pass criteria

| Table | Minimum rows | Max staleness |
|---|---|---|
| `mol_gold.molecule_profile` | ≥ 100,000 | 24h |
| `mol_gold.safety_signals` | ≥ 10,000 | 24h |
| `mol_gold.lifecycle_stages` | ≥ 100,000 | 24h |
| `mol_gold.competitive_landscape` | ≥ 1,000 | 24h |
| `mol_gold.company_pipeline` | ≥ 500 | 24h |

## Fill-in

```
Date/time run:     __________
Operator:          __________
molecule_profile:  rows=_____  staleness=_____
safety_signals:    rows=_____  staleness=_____
lifecycle_stages:  rows=_____  staleness=_____
competitive_landscape: rows=_____  staleness=_____
company_pipeline:  rows=_____  staleness=_____
Verdict:           PASS / FAIL
```

## Failure remediation

See `docs/runbooks/verify-gold-backfill.md` for failure modes and
recovery procedures. A fail here MUST block T089a.

## Related

- `docs/runbooks/verify-gold-backfill.md`
- `docs/reports/capacity-signoff.md`
- `grafana/alerts/gold-zero-rows.yaml` — T144 alert that will catch
  regressions after T089a
