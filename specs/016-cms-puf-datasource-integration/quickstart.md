# Quickstart: CMS PUF Datasource Integration

**Branch**: `016-cms-puf-datasource-integration`
**Date**: 2026-03-01

## Prerequisites

- Python 3.11+ (with venv at `.venv/`)
- PostgreSQL 16.4 accessible (local via docker-compose or port-forward to CloudNativePG cluster)
- PostgREST v12.2.3 running locally
- `uv` package manager installed
- Repository cloned and on `016-cms-puf-datasource-integration` branch
- Doppler CLI configured for `dk-data-fe` project
- Optional API keys provisioned in Doppler (see [External API Key Registration](#external-api-key-registration))

## Local Development Setup

### 1. Activate environment

```bash
cd /Users/pschloz/Desktop/DataKinetic/dk-data-FE
uv sync
source .venv/bin/activate
```

### 2. Run database migrations

```bash
# Foundation: silver/gold entity tables + agent audit infrastructure
psql $DATABASE_URL -f src/dk_data/sql/migrations/083_cms_puf_foundation.sql

# Provider & Claims raw/bronze tables (7 sources, year-partitioned)
psql $DATABASE_URL -f src/dk_data/sql/migrations/084_provider_raw_bronze_tables.sql

# Facility & Hospital raw/bronze tables (10 sources)
psql $DATABASE_URL -f src/dk_data/sql/migrations/085_facility_raw_bronze_tables.sql

# Drug & Market raw/bronze tables (9 sources)
psql $DATABASE_URL -f src/dk_data/sql/migrations/086_drug_market_raw_bronze_tables.sql

# Population & Clinical raw/bronze tables (9 sources)
psql $DATABASE_URL -f src/dk_data/sql/migrations/087_population_clinical_raw_bronze_tables.sql

# Seed ~30 new data source catalog entries
psql $DATABASE_URL -f src/dk_data/sql/seed_data_sources.sql
```

### 3. Update PostgREST config

```bash
# Add gold schema for provider/facility/market profiles
export PGRST_DB_SCHEMAS="api,mol_api,mol_gold,mol_silver,xenon,meta,gold"

# Or update local postgrest.conf:
# db-schemas = "api,mol_api,mol_gold,mol_silver,xenon,meta,gold"
```

### 4. Start services

```bash
# Terminal 1: FastAPI job-trigger (includes MCP endpoint)
cd src/dk_data/ingestion/batch
uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: PostgREST
postgrest postgrest.conf
```

### 5. Verify setup

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Retrieve pre-signed API key from Doppler:
#   Project: behaviorlabs-applications, Config: stg
#   Variable: DK_DATA_API_KEY
export DK_DATA_API_KEY="<your-pre-signed-api-key-from-doppler>"

# Verify MCP tool count (should be ~68 after registration)
python -c "from dk_data.services.mcp.tool_registry import TOOL_REGISTRY; print(f'Tools: {len(TOOL_REGISTRY)}')"

# Verify gold schema accessible via PostgREST
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  http://localhost:3000/gold/provider_profile?limit=1
```

> **Note:** Do NOT generate JWTs locally with `jwt.encode`. The API key is a
> pre-signed JWT stored in Doppler. The `gold` schema requires `analyst` role;
> `web_anon` has NO access to gold tables.

## Run Ingestion

### Batch data loaders (CLI)

```bash
# Provider sources
python -m dk_data.ingestion.main cms_nppes
python -m dk_data.ingestion.main cms_part_d_prescribers
python -m dk_data.ingestion.main cms_physician_puf
python -m dk_data.ingestion.main cms_open_payments
python -m dk_data.ingestion.main cms_care_compare

# Facility sources
python -m dk_data.ingestion.main cms_provider_of_services
python -m dk_data.ingestion.main cms_hospital_quality

# Drug & Market sources
python -m dk_data.ingestion.main fda_ndc
python -m dk_data.ingestion.main cms_part_d_spending

# Population sources
python -m dk_data.ingestion.main cms_geographic_variation
```

### MCP tool invocation (API)

```bash
# NPI lookup via MCP
curl -X POST http://localhost:8000/api/v1/mcp/tools/cms-nppes-search/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DK_DATA_API_KEY" \
  -d '{"npi": "1234567890"}'

# Part D prescriber lookup via MCP
curl -X POST http://localhost:8000/api/v1/mcp/tools/cms-partd-prescribers-search/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DK_DATA_API_KEY" \
  -d '{"npi": "1234567890", "year": 2023}'

# Hospital quality lookup via MCP
curl -X POST http://localhost:8000/api/v1/mcp/tools/cms-hospital-quality-search/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DK_DATA_API_KEY" \
  -d '{"facility_id": "050454"}'
```

## Run SQLMesh Transformations

```bash
cd src

# Preview what will be created/updated
python -m sqlmesh plan --no-prompts

# Apply bronze → silver → gold pipeline
python -m sqlmesh apply
```

### Verify transformations

```sql
-- Check bronze record counts
SELECT 'bronze.cms_nppes' AS model, COUNT(*) FROM bronze.cms_nppes
UNION ALL
SELECT 'bronze.cms_part_d_prescribers', COUNT(*) FROM bronze.cms_part_d_prescribers
UNION ALL
SELECT 'bronze.fda_ndc', COUNT(*) FROM bronze.fda_ndc;

-- Check silver entity counts
SELECT 'silver.providers' AS model, COUNT(*) FROM silver.providers
UNION ALL
SELECT 'silver.prescribing_profiles', COUNT(*) FROM silver.prescribing_profiles
UNION ALL
SELECT 'silver.drug_market', COUNT(*) FROM silver.drug_market;

-- Check gold profiles
SELECT COUNT(*) AS provider_profiles FROM gold.provider_profile;
SELECT COUNT(*) AS facility_profiles FROM gold.facility_profile;
```

## Run Agent Pipeline

```bash
# Dry-run to verify agent configuration
python -m dk_data.claude_sdk.runner --agent service_line_inference --dry-run

# Run a specific agent
python -m dk_data.claude_sdk.runner --agent service_line_inference --batch-size 100

# Verify agent registry
python -c "from dk_data.claude_sdk.agent_registry import AGENT_REGISTRY; print(f'Agents: {len(AGENT_REGISTRY)}')"
# Expected: 5
```

## Development Workflow

### Adding a new CMS/FDA MCP tool adapter

1. Create adapter: `src/dk_data/services/mcp/adapters/{source}.py`
2. Implement `normalize(api_response) -> dict` and `build_url(base_url, primary_query, params) -> str`
3. Register `ToolDefinition` in `src/dk_data/services/mcp/tool_registry.py` (Tier 4-6)
4. Add bronze transformer handler in `src/dk_data/services/mcp/bronze_transformer.py`
5. Add silver/gold refresh logic in `src/dk_data/services/mcp/silver_gold_refresher.py`
6. Add adapter unit test with `@responses.activate` mocking

### Adding a new batch data loader

1. Create fetcher: `src/dk_data/ingestion/fetchers/{source}.py`
   - For CMS Socrata sources, extend `CMSSocrataFetcher` base class
2. Create loader: `src/dk_data/ingestion/sources/{source}.py`
3. Register in `SOURCES` dict in `src/dk_data/ingestion/main.py`
4. Add rate limit entry in `src/dk_data/config/rate_limits.yaml`
5. Add catalog entry in `src/dk_data/sql/seed_data_sources.sql`
6. Create CronJob YAML: `k8s/base/ingestion/cronjob-fetch-{source}.yaml`

### Adding a new bronze SQLMesh model

1. Create SQL file: `src/dk_data/sqlmesh/models/molecules/bronze/{source}.sql`
2. Follow existing pattern (see `chembl_molecules.sql` or `clinicaltrials.sql`)
3. Use `INCREMENTAL_BY_TIME_RANGE` with `time_column request_timestamp`
4. Add `audits (not_null(columns := (...)))` for required columns
5. Validate: `cd src && python -m sqlmesh plan --no-prompts`

### Adding a new agent

1. Create agent: `src/dk_data/claude_sdk/agents/{agent_name}.py`
2. Extend `BaseAgent` with `SYSTEM_PROMPT`, `AGENT_NAME`, `_build_prompt()`, `_parse_response()`
3. Register `AgentDefinition` in `src/dk_data/claude_sdk/agent_registry.py`
4. Create CronJob YAML: `k8s/base/ingestion/cronjob-agent-{name}.yaml`
5. Add test: `tests/test_agents/test_{agent_name}.py`

## Running Tests

```bash
# All tests
pytest tests/ -v --tb=short

# CMS PUF specific tests
pytest tests/test_cms_puf_*.py -v

# Agent tests
pytest tests/test_agents/ -v

# Bronze model contract tests
pytest tests/test_bronze_model_contracts.py -v

# SQLMesh model validation
cd src && python -m sqlmesh plan --no-prompts

# Lint
ruff check .

# Full CI pipeline locally
ruff check . && pytest tests/ -v --tb=short
```

## Validating Kubernetes Manifests

```bash
# Validate staging overlays (includes ~17 new CronJobs)
kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null && echo "OK"
```

## Verifying Metrics

```bash
# Check provider/facility metrics
curl http://localhost:8000/api/v1/monitoring/metrics | grep -E 'dk_providers_total|dk_facilities_total|dk_agent_'

# Check data source health
curl http://localhost:8000/api/v1/monitoring/metrics | grep dk_source_health_status | grep -E 'cms_|fda_'
```

Expected output:
```
dk_source_health_status{source="cms_nppes"} 1
dk_source_health_status{source="cms_part_d_prescribers"} 1
dk_source_health_status{source="cms_hospital_quality"} 1
dk_source_health_status{source="fda_ndc"} 1
dk_providers_total 0
dk_facilities_total 0
```

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/dk_data/services/mcp/base_tool.py` | MODIFY — generic param handling (npi, ccn, not just drug_name) |
| `src/dk_data/services/mcp/tool_registry.py` | MODIFY — +30 ToolDefinitions in Tiers 4-6 |
| `src/dk_data/services/mcp/bronze_transformer.py` | MODIFY — +25 handler methods |
| `src/dk_data/services/mcp/silver_gold_refresher.py` | MODIFY — refresh_provider(), refresh_facility() |
| `src/dk_data/services/mcp/adapters/base.py` | MODIFY — build_url() backward-compat update |
| `src/dk_data/services/mcp/adapters/nppes.py` | NEW — NPPES NPI registry adapter |
| `src/dk_data/services/mcp/adapters/cms_partd_prescribers.py` | NEW — Part D prescriber adapter |
| `src/dk_data/services/mcp/adapters/cms_open_payments.py` | NEW — Open Payments adapter |
| `src/dk_data/services/mcp/adapters/cms_hospital_quality.py` | NEW — Hospital quality adapter |
| `src/dk_data/services/mcp/adapters/fda_ndc.py` | NEW — FDA NDC adapter |
| `src/dk_data/ingestion/fetchers/cms_socrata_base.py` | NEW — shared Socrata fetcher base |
| `src/dk_data/ingestion/fetchers/nppes.py` | NEW — NPPES bulk + REST fetcher |
| `src/dk_data/ingestion/fetchers/cms_partd_prescribers.py` | NEW — Part D fetcher |
| `src/dk_data/ingestion/sources/nppes.py` | NEW — NPPES loader |
| `src/dk_data/ingestion/sources/cms_partd_prescribers.py` | NEW — Part D loader |
| `src/dk_data/ingestion/main.py` | MODIFY — +25 SOURCES entries |
| `src/dk_data/sqlmesh/models/molecules/bronze/*.sql` | NEW — ~25 bronze models |
| `src/dk_data/sqlmesh/models/molecules/silver/providers.sql` | NEW — provider entity resolution |
| `src/dk_data/sqlmesh/models/molecules/silver/prescribing_profiles.sql` | NEW — prescribing silver model |
| `src/dk_data/sqlmesh/models/molecules/gold/provider_profile.sql` | NEW — gold provider profile |
| `src/dk_data/sqlmesh/models/molecules/gold/facility_profile.sql` | NEW — gold facility profile |
| `src/dk_data/claude_sdk/base_agent.py` | NEW — BaseAgent ABC for all agents |
| `src/dk_data/claude_sdk/agent_registry.py` | NEW — AgentDefinition registry |
| `src/dk_data/claude_sdk/runner.py` | NEW — CLI entry point for agent CronJobs |
| `src/dk_data/claude_sdk/agents/service_line_inference.py` | NEW — DRG→service-line agent |
| `src/dk_data/claude_sdk/agents/referral_network.py` | NEW — referral network inference agent |
| `src/dk_data/sql/migrations/083_cms_puf_foundation.sql` | NEW — silver/gold/agent tables |
| `src/dk_data/sql/migrations/084_provider_raw_bronze_tables.sql` | NEW — provider raw/bronze |
| `src/dk_data/sql/migrations/085_facility_raw_bronze_tables.sql` | NEW — facility raw/bronze |
| `src/dk_data/sql/migrations/086_drug_market_raw_bronze_tables.sql` | NEW — drug/market raw/bronze |
| `src/dk_data/sql/migrations/087_population_clinical_raw_bronze_tables.sql` | NEW — population/clinical raw/bronze |
| `src/dk_data/sql/seed_data_sources.sql` | MODIFY — +30 catalog entries |
| `src/dk_data/config/rate_limits.yaml` | MODIFY — +30 source rate limits |
| `src/dk_data/observability/metrics.py` | MODIFY — provider/facility/agent metrics |
| `k8s/base/postgrest/configmap.yaml` | MODIFY — add `gold` to PGRST_DB_SCHEMAS |
| `k8s/base/ingestion/cronjob-fetch-*.yaml` | NEW — ~12 data source CronJobs |
| `k8s/base/ingestion/cronjob-agent-*.yaml` | NEW — 5 agent CronJobs |

## Cross-Service Authentication

All dk-data-FE endpoints require JWT authentication, **except** `/health` and
`/data_catalog` which are served by the `web_anon` role. The `gold` schema
requires the `analyst` role — `web_anon` has NO access.

### How it works

The JWT is a **pre-signed API key** managed in Doppler. Consuming services
(HCP Compass, HCO Navigator, Lumina, SageAI) retrieve the key at deploy time
and pass it as a Bearer token.

| Doppler setting | Value |
|-----------------|-------|
| Project | `behaviorlabs-applications` |
| Configs | `stg` (staging), `prd` (production) |
| Variable name | `DK_DATA_API_KEY` |

### PostgREST query patterns for downstream products

```bash
export DK_DATA_API_KEY="<from-doppler>"

# HCP Compass — provider profile
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  http://localhost:3000/gold/provider_profile?npi=eq.1234567890

# HCO Navigator — facility profile
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  http://localhost:3000/gold/facility_profile?ccn=eq.050454

# Lumina — drug market profile
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  http://localhost:3000/gold/drug_market_profile?drug_name=eq.atorvastatin

# SageAI — market analytics
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  http://localhost:3000/gold/market_analytics?geo_code=eq.TX&year=eq.2024

# Provider network (filtered by confidence)
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  http://localhost:3000/gold/provider_network?source_npi=eq.1234567890&confidence_score=gte.0.50
```

## External API Key Registration

### Not required (fully open, no auth)

| Service | Status |
|---------|--------|
| CMS (data.cms.gov) | Fully open, no auth. Socrata API with pagination. |
| CMS NPPES | Open REST API. No key needed. |
| CMS Open Payments | Open API. No key needed. |
| CMS Care Compare | Open Provider-data API. No key needed. |
| NUCC Taxonomy | Open CSV download. No key needed. |

### Recommended (works without but with lower limits)

| Service | Doppler Var | Registration URL | Benefit |
|---------|------------|------------------|---------|
| OpenFDA | `OPENFDA_API_KEY` | https://open.fda.gov/apis/authentication/ | Daily limit: 1,000 → 120,000. Rate: 40/min → 240/min. |

### Required for agent pipeline

| Service | Doppler Var(s) | Registration URL | Notes |
|---------|---------------|------------------|-------|
| Anthropic (agents) | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ | Required for all 5 Claude SDK agents. Haiku model. |
| Google Places (contact verification) | `GOOGLE_PLACES_API_KEY` | https://console.cloud.google.com/ | ContactVerification agent only. |
| USPS Address (contact verification) | `USPS_API_KEY` | https://www.usps.com/business/web-tools-apis/ | ContactVerification agent only. |

### After registration

1. Add new env vars to Doppler (`dk-data-fe` project → `prd` config)
2. The `DopplerSecret` CRD (`k8s/base/doppler-secret.yaml`) auto-syncs all
   Doppler vars to the `dk-data-secrets` K8s secret every 300s
3. CronJobs and FastAPI pods reference these via `envFrom: secretRef`
4. No K8s manifest changes needed — new vars are automatically available

## Environment URLs

| Environment | PostgREST | FastAPI |
|-------------|-----------|---------|
| Local | http://localhost:3000 | http://localhost:8000 |
| Staging | https://data.staging.behaviorlabs.ai | (internal ClusterIP) |
| Production | https://data.behaviorlabs.ai | (internal ClusterIP) |

## Implementation Order

1. **Phase 1 — Foundation**: Migrations 083, base_tool.py generic params, BaseAgent + AgentRegistry, CMSSocrataFetcher base, PostgREST configmap
2. **Phase 2 — Provider Sources**: Migration 084, 7 adapters + 5 fetchers + 5 loaders, 7 bronze + 4 silver + 1 gold SQLMesh models, Tier 4 tool registry
3. **Phase 3 — Facility Sources**: Migration 085, 10 adapters + fetchers + loaders, bronze + silver + gold models, Tier 5 tool registry
4. **Phase 4 — Drug/Market Sources**: Migration 086, 9 adapters + fetchers + loaders, bronze + silver + gold models, Tier 6 tool registry
5. **Phase 5 — Population Sources**: Migration 087, 4 adapters + fetchers + loaders, bronze + silver + gold models
6. **Phase 6 — Clinical + News**: DDInter, Stabilis, Medicaid PDLs, RSS feed extensions
7. **Phase 7 — Agentic Processing**: 6 agents + CronJobs + validation pipeline
8. **Phase 8 — Integration Testing**: End-to-end validation, K8s manifest checks, metrics verification
