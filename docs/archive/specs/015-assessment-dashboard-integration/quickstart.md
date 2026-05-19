# Quickstart: Assessment Dashboard Integration

**Branch**: `015-assessment-dashboard-integration`

## Prerequisites

- Python 3.11+
- PostgreSQL 16.4 running locally (or port-forward to CloudNativePG cluster)
- PostgREST v12.2.3 running locally
- `uv` package manager installed
- Repository cloned and on `015-assessment-dashboard-integration` branch

## Local Setup

### 1. Install dependencies

```bash
cd /Users/pschloz/Desktop/DataKinetic/dk-data-FE
uv sync
```

### 2. Initialize database schemas

```bash
# Run existing migrations (creates mol_raw, mol_bronze, mol_silver, mol_gold, etc.)
python -m dk_data.scripts.run_migrations

# Run new migration for xenon schema + new raw tables (created in this feature)
# Migration file: src/dk_data/sql/migrations/074_xenon_schema.sql
psql -U postgres -d dk_data -f src/dk_data/sql/migrations/074_xenon_schema.sql
```

### 3. Update PostgREST config

```bash
# Local PostgREST config - add new schemas
export PGRST_DB_SCHEMAS="api,mol_api,mol_gold,mol_silver,xenon,meta"

# Or update local postgrest.conf:
# db-schemas = "api,mol_api,mol_gold,mol_silver,xenon,meta"
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

# For local development, retrieve your pre-signed API key from Doppler:
#   Project: behaviorlabs-applications, Config: stg
#   Variable: DK_DATA_API_KEY
export DK_DATA_API_KEY="<your-pre-signed-api-key-from-doppler>"

# Read mol_gold data
curl -H "Authorization: Bearer $DK_DATA_API_KEY" http://localhost:3000/molecule_profile?limit=1

# Read xenon data (empty initially)
curl -H "Authorization: Bearer $DK_DATA_API_KEY" http://localhost:3000/assessment_generated?limit=1
```

> **Note:** Do NOT generate JWTs locally with `jwt.encode`. The API key is a
> pre-signed JWT stored in Doppler. Xenon containers should never have the
> JWT signing secret.

## Development Workflow

### Adding a new bronze SQLMesh model

1. Create SQL file: `src/dk_data/sqlmesh/models/molecules/bronze/{source}.sql`
2. Follow existing pattern (see `chembl_molecules.sql` or `uspto_patents.sql`)
3. Register in `LAYER_MODELS` dict in `src/dk_data/ingestion/transform_molecules.py`
4. Add contract test: `tests/test_bronze_model_contracts.py`
5. Validate: `sqlmesh -p src/dk_data/sqlmesh plan --no-prompts`

### Adding a new MCP tool adapter

1. Create adapter: `src/dk_data/services/mcp/adapters/{source}.py`
2. Implement `normalize(api_response) -> dict` method
3. Register tool in tool registry
4. Add adapter unit test with `@responses.activate` mocking
5. Add integration test against bronze model

### Running tests

```bash
# All tests
pytest tests/ -v

# Security tests only
pytest tests/test_security.py -v

# Bronze model contracts only
pytest tests/test_bronze_model_contracts.py -v

# SQLMesh model validation
sqlmesh -p src/dk_data/sqlmesh plan --no-prompts
```

## Key File Locations

| Component | Path |
|-----------|------|
| FastAPI app entry | `src/dk_data/ingestion/batch/api.py` |
| Data platform router | `src/dk_data/api/routes/data_platform.py` |
| KOL router | `src/dk_data/api/routes/kols.py` |
| RBAC middleware | `src/dk_data/api/middleware/rbac.py` |
| JWT service | `src/dk_data/services/auth/jwt_service.py` |
| Transform pipeline | `src/dk_data/ingestion/transform_molecules.py` |
| SQLMesh models | `src/dk_data/sqlmesh/models/molecules/` |
| SQLMesh config | `src/dk_data/sqlmesh/config.yaml` |
| Fetchers | `src/dk_data/ingestion/fetchers/` |
| Rate limiters | `src/dk_data/services/external_apis/` |
| DB init | `k8s/base/db-init-job.yaml` |
| PostgREST config | `k8s/base/postgrest/configmap.yaml` |
| Tests | `tests/` |

## Cross-Service Authentication (Issue #550)

All dk-data-FE endpoints — both PostgREST views and FastAPI routes — require
JWT authentication, **except** `/health` and `/data_catalog` which are served
by the `web_anon` role.

### How it works

The JWT is a **pre-signed API key** managed in Doppler. Consuming services
(Xenon, Admin App, etc.) retrieve the key at deploy time and pass it as a
Bearer token. They never possess the JWT signing secret.

| Doppler setting | Value |
|-----------------|-------|
| Project | `behaviorlabs-applications` |
| Configs | `stg` (staging), `prd` (production) |
| Variable name | `DK_DATA_API_KEY` |

### Environment URLs

| Environment | PostgREST base URL |
|-------------|-------------------|
| Local | `http://localhost:3000` |
| Staging | `https://data.staging.behaviorlabs.ai` |
| Production | `https://data.behaviorlabs.ai` |

### Curl examples

```bash
export DK_DATA_API_KEY="<from-doppler>"

# PostgREST — query molecule_profile view
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  https://data.staging.behaviorlabs.ai/molecule_profile?limit=1

# MCP — list available tools
curl -H "Authorization: Bearer $DK_DATA_API_KEY" \
  https://data.staging.behaviorlabs.ai/api/v1/mcp/tools

# MCP — invoke a tool
curl -X POST \
  -H "Authorization: Bearer $DK_DATA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"drug_name":"durvalumab"}' \
  https://data.staging.behaviorlabs.ai/api/v1/mcp/tools/clinicaltrials-search/invoke

# Data platform — trigger a raw-to-bronze transform
curl -X POST \
  -H "Authorization: Bearer $DK_DATA_API_KEY" \
  https://data.staging.behaviorlabs.ai/api/v1/data-platform/transform-raw/clinicaltrials
```

### Public (unauthenticated) endpoints

The `web_anon` PostgreSQL role can **only** access two views:

- `api.health` — basic health check
- `api.data_catalog` — read-only catalog metadata

All other views and RPC functions require a valid JWT with an authorized role.

### Key rotation

The pre-signed API key has a **1-year expiry**. To rotate:

1. Generate a new JWT signed with `DK_DATA_JWT_SECRET` (stored separately in
   Doppler under the `dk-data` project, not shared with consumers).
2. Update `DK_DATA_API_KEY` in the `behaviorlabs-applications` Doppler project
   for both `stg` and `prd` configs.
3. Restart consuming services so they pick up the new key.

### Security note

Migration `077` defensively revokes any stale `web_anon` grants that may have
been applied in earlier migrations. This ensures `web_anon` is locked down to
only `api.health` and `api.data_catalog`, even if previous migrations
inadvertently granted broader access.

## External API Key Registration

The following API keys should be registered and stored in Doppler
(`dk-data-fe` project, `prd` config) to unlock higher rate limits
and reliable access.

### Required (will fail without)

| Service | Doppler Var(s) | Registration URL | Notes |
|---------|---------------|------------------|-------|
| OpenAlex | `OPENALEX_API_KEY` | https://openalex.org/settings/api | **Mandatory since Feb 2026**. Old `mailto` polite pool removed. |
| ORCID | `ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET` | https://orcid.org → Developer Tools | OAuth2 client credentials. Scope: `/read-public`. |
| WHO ICD | `WHO_ICD_CLIENT_ID`, `WHO_ICD_CLIENT_SECRET` | https://icd.who.int/icdapi/Account/Register | OAuth2 client credentials. Scope: `icdapi_access`. |

### Recommended (works without but with lower limits)

| Service | Doppler Var | Registration URL | Benefit |
|---------|------------|------------------|---------|
| OpenFDA | `OPENFDA_API_KEY` | https://open.fda.gov/apis/authentication/ (via api.data.gov) | Daily limit: 1,000 → 120,000. Rate: 40/min → 240/min. |
| NCBI/PubMed | `NCBI_API_KEY` | https://www.ncbi.nlm.nih.gov/account/settings/ | Rate: 3 req/s → 10 req/s. |

### Not available / no benefit

| Service | Status |
|---------|--------|
| ClinicalTrials.gov | No API key system. ~50 req/min per IP. |
| PubChem | No API key. 5 req/s, 400 req/min. Monitor `X-Throttling-Control` header. |
| SEC EDGAR | User-Agent only (already implemented). 10 req/s. |
| UniProt | No auth needed. Fair-use policy. |
| RCSB PDB | No auth needed. Conservative 3 req/s. |
| EMA | Open data, no auth. |
| CMS (data.cms.gov) | Fully open, no auth. |
| ChEMBL | No formal API key. Email chembl-help@ebi.ac.uk for enhanced access. 1 req/s default. |

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
