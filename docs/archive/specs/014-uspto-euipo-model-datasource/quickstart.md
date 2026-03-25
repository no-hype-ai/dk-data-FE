# Quickstart: USPTO & EUIPO Model Datasource Integration

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16

## Prerequisites

- Python 3.11+ (with venv at `.venv/`)
- PostgreSQL 16.4 accessible (local via docker-compose or remote)
- Doppler CLI configured for `dk-data-fe` project
- Required secrets provisioned in Doppler:
  - `USPTO_TSDR_API_KEY` — register at `https://account.uspto.gov/api-manager/`
  - `EUIPO_API_KEY` — TMview API key or IBM Client ID
  - `EUIPO_SECRET_KEY` — IBM Client Secret (only if using IBM Gateway)

## Local Development Setup

### 1. Activate Environment

```bash
cd /Users/pschloz/Desktop/DataKinetic/dk-data-FE
source .venv/bin/activate
```

### 2. Run Database Migrations

```bash
# Apply new migrations (071-073)
psql -h localhost -p 5433 -U postgres -d dk_data \
  -f src/dk_data/sql/migrations/071_uspto_trademarks_raw.sql
psql -h localhost -p 5433 -U postgres -d dk_data \
  -f src/dk_data/sql/migrations/072_euipo_trademarks_raw.sql
psql -h localhost -p 5433 -U postgres -d dk_data \
  -f src/dk_data/sql/migrations/073_trademark_status_history.sql

# Re-run seed data
psql -h localhost -p 5433 -U postgres -d dk_data \
  -f src/dk_data/sql/seed_data_sources.sql
```

### 3. Run SQLMesh Plan (Bronze Models)

```bash
cd src/dk_data
python -m sqlmesh plan --select-model "bronze.uspto_patents" "bronze.uspto_ci" "bronze.epo_patents" "bronze.uspto_trademarks" "bronze.euipo_trademarks"
```

This will:
- Fix the broken `bronze.uspto_patents` model (JSONB -> flat column)
- Create new bronze models for USPTO CI, EPO, and both trademark sources
- Show the diff and ask for confirmation

### 4. Run SQLMesh Apply

```bash
python -m sqlmesh apply
```

### 5. Verify Bronze Layer

```sql
-- Check record counts
SELECT 'bronze.uspto_patents' AS model, COUNT(*) FROM bronze.uspto_patents
UNION ALL
SELECT 'bronze.uspto_ci', COUNT(*) FROM bronze.uspto_ci
UNION ALL
SELECT 'bronze.epo_patents', COUNT(*) FROM bronze.epo_patents;
```

### 6. Test Fetchers

```bash
# Fetch USPTO trademarks (requires API key)
python -m dk_data.ingestion.fetch_data --source uspto_trademarks

# Fetch EUIPO trademarks (TMview backend by default)
python -m dk_data.ingestion.fetch_data --source euipo_trademarks

# Override EUIPO backend to IBM Gateway
EUIPO_BACKEND=ibm_gateway python -m dk_data.ingestion.fetch_data --source euipo_trademarks
```

## Running Tests

```bash
# All tests
pytest tests/ -v --tb=short

# Only trademark-related tests
pytest tests/test_euipo_trademarks_fetcher.py tests/test_uspto_trademarks_fetcher.py -v

# Contract tests for bronze/silver models
pytest tests/test_bronze_model_contracts.py tests/test_silver_model_contracts.py -v

# Full CI pipeline locally
ruff check . && pytest tests/ -v --tb=short
```

## Verifying Metrics

```bash
# Start the API locally
python -m dk_data.ingestion.main

# Check metrics endpoint
curl http://localhost:8000/metrics | grep -E 'dk_source_health_status|dk_table_record_count' | grep -E 'uspto|epo|euipo'
```

Expected output:
```
dk_source_health_status{source="uspto_patents"} 1
dk_source_health_status{source="uspto_ci"} 1
dk_source_health_status{source="epo_patents"} 1
dk_source_health_status{source="uspto_trademarks"} 1
dk_source_health_status{source="euipo_trademarks"} 1
```

## Validating Kubernetes Manifests

```bash
# Validate staging overlays (includes new CronJobs)
kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null && echo "OK"
```

## Implementation Order

1. **Phase 1**: Fix `bronze.uspto_patents` + create `bronze.uspto_ci`, `bronze.epo_patents` (unblocks silver)
2. **Phase 2**: Extend `silver.patents` to UNION ALL 4 sources
3. **Phase 3**: Migrations (071-073) + Pydantic validators
4. **Phase 4**: USPTO trademark fetcher + loader
5. **Phase 5**: EUIPO trademark fetcher + loader (dual backend)
6. **Phase 6**: Bronze + silver trademark models
7. **Phase 7**: Gold molecule_profile trademark section
8. **Phase 8**: Metrics, seed data, fetcher registration
9. **Phase 9**: K8s CronJobs, tests, CI/CD validation

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/dk_data/sqlmesh/models/molecules/bronze/uspto_patents.sql` | Fix JSONB bug |
| `src/dk_data/sqlmesh/models/molecules/bronze/uspto_ci.sql` | NEW bronze model |
| `src/dk_data/sqlmesh/models/molecules/bronze/epo_patents.sql` | NEW bronze model |
| `src/dk_data/sqlmesh/models/molecules/bronze/uspto_trademarks.sql` | NEW bronze model |
| `src/dk_data/sqlmesh/models/molecules/bronze/euipo_trademarks.sql` | NEW bronze model |
| `src/dk_data/sqlmesh/models/molecules/silver/patents.sql` | MODIFY UNION ALL |
| `src/dk_data/sqlmesh/models/molecules/silver/trademarks.sql` | NEW silver model |
| `src/dk_data/sqlmesh/models/molecules/gold/molecule_profile.sql` | MODIFY IP section |
| `src/dk_data/ingestion/fetchers/uspto_trademarks.py` | NEW fetcher |
| `src/dk_data/ingestion/fetchers/euipo_trademarks.py` | NEW fetcher |
| `src/dk_data/ingestion/sources/uspto_trademarks.py` | NEW loader |
| `src/dk_data/ingestion/sources/euipo_trademarks.py` | NEW loader |
| `src/dk_data/ingestion/utils/validators.py` | MODIFY validators |
| `src/dk_data/ingestion/fetch_data.py` | MODIFY registration |
| `src/dk_data/observability/metrics.py` | MODIFY metrics |
| `src/dk_data/sql/seed_data_sources.sql` | MODIFY seed data |
| `src/dk_data/sql/migrations/071_*.sql` | NEW migration |
| `src/dk_data/sql/migrations/072_*.sql` | NEW migration |
| `src/dk_data/sql/migrations/073_*.sql` | NEW migration |
| `k8s/base/ingestion/cronjob-fetch-uspto-trademarks.yaml` | NEW CronJob |
| `k8s/base/ingestion/cronjob-fetch-euipo.yaml` | NEW CronJob |
| `tests/test_euipo_trademarks_fetcher.py` | NEW tests |
| `tests/test_uspto_trademarks_fetcher.py` | NEW tests |
| `tests/test_bronze_model_contracts.py` | NEW tests |
| `tests/test_silver_model_contracts.py` | NEW tests |
