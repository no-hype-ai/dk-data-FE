# Runbook: ChEMBL consolidation — sequential parameterized cronjob

**Feature**: 002-external-integration-foundation (US-20, T127a–T127c, T127d)
**Last verified**: 2026-04-13

## Summary

The legacy `cronjob-fetch-chembl-activities-{2010..2026}.yaml` series
(17 separate CronJob YAMLs) has been deleted in favor of ONE parameterized
CronJob that reads `meta.backfill_state` on each tick and fetches the next
un-backfilled year. **This is sequential — not a fan-out.** Per F-D016,
the decision was reverted from the original "fan-out per year" draft because
the fan-out draft risked rate-limit cascades against the ChEMBL public API
and was strictly worse under concurrent load.

Same pattern applies to `cronjob-fetch-pubchem.yaml` which iterates over 6
CID ranges instead of 17 years — see below for the PubChem half.

## Contract

The consolidated CronJob `cronjob-fetch-chembl-activities.yaml` is
triggered by the backfill orchestrator every 10 minutes. Each tick:

1. Reads `meta.backfill_state WHERE source_name = 'chembl_activities'`
2. If `status='active'` and `last_year_processed < 2026`, fetches
   year `last_year_processed + 1`
3. Writes rows to `mol_raw.chembl_activities` with
   `INSERT ... ON CONFLICT DO NOTHING` (idempotent — see T127b)
4. Updates `meta.backfill_state.last_year_processed` on success
5. Exits. The next tick picks up the next year.

17 ticks complete the initial historical backfill (170 minutes). After
that, subsequent ticks keep the latest year current. Any tick that
fails retries cleanly on the next tick because of (a) ON CONFLICT and
(b) `meta.refresh_state.last_chunk_position` capturing partial
chunk progress.

## `meta.backfill_state` schema requirements

The orchestrator reads/writes these columns per source:

| Column | Type | Purpose |
|---|---|---|
| `source_name` | TEXT PK | canonical source name — **`chembl_activities`** not `chembl` |
| `status` | TEXT | `active` / `paused` / `completed` / `failed` |
| `last_year_processed` | INT | last fully-processed year (NULL on first tick) |
| `last_range_processed` | INT | used by pubchem; NULL here |
| `last_run_at` | TIMESTAMPTZ | updated on every tick regardless of outcome |
| `last_success_at` | TIMESTAMPTZ | updated only on success |
| `last_error` | TEXT | the error message on the most recent failed tick |

Migration 220 verifies these columns exist and adds them if missing
(see T152a/b).

## Idempotency guarantee

Running the same year twice MUST be a no-op against `mol_raw.chembl_activities`.
The loader uses:

```sql
INSERT INTO mol_raw.chembl_activities (...)
VALUES (...)
ON CONFLICT (activity_id) DO NOTHING;
```

The primary key is `activity_id` — every ChEMBL activity has a stable ID.
The T127b test (`tests/cronjobs/test_chembl_idempotency.py`) pins this
behavior against a dry-run fixture.

## Per-year WAL budget

Each year produces roughly 500k–2M rows. At ~200 bytes per row, WAL
emission per tick stays under 2 GB, which is the budget set by
`[WALMX]`. If a year exceeds 2 GB (e.g., 2026 activity data grows),
split the year into quarters via the chunked loader
(`src/dk_data/ingestion/sources/chembl_activities.py`).

## Wall clock

- **Initial backfill (17 ticks × 10 min cadence)**: 170 minutes minimum
- **Steady state**: one tick per 10 minutes keeping `2026` current
- **Recovery from failure**: one tick per 10 minutes, resumable at the
  chunk level via `meta.refresh_state.last_chunk_position`

## Operator checks

```bash
# What year is chembl currently on?
psql ... -c "
  SELECT source_name, status, last_year_processed, last_success_at
  FROM meta.backfill_state
  WHERE source_name = 'chembl_activities';
"

# Tick history
psql ... -c "
  SELECT started_at, status, chunks_processed, chunks_failed, error_detail
  FROM meta.transform_runs
  WHERE source_name = 'chembl_activities'
  ORDER BY started_at DESC
  LIMIT 20;
"

# What was emitted in the last successful year?
psql ... -c "
  SELECT MAX(year) FROM mol_raw.chembl_activities;
"
```

## Related

- `docs/runbooks/pubchem-consolidation.md` — same pattern, 6 CID ranges
- `src/dk_data/sql/migrations/220_align_source_naming.sql` — canonical source name alignment
- `k8s/apps/cronjobs/base/cronjob-fetch-chembl-activities.yaml` — the single parameterized job
- `tests/cronjobs/test_chembl_idempotency.py` — T127b idempotency test
