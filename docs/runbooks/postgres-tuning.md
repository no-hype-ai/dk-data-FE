# Runbook: PostgreSQL tuning requirements for dk-data

**Feature**: 002-external-integration-foundation (k8s/db audit)
**Last verified**: 2026-04-13
**Owner**: dk-data team coordinates with infra team

The dk-data application depends on a number of PostgreSQL configuration
parameters that live in the **infrastructure repo** (the CNPG cluster
spec), not in this repo. This runbook is the contract: the parameters
listed below MUST be set on the shared cluster for dk-data to work
correctly under production load.

If any of these are wrong, the symptoms range from "individual queries
slow" (auto_explain off) to "cluster crashes under burst load"
(max_connections too low) to "WAL fills disk overnight" (max_wal_size
too small). The capacity-audit and capacity-signoff reports in
`docs/reports/` are the verification side; this runbook is the
*requirement* side.

## Required `postgresql.conf` parameters

```yaml
# CNPG cluster spec — postgresql.parameters
postgresql:
  parameters:
    # ---- Connection budget ----
    max_connections: "300"           # was 200; bumped per capacity-signoff.md
    superuser_reserved_connections: "5"
    # ---- Memory ----
    shared_buffers: "8GB"            # 25% of node RAM (32GB nodes)
    effective_cache_size: "24GB"     # 75% of node RAM
    work_mem: "32MB"                 # raise via SET LOCAL for bulk loaders
    maintenance_work_mem: "1GB"      # autovacuum + REINDEX
    huge_pages: "try"
    # ---- WAL / checkpoint ----
    wal_level: "replica"
    max_wal_size: "8GB"              # default 1GB → too small for our backfills
    min_wal_size: "1GB"
    checkpoint_timeout: "15min"
    checkpoint_completion_target: "0.9"
    wal_compression: "on"
    wal_keep_size: "2GB"             # for replicas to catch up after lag
    # ---- Query planner ----
    random_page_cost: "1.1"          # SSD storage
    effective_io_concurrency: "200"  # NVMe
    default_statistics_target: "200" # higher = better plans, slower ANALYZE
    # ---- Autovacuum ----
    autovacuum_naptime: "30s"        # default 1min; we have hot tables
    autovacuum_vacuum_scale_factor: "0.05"   # default 0.2 (20%); too lazy for 15M-row tables
    autovacuum_analyze_scale_factor: "0.02"
    autovacuum_max_workers: "5"       # default 3
    # ---- Logging (slow query) ----
    log_min_duration_statement: "500"   # log queries >500ms
    log_lock_waits: "on"
    log_temp_files: "10MB"              # find sorts/joins spilling to disk
    log_autovacuum_min_duration: "5s"
    # ---- Extensions ----
    shared_preload_libraries: "pg_stat_statements,auto_explain"
    "pg_stat_statements.track": "all"
    "pg_stat_statements.max": "5000"
    "auto_explain.log_min_duration": "1000"  # explain plans for queries >1s
    "auto_explain.log_analyze": "off"        # too expensive in prod
    "auto_explain.log_buffers": "on"
    "auto_explain.log_format": "json"
```

## Required extensions

These need both `CREATE EXTENSION` (in dk-data migrations) AND
`shared_preload_libraries` entry (in CNPG cluster spec):

| Extension | Why | Migration | shared_preload? |
|---|---|---|---|
| `pg_trgm` | Trigram indexes for ILIKE searches | 225 | NO (operator class only) |
| `pg_stat_statements` | Per-query latency tracking | 226 | **YES** |
| `auto_explain` | Auto-log slow query plans | (none — config only) | **YES** |
| `pgcrypto` | bcrypt for `consumers.yaml` API key hashes | (older migration) | NO |

If `shared_preload_libraries` doesn't include `pg_stat_statements` and
`auto_explain`, the migrations succeed but the data never populates.

## Connection budget breakdown

Total = `max_connections = 300` (after the bump from 200):

| Consumer | Per-replica | Replicas | Total |
|---|---|---|---|
| postgres superuser + pg_stat_replication | — | — | 5 |
| Replication slots | — | — | 10 |
| dk_data via PgBouncer | 50 (pool_size) | 2 (pgbouncer replicas) | 100 |
| behavior_labs via PgBouncer | 25 | 2 | 50 |
| litellm via PgBouncer | 10 | 2 | 20 |
| SQLMesh transform jobs (direct) | 10 | 1 | 10 |
| Backup / monitoring | — | — | 10 |
| **Total** | — | — | **205** |
| **Headroom** | — | — | **95** |

The 95-slot headroom absorbs:
- Migration runner connections (direct, bypassing PgBouncer)
- Backfill cronjobs (direct)
- pg_stat_statements collection
- Ad-hoc operator psql sessions

If `max_connections` cannot be raised to 300, the alternative is to
shrink the PgBouncer pool budget — but doing so caps PostgREST's
projected 3-replica scale.

## Autovacuum tuning rationale

Default Postgres autovacuum is too lazy for tables in the millions of
rows. The dk-data tables that need aggressive vacuum:

- `mol_silver.molecules` (~2M rows)
- `mol_silver.publications` (~15M rows)
- `mol_silver.bioactivity` (~50M rows)
- `mol_raw.chembl_activities` (~50M rows after backfill)
- `meta.transform_runs` (write-heavy, ~10k rows/day)
- `meta.api_audit_log` (write-heavy, append-only)

With `autovacuum_vacuum_scale_factor=0.05`, autovacuum kicks in when
5% of tuples are dead — for a 15M-row table that's 750k dead tuples,
not the default 3M. This keeps the bloat budget under control.

For the heaviest writers, set per-table overrides via `ALTER TABLE`:

```sql
ALTER TABLE mol_raw.chembl_activities SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_cost_limit = 2000
);
```

## WAL configuration rationale

`max_wal_size = 8GB` (default 1GB) prevents the backfill jobs from
forcing checkpoints every 1GB. The chembl backfill runs at ~500MB
per year × 17 years; if WAL rotates mid-backfill, the checkpoint IO
spikes saturate the disk and stall every reader.

`wal_compression = on` saves about 30-50% of WAL volume on row-heavy
workloads at a small CPU cost. Worth it given dk-data writes
~50GB/day during full backfill.

`wal_keep_size = 2GB` ensures replicas have enough lag headroom; if a
replica disconnects briefly, it can resume from WAL instead of needing
a basebackup.

See `docs/runbooks/wal-budget.md` for the application-side WAL discipline
that goes hand-in-hand with these cluster-side settings.

## Verification queries

Once the cluster spec is updated, verify each setting from psql:

```sql
-- Connection budget
SHOW max_connections;
SELECT count(*), state FROM pg_stat_activity GROUP BY state;

-- Memory settings
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW work_mem;

-- WAL settings
SHOW max_wal_size;
SHOW checkpoint_timeout;

-- Extensions loaded
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name IN ('pg_stat_statements', 'auto_explain', 'pg_trgm');

SELECT extname FROM pg_extension WHERE extname IN ('pg_stat_statements', 'pg_trgm');

-- shared_preload check
SHOW shared_preload_libraries;

-- Top slow queries (after migration 226 + cluster spec update)
SELECT * FROM meta.top_slow_queries LIMIT 5;
```

Save the output to `docs/reports/T_postgres-tuning-verified.md` with
a timestamp.

## Coordinating with the infra team

When you need a parameter changed:

1. Open a ticket against the infra repo referencing this runbook
2. Specify the EXACT parameter, current value, target value, and
   the dk-data symptom that motivates the change
3. The infra team applies via `kubectl apply` to the CNPG cluster spec
4. CNPG handles the rolling restart — most parameters are
   `context: postmaster` and require a restart, others
   (`work_mem`, `log_*`) are SIGHUP-reload only
5. Re-run the verification queries above and update this runbook's
   "Last verified" date

**Restart-required parameters**: `shared_preload_libraries`,
`max_connections`, `shared_buffers`, `wal_level`, `max_wal_senders`.
A change to any of these is a CNPG rolling restart of every Postgres
pod. Plan accordingly — schedule for an off-peak window.

## Related

- `docs/reports/capacity-audit-2026-Q2.md` — capacity numbers
- `docs/reports/capacity-signoff.md` — infra team contract
- `docs/runbooks/wal-budget.md` — application-side WAL discipline
- `src/dk_data/sql/migrations/225_trgm_indexes_for_search.sql` — pg_trgm indexes
- `src/dk_data/sql/migrations/226_pg_stat_statements.sql` — pg_stat_statements
- `k8s/apps/infrastructure/base/pgbouncer.yaml` — pool size budget
- `k8s/apps/postgrest/base/configmap.yaml` — PGRST_DB_POOL=30
