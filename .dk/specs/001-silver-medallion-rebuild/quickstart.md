# Quickstart — Silver Medallion Rebuild

## Prerequisites

- A running CNPG postgres instance with the existing dk-data bronze schemas populated. For local dev, the easiest path is `kubectl port-forward -n infra svc/postgresql 5432:5432` against the staging cluster.
- Python 3.11+, `uv` for dependency management (already configured in `pyproject.toml`).
- SQLMesh ≥0.90.
- Doppler CLI configured for `dk-data-staging` if running against the staging database.

## 1. Apply the migrations

```bash
cd /Users/pschloz/Desktop/DataKinetic/dk-data-FE
psql "$DATABASE_URL" -f src/dk_data/sql/migrations/031_silver_hub_rebuild/001_meta_job_locks.sql
psql "$DATABASE_URL" -f src/dk_data/sql/migrations/031_silver_hub_rebuild/002_meta_refresh_state.sql
psql "$DATABASE_URL" -f src/dk_data/sql/migrations/031_silver_hub_rebuild/003_meta_linkage_conflicts.sql
# ... apply 004 through 013 (resolve functions)
# ... apply 014 through 023 (bootstrap procedures)
```

Or, using the existing migration runner:

```bash
uv run python -m dk_data.sql.run_migrations 031_silver_hub_rebuild
```

## 2. Run the hub bootstrap (smallest-first)

```bash
psql "$DATABASE_URL_DIRECT" -c "CALL hcs_silver.bootstrap_facilities();"          # ~6K rows, 1 min, 10 MB WAL
psql "$DATABASE_URL_DIRECT" -c "CALL mol_silver.bootstrap_companies();"           # ~10K rows, 2 min
psql "$DATABASE_URL_DIRECT" -c "CALL ind_silver.bootstrap_conditions();"          # ~50K rows, 3 min
psql "$DATABASE_URL_DIRECT" -c "CALL mol_silver.bootstrap_targets();"             # ~500K rows, 5 min
psql "$DATABASE_URL_DIRECT" -c "CALL mol_silver.bootstrap_molecules();"           # ~500K rows, 10 min, ~1 GB WAL
psql "$DATABASE_URL_DIRECT" -c "CALL mol_silver.bootstrap_drug_products();"       # ~300K rows, 5 min
psql "$DATABASE_URL_DIRECT" -c "CALL ip_silver.bootstrap_designs();"             # ~3M rows, 8 min
psql "$DATABASE_URL_DIRECT" -c "CALL ip_silver.bootstrap_patents();"             # ~5M rows, 12 min
psql "$DATABASE_URL_DIRECT" -c "CALL ip_silver.bootstrap_trademarks();"          # ~12M rows, 18 min
psql "$DATABASE_URL_DIRECT" -c "CALL hcs_silver.bootstrap_providers();"           # ~10M rows, 15 min, riskiest
```

Note: bootstraps use `DATABASE_URL_DIRECT` (postgres primary), not `DATABASE_URL` (PgBouncer), because PL/pgSQL procedures need session-level features (FR-024).

Total budget: ≤105 min wall clock, ≤7 GB total WAL (SC-008).

## 3. Verify the bootstrap

```sql
-- Hub row counts
SELECT 'molecules' AS hub, count(*) FROM mol_silver.molecules
UNION ALL SELECT 'drug_products', count(*) FROM mol_silver.drug_products
UNION ALL SELECT 'targets', count(*) FROM mol_silver.targets
UNION ALL SELECT 'conditions', count(*) FROM ind_silver.conditions
UNION ALL SELECT 'companies', count(*) FROM mol_silver.companies
UNION ALL SELECT 'providers', count(*) FROM hcs_silver.providers
UNION ALL SELECT 'facilities', count(*) FROM hcs_silver.facilities
UNION ALL SELECT 'patents', count(*) FROM ip_silver.patents
UNION ALL SELECT 'trademarks', count(*) FROM ip_silver.trademarks
UNION ALL SELECT 'designs', count(*) FROM ip_silver.designs;

-- Resolve function smoke test
SELECT mol_silver.resolve_molecule(p_chembl_id := 'CHEMBL192');     -- expect non-null molecule_id
SELECT mol_silver.resolve_molecule(p_drugbank_id := 'DB00203');     -- expect SAME molecule_id
SELECT mol_silver.resolve_molecule(p_inchi_key := 'BNRNXUUZRGQAQC-UHFFFAOYSA-N');  -- same again
SELECT mol_silver.resolve_drug_product(p_ndc := '0069-4200-30');    -- expect non-null product_id

-- Verify FR-021: no chunk produced more than 2 GB WAL
SELECT procedure_name, max(wal_bytes) AS max_wal_bytes
FROM meta.transform_runs
GROUP BY procedure_name
HAVING max(wal_bytes) > 2 * 1024 * 1024 * 1024;
-- Expect zero rows.

-- Verify SC-007: no incomplete bootstrap state
SELECT procedure_name, status FROM meta.refresh_state WHERE status != 'completed';
-- Expect zero rows.

-- Verify FR-026a: no unresolved linkage conflicts
SELECT count(*) FROM meta.linkage_conflicts;
-- Expect zero (or a small number that have been triaged).
```

## 4. Run the contract tests

```bash
uv run pytest tests/test_silver_column_retention.py -v        # FR-005 — every non-system bronze column carried forward
uv run pytest tests/test_silver_antipatterns.py -v            # FR-020 — no S1–S5 antipatterns in any silver model
uv run pytest tests/test_resolve_molecule.py -v               # one per resolve function
uv run pytest tests/test_resolve_drug_product.py -v
uv run pytest tests/test_build_dsn.py -v                      # FR-030 — single connection helper enforced
uv run pytest tests/test_meta_job_locks.py -v                 # FR-025 — TTL lock concurrency
```

## 5. Verify a single rewritten silver model

Pick the first rewrite target — `mol_silver.bioactivity` (worst antipattern S3, largest blast radius):

```bash
sqlmesh run mol_silver.bioactivity --start 2026-04-10 --end 2026-04-11
```

Then compare row counts and a sample of rows against the legacy model:

```sql
-- Row count delta
SELECT (SELECT count(*) FROM mol_silver.bioactivity_legacy) AS legacy_rows,
       (SELECT count(*) FROM mol_silver.bioactivity) AS new_rows,
       ((SELECT count(*) FROM mol_silver.bioactivity)::numeric /
        (SELECT count(*) FROM mol_silver.bioactivity_legacy)::numeric - 1) * 100 AS pct_delta;

-- 1% sample comparison
WITH sample AS (
    SELECT activity_id FROM mol_silver.bioactivity TABLESAMPLE BERNOULLI (1)
)
SELECT b.activity_id,
       b.molecule_id IS NOT NULL AS new_has_mol,
       l.molecule_id IS NOT NULL AS legacy_has_mol
FROM sample s
JOIN mol_silver.bioactivity b USING (activity_id)
LEFT JOIN mol_silver.bioactivity_legacy l USING (activity_id)
WHERE (b.molecule_id IS NULL) != (l.molecule_id IS NULL);
```

Document any row-count delta > 1% in the PR description before merging.

## 6. Local dev workflow

For development against a fresh local CNPG cluster:

```bash
# 1. Spin up CNPG with the same config as production (uses the dk-alchemy postgres manifests)
kubectl apply -k k8s/local/postgres-dev/

# 2. Restore a recent staging dump (bronze layer only — silver and gold rebuild from scratch)
pg_restore --no-owner --no-acl -d "$DATABASE_URL_LOCAL" /path/to/staging-bronze-dump.sql

# 3. Run migrations + bootstrap
make sqlmesh-bootstrap-silver-hubs

# 4. Run tests
uv run pytest tests/ -k silver_hub -v
```

## IP Domain Migration Verification

After applying migrations 050–054 and running SQLMesh, verify the ip_* domain end-to-end:

### 1. Confirm schemas exist

```sql
SELECT schema_name FROM information_schema.schemata
WHERE schema_name LIKE 'ip_%'
ORDER BY schema_name;
-- Expect: ip_raw, ip_bronze, ip_silver, ip_gold
```

### 2. Verify bronze table row counts match mol_bronze sources

```sql
SELECT
  'ip_bronze.uspto_patents'   AS table_name, COUNT(*) FROM ip_bronze.uspto_patents
UNION ALL SELECT 'mol_bronze.uspto_patents',   COUNT(*) FROM mol_bronze.uspto_patents
UNION ALL SELECT 'ip_bronze.uspto_ci',          COUNT(*) FROM ip_bronze.uspto_ci
UNION ALL SELECT 'mol_bronze.uspto_ci',          COUNT(*) FROM mol_bronze.uspto_ci
UNION ALL SELECT 'ip_bronze.uspto_trademarks',  COUNT(*) FROM ip_bronze.uspto_trademarks
UNION ALL SELECT 'mol_bronze.uspto_trademarks', COUNT(*) FROM mol_bronze.uspto_trademarks
UNION ALL SELECT 'ip_bronze.epo_patents',       COUNT(*) FROM ip_bronze.epo_patents
UNION ALL SELECT 'mol_bronze.epo_patents',      COUNT(*) FROM mol_bronze.epo_patents
UNION ALL SELECT 'ip_bronze.euipo_trademarks',  COUNT(*) FROM ip_bronze.euipo_trademarks
UNION ALL SELECT 'mol_bronze.euipo_trademarks', COUNT(*) FROM mol_bronze.euipo_trademarks
UNION ALL SELECT 'ip_bronze.euipo_designs',     COUNT(*) FROM ip_bronze.euipo_designs
UNION ALL SELECT 'mol_bronze.euipo_designs',    COUNT(*) FROM mol_bronze.euipo_designs
UNION ALL SELECT 'ip_bronze.trademark_status_history', COUNT(*) FROM ip_bronze.trademark_status_history
UNION ALL SELECT 'mol_bronze.trademark_status_history', COUNT(*) FROM mol_bronze.trademark_status_history;
-- Row counts in ip_bronze should be >= mol_bronze counts (>=99.9%).
```

### 3. Verify silver table row counts match mol_silver sources

```sql
SELECT 'ip_silver.patents'                   AS table_name, COUNT(*) FROM ip_silver.patents
UNION ALL SELECT 'mol_silver.patents',         COUNT(*) FROM mol_silver.patents
UNION ALL SELECT 'ip_silver.trademarks',       COUNT(*) FROM ip_silver.trademarks
UNION ALL SELECT 'mol_silver.trademarks',      COUNT(*) FROM mol_silver.trademarks
UNION ALL SELECT 'ip_silver.patent_exclusivities', COUNT(*) FROM ip_silver.patent_exclusivities
UNION ALL SELECT 'mol_silver.patent_exclusivities', COUNT(*) FROM mol_silver.patent_exclusivities
UNION ALL SELECT 'ip_silver.trademark_status_changes', COUNT(*) FROM ip_silver.trademark_status_changes
UNION ALL SELECT 'mol_silver.trademark_status_changes', COUNT(*) FROM mol_silver.trademark_status_changes
UNION ALL SELECT 'ip_silver.designs',          COUNT(*) FROM ip_silver.designs
UNION ALL SELECT 'mol_silver.euipo_designs',   COUNT(*) FROM mol_silver.euipo_designs;
```

### 4. Verify migration state is completed

```sql
SELECT procedure_name, status, last_chunk_position, last_commit_at
FROM meta.refresh_state
WHERE procedure_name LIKE 'migrate_%'
ORDER BY procedure_name;
-- Expect: status = 'completed' for all migrate_* procedures.
```

### 5. Verify SQLMesh models resolve correctly

```bash
sqlmesh run ip_bronze.uspto_patents --start 2026-04-01 --end 2026-04-11
sqlmesh run ip_bronze.epo_patents --start 2026-04-01 --end 2026-04-11
sqlmesh run ip_silver.patents --start 2026-04-01 --end 2026-04-11
sqlmesh run ip_silver.trademarks --start 2026-04-01 --end 2026-04-11
sqlmesh run ip_silver.designs --start 2026-04-01 --end 2026-04-11
```

### 6. Verify PostgREST role grants

```sql
SET ROLE analyst;
SELECT COUNT(*) FROM ip_silver.patents;
SELECT COUNT(*) FROM ip_silver.trademarks;
SELECT COUNT(*) FROM ip_silver.designs;
RESET ROLE;
```

### 7. Verify gold model references updated

```sql
-- lifecycle_stages uses ip_silver.patents
SELECT COUNT(*) FROM ip_silver.patents WHERE molecule_id IS NOT NULL;
-- molecule_profile uses ip_silver.trademarks
SELECT COUNT(*) FROM ip_silver.trademarks WHERE molecule_id IS NOT NULL;
-- lifecycle_evidence uses ip_silver.patent_exclusivities
SELECT COUNT(*) FROM ip_silver.patent_exclusivities WHERE molecule_id IS NOT NULL;
```

### 8. Cleanup — ONLY after full verification

```sql
DROP TABLE IF EXISTS mol_bronze.uspto_patents;
DROP TABLE IF EXISTS mol_bronze.uspto_ci;
DROP TABLE IF EXISTS mol_bronze.uspto_trademarks;
DROP TABLE IF EXISTS mol_bronze.epo_patents;
DROP TABLE IF EXISTS mol_bronze.euipo_trademarks;
DROP TABLE IF EXISTS mol_bronze.euipo_designs;
DROP TABLE IF EXISTS mol_bronze.trademark_status_history;
DROP TABLE IF EXISTS mol_silver.patents;
DROP TABLE IF EXISTS mol_silver.trademarks;
DROP TABLE IF EXISTS mol_silver.patent_exclusivities;
DROP TABLE IF EXISTS mol_silver.trademark_status_changes;
DROP TABLE IF EXISTS mol_silver.euipo_designs;
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Bootstrap procedure crashes mid-run | OOM or active deadline | Restart it — `meta.refresh_state` will resume from the last chunk (FR-026) |
| `meta.linkage_conflicts` is non-empty | Two source datasets disagree on a `(source, identifier) → hub_id` mapping | Triage manually; update the source priority in the relevant `resolve_*()` function or fix the source data |
| `meta.job_locks` row stuck for hours | Pod crashed without cleanup | Wait for `expires_at` to elapse, or `DELETE FROM meta.job_locks WHERE name = '...'` if you're sure no one holds it |
| Contract test fails with "missing column X in silver model Y" | Bronze column added but silver model not updated | Add the column to the silver model's SELECT (FR-001) |
| Antipattern grep test fails | New silver code uses a banned pattern | Rewrite to use `resolve_*()` or an indexed crosswalk join |
| `pg_stat_activity` shows BLAI queries waiting on locks | Bootstrap is too aggressive | Increase the `pg_sleep` interval in the offending procedure (FR-028) |
