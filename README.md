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
┌─────────────────────────────────────────────────────────────────┐
│                        External Sources                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐ │
│  │   CMS   │  │  HRSA   │  │   ACC   │  │ Socrata │  │  APIs  │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬───┘ │
└───────┼────────────┼────────────┼────────────┼────────────┼─────┘
        │            │            │            │            │
        └────────────┴────────────┴────────────┴────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Job Trigger Service                        │
│                    (FastAPI - port 8000)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ fetch-cms-all│  │catalog-refresh│  │ sqlmesh-run │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         PostgreSQL                               │
│                      (port 5433)                                 │
│  ┌────────┐  ┌─────────┐  ┌────────┐  ┌─────────┐  ┌─────────┐ │
│  │  raw   │  │ staging │  │  mart  │  │ scoring │  │  meta   │ │
│  └────────┘  └─────────┘  └────────┘  └─────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PostgREST API                             │
│                      (port 3030)                                 │
│  /catalog  /jobs  /job_runs  /health  /targets  /hospitals      │
│  Schemas: api, mol_api                                          │
└─────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│   Metabase   │        │   Frontend   │        │  Monitoring  │
│  (port 3000) │        │  (port 3001) │        │  (optional)  │
│   BI Tool    │        │  Onboarding  │        │ Prometheus   │
│              │        │     UI       │        │   Grafana    │
└──────────────┘        └──────────────┘        └──────────────┘
```

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

### Molecule Onboarding API

The platform provides APIs for onboarding users and molecules:

```bash
# User onboarding
curl -X POST http://localhost:8000/api/v1/onboarding/user \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "name": "John Doe",
    "role": "analyst",
    "organization": "Pharma Corp",
    "therapeutic_areas": ["oncology", "cardiology"]
  }'

# Molecule tracking setup
curl -X POST http://localhost:8000/api/v1/onboarding/molecules \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-uuid",
    "molecules": [
      {"name": "Dupilumab", "identifier_type": "drug_name"},
      {"name": "DUPIXENT", "identifier_type": "brand_name"}
    ]
  }'

# Bulk molecule onboarding
curl -X POST http://localhost:8000/api/v1/onboarding/molecules/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "identifiers": [
      {"value": "CHEMBL1201586", "type": "chembl_id"},
      {"value": "DB05429", "type": "drugbank_id"}
    ]
  }'

# Check onboarding status
curl http://localhost:8000/api/v1/onboarding/status/{user_id}
```

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
│   ├── ingestion/           # Data ingestion modules
│   │   ├── batch/           # Job trigger service
│   │   ├── fetchers/        # Data source fetchers
│   │   └── sources/        # Source-specific loaders
│   ├── sql/                 # SQL schemas and migrations
│   ├── models/              # SQLMesh models
│   ├── frontend/            # Data platform onboarding UI (optional)
│   └── monitoring/          # Prometheus/Grafana configs (optional)
├── specs/                   # Feature specifications
└── docs/                    # Additional documentation
```

## Data Sources

| Source | Description | Refresh |
|--------|-------------|---------|
| `cms_medicare_inpatient` | TAVR procedure volumes (DRG 266/267) | Quarterly |
| `cms_hospital_info` | Hospital demographics and ratings | Monthly |
| `cms_cost_reports` | Hospital financial metrics (HCRIS) | Annual |
| `acc_tvc` | ACC Transcatheter Valve Certifications | Quarterly |
| `hrsa_shortage_areas` | Health Professional Shortage Areas | Monthly |

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

Tables are created automatically during data ingestion and transformation - see [Medallion Architecture](#medallion-architecture) section below.

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

### Adding a new data source (Medallion Architecture)

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

## Molecule Platform Features

### Molecule Onboarding

The platform supports onboarding users and tracking molecules through a comprehensive API:

**User Onboarding**:
- Create user accounts with roles and therapeutic areas
- Track user preferences and access levels
- Manage organization affiliations

**Molecule Tracking**:
- Set up molecule tracking by various identifiers (drug name, brand name, ChEMBL ID, DrugBank ID, etc.)
- Bulk onboarding support for multiple molecules
- Automatic entity resolution and deduplication

**API Endpoints**:
- `POST /api/v1/onboarding/user` - Onboard a new user
- `POST /api/v1/onboarding/molecules` - Set up molecule tracking
- `POST /api/v1/onboarding/molecules/bulk` - Bulk molecule onboarding
- `GET /api/v1/onboarding/status/{user_id}` - Check onboarding status

See the [Molecule Onboarding API](#molecule-onboarding-api) section above for examples.

### Data Platform Features

- **Pipeline Scheduler**: Automated data syncs (daily/weekly/monthly)
- **Dynamic Source Configuration**: Add new data sources via API
- **Entity Resolution**: Automatic molecule deduplication across sources
- **Identifier Linking**: Cross-reference molecules by various identifiers
- **Data Quality Monitoring**: Track data freshness and quality metrics

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

### Frontend (Onboarding UI)

The data platform onboarding UI helps configure and manage data sources:

```bash
# Start with frontend profile
docker compose -f src/dk_data/docker-compose.yml --profile frontend up -d

# Access at http://localhost:3001
```

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
