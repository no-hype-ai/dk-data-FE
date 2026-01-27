# Quickstart: DK Molecule Data Platform

**Feature**: 012-dk-data-platform
**Created**: 2026-01-24
**Status**: Draft

---

## Prerequisites

- **Docker** 20.10+ with Docker Compose
- **PostgreSQL** 14+ (or use containerized version)
- **Python** 3.10+ (for SQLMesh and data loading scripts)
- **Node.js** 18+ (optional, for API client generation)

---

## 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd dk-data-platform

# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### Required Environment Variables

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=molecule_platform
POSTGRES_USER=platform_user
POSTGRES_PASSWORD=<secure-password>

# PostgREST
PGRST_DB_URI=postgres://platform_user:password@localhost:5432/molecule_platform
PGRST_DB_SCHEMA=gold
PGRST_JWT_SECRET=<32-character-secret>

# Data Sources (API Keys)
DRUGBANK_API_KEY=<your-key>  # Optional, for extended data
CHEMBL_API_BASE=https://www.ebi.ac.uk/chembl/api/data

# SQLMesh
SQLMESH_GATEWAY=local
```

---

## 2. Start Infrastructure

```bash
# Start all services with Docker Compose
docker-compose up -d

# Verify services are running
docker-compose ps

# Expected output:
# NAME                STATUS
# postgres            Up
# postgrest           Up
# sqlmesh             Up
# prometheus          Up
# grafana             Up
```

---

## 3. Initialize Database

```bash
# Run database migrations
docker-compose exec postgres psql -U platform_user -d molecule_platform -f /migrations/001_create_schema.sql
docker-compose exec postgres psql -U platform_user -d molecule_platform -f /migrations/002_raw_tables.sql
docker-compose exec postgres psql -U platform_user -d molecule_platform -f /migrations/003_bronze_tables.sql
docker-compose exec postgres psql -U platform_user -d molecule_platform -f /migrations/004_silver_tables.sql
docker-compose exec postgres psql -U platform_user -d molecule_platform -f /migrations/005_gold_views.sql

# Or use the migration script
python scripts/migrate.py --up
```

---

## 4. Load Initial Data

### Option A: Load Sample Data (Fast Start)

```bash
# Load curated sample dataset (~1000 molecules)
python scripts/load_sample_data.py

# Verify data loaded
curl http://localhost:3000/gold_molecule_profile?limit=5
```

### Option B: Load from External Sources (Full Setup)

```bash
# Start initial sync from all sources
python scripts/sync_sources.py --sources all --mode full

# Monitor progress
python scripts/sync_sources.py --status

# Expected duration: 2-4 hours for full initial load
```

---

## 5. Verify Setup

### Check Database Layers

```bash
# Connect to database
docker-compose exec postgres psql -U platform_user -d molecule_platform

# Check record counts by layer
SELECT
    'raw' as layer, count(*) as records FROM raw.chembl
UNION ALL SELECT
    'bronze', count(*) FROM bronze.chembl_molecules
UNION ALL SELECT
    'silver', count(*) FROM silver.molecules
UNION ALL SELECT
    'gold', count(*) FROM gold.molecule_profile;
```

### Check API Access

```bash
# Get JWT token
TOKEN=$(curl -s -X POST http://localhost:3000/rpc/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

# List molecules
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/gold_molecule_profile?limit=10

# Search for aspirin
curl -H "Authorization: Bearer $TOKEN" \
  -X POST http://localhost:3000/rpc/search_molecules \
  -H "Content-Type: application/json" \
  -d '{"query":"aspirin"}'
```

### Check Pipeline Status

```bash
# View SQLMesh plan
sqlmesh plan

# Check transformation status
sqlmesh audit

# View model DAG
sqlmesh dag
```

---

## 6. Access Dashboards

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| PostgREST API | http://localhost:3000 | JWT auth |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | (no auth) |
| SQLMesh UI | http://localhost:8000 | (no auth) |

---

## 7. Development Workflow

### Adding a New Data Source

1. Create raw table schema:
```sql
-- migrations/010_raw_new_source.sql
CREATE TABLE raw.new_source (
    id SERIAL PRIMARY KEY,
    payload JSONB NOT NULL,
    fetched_at TIMESTAMP DEFAULT NOW(),
    api_version TEXT
);
```

2. Add Bronze model in SQLMesh:
```python
# sqlmesh/models/bronze/new_source.py
from sqlmesh import model

@model(
    name="bronze.new_source",
    kind="incremental_by_time_range"
)
def bronze_new_source(context):
    return """
    SELECT
        payload->>'id' as source_id,
        payload->>'name' as name,
        -- Extract typed columns
        fetched_at
    FROM raw.new_source
    WHERE fetched_at BETWEEN @start_ts AND @end_ts
    """
```

3. Add Silver entity resolution:
```python
# sqlmesh/models/silver/molecules.py
# Add JOIN to new source in molecule resolution query
```

4. Run transformations:
```bash
sqlmesh plan --select bronze.new_source silver.molecules
sqlmesh run
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test suite
pytest tests/test_entity_resolution.py -v

# Run with coverage
pytest --cov=src tests/
```

### Local API Development

```bash
# Generate TypeScript client from OpenAPI
npx openapi-generator-cli generate \
  -i specs/contracts/molecules-api.yaml \
  -g typescript-fetch \
  -o src/client

# Run PostgREST with auto-reload
docker-compose up postgrest --build
```

---

## 8. Common Operations

### Trigger Manual Sync

```bash
# Sync specific source
python scripts/sync_sources.py --sources chembl --mode incremental

# Force full refresh
python scripts/sync_sources.py --sources drugbank --mode full
```

### Review Entity Resolution Queue

```bash
# View pending resolutions
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/pipeline_resolution_queue?limit=10

# Approve a resolution
curl -H "Authorization: Bearer $TOKEN" \
  -X PUT http://localhost:3000/pipeline_resolution_queue?inchi_key=eq.XXXX \
  -d '{"action":"approve"}'
```

### Backup Database

```bash
# Create manual backup
docker-compose exec postgres pgbackrest backup --stanza=main --type=full

# List available backups
docker-compose exec postgres pgbackrest info
```

---

## 9. Troubleshooting

### PostgREST Not Responding

```bash
# Check logs
docker-compose logs postgrest

# Common issues:
# - Wrong PGRST_DB_URI format
# - Missing JWT secret
# - Schema not exposed (check PGRST_DB_SCHEMA)
```

### SQLMesh Plan Fails

```bash
# Check for schema drift
sqlmesh diff

# Reset state (caution: clears incremental state)
sqlmesh clean
```

### Entity Resolution Low Confidence

```bash
# Check resolution stats
SELECT
    CASE
        WHEN resolution_confidence >= 0.8 THEN 'high'
        WHEN resolution_confidence >= 0.5 THEN 'medium'
        ELSE 'low'
    END as confidence_bucket,
    count(*) as molecules
FROM silver.molecules
GROUP BY 1;

# Review low-confidence records
SELECT * FROM silver.molecules
WHERE needs_review = true
ORDER BY resolution_confidence
LIMIT 20;
```

---

## 10. Next Steps

- [ ] Configure production secrets in secure vault
- [ ] Set up automated backups with pgBackRest
- [ ] Configure alerting in Grafana
- [ ] Load production data from all sources
- [ ] Set up cron jobs for scheduled syncs
- [ ] Configure network policies for Kubernetes deployment

---

## Support

- **Documentation**: See `docs/` directory
- **Issues**: File in project issue tracker
- **API Reference**: http://localhost:3000/ (OpenAPI auto-generated)
