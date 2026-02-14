# TAVR Data Infrastructure Platform

A data platform for TAVR (Transcatheter Aortic Valve Replacement) hospital targeting and analysis. Features automated data ingestion from CMS, HRSA, and ACC sources, a PostgREST API layer, and GitOps-ready Kubernetes deployment.

## Quick Start

```bash
# Start all services
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
└─────────────────────────────────────────────────────────────────┘
```

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

The PostgREST API auto-generates REST endpoints from PostgreSQL views:

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
```

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
│   ├── ingestion/           # Data ingestion modules
│   │   ├── batch/           # Job trigger service
│   │   ├── fetchers/        # Data source fetchers
│   │   └── sources/         # Source-specific loaders
│   ├── sql/                 # SQL schemas and migrations
│   └── models/              # SQLMesh models
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

| Schema | Purpose |
|--------|---------|
| `raw` | Raw ingested data from external sources |
| `staging` | Cleaned and standardized data |
| `mart` | Business-ready dimensional models |
| `scoring` | Hospital scoring and targeting data |
| `meta` | Data catalog, jobs, and health metadata |
| `api` | Views exposed via PostgREST |

## Environment Variables

Create a `.env` file in `src/dk_data/` to override defaults:

```bash
# PostgreSQL
POSTGRES_PORT=5433
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=dk_data

# PostgREST
POSTGREST_PORT=3030
POSTGREST_PASSWORD=  # REQUIRED: set a secure password

# Job Trigger
JOB_TRIGGER_PORT=8000
JOB_RUNNER_MODE=local  # or 'k8s' for Kubernetes

# JWT (optional)
PGRST_JWT_SECRET=your-secret-key
```

## Troubleshooting

### Services won't start

```bash
# Check Docker is running
docker info

# Check for port conflicts
lsof -i :5433
lsof -i :3030
lsof -i :8000

# View detailed logs
make logs
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
```

## Development

### Adding a new data source

1. Create fetcher in `src/dk_data/ingestion/fetchers/`
2. Create loader in `src/dk_data/ingestion/sources/`
3. Register in `src/dk_data/ingestion/main.py`
4. Add seed data in `src/dk_data/sql/seed_data_sources.sql`
5. Create job definition in `src/dk_data/sql/seed_batch_jobs.sql`

### Adding a new API endpoint

1. Create view in `src/dk_data/sql/api_views.sql`
2. Grant permissions to appropriate roles
3. PostgREST will auto-generate the endpoint

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
