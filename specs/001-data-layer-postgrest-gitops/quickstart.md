# Quickstart: TAVR Data Platform

**Feature**: 001-data-layer-postgrest-gitops
**Date**: 2026-01-14

## Prerequisites

- Docker & Docker Compose v2.x
- Python 3.11+
- kubectl (for GitOps testing)
- k3d or k3s (optional, for local K8s)

## Local Development Setup

### 1. Clone and Setup Environment

```bash
# Clone repository
cd /Users/nicholas/Code/dk-data-fe

# Create Python virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r src/dk_data/requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy example environment file
cp src/dk_data/.env.example src/dk_data/.env.local

# Edit .env.local with your settings
# Default values work for local development
```

Default configuration (`.env.local`):
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=edwards_tavr
POSTGREST_PORT=3030
POSTGREST_PASSWORD=postgrest_secret_change_me
```

### 3. Start the Stack

```bash
cd src/dk_data

# Start all services (PostgreSQL + PostgREST)
docker compose up -d

# Verify services are running
make status
```

Expected output:
```
Services:
  PostgreSQL:  running (localhost:5433)
  PostgREST:   running (http://localhost:3030)
```

### 4. Initialize Database

```bash
# Create schemas and tables
make init-db

# Seed data sources metadata
# (Automatically done by init-db)
```

### 5. Verify API is Working

```bash
# Test API endpoint
curl http://localhost:3030/targets?limit=3

# View available endpoints
curl http://localhost:3030/
```

## Quick Commands

| Command | Description |
|---------|-------------|
| `make dev` | Start development environment |
| `make status` | Check service status |
| `make db-shell` | Open PostgreSQL shell |
| `make api-test` | Test API endpoints |
| `make logs` | View service logs |
| `make down` | Stop all services |

## Data Operations

### Fetch Data from External Sources

```bash
# Fetch all data sources
make fetch-all

# Fetch specific source
make fetch-cms-hospitals
make fetch-cms-inpatient YEAR=2024
make fetch-acc-tvc
```

### Run Transformations

```bash
# Preview SQLMesh changes
make sqlmesh-plan

# Apply transformations
make sqlmesh-run

# Full refresh (fetch + transform)
make refresh-all
```

## API Usage Examples

### Query Hospital Targets

```bash
# Get all targets
curl 'http://localhost:3030/targets'

# Filter by state
curl 'http://localhost:3030/targets?state=eq.CA'

# Filter by tier and sort by score
curl 'http://localhost:3030/targets?tier_classification=eq.A&order=total_trs.desc'

# Pagination
curl 'http://localhost:3030/targets?limit=50&offset=100'
```

### Query Data Catalog

```bash
# Get all catalog entries
curl 'http://localhost:3030/catalog'

# Filter by topic
curl 'http://localhost:3030/catalog?topic_tags=cs.{cms}'

# Filter by health status
curl 'http://localhost:3030/catalog?health_status=eq.healthy'

# Get specific source metadata
curl 'http://localhost:3030/catalog?source_name=eq.cms_hospital_info'
```

### Trigger Batch Jobs (when job-trigger service is running)

```bash
# List available jobs
curl 'http://localhost:8080/jobs'

# Trigger a job manually
curl -X POST 'http://localhost:8080/jobs/fetch-cms-all/trigger'

# Check job run history
curl 'http://localhost:3030/job_runs?order=started_at.desc&limit=10'
```

## GitOps Deployment (Kubernetes)

### Local k3s Testing

```bash
# Create local cluster (using k3d)
k3d cluster create tavr-dev

# Apply Kustomize manifests
kubectl apply -k .gitops/overlays/dev

# Verify deployment
kubectl get pods -n tavr-data
kubectl get svc -n tavr-data
```

### Production Deployment (ArgoCD)

```bash
# Apply ArgoCD Application
kubectl apply -f .gitops/argocd/application.yaml

# Monitor sync status
argocd app get tavr-data-platform
```

## Directory Structure

```
src/dk_data/
├── docker-compose.yml      # Local development stack
├── Makefile                # Build/run commands
├── .env.local              # Local environment config
├── sql/                    # Database initialization
├── sqlmesh/                # Data transformation models
├── ingestion/              # Data fetchers and loaders
└── scripts/                # Utility scripts

.gitops/
├── base/                   # Shared K8s manifests
├── overlays/               # Environment-specific configs
│   ├── dev/
│   ├── staging/
│   └── prod/
└── argocd/                 # ArgoCD Application
```

## Troubleshooting

### PostgreSQL Connection Issues

```bash
# Check if PostgreSQL container is running
docker ps | grep postgres

# View PostgreSQL logs
docker logs system-postgres

# Test connection
docker exec -it system-postgres pg_isready
```

### PostgREST Not Responding

```bash
# Check PostgREST container
docker ps | grep postgrest

# View PostgREST logs
docker logs postgrest

# Restart PostgREST
make api-stop && make api-start
```

### API Returns Empty Results

```bash
# Check database has data
make db-status

# Verify API schema has views
docker exec system-postgres psql -U postgres -d edwards_tavr -c "\dv api.*"

# Check PostgREST schema config
docker exec postgrest env | grep PGRST
```

## Next Steps

1. **Ingest Data**: Run `make fetch-all` to populate the database
2. **Transform Data**: Run `make sqlmesh-run` to create mart tables
3. **Explore API**: Use the OpenAPI spec at `/specs/001-data-layer-postgrest-gitops/contracts/openapi.yaml`
4. **Deploy to K8s**: Follow GitOps deployment section above
