# Runbook: PubChem consolidation — sequential parameterized cronjob

**Feature**: 002-external-integration-foundation (US-20, T127d)
**Last verified**: 2026-04-13

## Summary

The legacy `cronjob-fetch-pubchem-range-{1..6}.yaml` series (6 separate
CronJob YAMLs covering 6 disjoint CID ranges) has been deleted in favor
of ONE parameterized CronJob that reads `meta.backfill_state` on each
tick and fetches the next un-backfilled range. Like the ChEMBL runbook,
this is **sequential** — per F-D016 the fan-out draft was reverted
because parallel PubChem fetches risked tripping the `400 requests/min`
PubChem API rate limit.

## Contract

The consolidated CronJob `cronjob-fetch-pubchem.yaml` is triggered by
the backfill orchestrator every 10 minutes. Each tick:

1. Reads `meta.backfill_state WHERE source_name = 'pubchem_molecules'`
2. If `status='active'` and `last_range_processed < 6`, fetches
   range `last_range_processed + 1`
3. Writes rows to `mol_raw.pubchem_molecules` with
   `INSERT ... ON CONFLICT DO NOTHING`
4. Updates `meta.backfill_state.last_range_processed` on success
5. Exits. The next tick picks up the next range.

6 ticks complete the initial backfill (60 minutes). After that,
steady-state re-runs cycle through the ranges picking up mutations.

## CID range definitions

Each range is a fixed disjoint slice of the PubChem CID space:

| Range | CID lower | CID upper | Rough row count |
|---|---|---|---|
| 1 | 1          | 25_000_000  | ~5M  active compounds |
| 2 | 25_000_001 | 50_000_000  | ~4M |
| 3 | 50_000_001 | 75_000_000  | ~3M |
| 4 | 75_000_001 | 100_000_000 | ~3M |
| 5 | 100_000_001| 130_000_000 | ~2.5M |
| 6 | 130_000_001| 200_000_000 | ~1.5M |

Ranges are hard-coded in `src/dk_data/ingestion/sources/pubchem_molecules.py`
and documented in migration 220's comment block. Changing the range
partitioning requires a coordinated migration to `meta.backfill_state`
AND updated cron idempotency tests.

## Wall clock

- **Initial backfill (6 ticks × 10 min cadence)**: 60 minutes minimum
- **Steady state refresh**: one range per 10 minutes, full cycle every hour
- **Failure**: retries on next tick; partial chunk state carried in
  `meta.refresh_state.last_chunk_position`

## Rate-limit discipline

PubChem enforces 5 requests/second, 400 requests/minute, and 5,000
requests/day per IP. One tick = ~50 requests (25M CIDs / page_size=500k
= 50 HTTP calls), so one tick consumes ~12.5% of the daily quota. Six
ticks per hour = 72% of quota per day — at the edge but within budget
as long as NO OTHER service also hits PubChem from the same IP.

If the tick ever returns 429 from PubChem, the loader backs off for
30 seconds and retries. On two consecutive 429s, `meta.backfill_state.status`
flips to `paused` and the operator must unblock manually after
confirming the IP is not hitting unrelated quota.

## Operator checks

```bash
# Which range is pubchem currently on?
psql ... -c "
  SELECT source_name, status, last_range_processed, last_success_at
  FROM meta.backfill_state
  WHERE source_name = 'pubchem_molecules';
"

# Most-recent ticks and their outcome
psql ... -c "
  SELECT started_at, status, chunks_processed, chunks_failed, error_detail
  FROM meta.transform_runs
  WHERE source_name = 'pubchem_molecules'
  ORDER BY started_at DESC
  LIMIT 20;
"

# Verify no duplicate rows
psql ... -c "
  SELECT cid, COUNT(*) FROM mol_raw.pubchem_molecules
  GROUP BY cid HAVING COUNT(*) > 1 LIMIT 5;
"
# Expected: 0 rows
```

## Related

- `docs/runbooks/chembl-consolidation.md` — same pattern, 17 years
- `src/dk_data/sql/migrations/220_align_source_naming.sql` — canonical name alignment
- `k8s/apps/cronjobs/base/cronjob-fetch-pubchem.yaml` — the parameterized job
