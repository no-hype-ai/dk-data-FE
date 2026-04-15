# Stage 7 — Operator sign-off (single-source rehearsal against prod)

**Feature**: 005-prestaged-hydration
**Stage**: 7 (small-source dry-run + dashboard prep)
**Exit gate type**: runtime-green
**Created**: <FILL: ISO-8601 timestamp at start of rehearsal>
**Signed off**: <FILL: ISO-8601 timestamp + signer name>

## Pre-conditions (must all be true before Stage 8 fires)

- [ ] Stage 6 closed (code, tests, mypy, CI smoke green at HEAD `2bda008`)
- [ ] Migration 229 applied to prod `meta.transform_runs` and verified (`\d meta.transform_runs` shows `status text`, `details jsonb`, plus `meta_transform_runs_status_idx` and `meta_transform_runs_run_label_idx`)
- [ ] Migration 230 applied to prod (3 hydration views + grants to `api_user`)
- [ ] Pre-hydration snapshot captured at `~/dk-data-prod-snapshots/pre_hydration_<date>.dump` and size > 0
- [ ] SSH tunnel to prod PgBouncer is open and `psql 'postgresql://…:6432/dk_data' -c 'select 1'` returns 1
- [ ] `python -m dk_data.ingestion.prestaged --dry-run --source-list mol_raw.kegg_drug` against prod emits one JSON step + summary line, exit 0, zero writes
- [ ] Single-source live restore (`--source-list mol_raw.kegg_drug`, no `--dry-run`) completed
- [ ] `meta.transform_runs` has exactly one row for `mol_raw.kegg_drug` with `status='completed'`, `details->>'source_kind'='pg_dump'`, `details->>'run_label' = <expected hash>`
- [ ] `SELECT count(*) FROM mol_raw.kegg_drug` matches the dump's manifest count within 1%
- [ ] Dashboard at `dashboards/hydration-dashboard.html` opens in browser, polls `https://prod-postgrest/hydration_summary`, renders the kegg_drug row

## Rehearsal data

| Field | Value |
|-------|-------|
| `run_label` | `<FILL>` (truncated to 16 chars) |
| Source | `mol_raw.kegg_drug` |
| Artifact path | `<FILL>` |
| Artifact sha256 | `<FILL>` |
| Artifact size_bytes | `<FILL>` |
| Restore start | `<FILL: ISO-8601>` |
| Restore end | `<FILL: ISO-8601>` |
| Duration (s) | `<FILL>` |
| Rows after restore | `<FILL>` |
| Manifest rows (from inventory) | `<FILL>` |
| Delta from manifest | `<FILL>%` (must be ≤ 1%) |
| WAL `pct_used` peak | `<FILL>%` |
| Any `failed`/`blocked` rows | `<FILL: count + brief>` |

## Anomalies / notes

`<FILL: anything unexpected. Examples: pg_restore took longer than expected; advisory lock contention; partial chunk apply; OTLP emission failure (expected); missed view-safety check etc.>`

## Rollback plan (if a problem is discovered post-sign-off)

1. Stop any running Stage 8 orchestrator: `pkill -f 'prestaged.*--source-list all'`
2. Restore from snapshot:
   ```bash
   pg_restore -Fc --clean --if-exists \
     --schema=meta --schema=mol_raw --schema=mol_bronze --schema=mol_silver \
     --schema=hcs_raw --schema=hcs_bronze --schema=hcs_silver \
     -h <prod-pgbouncer> -U postgres -d dk_data \
     ~/dk-data-prod-snapshots/pre_hydration_<date>.dump
   ```
3. Optionally drop the new columns if they're causing harm:
   ```sql
   ALTER TABLE meta.transform_runs DROP COLUMN status, DROP COLUMN details;
   DROP VIEW IF EXISTS meta.hydration_dashboard, meta.hydration_summary, meta.hydration_wal;
   ```

## Sign-off

I confirm all pre-conditions above are met and the rehearsal data shows
the code path works as designed. Stage 8 (full inventory) is approved.

Signed: `<FILL: name>` at `<FILL: ISO-8601>`.
