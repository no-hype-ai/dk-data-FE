# Quickstart: CMS PUF & Platform Data Reconciliation

**Feature**: `019-cms-puf-platform-reconciliation`
**Branch**: `019-cms-puf-platform-reconciliation`

---

## Prerequisites

- Python 3.11+, `uv` for dependency management
- PostgreSQL accessible (via `docker compose up db` or SSH tunnel to staging)
- Doppler CLI configured: `doppler setup --project dk-infrastructure --config prd`
- `kubectl` context set to target cluster

---

## Local Development Setup

```bash
# 1. Switch to feature branch
cd /Users/pschloz/Desktop/DataKinetic/dk-data-FE
git checkout 019-cms-puf-platform-reconciliation

# 2. Install dependencies
uv sync

# 3. Start local database
docker compose up db -d

# 4. Apply migration
doppler run -- python -m dk_data.scripts.run_migration src/dk_data/sql/migrations/085_cms_puf_platform_reconciliation.sql

# 5. Verify meta tables
doppler run -- psql $DATABASE_URL -c "SELECT source_name, source_type FROM meta.data_sources ORDER BY source_name;"
```

---

## Running Tests

```bash
# All tests (must pass before PR)
doppler run -- pytest tests/ -v

# Specific new test files
doppler run -- pytest tests/test_cms_part_d_fetcher.py -v
doppler run -- pytest tests/test_publication_evidence_agent.py -v
doppler run -- pytest tests/test_data_tools_gateway.py -v

# Coverage check
doppler run -- pytest --cov=src/dk_data --cov-report=term-missing tests/
```

---

## Running a CMS PUF Ingestion Locally

CMS PUF files must be downloaded manually for local testing (bulk annual releases):

```bash
# 1. Download a CMS Part D file (example — real URL from data.cms.gov)
curl -L "https://data.cms.gov/.../PartD_Spending_Drug_2023.csv" -o /tmp/PartD_2023.csv

# 2. Run the loader
doppler run -- python -m dk_data.ingestion.main --source cms_part_d_spending --file /tmp/PartD_2023.csv

# 3. Verify ingestion
doppler run -- psql $DATABASE_URL -c "SELECT COUNT(*) FROM hcs_raw.cms_part_d_spending;"
doppler run -- psql $DATABASE_URL -c "SELECT source_name, last_successful_refresh, last_refresh_status FROM meta.data_sources WHERE source_name = 'cms_part_d_spending';"
```

---

## Running an API Source Locally

```bash
# EuropePMC (API-based, incremental)
doppler run -- python -m dk_data.ingestion.main --source europepmc

# NIH Reporter
doppler run -- python -m dk_data.ingestion.main --source nih_reporter

# Check refresh log
doppler run -- psql $DATABASE_URL -c "SELECT source_name, status, records_inserted FROM meta.refresh_log ORDER BY refresh_started_at DESC LIMIT 10;"
```

---

## Running an Agent Locally

```bash
# Publication evidence extraction (requires LiteLLM proxy)
doppler run -- python -m dk_data.agents.publication_evidence_extractor --limit 100

# Check output
doppler run -- psql $DATABASE_URL -c "SELECT COUNT(*), AVG(confidence_score) FROM mol_silver.publication_evidence;"
doppler run -- psql $DATABASE_URL -c "SELECT COUNT(*) FROM mol_silver.agent_quarantine WHERE agent_name = 'publication_evidence_extractor';"
```

---

## Testing the Data Tools Gateway API

```bash
# Start the API server
doppler run -- uvicorn dk_data.api.main:app --reload --port 8000

# List all registered tools
curl http://localhost:8000/api/v1/data-tools/registry | jq '.total'

# Trigger a backfill
curl -X POST http://localhost:8000/api/v1/data-tools/backfill \
  -H "Content-Type: application/json" \
  -d '{"source_name": "cms_part_d_spending", "force": false}'

# List agents
curl http://localhost:8000/api/v1/agents | jq '.agents[].agent_id'
```

---

## Verifying trial_outcomes Migration

```bash
# Confirm xenon is no longer referenced
doppler run -- psql $DATABASE_URL -c "SELECT * FROM mol_gold.trial_outcomes WHERE evidence_source = 'publication' LIMIT 5;"

# Should return rows sourced from mol_silver.publication_evidence, not xenon
doppler run -- psql $DATABASE_URL -c "\d+ mol_silver.publication_evidence"
```

---

## Running SQLMesh Transformations

```bash
# Run all models (local dev)
doppler run -- sqlmesh run

# Run only HCS models
doppler run -- sqlmesh run --model "hcs_bronze.*" --model "hcs_silver.*" --model "hcs_gold.*"

# Run mol_gold.trial_outcomes
doppler run -- sqlmesh run --model "mol_gold.trial_outcomes"
```

---

## K8s Deployment (staging)

ArgoCD auto-syncs from the feature branch if configured, or trigger manually:

```bash
# Apply new CronJob manifests
kubectl apply -k k8s/apps/cronjobs/base/

# Verify CronJobs created
kubectl get cronjobs -n dk-data | grep cms

# Trigger a manual test job
kubectl create job --from=cronjob/fetch-cms-part-d test-cms-part-d -n dk-data
kubectl logs job/test-cms-part-d -n dk-data -f
```

---

## Key File Locations

| What | Where |
|---|---|
| SOURCES registry | `src/dk_data/ingestion/main.py` |
| BaseFetcher | `src/dk_data/ingestion/fetchers/base.py` |
| CMS PUF fetchers | `src/dk_data/ingestion/fetchers/cms_*.py` |
| CMS PUF loaders | `src/dk_data/ingestion/sources/cms_*.py` |
| Agents | `src/dk_data/agents/` |
| Data tools router | `src/dk_data/api/routes/data_tools.py` |
| Agents router | `src/dk_data/api/routes/agents.py` |
| SQLMesh HCS models | `src/dk_data/sqlmesh/models/hcs/` |
| SQLMesh mol additions | `src/dk_data/sqlmesh/models/molecules/` |
| Consolidated migration | `src/dk_data/sql/migrations/085_cms_puf_platform_reconciliation.sql` |
| CronJob manifests | `k8s/apps/cronjobs/base/` |
| Grafana alert | `monitoring/provisioning/alerts/pipeline-source-failures.yaml` |
