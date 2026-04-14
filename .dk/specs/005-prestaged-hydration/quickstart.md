# Quickstart

## Prerequisites

- Python 3.11
- `postgresql-client-16` (`pg_restore` on `$PATH`)
- A local Postgres 16 with empty `meta`, `mol_*`, `hcs_*` schemas (or use the dev docker-compose)
- At least one `.dump` file under `./data/` — either from the Drive inventory (if you have access) or from a small fixture

## 1. Set up

```bash
uv sync                 # installs dk-data pyproject dependencies
export PRESTAGED_ROOT="$PWD/data"
export PG_URL="postgresql://dk:dk@localhost:5432/dkdata_dev"
```

## 2. Dry run

```bash
python -m dk_data.ingestion.prestaged --dry-run --source-list all
```

Expected: JSON lines enumerating the ordered plan, ending with a summary line. No writes to Postgres.

## 3. Validate a single tier

```bash
python -m dk_data.ingestion.prestaged --only-tier 1   # metadata + lineage
python -m dk_data.ingestion.prestaged --only-tier 2   # molecule hub raw
```

Between tiers, confirm row counts:

```sql
SELECT schema, "table", status, row_count, finished_at
FROM meta.transform_runs
WHERE run_id = (SELECT max(run_id) FROM meta.transform_runs)
ORDER BY finished_at;
```

## 4. Run end-to-end (local)

```bash
python -m dk_data.ingestion.prestaged --source-list all
```

Monitor WAL pressure in another shell:

```sql
SELECT * FROM meta.wal_usage ORDER BY observed_at DESC LIMIT 10;
```

No row should show `pct_used > 70`.

## 5. Re-run (idempotency check)

Run step 4 again. Expected: <5 minute wall-clock, every step logs `status=completed` (read from prior run) with no `pg_restore` subprocess.

## 6. Run a specific source via live-fetch fallback

```bash
# Remove any local dumps for drugbank first
rm -rf data/_staging/*/dk-data-files/mol_raw/drugbank/
python -m dk_data.ingestion.prestaged --source-list mol_raw.drugbank
# Expect: source_kind=live_fetch in meta.transform_runs
```

## 7. Promote to staging / prod

Follow `contracts/k8s-job.md`. The prod cutover is out of scope for local quickstart.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `PRESTAGED_ROOT not set` | Step 1 skipped | Export the env var |
| `pg_restore: not found` | Missing apt package | `brew install libpq` on macOS; add to `PATH` |
| `relkind check failed: 'v'` | Artifact targets a view | Expected per FR-015; skipped with warning |
| `psycopg2.OperationalError: connection refused` | Postgres not running | Start docker-compose |
| `WAL budget exhausted` | `max_wal_size` too small for local | Increase in `postgresql.conf` or lower `WAL_PAUSE_HIGH_PCT` |
