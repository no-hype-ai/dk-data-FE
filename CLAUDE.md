# dk-data-FE Development Guidelines

## Tech Stack
- **Language**: Python 3.11+
- **API**: FastAPI >= 0.109.0, uvicorn
- **Pipeline**: SQLMesh >= 0.90.0 (transforms raw → bronze → silver → gold)
- **Database**: PostgreSQL 16.4 (`dk_data` database)
- **Data Access**: PostgREST v12.2.3 (REST API over mol_silver/mol_gold schemas)
- **Key libs**: Pydantic v2, httpx, structlog, OpenTelemetry, anthropic SDK, psycopg2-binary
- **Package Manager**: uv (see `uv.lock`)

## Project Structure

```text
src/dk_data/
  api/
    routes/         # FastAPI route handlers (onboarding, data_platform, data_tools, agents, ...)
    middleware/     # Auth (JWT/RBAC), request middleware
  ingestion/
    sources/        # One file per external data source (~50 sources: CMS, FDA, patents, etc.)
    fetchers/       # Shared fetch utilities
    services/       # Ingestion orchestration
  sqlmesh/
    models/         # SQLMesh transformation models (raw → bronze → silver → gold)
      molecules/    # mol_* schema models
      cms/          # CMS PUF models
      mart/         # Gold/mart models
      staging/      # Staging transforms
  agents/           # Claude-powered data agents
  services/         # Business logic (ground truth, onboarding, data platform)
  data_registry.py  # Single source of truth for ALL table definitions
  config/           # Settings and configuration
tests/
```

## Commands

```bash
# Services
make up             # Start all services (postgres, postgrest, job-trigger)
make down           # Stop all services
make status         # Show service health
make logs-jobs      # Tail job-trigger logs
make shell          # Shell into job-trigger container

# Database
make init-db        # Initialize schema and seed data
make db-reset       # Reset database (DESTRUCTIVE)
make psql           # Open PostgreSQL shell (port 5433)

# Pipeline
make pipeline       # Full pipeline: fetch → transform → catalog
make fetch-all      # Fetch all external data sources
make sqlmesh-run    # Run SQLMesh transformations only
make catalog-refresh # Refresh data catalog metadata

# Testing & linting
make test           # Run all tests (pytest)
make lint           # Run ruff linter
pytest tests/       # Run tests directly

# Rebuild job-trigger after code changes
docker compose build job-trigger && docker compose up -d --force-recreate job-trigger
```

## Docker Services

| Service | Container | Port |
|---|---|---|
| PostgreSQL 16 | `dk-data-fe-postgres` | 5433 (host) |
| PostgREST v12.2.3 | `dk-data-fe-postgrest` | 3030 (host) |
| FastAPI job-trigger | `dk-data-fe-job-trigger` | 8000 (host) |
| SQLMesh scheduler | `dk-data-fe-sqlmesh-scheduler` | — |
| Metabase v0.50.26 | `dk-data-fe-metabase` | 3000 (host) |

## Database Schema Architecture

Medallion pipeline — data flows left to right:

```
mol_raw → mol_bronze → mol_silver → mol_gold
```

| Schema | Description | molecule_id type |
|---|---|---|
| `mol_raw` | Raw ingested data (no transforms) | varies |
| `mol_bronze` | Cleaned, validated, deduplicated | UUID |
| `mol_silver` | Entity-linked, enriched (FK to `mol_silver.molecules`) | UUID |
| `mol_gold` | Aggregated analytics views | TEXT (no FK) |
| `ind_silver/gold` | Indication/disease data | — |
| `hcs_silver/gold` | Healthcare system (CMS) data | — |
| `xenon` | Xenon app data (read-only for dk-data-FE) | — |

**PostgREST needs restart after any schema or config changes.**

## Data Registry

`src/dk_data/data_registry.py` is the single source of truth for all table definitions. Every table has a `TableDef` specifying schema, description, molecule_id type, source, and PostgREST path. When adding a new table:
1. Create the SQLMesh model in the appropriate domain schema
2. Add `TableDef` to the correct dict in `data_registry.py`
3. Notify Xenon team to update their local `data-registry.ts`

## Ingestion API (consumed by Xenon)

The job-trigger FastAPI service (port 8000) exposes these endpoints used by Xenon's `McpClient`:

```
POST /api/v1/onboarding/molecule          # Onboard new molecule (resolves UUID, triggers all sources)
GET  /api/v1/onboarding/molecule/{id}     # Poll onboarding status (pending → ingesting → completed)
POST /api/v1/data-platform/ingest/{source} # Trigger ingestion for a specific source
GET  /api/v1/data-platform/molecules/search # Search molecules by name
```

**Ingest sources** are the filenames in `src/dk_data/ingestion/sources/` (e.g. `clinicaltrials_gov`, `openfda_labels`, `sec_edgar`, `pubmed`, `drugbank`). Ingestion is async — the POST returns immediately with a `job_id`; data lands in silver/gold after the medallion pipeline runs. Xenon polls PostgREST for data arrival rather than using fixed delays.

## Key Conventions
- `data_registry.py` is authoritative — never hardcode table/schema names elsewhere
- openFDA fields can be arrays OR strings — handle both in ingestion and transforms
- CMS PUF tables use range partitioning for high-volume data (Part D, Physician PUF)
- PostgREST needs restart after schema changes: `docker compose restart postgrest`
- SQLMesh manages all raw → silver → gold promotions; do not write directly to silver/gold
- JWT auth required for all non-health endpoints; `web_anon` role has restricted permissions
