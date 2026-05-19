# Runbook: Silver Hub Bootstrap Incident Response

**Feature**: 001-silver-medallion-rebuild  
**Task**: T144  
**Scope**: Stuck job locks, runaway WAL, mid-bootstrap pod kill

---

## Overview

The silver hub bootstrap procedures populate 10 entity-resolution hubs by reading bronze tables and inserting into `mol_silver`, `hcs_silver`, `ind_silver`, `hcp_silver`, and `ip_silver`. Each bootstrap procedure:

- Acquires a row in `meta.job_locks` before starting
- Records progress per chunk in `meta.transform_runs`
- Uses chunked PL/pgSQL with `≤50K rows/chunk` and `pg_sleep(0.05)` between chunks
- Connects via `POSTGRES_HOST_DIRECT` (bypassing PgBouncer) to maintain session state

---

## Scenario 1: Stuck `meta.job_locks`

### Symptoms
- Bootstrap CronJob hangs indefinitely with no progress in `meta.transform_runs`
- `meta.job_locks` shows a lock held past its `expires_at`

### Diagnosis
```sql
-- Check current locks
SELECT name, locked_by, locked_at, expires_at,
       CASE WHEN expires_at < NOW() THEN 'EXPIRED' ELSE 'ACTIVE' END AS status
FROM meta.job_locks
ORDER BY locked_at;

-- Check if the holding pod is still alive (run in kubectl)
-- kubectl get pods -n dk-data | grep <locked_by pod prefix>
```

### Resolution
```sql
-- Option 1: Delete expired lock (safe — pod is dead)
DELETE FROM meta.job_locks
WHERE name = '<procedure_name>'
  AND expires_at < NOW();

-- Option 2: Force-release active lock (use only if pod is confirmed dead)
DELETE FROM meta.job_locks
WHERE name = '<procedure_name>';

-- Re-trigger the bootstrap CronJob
-- kubectl create job --from=cronjob/dk-bootstrap-<hub> manual-bootstrap-<hub>-$(date +%s) -n dk-data
```

### Prevention
The `expires_at` TTL is set to 4 hours per bootstrap procedure. If a procedure takes longer, increase the TTL in the `001_meta_job_locks.sql` migration or in the procedure's CALL statement.

---

## Scenario 2: Runaway `meta.transform_runs.wal_bytes`

### Symptoms
- A bootstrap procedure is generating > 200 MB WAL per chunk (exceeds the FR-021 budget of 200 MB/chunk)
- Grafana alert `dk_data_wal_explosion` fires (> 5 GB per job)
- `meta.transform_runs` shows `wal_bytes > 200_000_000` on recent rows

### Diagnosis
```sql
-- Identify the offending procedure
SELECT procedure_name, chunk_position,
       wal_bytes / 1e6 AS wal_mb,
       rows_processed,
       started_at, ended_at
FROM meta.transform_runs
WHERE wal_bytes > 200000000
ORDER BY started_at DESC
LIMIT 20;

-- Check current WAL pressure
SELECT wal_files, wal_size_bytes / 1e9 AS wal_gb
FROM meta.wal_status
ORDER BY logged_at DESC
LIMIT 5;
```

### Resolution
1. **Kill the running procedure** (if WAL is still growing):
   ```bash
   # Find the backend PID
   SELECT pid, query_start, state, left(query, 100)
   FROM pg_stat_activity
   WHERE datname = 'dk_data'
     AND query ILIKE '%bootstrap%'
   ORDER BY query_start;

   -- Cancel (soft kill)
   SELECT pg_cancel_backend(<pid>);
   -- Terminate (hard kill)
   SELECT pg_terminate_backend(<pid>);
   ```

2. **Release the lock** (see Scenario 1)

3. **Investigate root cause**: Check if the chunk size increased (e.g., the bronze table grew significantly) or if a non-indexed scan is touching more rows than expected.

4. **Restart with smaller chunk size**: Temporarily reduce `CHUNK_SIZE` constant in the procedure from 50000 to 10000 and redeploy.

### Prevention
- All bootstrap procedures bracket each chunk with `pg_current_wal_lsn()` and abort if WAL > 200 MB
- The `meta.wal_usage` table tracks per-job WAL; alert fires at 5 GB

---

## Scenario 3: Mid-Bootstrap Pod Kill (Kubernetes eviction / OOM kill)

### Symptoms
- Bootstrap CronJob pod disappears mid-run (OOM, node eviction, spot instance preemption)
- `meta.job_locks` still holds the lock with an `expires_at` in the future
- `meta.refresh_state` shows `status = 'in_progress'` for the procedure
- Hub table is partially populated (some chunks committed, remainder missing)

### Diagnosis
```sql
-- Check what was committed before the pod died
SELECT procedure_name, last_chunk_position, last_commit_at, status
FROM meta.refresh_state
WHERE procedure_name = 'bootstrap_<hub>';

-- Count committed rows
SELECT COUNT(*) FROM mol_silver.<hub_table>;
-- Compare to expected count from bronze
SELECT COUNT(*) FROM mol_bronze.<source_table>;
```

### Resolution
The bootstrap procedures support **resumability** via `meta.refresh_state`. When the CronJob is re-triggered:

1. The procedure reads `last_chunk_position` from `meta.refresh_state`
2. It skips already-committed chunks (OFFSET = last_chunk_position)
3. It continues from where it left off

**Manual re-trigger**:
```bash
kubectl create job --from=cronjob/dk-bootstrap-<hub> \
  manual-bootstrap-<hub>-$(date +%s) \
  -n dk-data
```

**If resumability is broken** (e.g., the resume position is corrupted):
```sql
-- Reset resume position (will re-process all chunks from scratch)
UPDATE meta.refresh_state
SET last_chunk_position = 0, status = 'in_progress', last_commit_at = NOW()
WHERE procedure_name = 'bootstrap_<hub>';

-- Clear the partial data from the hub (TRUNCATE is safe — bootstrap will repopulate)
TRUNCATE mol_silver.<hub_table>;
TRUNCATE mol_silver.<hub_identifiers_table>;
TRUNCATE mol_silver.<hub_names_table>;
```

### Idempotency guarantee
All bootstrap procedures use `INSERT ... ON CONFLICT DO NOTHING` (or `ON CONFLICT DO UPDATE` for hub rows where source priority may improve the record). Re-running from scratch is always safe.

---

## Monitoring Queries

```sql
-- Active bootstrap jobs (running right now)
SELECT jl.name, jl.locked_by, jl.locked_at,
       tr.chunk_position, tr.rows_processed, tr.wal_bytes / 1e6 AS wal_mb,
       tr.started_at
FROM meta.job_locks jl
LEFT JOIN meta.transform_runs tr
    ON tr.procedure_name = jl.name
    AND tr.started_at = (
        SELECT MAX(started_at) FROM meta.transform_runs
        WHERE procedure_name = jl.name
    )
ORDER BY jl.locked_at DESC;

-- Recent bootstrap completions
SELECT procedure_name, last_chunk_position, last_commit_at, status
FROM meta.refresh_state
ORDER BY last_commit_at DESC NULLS LAST;

-- WAL produced per bootstrap run (last 24h)
SELECT procedure_name,
       SUM(wal_bytes) / 1e9 AS total_wal_gb,
       SUM(rows_processed) AS total_rows,
       MIN(started_at) AS run_start,
       MAX(ended_at) AS run_end
FROM meta.transform_runs
WHERE started_at > NOW() - INTERVAL '24 hours'
GROUP BY procedure_name
ORDER BY total_wal_gb DESC;
```

---

## Contact

- **On-call**: Check Grafana alert `dk_data_wal_explosion` and `dk_data_long_transaction`
- **Slack**: `#dk-data-oncall`
- **Procedure code**: `src/dk_data/sql/migrations/031_silver_hub_rebuild/014_bootstrap_*.sql`
