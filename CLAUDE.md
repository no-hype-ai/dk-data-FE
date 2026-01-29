# dk-data-fe Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-14

## Active Technologies
- Python 3.11+ (Job Trigger FastAPI service), SQL (PostgreSQL 16.4), YAML (Kubernetes manifests) + PostgREST v12.2.3, FastAPI, uvicorn, psycopg2-binary, opentelemetry-*, structlog, prometheus-client, kubernetes clien (003-alchemy-cluster-deploy)
- Shared CloudNativePG PostgreSQL 16.4 cluster (`postgresql.infra.svc.cluster.local:5432`), dedicated `dk_data` database (003-alchemy-cluster-deploy)
- Python 3.11+ + FastAPI, psycopg2-binary, httpx (new), pyjwt (new), SQLMesh, Pydantic, structlog, OpenTelemetry, prometheus-client, kubernetes (004-molecule-platform-integration)
- PostgreSQL 16+ via PostgREST v12.x, 12 schemas (6 existing + 6 new molecule schemas) (004-molecule-platform-integration)

- Python 3.11+ (existing ingestion layer), SQL (PostgreSQL 16+) + PostgREST v12.x, SQLMesh, psycopg2, Pydantic, requests (001-data-layer-postgrest-gitops)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11+ (existing ingestion layer), SQL (PostgreSQL 16+): Follow standard conventions

## Recent Changes
- 004-molecule-platform-integration: Added Python 3.11+ + FastAPI, psycopg2-binary, httpx (new), pyjwt (new), SQLMesh, Pydantic, structlog, OpenTelemetry, prometheus-client, kubernetes
- 003-alchemy-cluster-deploy: Added Python 3.11+ (Job Trigger FastAPI service), SQL (PostgreSQL 16.4), YAML (Kubernetes manifests) + PostgREST v12.2.3, FastAPI, uvicorn, psycopg2-binary, opentelemetry-*, structlog, prometheus-client, kubernetes clien

- 001-data-layer-postgrest-gitops: Added Python 3.11+ (existing ingestion layer), SQL (PostgreSQL 16+) + PostgREST v12.x, SQLMesh, psycopg2, Pydantic, requests

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
