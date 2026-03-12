# Quickstart: CMS PUF Data Source Integration

**Branch**: `016-cms-puf-datasource-integration`
**Revised**: 2026-03-11

---

## 1. Prerequisites

- Docker + Docker Compose running
- Python 3.11+ with `uv` package manager
- PostgreSQL client (`psql`)
- Doppler CLI configured for `dk-data-fe` project

---

## 2. Environment Setup

### 2.1 Start Local Stack

```bash
make up
# Starts: postgres (5433), postgrest (3030), job-trigger (8000)
```

### 2.2 Apply Migrations

```bash
# Apply all migrations including new CMS migrations (083-088)
make init-db

# Verify CMS tables created
psql -h localhost -p 5433 -U dk_data -d dk_data -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='raw' AND table_name LIKE 'cms_%';"
# Expected: 30
```

### 2.3 LiteLLM Configuration

Agents require LiteLLM access. For local development:

```bash
# Set via Doppler (recommended)
doppler secrets set LITELLM_BASE_URL "http://litellm.infra.svc.cluster.local:8000"
doppler secrets set LITELLM_API_KEY "your-litellm-virtual-key"

# Or export directly for local testing
export LITELLM_BASE_URL="http://localhost:4000"  # Local LiteLLM instance
export LITELLM_API_KEY="sk-..."
```

---

## 3. Ingestion

### 3.1 Fetch a Single Source

```bash
# Fetch NPPES bulk CSV
python -m dk_data.ingestion.fetch_data cms_nppes

# Fetch Part D Prescriber data
python -m dk_data.ingestion.fetch_data cms_part_d_prescriber
```

### 3.2 Ingest Fetched Data

```bash
# Ingest NPPES into raw.cms_nppes
python -m dk_data.ingestion.main cms_nppes

# Ingest all CMS sources
python -m dk_data.ingestion.main cms_all
```

### 3.3 Verify Ingestion

```bash
psql -h localhost -p 5433 -U dk_data -d dk_data -c \
  "SELECT table_name, n_live_tup FROM pg_stat_user_tables WHERE schemaname='raw' AND tablename LIKE 'cms_%' ORDER BY n_live_tup DESC;"
```

---

## 4. SQLMesh Transformations

### 4.1 Run Pipeline

```bash
cd src/dk_data/sqlmesh

# Plan changes (dry run)
sqlmesh plan

# Apply transformations
sqlmesh plan --auto-apply

# Run specific model
sqlmesh run bronze.cms_nppes
```

### 4.2 Verify Bronze/Silver/Gold

```bash
# Check bronze
psql -c "SELECT count(*) FROM bronze.cms_nppes;"

# Check silver
psql -c "SELECT count(*) FROM silver.cms_provider_profile;"

# Check gold (materialized view)
psql -c "SELECT count(*) FROM gold.cms_provider_360;"
```

---

## 5. Agent Pipeline

### 5.1 Run an Agent Locally

```bash
# Run ServiceLineInference agent
python -m dk_data.agents.service_line_inference

# Run all agents
python -m dk_data.agents --all
```

### 5.2 Check Execution Log

```bash
psql -c "SELECT agent_name, status, records_enriched, records_quarantined, cost_usd FROM meta.agent_execution_log ORDER BY started_at DESC LIMIT 10;"
```

### 5.3 Review Quarantine

```bash
psql -c "SELECT agent_name, reason, confidence_score, status FROM meta.agent_quarantine WHERE status='PENDING' LIMIT 20;"
```

---

## 6. PostgREST API

### 6.1 Query Gold Views

```bash
# Provider by NPI
curl -s "http://localhost:3030/gold.cms_provider_360?npi=eq.1234567890" | jq '.'

# Facility by CCN
curl -s "http://localhost:3030/gold.cms_facility_360?ccn=eq.050001" | jq '.'

# Drug market by NDC
curl -s "http://localhost:3030/gold.cms_drug_market_profile?ndc=eq.00002-7510-01" | jq '.'

# Market analytics by state
curl -s "http://localhost:3030/gold.cms_market_analytics?state=eq.CA" | jq '.'

# Provider network edges
curl -s "http://localhost:3030/gold.cms_provider_network?source_npi=eq.1234567890" | jq '.'
```

### 6.2 Authenticated Queries

```bash
# As analyst role
curl -s -H "Authorization: Bearer $(python -c 'import jwt; print(jwt.encode({"role":"analyst"}, "your-jwt-secret", algorithm="HS256"))')" \
  "http://localhost:3030/gold.cms_provider_360?limit=5" | jq '.'
```

---

## 7. Kubernetes Validation

### 7.1 Verify CronJobs

```bash
# List CMS CronJobs
kubectl get cronjobs -n dk-data-prod | grep cms

# Check recent job runs
kubectl get jobs -n dk-data-prod | grep cms | tail -10
```

### 7.2 Verify Agent Jobs

```bash
# Trigger agent manually
curl -X POST http://localhost:8000/agents/service_line_inference/run

# Check job status
kubectl get jobs -n dk-data-prod | grep agent
```

---

## 8. Testing

```bash
# Run all CMS tests
pytest tests/test_cms_*.py -v

# Run agent tests
pytest tests/test_agents/ -v

# Run integration tests
pytest tests/test_cms_*integration*.py -v
```

---

## 9. Key Files

| Purpose | Path |
|---------|------|
| Fetcher base | `src/dk_data/ingestion/fetchers/base.py` |
| CMS fetchers | `src/dk_data/ingestion/fetchers/cms_*.py` |
| CMS loaders | `src/dk_data/ingestion/sources/cms_*.py` |
| Source registry | `src/dk_data/ingestion/main.py` |
| SQLMesh config | `src/dk_data/sqlmesh/config.yaml` |
| CMS bronze models | `src/dk_data/sqlmesh/models/cms/bronze/*.sql` |
| CMS silver models | `src/dk_data/sqlmesh/models/cms/silver/*.sql` |
| CMS gold models | `src/dk_data/sqlmesh/models/cms/gold/*.sql` |
| Agent base | `src/dk_data/agents/base_agent.py` |
| Agent implementations | `src/dk_data/agents/*.py` |
| Migrations | `src/dk_data/sql/migrations/083-088_*.sql` |
| CronJobs | `k8s/base/ingestion/cronjob-fetch-cms-*.yaml` |
| Tests | `tests/test_cms_*.py`, `tests/test_agents/*.py` |

---

## 10. Common Issues

| Issue | Fix |
|-------|-----|
| `LITELLM_BASE_URL` not set | Add to Doppler or export locally |
| PostgREST returns empty for gold views | Verify `gold` in `PGRST_DB_SCHEMAS` configmap |
| NPPES fetch OOM | Ensure streaming mode in fetcher (default) |
| Agent confidence all < 0.5 | Check LiteLLM model alias resolves correctly |
| Migration fails on existing table | Migrations are CREATE IF NOT EXISTS — safe to re-run |
