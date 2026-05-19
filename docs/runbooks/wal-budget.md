# Runbook: WAL budget discipline for bulk loaders

**Feature**: 002-external-integration-foundation (perf pass, [WALMX])
**Last verified**: 2026-04-13

## Why

PostgreSQL's Write-Ahead Log is the single biggest cluster-stability
risk for any write-heavy loader. A careless bulk insert can:

1. Fill the WAL directory on disk
2. Trigger an IO-heavy checkpoint that stalls every reader
3. Put replicas behind far enough to trigger re-sync
4. Force PgBouncer to reject new connections on the back of
   connection pool exhaustion (because writers are waiting on
   slow fsync)

All of these cascade into the "bring down the cluster" failure
mode the team explicitly wants to avoid.

**Rule of thumb**: keep per-transaction WAL under **2 GB**. That's
the [WALMX] tag budget.

## What counts as "too much WAL"

> **Infra freeze ceiling (2026-04-13)**: The CNPG cluster's `max_wal_size` is still at
> the Postgres default of **1 GB** (the planned 8 GB value is a Group B parameter —
> pending infra ticket, see `docs/runbooks/postgres-tuning.md`). With a 1 GB ceiling,
> a checkpoint fires every ~1 GB of WAL and causes an IO spike that stalls readers.
> **Treat 500 MB / load as the practical limit until the infra change lands.**

| Volume | Classification | Action |
|---|---|---|
| < 100 MB / txn | Normal write path | No special handling |
| 100 MB – 500 MB / txn | Bulk load (infra-freeze safe) | Use `bulk_load_session` + 5k-row commits |
| 500 MB – 1 GB / txn | **Infra-freeze danger zone** | Split into smaller ticks OR run off-peak only |
| > 1 GB / txn | **Always dangerous** | Triggers checkpoint mid-load; split across multiple ticks |
| > 2 GB / txn | **Cluster risk** | Split across multiple cronjob ticks; page on-call |

## Backend-side controls

These live in the database configuration, not in this repo:

- `max_wal_size = 4GB` — triggers checkpoint at this volume; lower
  = more frequent checkpoints but smaller per-checkpoint IO spikes.
- `checkpoint_completion_target = 0.9` — spreads checkpoint IO over
  90% of the interval (default is already this).
- `wal_keep_size = 1GB` — minimum WAL retained for replicas.
- `synchronous_commit = on` (cluster default) — every commit fsyncs.
  Bulk loaders override to `off` via the helper below.

If you're changing any of these, file a ticket to the infra team
and document in `docs/reports/capacity-audit-2026-Q2.md`.

## Client-side pattern (this repo)

Use `src/dk_data/ingestion/utils/wal_budget.py`:

```python
from dk_data.ingestion.utils.wal_budget import (
    bulk_load_session,
    chunked_insert,
)

def load_year(conn, year: int, rows: Iterator[tuple]) -> int:
    with bulk_load_session(conn):
        return chunked_insert(
            conn,
            table="mol_raw.chembl_activities",
            columns=("activity_id", "molecule_id", "target_id", "phase", "year"),
            rows=rows,
            chunk_size=5_000,   # 5k under infra freeze (was 10k); restore when max_wal_size=8GB
            on_conflict="(activity_id) DO NOTHING",
        )
```

What this does:

- `bulk_load_session` sets `synchronous_commit = off` so commits
  don't fsync. Safe because the loader is idempotent — if the pod
  crashes, the next tick re-runs the uncommitted chunk.
- `chunked_insert` commits every 10,000 rows. For ~200-byte rows,
  that's ~4 MB WAL per commit — 500× below the 2 GB budget.
- `ON CONFLICT DO NOTHING` makes the loader re-runnable. No
  duplicates, no data corruption from a partial tick.

## Anti-patterns to watch for

### `INSERT ... SELECT` over a whole table

```sql
-- DON'T — generates WAL proportional to the source table size
-- in ONE transaction.
INSERT INTO mol_silver.molecules (...)
SELECT ... FROM mol_bronze.chembl_molecules;
```

Fix: write the same transformation in SQLMesh so it's incremental,
or use chunked loops keyed by a stable cursor (e.g. `id BETWEEN
$1 AND $2`) and commit per chunk.

### Single giant COPY FROM

```python
# DON'T — no way to observe WAL growth mid-copy
cursor.copy_from(io.StringIO(giant_csv), 'table')
```

Fix: split the input file into ≤100k-row chunks and call
`copy_from` per chunk with a commit between each.

### Untransacted individual INSERTs via PgBouncer transaction mode

```python
# DON'T — PgBouncer transaction mode issues an implicit transaction
# per statement; session-level `SET synchronous_commit=off` is
# dropped before the next INSERT.
for row in rows:
    cursor.execute("INSERT INTO ...", row)
```

Fix: wrap in `bulk_load_session` which uses `SET LOCAL` so the
setting sticks for the duration of the transaction. And batch the
inserts with `executemany` / `chunked_insert`.

## Observability

Emit `dk_bronze_wal_bytes_per_tick` from the loader:

```python
import dk_data.observability.metrics as m

wal_before = cursor.execute("SELECT pg_current_wal_lsn()").fetchone()[0]
# ... do the bulk load ...
wal_after = cursor.execute("SELECT pg_current_wal_lsn()").fetchone()[0]
# pg_wal_lsn_diff returns bytes
diff_bytes = cursor.execute(
    "SELECT pg_wal_lsn_diff(%s, %s)", (wal_after, wal_before)
).fetchone()[0]

# Metric: DK_BRONZE_WAL_BYTES_PER_TICK (to be added to metrics.py)
# labels: source_name, year_or_range
m.DK_BRONZE_WAL_BYTES_PER_TICK.labels(
    source_name=source_name,
    partition=year_or_range,
).set(diff_bytes)
```

Alert: if per-tick WAL exceeds **800 MB**, warn (Grafana alert `dk-data-checkpoint-storm`
in `grafana/alerts/dk-data.yaml`). This is the infra-freeze threshold — 200 MB below
the 1 GB max_wal_size that triggers a checkpoint. If > 1.5 GB, escalate to critical.

## Off-peak backfill scheduling

Under the infra freeze (max_wal_size=1 GB), large backfills that generate 500 MB+ of WAL
MUST run during off-peak hours to avoid starving PostgREST's read queries with checkpoint
IO. PostgREST serves external consumers 24/7, so "off-peak" means the window when consumer
API traffic is lowest.

**Required off-peak window**: **02:00 – 06:00 UTC** (no consumer SLAs in effect).

Affected cronjobs that must be scheduled in this window:
- `cronjob-chembl-activities-backfill` — can generate 500 MB/tick at 17 years × ~30 MB/year
- `cronjob-pubchem-consolidation` — can generate 300–800 MB depending on the compound range
- Any manual backfill that uses `bulk_load_session` + `chunked_insert` for > 100k rows

Implementation: all affected CronJob manifests must set their `schedule` to a cron
expression that starts no earlier than `0 2 * * *` (02:00 UTC) and ends by `0 6 * * *`.

**Alert**: a Grafana alert (`dk-data-checkpoint-storm`) fires when WAL per tick exceeds
800 MB during peak hours (06:00 – 02:00 UTC). See `grafana/alerts/dk-data.yaml`.

When the infra team applies `max_wal_size=8GB`, this off-peak restriction can be relaxed.
Update this runbook's "Last verified" date and remove the off-peak requirement.

## Connection routing

Bulk loaders MUST connect via `POSTGRES_HOST_DIRECT` (not PgBouncer).
Reasons:

1. `SET LOCAL synchronous_commit = off` only sticks in session mode
2. Session-scoped advisory locks (used by `meta.job_locks`) don't
   work in transaction-mode PgBouncer
3. Preventing accidental transaction-mode fan-out from a single
   loader that assumes session state

The `cronjob-build-model-lineage.yaml` cronjob is an example of the
correct pattern — it reads `POSTGRES_HOST_DIRECT` from env and
bypasses PgBouncer entirely.

## Related

- `src/dk_data/ingestion/utils/wal_budget.py` — the helper
- `docs/runbooks/chembl-consolidation.md` — per-year budget
- `docs/runbooks/pubchem-consolidation.md` — per-range budget
- `.dk/memory/tags.md` — `[WALMX]` tag definition
- `docs/reports/capacity-audit-2026-Q2.md` — where WAL config changes get tracked
