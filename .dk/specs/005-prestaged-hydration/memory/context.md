# Feature Context: 005-prestaged-hydration

**Active tags**: `[TYPED]`, `[IDMPT]`, `[DRYBK]`, `[AUDIT]`, `[VIEWSAFE]`, `[WALBUD]`, `[TESTE]`

## Why this feature exists

dk-data-prod is stuck: fetchers are broken, upstream APIs have drifted, and the observability stack is partially down. A Drive folder with 13 archives (120 dumps, 42.5 GB of `pg_dump -Fc` files) can bypass the broken pipeline and hydrate prod directly. This feature operationalizes that bypass.

## Load order, in one sentence

metadata → molecule hubs (raw → bronze → silver) → clinical/activity spokes → hcs raw → hcs bronze → hcs silver → gold. Serial. WAL-throttled. View-safe. Idempotent.

## What NOT to touch

- `wal_budget.py` — only consume, don't reinvent
- `main.run_ingestion` — live-fetch fallback entry point, stable interface
- `sqlmesh/models/**` — SQLMesh owns transform layer DDL, never overwrite
- Silver views (`mol_silver.publications`, `mol_silver.bioactivity`) — managed by SQLMesh
- `ip_*`, `ind_*`, `hcp_silver` — explicitly out of scope

## Where the artifacts live

`${PRESTAGED_ROOT}` env var. Prod `/data/prestaged`, local `./data`. Two layouts:
- `_staging/<archive>/dk-data-files/{schema}/{table_or_dir}/*.dump`
- `_loose_dumps/{schema}/*.dump`

## Key numbers

- 120 dumps, 42.5 GB
- 5 tables > 5 GB (WAL-mode): `mol_raw.pubchem`, `mol_raw.clinicaltrials`, `mol_bronze.pubchem`, `mol_bronze.chembl_activities`, `mol_bronze.clinicaltrials`
- WAL throttle: pause at 70% of `max_wal_size`, resume at 40%
- SLA: full run < 4 h; re-run < 5 min (idempotency)
