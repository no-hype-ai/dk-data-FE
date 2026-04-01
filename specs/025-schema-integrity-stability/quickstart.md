# Quickstart: Schema Integrity & Platform Stability

**Branch**: `025-schema-integrity-stability` | **Date**: 2026-04-01

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (for local DB)
- kubectl + kubeconfig (for cluster verification)
- Doppler CLI (for secrets)

## Local Development

### 1. Start local environment

```bash
doppler run --config dev -- docker compose up -d
```

### 2. Apply migration 138

```bash
doppler run --config dev -- docker compose exec -T postgres psql -U postgres -d dk_data \
  -f /migrations/138_schema_integrity.sql
```

### 3. Verify refresh_log columns

```bash
doppler run --config dev -- docker compose exec -T postgres psql -U postgres -d dk_data -c \
  "SELECT column_name FROM information_schema.columns WHERE table_schema='meta' AND table_name='refresh_log' ORDER BY ordinal_position;"
```

Expected: `refresh_started_at` and `refresh_completed_at` present.

### 4. Test affected sources

```bash
# Test pubchem (was failing with missing UNIQUE constraint)
doppler run --config dev -- docker compose run --rm --no-deps --entrypoint "" job-trigger \
  python -m dk_data.ingestion.main pubchem --max-records 100

# Test chembl_molecules
doppler run --config dev -- docker compose run --rm --no-deps --entrypoint "" job-trigger \
  python -m dk_data.ingestion.main chembl_molecules --max-records 100

# Test who_gho
doppler run --config dev -- docker compose run --rm --no-deps --entrypoint "" job-trigger \
  python -m dk_data.ingestion.main who_gho --max-records 100
```

Verify `records_inserted > 0` in output.

### 5. Verify refresh_log entries

```bash
doppler run --config dev -- docker compose exec -T postgres psql -U postgres -d dk_data -c \
  "SELECT source_name, refresh_started_at, refresh_completed_at, status, records_inserted FROM meta.refresh_log ORDER BY log_id DESC LIMIT 5;"
```

### 6. Test MCP adapters

```bash
# Test a fixable adapter
curl -s -X POST http://localhost:8000/api/v1/data-tools/fda-drugs-search/invoke \
  -H "Content-Type: application/json" -d '{"drug_name": "imatinib"}' | python -m json.tool

# Test a bulk-only adapter (should return structured message, not 500)
curl -s -X POST http://localhost:8000/api/v1/data-tools/ema-search/invoke \
  -H "Content-Type: application/json" -d '{"drug_name": "imatinib"}' | python -m json.tool
```

## Cluster Verification

### Staging

```bash
# Apply migration
kubectl exec -n dk-data-staging deploy/job-trigger -- psql "$DATABASE_URL" -f /app/sql/migrations/138_schema_integrity.sql

# Verify CronJob memory limits
kubectl get cronjob fetch-sider -n dk-data-staging -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].resources.limits.memory}'
# Expected: 1Gi

# Trigger a test job
kubectl create job --from=cronjob/fetch-pubchem fetch-pubchem-test -n dk-data-staging
kubectl logs -f job/fetch-pubchem-test -n dk-data-staging
```

## Running Tests

```bash
cd src && pytest tests/test_mcp_data_tools.py -v
cd src && pytest tests/ -k "pubchem or chembl or who_gho" -v
```
