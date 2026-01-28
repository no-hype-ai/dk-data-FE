# TAVR Data Infrastructure Platform

A data platform for TAVR (Transcatheter Aortic Valve Replacement) hospital targeting and analysis. Features automated data ingestion from CMS, HRSA, and ACC sources, a PostgREST API layer, and GitOps-ready Kubernetes deployment.

## Quick Start

```bash
# Start all services (PostgreSQL, PostgREST, Job Trigger, Metabase)
make up

# Initialize the database (first time only)
make init-db

# Refresh catalog metadata
make catalog-refresh

# Check status
make status
```

Or use the one-liner:
```bash
make quick-start
```

### Optional Services

Start with additional services:

```bash
# Start with frontend UI
docker compose -f src/dk_data/docker-compose.yml --profile frontend up -d

# Start with monitoring stack (Prometheus, Grafana, Jaeger)
docker compose -f src/dk_data/docker-compose.yml --profile monitoring up -d

# Start everything
docker compose -f src/dk_data/docker-compose.yml --profile frontend --profile monitoring up -d
```

## Prerequisites

- Docker & Docker Compose
- Make
- curl (for health checks)
- jq (optional, for JSON formatting)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          External Data Sources                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐  ┌──────┐ │
│  │   CMS   │  │  HRSA   │  │   ACC   │  │ Socrata │  │  APIs  │  │ New  │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬───┘  └──┬───┘ │
└───────┼────────────┼────────────┼────────────┼────────────┼─────────┼─────┘
        │            │            │            │            │         │
        └────────────┴────────────┴────────────┴────────────┘         │
                                  │                                    │
                                  │                                    │
        ┌─────────────────────────┴─────────────────────────┐         │
        │                                                     │         │
        ▼                                                     ▼         │
┌─────────────────────────────────────────────────────────┐  │         │
│              Data Source Onboarding                      │  │         │
│  ┌───────────────────────────────────────────────────┐  │  │         │
│  │  Frontend UI (port 3001)                          │  │  │         │
│  │  5-Step Wizard: Register → Credentials → Test →  │  │  │         │
│  │  Schema Detect → Generate Table                   │  │  │         │
│  └──────────────────────┬────────────────────────────┘  │  │         │
│                         │                                 │  │         │
│  ┌──────────────────────▼────────────────────────────┐  │  │         │
│  │  Job Trigger API (port 8000)                       │  │  │         │
│  │  /api/v1/data-sources/*                            │  │  │         │
│  │  - Register source                                 │  │  │         │
│  │  - Store credentials                               │  │  │         │
│  │  - Detect schema                                   │  │  │         │
│  │  - Generate bronze table                           │  │  │         │
│  └──────────────────────┬────────────────────────────┘  │  │         │
└──────────────────────────┼────────────────────────────────┘  │         │
                           │                                    │         │
                           ▼                                    │         │
┌───────────────────────────────────────────────────────────────┼─────────┘
│                    Job Trigger Service                        │
│                 (FastAPI - port 8000)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ fetch-cms-all│  │catalog-refresh│  │ sqlmesh-run │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Pipeline Scheduler                                   │    │
│  │  - Daily/Weekly/Monthly syncs                         │    │
│  │  - Raw → Bronze → Silver → Gold                      │    │
│  └──────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          PostgreSQL (port 5433)                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  TAVR Data Schemas                                                   │  │
│  │  ┌────────┐  ┌─────────┐  ┌────────┐  ┌─────────┐  ┌─────────┐   │  │
│  │  │  raw   │  │ staging │  │  mart  │  │ scoring │  │  meta   │   │  │
│  │  └────────┘  └─────────┘  └────────┘  └─────────┘  └─────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  Molecule Platform - Medallion Architecture                           │  │
│  │                                                                       │  │
│  │  ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐ │  │
│  │  │   raw    │ ────▶│  bronze  │ ────▶│  silver  │ ────▶│   gold   │ │  │
│  │  │          │      │          │      │          │      │          │ │  │
│  │  │ Unmodified│      │ Parsed/ │      │ Entity-  │      │ Aggregated│ │  │
│  │  │ responses │      │ typed   │      │ resolved │      │ views    │ │  │
│  │  └──────────┘      └──────────┘      └──────────┘      └──────────┘ │  │
│  │                                                                       │  │
│  │  ┌───────────────────────────────────────────────────────────────┐   │  │
│  │  │  application - User data, onboarding, tracking                │   │  │
│  │  └───────────────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        PostgREST API (port 3030)                           │
│  /catalog  /jobs  /job_runs  /health  /targets  /hospitals                │
│  Schemas: api (TAVR), mol_api (Molecule Platform)                          │
└───────────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│   Metabase   │        │   Frontend   │        │  Monitoring  │
│  (port 3000) │        │  (port 3001) │        │  (optional)   │
│   BI Tool    │        │ Data Source │        │ Prometheus   │
│              │        │  Onboarding │        │   Grafana    │
│              │        │     UI       │        │   Jaeger     │
└──────────────┘        └──────────────┘        └──────────────┘
```

### Architecture Overview

**Data Flow**:
1. **External Sources** → Data ingestion from CMS, HRSA, ACC, Socrata, and custom APIs
2. **Data Source Onboarding** → Frontend UI or API for registering new sources
3. **Job Trigger Service** → Orchestrates data syncs and transformations
4. **Pipeline Scheduler** → Automated daily/weekly/monthly syncs through medallion layers
5. **PostgreSQL** → Stores data in TAVR schemas and medallion architecture (raw → bronze → silver → gold)
6. **PostgREST API** → Auto-generated REST endpoints from database views
7. **Consumers** → Metabase (BI), Frontend (onboarding), Monitoring (observability)

### Services

| Service | Port | Description | Profile |
|---------|------|-------------|---------|
| PostgreSQL | 5433 | Database with pgvector extension | Default |
| PostgREST | 3030 | Auto-generated REST API | Default |
| Job Trigger | 8000 | FastAPI service for batch jobs | Default |
| Metabase | 3000 | BI dashboard tool | Default |
| Frontend | 3001 | Data platform onboarding UI | `frontend` |
| Prometheus | 9090 | Metrics collection | `monitoring` |
| Grafana | 3003 | Metrics visualization | `monitoring` |
| Jaeger | 16686 | Distributed tracing UI | `monitoring` |
| Jaeger OTLP | 4317/4318 | OTLP gRPC/HTTP endpoints | `monitoring` |

## Available Commands

### Service Lifecycle

| Command | Description |
|---------|-------------|
| `make up` | Start all services (postgres, postgrest, job-trigger) |
| `make down` | Stop all services |
| `make restart` | Restart all services |
| `make status` | Show status with health checks |
| `make logs` | Tail all service logs |
| `make logs-postgres` | Tail PostgreSQL logs |
| `make logs-postgrest` | Tail PostgREST logs |
| `make logs-jobs` | Tail job-trigger logs |

### Database

| Command | Description |
|---------|-------------|
| `make init-db` | Initialize database schema and seed data |
| `make db-reset` | Reset database (WARNING: destroys all data) |
| `make db-stats` | Show database statistics |
| `make psql` | Open PostgreSQL shell |

### Jobs

| Command | Description |
|---------|-------------|
| `make job-list` | List all available batch jobs |
| `make job-runs` | Show recent job runs |
| `make fetch-all` | Fetch all external data sources |
| `make fetch-cms` | Fetch CMS data |
| `make fetch-hrsa` | Fetch HRSA shortage area data |
| `make fetch-acc` | Fetch ACC TVC certification data |
| `make catalog-refresh` | Refresh data catalog metadata |
| `make sqlmesh-run` | Run SQLMesh transformations |

### Monitoring

| Command | Description |
|---------|-------------|
| `make health` | Check health of all services |
| `make catalog` | Show data catalog status |
| `make api-health` | Check PostgREST API health |
| `make api-openapi` | Show available API endpoints |

### Development

| Command | Description |
|---------|-------------|
| `make build` | Build all Docker images |
| `make build-no-cache` | Build without cache |
| `make test` | Run all tests |
| `make lint` | Run linters |
| `make clean` | Clean up Docker resources |
| `make shell` | Open shell in job-trigger container |

### Pipeline

| Command | Description |
|---------|-------------|
| `make pipeline` | Run full data pipeline (fetch → transform → catalog) |
| `make quick-start` | Quick start: up + init-db + catalog-refresh |

## API Endpoints

### PostgREST API (port 3030)

The PostgREST API auto-generates REST endpoints from PostgreSQL views in the `api` and `mol_api` schemas:

```bash
# Get data catalog
curl http://localhost:3030/catalog

# Get catalog with specific fields
curl "http://localhost:3030/catalog?select=source_name,health_status,record_count"

# Get batch jobs
curl http://localhost:3030/jobs

# Get job runs
curl http://localhost:3030/job_runs

# Get system health
curl http://localhost:3030/health

# Filter by source name
curl "http://localhost:3030/catalog?source_name=eq.cms_hospital_info"

# View OpenAPI schema
curl http://localhost:3030/
```

**Available Schemas**: `api`, `mol_api` (molecule platform views)

### Job Trigger API (port 8000)

```bash
# Health check
curl http://localhost:8000/health

# List jobs
curl http://localhost:8000/jobs

# Trigger a job
curl -X POST http://localhost:8000/jobs/catalog-refresh/trigger

# Get job runs
curl http://localhost:8000/runs
```

### Data Source Onboarding API

The platform provides comprehensive APIs for onboarding new external data sources:

```bash
# Register a new data source
curl -X POST http://localhost:8000/api/v1/data-sources/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "new_api_source",
    "display_name": "New API Source",
    "api_type": "rest",
    "base_url": "https://api.example.com",
    "auth_type": "api_key",
    "refresh_tier": "daily",
    "rate_limit_requests": 10,
    "batch_size": 100
  }'

# Test connection to a data source
curl -X POST http://localhost:8000/api/v1/data-sources/test-connection \
  -H "Content-Type: application/json" \
  -d '{
    "source_name": "new_api_source",
    "base_url": "https://api.example.com",
    "auth_type": "api_key"
  }'

# Store credentials for a data source
curl -X POST http://localhost:8000/api/v1/data-sources/{source_name}/credentials \
  -H "Content-Type: application/json" \
  -d '{
    "key_name": "api_key",
    "value": "your-api-key-here",
    "credential_type": "api_key"
  }'

# Auto-detect schema from sample responses
curl -X POST http://localhost:8000/api/v1/data-sources/{source_name}/detect-schema \
  -H "Content-Type: application/json" \
  -d '{
    "sample_responses": [
      {"id": 1, "name": "Example", "value": 123.45}
    ]
  }'

# Generate and create bronze table
curl -X POST http://localhost:8000/api/v1/data-sources/{source_name}/generate-table

# Trigger initial sync
curl -X POST http://localhost:8000/api/v1/data-sources/{source_name}/sync

# List all data sources
curl http://localhost:8000/api/v1/data-sources

# Get data source details
curl http://localhost:8000/api/v1/data-sources/{source_name}

# Check sync status
curl http://localhost:8000/api/v1/data-sources/{source_name}/sync/status
```

**Note**: The frontend UI (`http://localhost:3001`) provides a guided 5-step wizard for data source onboarding with schema detection and table generation.

## Project Structure

```
dk-data-fe/
├── Makefile                 # Root orchestration commands
├── README.md                # This file
├── ARCHITECTURE.md          # Detailed architecture documentation
├── .gitops/                 # Kubernetes GitOps manifests
│   ├── base/                # Base Kustomize resources
│   └── overlays/            # Environment-specific overlays
│       ├── dev/
│       ├── staging/
│       └── prod/
├── scripts/                 # Operational scripts
│   ├── data/                # Data processing scripts
│   ├── ops/                 # Operational scripts
│   └── utils/               # Utility scripts
├── src/dk_data/             # Main application code
│   ├── docker-compose.yml   # Local development stack
│   ├── docker-compose.prod.yml  # Production overrides
│   ├── data/                # Bronze layer data loaders
│   │   ├── load_orange_book.py    # FDA Orange Book
│   │   ├── load_ema.py            # EMA authorized medicines
│   │   ├── load_drugbank.py       # DrugBank database
│   │   ├── load_bindingdb.py      # BindingDB affinities
│   │   ├── load_tdc_data.py       # TDC ADMET datasets
│   │   ├── load_uniprot.py        # UniProt proteins
│   │   ├── load_pdb.py            # PDB structures
│   │   ├── load_uspto_patents.py  # USPTO patents
│   │   └── load_openalex.py       # OpenAlex publications
│   ├── ingestion/           # Data ingestion modules
│   │   ├── batch/           # Job trigger service
│   │   ├── fetchers/        # Data source fetchers
│   │   └── sources/        # Source-specific loaders
│   ├── models/              # Pydantic models
│   │   └── data_platform/   # Medallion layer base models
│   ├── services/            # Business logic services
│   │   ├── data_platform/   # Medallion architecture services
│   │   └── external_apis/   # External API clients
│   ├── sql/                 # SQL schemas and migrations
│   ├── sqlmesh/             # SQLMesh transformation models
│   ├── frontend/            # Data platform onboarding UI (optional)
│   └── monitoring/          # Prometheus/Grafana configs (optional)
├── specs/                   # Feature specifications
└── docs/                    # Additional documentation
    ├── MEDALLION_ARCHITECTURE.md  # Medallion layer documentation
    └── DATA_LOADERS.md            # Data loader reference
```

## Data Sources

| Source | Description | Refresh |
|--------|-------------|---------|
| `cms_medicare_inpatient` | TAVR procedure volumes (DRG 266/267) | Quarterly |
| `cms_hospital_info` | Hospital demographics and ratings | Monthly |
| `cms_cost_reports` | Hospital financial metrics (HCRIS) | Annual |
| `acc_tvc` | ACC Transcatheter Valve Certifications | Quarterly |
| `hrsa_shortage_areas` | Health Professional Shortage Areas | Monthly |

### Molecule Platform Data Loaders

The platform includes data loaders for pharmaceutical and scientific data sources. These populate the bronze layer of the medallion architecture.

| Loader | Description | Target Table |
|--------|-------------|--------------|
| `load_orange_book` | FDA Orange Book (approved drugs, patents, exclusivities) | `bronze.orange_book_*` |
| `load_ema` | EMA authorized medicines | `bronze.ema` |
| `load_drugbank` | DrugBank database (drugs, interactions, targets) | `bronze.drugbank_*` |
| `load_bindingdb` | BindingDB binding affinity data | `bronze.bindingdb_affinities` |
| `load_tdc_data` | TDC ADMET datasets with molecular descriptors | `bronze.tdc_*` |
| `load_uniprot` | UniProt protein targets | `bronze.uniprot` |
| `load_pdb` | RCSB PDB protein structures | `bronze.pdb` |
| `load_uspto_patents` | USPTO patent data | `bronze.uspto_patents` |
| `load_openalex` | OpenAlex scientific publications | `bronze.openalex` |

**Usage Examples**:
```bash
# Regulatory data
python -m dk_data.data.load_orange_book --download
python -m dk_data.data.load_ema --download
python -m dk_data.data.load_drugbank --xml /path/to/drugbank.xml

# Chemical/molecular data
python -m dk_data.data.load_bindingdb /path/to/BindingDB_All.tsv
python -m dk_data.data.load_tdc_data --category absorption

# Protein data
python -m dk_data.data.load_uniprot --mode drug-targets
python -m dk_data.data.load_pdb --mode drug-targets

# Patents & Publications
python -m dk_data.data.load_uspto_patents --mode drugs
python -m dk_data.data.load_openalex --mode drugs
```

For detailed documentation, see [docs/DATA_LOADERS.md](docs/DATA_LOADERS.md).

## Database Schemas

### TAVR Data Schemas

| Schema | Purpose |
|--------|---------|
| `raw` | Raw ingested data from external sources |
| `staging` | Cleaned and standardized data |
| `mart` | Business-ready dimensional models |
| `scoring` | Hospital scoring and targeting data |
| `meta` | Data catalog, jobs, and health metadata |
| `api` | Views exposed via PostgREST (TAVR data) |

### Molecule Platform Schemas (Medallion Architecture)

The platform implements a **medallion architecture** for molecule/drug data:

| Schema | Purpose | Description |
|--------|---------|-------------|
| `raw` | Raw layer | Unprocessed API responses from external sources |
| `bronze` | Bronze layer | Source-native typed data, parsed from raw |
| `silver` | Silver layer | Entity-resolved, normalized, deduplicated data |
| `gold` | Gold layer | Pre-aggregated analytics and decision-ready views |
| `application` | Application layer | User-specific data, onboarding, tracking |
| `mol_api` | API views | Views exposed via PostgREST (molecule platform) |

**Data Flow**: `raw` → `bronze` → `silver` → `gold` → `mol_api`

Tables are created automatically during data ingestion and transformation. For detailed documentation, see [docs/MEDALLION_ARCHITECTURE.md](docs/MEDALLION_ARCHITECTURE.md).

## Environment Variables

Create a `.env` file in `src/dk_data/` to override defaults:

```bash
# PostgreSQL
POSTGRES_PORT=5433
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=edwards_tavr

# PostgREST
POSTGREST_PORT=3030
POSTGREST_PASSWORD=postgrest_secret_change_me
PGRST_JWT_SECRET=your-secret-key  # Optional, for JWT authentication

# Job Trigger
JOB_TRIGGER_PORT=8000
JOB_RUNNER_MODE=local  # or 'k8s' for Kubernetes

# Metabase (optional)
METABASE_PORT=3000

# Frontend (optional)
FRONTEND_PORT=3001

# Monitoring (optional)
PROMETHEUS_PORT=9090
GRAFANA_PORT=3003
JAEGER_UI_PORT=16686
JAEGER_OTLP_GRPC_PORT=4317
JAEGER_OTLP_HTTP_PORT=4318
```

## Troubleshooting

### Services won't start

```bash
# Check Docker is running
docker info

# Check for port conflicts
lsof -i :5433  # PostgreSQL
lsof -i :3030  # PostgREST
lsof -i :8000  # Job Trigger
lsof -i :3000  # Metabase
lsof -i :3001  # Frontend (if enabled)

# View detailed logs
make logs

# Check specific service logs
make logs-postgres
make logs-postgrest
make logs-jobs
```

### Database connection issues

```bash
# Test PostgreSQL connection
make psql

# Check PostgREST can connect
make logs-postgrest
```

### Jobs failing

```bash
# View job logs
make logs-jobs

# Check job runs
make job-runs

# View detailed job output
docker compose -f src/dk_data/docker-compose.yml exec job-trigger \
  python -m ingestion.fetch_data --source cms_hospital_info
```

### Reset everything

```bash
# Full reset (destroys all data)
make db-reset

# Stop and remove all containers and volumes
make down
docker compose -f src/dk_data/docker-compose.yml down -v
```

### Accessing Services

Once services are running:

- **Metabase**: http://localhost:3000 (BI dashboard)
- **Frontend UI**: http://localhost:3001 (if enabled)
- **PostgREST API**: http://localhost:3030
- **Job Trigger API**: http://localhost:8000
- **Grafana**: http://localhost:3003 (if monitoring enabled)
- **Prometheus**: http://localhost:9090 (if monitoring enabled)
- **Jaeger**: http://localhost:16686 (if monitoring enabled)

## Development

### Adding a new data source

1. Create fetcher in `src/dk_data/ingestion/fetchers/`
2. Create loader in `src/dk_data/ingestion/sources/`
3. Register in `src/dk_data/ingestion/main.py`
4. Add seed data in `src/dk_data/sql/seed_data_sources.sql`
5. Create job definition in `src/dk_data/sql/seed_batch_jobs.sql`

### Adding a new API endpoint

1. Create view in `src/dk_data/sql/api_views.sql` or `src/dk_data/sql/migrations/021_mol_api_views.sql`
2. Grant permissions to appropriate roles
3. PostgREST will auto-generate the endpoint

### Medallion Layer Base Models

The platform provides Pydantic base models for each medallion layer in `src/dk_data/models/data_platform/base.py`:

```python
from dk_data.models.data_platform import RawBaseModel, BronzeBaseModel, SilverBaseModel, GoldBaseModel

# Raw layer: Unmodified API responses
class MyRawRecord(RawBaseModel):
    request_id: str
    response_body: Dict[str, Any]
    processed_to_bronze: bool = False

# Bronze layer: Source-native typed data
class MyBronzeRecord(BronzeBaseModel):
    raw_source_id: UUID
    source: str
    processed_to_silver: bool = False

# Silver layer: Entity-resolved normalized data
class MySilverRecord(SilverBaseModel):
    source: str

# Gold layer: Aggregated analytics views
class MyGoldRecord(GoldBaseModel):
    pass
```

### Adding a new data source (Medallion Architecture)

**Option 1: Via API (Recommended)**

Use the data source onboarding API or UI:

```bash
# Register via API
curl -X POST http://localhost:8000/api/v1/data-sources/register \
  -H "Content-Type: application/json" \
  -d '{...}'

# Or use the frontend UI at http://localhost:3001
```

The onboarding process will:
1. Register the source in `raw.sync_schedules`
2. Store credentials securely
3. Auto-detect schema from sample responses
4. Generate bronze table automatically
5. Create SQLMesh transformation model
6. Set up sync schedule

**Option 2: Manual Configuration**

1. Add source configuration to `raw.sync_schedules`:
   ```sql
   INSERT INTO raw.sync_schedules (source, tier, cron_expression, priority, options)
   VALUES ('new_source', 'daily', '0 2 * * *', 'normal', '{"base_url": "...", "target_table": "..."}');
   ```

2. Create fetcher in `src/dk_data/ingestion/fetchers/`
3. Create loader in `src/dk_data/ingestion/sources/`
4. Register in `src/dk_data/ingestion/main.py`
5. Bronze table will be created automatically on first sync
6. Add transformation logic for bronze → silver → gold

## Data Source Onboarding

The platform provides comprehensive **data source onboarding** capabilities for adding new external data sources to the medallion architecture:

### Features

- **5-Step Onboarding Wizard**: Guided UI for configuring new data sources
- **Auto-Schema Detection**: Automatically detects schema from sample API responses
- **Credential Management**: Secure storage and rotation of API keys and tokens
- **Connection Testing**: Validate API connectivity before onboarding
- **Automatic Table Generation**: Creates bronze layer tables automatically
- **SQLMesh Model Generation**: Auto-generates transformation models
- **Pagination Support**: Configure offset, page-based, or cursor pagination
- **Incremental Sync**: Set up incremental data fetching by date fields
- **Rate Limiting**: Configure request rate limits per source

### Onboarding Process

1. **Register Source**: Provide API details (base URL, auth type, etc.)
2. **Store Credentials**: Securely store API keys or tokens
3. **Test Connection**: Validate connectivity and fetch sample data
4. **Detect Schema**: Auto-detect table structure from sample responses
5. **Generate Tables**: Create bronze layer table and SQLMesh model
6. **Trigger Sync**: Start initial data ingestion

### Data Platform Features

- **Pipeline Scheduler**: Automated data syncs (daily/weekly/monthly)
- **Dynamic Source Configuration**: Add new data sources via API without code changes
- **Entity Resolution**: Automatic molecule deduplication across sources
- **Identifier Linking**: Cross-reference molecules by various identifiers
- **Data Quality Monitoring**: Track data freshness and quality metrics
- **Medallion Architecture**: Automatic bronze → silver → gold transformations

## Optional Services

### Metabase (BI Dashboard)

Metabase provides a user-friendly interface for querying and visualizing data:

```bash
# Access at http://localhost:3000
# First-time setup: Create admin account
# Connect to PostgreSQL:
#   Host: postgres
#   Port: 5432
#   Database: edwards_tavr
#   Username: postgres
#   Password: postgres
```

### Frontend (Data Source Onboarding UI)

The data source onboarding UI provides a guided 5-step wizard for onboarding new external data sources:

```bash
# Start with frontend profile
docker compose -f src/dk_data/docker-compose.yml --profile frontend up -d

# Access at http://localhost:3001
```

**Features**:
- Step 1: Source registration (name, API type, base URL)
- Step 2: Credential management (API keys, tokens)
- Step 3: Connection testing and sample data fetching
- Step 4: Schema detection and table generation
- Step 5: Sync configuration and initial data load

The UI automatically generates bronze layer tables and SQLMesh models based on detected schemas.

### Monitoring Stack

Prometheus, Grafana, and Jaeger for observability:

```bash
# Start monitoring services
docker compose -f src/dk_data/docker-compose.yml --profile monitoring up -d

# Access:
# - Grafana: http://localhost:3003 (admin/admin123)
# - Prometheus: http://localhost:9090
# - Jaeger: http://localhost:16686
```

## GitOps Deployment

For Kubernetes deployment, see `.gitops/README.md`.

```bash
# Validate Kustomize manifests
kubectl kustomize .gitops/overlays/dev

# Deploy to dev
kubectl apply -k .gitops/overlays/dev
```

## License

Proprietary - Edwards Lifesciences
