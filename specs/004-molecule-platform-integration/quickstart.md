# Quickstart: Molecule Platform Integration

**Feature**: 004-molecule-platform-integration
**Date**: 2026-01-28

## Prerequisites

- Branch `004-molecule-platform-integration` checked out (based on `staging`)
- `origin/Philipp-working` fetched (`git fetch origin`)
- Python 3.11+, `uv` package manager
- Docker for local builds
- `kustomize` CLI for manifest validation
- Access to dk-data-fe GitHub repo

## Step 1: Selective Code Checkout

```bash
# From the 004-molecule-platform-integration branch:

# 1a. Bring application Python code (excluding docker-compose, nginx, frontend, .env files)
git checkout origin/Philipp-working -- \
  src/dk_data/api/ \
  src/dk_data/core/ \
  src/dk_data/data/ \
  src/dk_data/models/ \
  src/dk_data/services/ \
  src/dk_data/ingestion/fetch_molecules.py \
  src/dk_data/ingestion/transform_molecules.py \
  src/dk_data/ingestion/run_molecule_pipeline.py

# 1b. Bring SQL migrations
git checkout origin/Philipp-working -- src/dk_data/sql/migrations/

# 1c. Bring SQLMesh models
git checkout origin/Philipp-working -- src/dk_data/sqlmesh/

# 1d. Bring documentation
git checkout origin/Philipp-working -- \
  specs/012-dk-data-platform/ \
  docs/DATA_LOADERS.md \
  docs/MEDALLION_ARCHITECTURE.md
```

## Step 2: Fix Import Paths

All imports from the source branch that use bare module names must be prefixed with `dk_data.`:

```bash
# Find bare imports that need fixing
ruff check src/ 2>&1 | head -50
```

Key patterns to fix:
- `from api.routes import ...` → `from dk_data.api.routes import ...`
- `from services.data_platform import ...` → `from dk_data.services.data_platform import ...`
- `from models.silver import ...` → `from dk_data.models.silver import ...`
- `from core.config import ...` → `from dk_data.core.config import ...`

## Step 3: Update Dependencies

```bash
# Check what's new in Philipp-working pyproject.toml
git diff staging...origin/Philipp-working -- pyproject.toml

# Add missing deps to pyproject.toml:
# httpx>=0.25.0       (async HTTP for external API clients)
# pyjwt>=2.8.0        (JWT for PostgREST auth)

# Regenerate lock file
uv lock
```

## Step 4: Wire Molecule Routes into API

Edit `src/dk_data/ingestion/batch/api.py` to include molecule routers:

```python
# After existing TAVR endpoints, add:
try:
    from dk_data.api.routes import (
        data_platform_router,
        monitoring_router,
        data_sources_router,
        onboarding_router,
        alerts_router,
    )
    app.include_router(data_platform_router, prefix="/api/v1")
    app.include_router(monitoring_router, prefix="/api/v1")
    app.include_router(data_sources_router, prefix="/api/v1")
    app.include_router(onboarding_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
except ImportError as e:
    logger.warning(f"Molecule platform routers not available: {e}")
```

## Step 5: Add Molecule Jobs to job_runner.py

Add to `JOB_COMMANDS` dict in `LocalJobRunner`:

```python
# Molecule platform jobs
"fetch-clinicaltrials": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "clinicaltrials"],
"fetch-openfda-labels": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openfda_labels"],
"fetch-openfda-faers": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "openfda_faers"],
"fetch-chembl": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "chembl"],
"fetch-pubchem": ["python", "-m", "dk_data.ingestion.fetch_molecules", "--source", "pubchem"],
"mol-bronze-transform": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "bronze"],
"mol-silver-transform": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "silver"],
"mol-gold-aggregate": ["python", "-m", "dk_data.ingestion.transform_molecules", "--layer", "gold"],
"mol-pipeline-full": ["python", "-m", "dk_data.ingestion.run_molecule_pipeline"],
```

## Step 6: Update Database Init Job

Extend `k8s/base/db-init-job.yaml` SQL to add molecule schemas:

```sql
-- Molecule schemas (added to existing init block)
CREATE SCHEMA IF NOT EXISTS mol_raw;
CREATE SCHEMA IF NOT EXISTS mol_bronze;
CREATE SCHEMA IF NOT EXISTS mol_silver;
CREATE SCHEMA IF NOT EXISTS mol_gold;
CREATE SCHEMA IF NOT EXISTS mol_app;
CREATE SCHEMA IF NOT EXISTS mol_api;

-- Extensions for entity resolution
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Grants for molecule schemas
GRANT USAGE ON SCHEMA mol_api TO web_anon, analyst, api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_api TO web_anon, analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_api GRANT SELECT ON TABLES TO web_anon, analyst;
```

## Step 7: Update PostgREST Config

Edit `k8s/base/postgrest/configmap.yaml`:

```yaml
PGRST_DB_SCHEMAS: "api,mol_api"
```

## Step 8: Add Molecule K8s Resources

Create the 3 CronJob manifests and ConfigMap in `k8s/base/ingestion/`, then add them to `k8s/base/kustomization.yaml`:

```yaml
resources:
  # ... existing resources ...
  - ingestion/cronjob-mol-fetch-daily.yaml
  - ingestion/cronjob-mol-fetch-weekly.yaml
  - ingestion/cronjob-mol-transform.yaml
  - ingestion/molecule-pipeline-config.yaml
```

## Step 9: Validate

```bash
# Lint
ruff check src/

# Kustomize
kustomize build k8s/overlays/staging
kustomize build k8s/overlays/prod

# Docker build
docker build -t dk-data-fe-test .

# Quick smoke test
docker run --rm dk-data-fe-test python -c "import dk_data; print('OK')"
```

## Step 10: Secrets & Env

Update `.env.example` with new variables:

```bash
# Optional: External API Keys (molecule platform)
OPENFDA_API_KEY=         # Optional: higher rate limits
CHEMBL_API_KEY=          # Optional: not required for public access
DRUGBANK_API_KEY=        # Optional: requires paid subscription

# Pipeline Configuration
BATCH_SIZE=100
ENTITY_RESOLUTION_THRESHOLD=0.80
```

## Verification Checklist

- [ ] `ruff check src/` — zero errors
- [ ] `kustomize build k8s/overlays/staging` — includes mol CronJobs
- [ ] `kustomize build k8s/overlays/prod` — includes mol CronJobs
- [ ] `docker build .` — succeeds
- [ ] `python -c "import dk_data"` — succeeds inside container
- [ ] `/health` endpoint responds 200
- [ ] `/jobs` endpoint lists molecule jobs alongside TAVR jobs
- [ ] No hardcoded credentials (`gitleaks detect`)
