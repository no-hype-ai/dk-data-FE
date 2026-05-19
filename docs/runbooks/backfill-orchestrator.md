# Backfill Orchestrator Runbook

## What it is

A self-driving cron-tick state machine that incrementally backfills historical data
from external sources without operator supervision. Replaces the manual
`job-initial-backfill.yaml` workflow.

- **State table**: `meta.backfill_state` (one row per source)
- **Picker function**: `meta.backfill_orchestrator_pick(max_active, pg_activity_threshold, daily_wal_budget_gb)`
- **Cronjob**: `cronjob-backfill-orchestrator.yaml` (runs every 10 min)
- **Migrations**: `165_meta_backfill_state.sql`, `166_seed_backfill_state.sql`
- **Reference**: github issue #256 for per-source historical depth targets
- **Alert**: `dk-data-backfill-stuck` in `grafana/alerts/dk-data.yaml`

## How it ticks

1. Every 10 min the orchestrator pod boots
2. Releases any orphaned `running` locks (pods that died mid-chunk) older than 60 min
3. Calls `meta.backfill_orchestrator_pick()` which checks circuit breakers:
   - `pg_stat_activity` active count > 30 → skip
   - Today's `meta.wal_usage` total > 50 GB → skip
   - Another row already in `status='running'` → skip (max 1 concurrent)
4. Picks one row with `status='active'`, highest priority, oldest `last_success_at`
5. Atomically marks it `running` (`FOR UPDATE SKIP LOCKED`)
6. Runs `python -m <fetcher_module> <source_name> <fetcher_args...>`
7. On exit, computes WAL bytes / row delta and calls `_complete()` or `_fail()`

## Cluster parallelism math

The cluster has 2 vCPU shared with BLAI (~30%) + litellm (~10%), leaving ~60% (1.2 vCPU)
for dk-data. A single chunked fetcher with `SET LOCAL work_mem='128MB'` consumes
0.5–1 vCPU.

| Concurrent backfills | Total vCPU | Verdict |
|---|---|---|
| 1 | 0.5–1.0 | ✅ safe, leaves headroom for daily fetchers |
| 2 | 1.0–2.0 | ⚠️ only safe if both are I/O-bound on external API |
| 3+ | 1.5–3.0+ | ❌ starves BLAI |

The orchestrator enforces **max 1 concurrent backfill** via the `running` status
check. To allow 2, set `max_active=2` in the pick function call (NOT recommended
without monitoring).

## Operator commands

### See what's happening
```sql
SELECT * FROM meta.backfill_progress;
```

### Activate a source
```sql
UPDATE meta.backfill_state
SET status = 'active', activated_at = NOW()
WHERE source_name = 'clinicaltrials';
```

The next orchestrator tick (within 10 min) will pick it up.

### Pause a source
```sql
UPDATE meta.backfill_state SET status = 'paused' WHERE source_name = '...';
```

### Recover a failed source
```sql
SELECT source_name, last_failure_reason, consecutive_failures
FROM meta.backfill_progress
WHERE status = 'failed';

-- After fixing the underlying issue:
UPDATE meta.backfill_state
SET status = 'active', consecutive_failures = 0
WHERE source_name = '...';
```

### Release a stuck `running` lock
```sql
SELECT meta.backfill_orchestrator_release('source_name');
```

(The orchestrator does this automatically on every tick for rows older than 60 min.)

### Pause everything (emergency stop)
```sql
UPDATE meta.backfill_state SET status = 'paused' WHERE status IN ('active','running');
```

Or delete the cronjob: `kubectl delete cronjob backfill-orchestrator -n dk-data-prod`

### See per-source resource consumption so far
```sql
SELECT source_name,
       chunks_run,
       total_rows_loaded,
       total_wal_mb,
       ROUND(total_duration_seconds::numeric / 60, 1) AS total_minutes
FROM meta.backfill_state
WHERE status IN ('active','complete','failed','running')
ORDER BY total_wal_mb DESC;
```

## Suggested rollout (phased activation)

The seed data inserts all sources with `status='paused'`. **Do not** activate them
all at once. Activate in priority order, one cohort at a time, watching the cluster
for an hour before the next:

1. **Cohort 1 — small one-shots** (priority 50): `purple_book`, `cms_ddinter`,
   `imgt`, `nice_hta`, `acc_tvc`, `cms_chronic_conditions`, `cms_hospital_general_info`,
   `fda_ndc`. Each loads in <10 min. Confirms the orchestrator + each fetcher binary work.

2. **Cohort 2 — checkpoint resumes** (priority 30): `chembl_activities`, `npi_registry`,
   `kegg_drug`. These resume from existing checkpoints and finish in 1–4 hours each.

3. **Cohort 3 — high-value gap fixes** (priority 10): `clinicaltrials`,
   `pubmed`, `uspto_patents`, `uspto_ci`, `epo_patents`. Each takes hours-to-days
   spread across orchestrator ticks.

4. **Cohort 4 — medium gaps** (priority 20): `europepmc`, `openalex_ci`, `nih_reporter`,
   `sec_edgar`, `uspto_trademarks`, `euipo_trademarks`, `euipo_designs`.

5. **Cohort 5 — CMS multi-year** (priority 40): `cms_open_payments`, `cms_part_d_prescriber`,
   `cms_opioid_puf`, `cms_telehealth_puf`, `cms_physician_puf_services`. Largest WAL
   footprint per chunk; do these last.

6. **Cohort 6 — pubchem** (priority 30): `pubchem`. ~84M compounds remaining.
   Already partially handled by per-shard cronjobs (`cronjob-fetch-pubchem-range-1..6.yaml`).
   The orchestrator entry just kicks it along.

To activate a whole cohort:
```sql
UPDATE meta.backfill_state SET status = 'active', activated_at = NOW()
WHERE source_name IN ('purple_book', 'cms_ddinter', /* ... */);
```

Watch:
```bash
kubectl logs -n dk-data-prod -f -l app=backfill-orchestrator
```

And:
```sql
SELECT * FROM meta.backfill_progress WHERE status IN ('running','active','failed');
```

## Coexistence with daily fetcher cronjobs

Daily/weekly fetcher cronjobs and the backfill orchestrator share the same fetcher
binary and the same `meta.fetch_checkpoints` table. They never conflict because:

- The orchestrator only picks sources with `status='active'` in `meta.backfill_state`
- Daily fetchers don't touch `meta.backfill_state`; they advance their own checkpoint
  in `meta.fetch_checkpoints`
- The fetcher binary is idempotent (`ON CONFLICT DO NOTHING`), so even if both ran
  the same source simultaneously the result would be correct (just wasted work)
- The orchestrator's circuit breaker checks `pg_stat_activity` and skips if the
  cluster is busy

## Coexistence with the SQLMesh transform pipeline

The orchestrator only loads `mol_raw.*` / `hcs_raw.*` / `ip_raw.*` data via the
fetcher binaries. SQLMesh transforms (cron schedule 06:00–12:00 UTC) consume that
raw data and promote it through bronze→silver→gold. The orchestrator does **not**
trigger SQLMesh.

If you want a backfilled source's data to flow into bronze/silver immediately, run
the relevant transform manually:

```bash
kubectl create job --from=cronjob/mol-transform-bronze backfill-bronze-now -n dk-data-prod
```

Or just wait — the next scheduled transform will pick it up.

## Why this beats manual orchestration

| | Manual | Orchestrator |
|---|---|---|
| Operator supervision | hours-to-days | zero |
| Risk of WAL explosion | high | bounded by circuit breakers |
| Resumability after pod death | no — restart from scratch | yes — next tick picks up |
| Visibility | log scraping | `SELECT * FROM meta.backfill_progress` |
| Coordination with daily cronjobs | manual deconfliction | automatic via `pg_stat_activity` check |
| Failure isolation | one bad source kills the whole run | one bad source pauses just itself |
| Time to add a new source | re-run initial backfill | `INSERT INTO meta.backfill_state` |
