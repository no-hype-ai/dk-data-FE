# dk-data-fe Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-30

## Active Technologies
- Python 3.11+ (Job Trigger FastAPI service), SQL (PostgreSQL 16.4), YAML (Kubernetes manifests) + PostgREST v12.2.3, FastAPI, uvicorn, psycopg2-binary, opentelemetry-*, structlog, prometheus-client, kubernetes clien (003-alchemy-cluster-deploy)
- Shared CloudNativePG PostgreSQL 16.4 cluster (`postgresql.infra.svc.cluster.local:5432`), dedicated `dk_data` database (003-alchemy-cluster-deploy)
- Python 3.11+ + FastAPI, psycopg2-binary, httpx (new), pyjwt (new), SQLMesh, Pydantic, structlog, OpenTelemetry, prometheus-client, kubernetes (004-molecule-platform-integration)
- PostgreSQL 16+ via PostgREST v12.x, 12 schemas (6 existing + 6 new molecule schemas) (004-molecule-platform-integration)
- Python 3.11+, SQL (PostgreSQL 16.4), YAML (Kubernetes manifests) + PostgREST v12.2.3, FastAPI, uvicorn, psycopg2-binary, opentelemetry-*, structlog, prometheus-clien (005-prioritized-issue-resolution)
- SQL (PostgreSQL 16.4), YAML (Kubernetes manifests), TypeScript (Admin App components) + PostgREST v12.2.3, PostgreSQL 16.4, Next.js (Admin App) (006-006-admin-integration)
- Python 3.11+, SQL (PostgreSQL 16.4), YAML (Kubernetes manifests), Bash (backup/setup scripts) + FastAPI, PostgREST v12.2.3, psycopg2-binary, pytest-cov (new), responses (new), Kustomize, crane (new CI tool) (010-platform-stabilization)
- PostgreSQL 16.4 (shared infra namespace), MinIO (backup storage, infra namespace) (010-platform-stabilization)
- Python 3.11+ (existing codebase) + psycopg2-binary, Pydantic, httpx, requests, structlog, opentelemetry-sdk, pandas, feedparser (new, for RSS) (011-datasource-integration)
- PostgreSQL 16.4 via CloudNativePG — schemas: `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `raw`, `staging`, `meta`, `api` (011-datasource-integration)
- Python 3.11+ (existing codebase) + psycopg2-binary, Pydantic, httpx, requests, structlog, opentelemetry-sdk, feedparser, uv (new — dependency management) (012-platform-hardening)
- PostgreSQL 16.4 via CloudNativePG — schemas: raw, staging, meta, api, mol_raw, mol_bronze, mol_silver, mol_gold (012-platform-hardening)
- Python 3.11+, SQL (PostgreSQL 16.4), YAML (Kubernetes manifests) + FastAPI, psycopg2-binary, Pydantic, prometheus-client, structlog, PostgREST v12.2.3 (013-observability-governance)
- PostgreSQL 16.4 via CloudNativePG (shared `postgresql.infra.svc.cluster.local:5432`) (013-observability-governance)
- Python 3.11+ + FastAPI, SQLMesh, Pydantic, psycopg2-binary, requests, responses (test), structlog, OpenTelemetry, prometheus-client, kubernetes (014-uspto-euipo-model-datasource)
- PostgreSQL 16.4 (CloudNativePG cluster, `postgresql.infra.svc.cluster.local:5432`, database `dk_data`) (014-uspto-euipo-model-datasource)
- Python 3.11+, SQL (PostgreSQL 16.4) + FastAPI >=0.109.0, SQLMesh >=0.90.0, asyncpg >=0.29.0, psycopg2-binary >=2.9.9, httpx >=0.25.0, pyjwt >=2.8.0, Pydantic >=2.5.0, structlog >=24.0.0, OpenTelemetry (tracing+metrics), prometheus-client >=0.19.0, responses >=0.25.0 (test) (015-assessment-dashboard-integration)
- PostgreSQL 16.4 via CloudNativePG (`postgresql.infra.svc.cluster.local:5432`, database `dk_data`). Schemas: 15 existing + 1 new (`xenon`). PostgREST v12.2.3 for REST API exposure. (015-assessment-dashboard-integration)
- Python 3.11+ (existing codebase), SQL (PostgreSQL 16.4) + FastAPI >=0.109.0, SQLMesh >=0.90.0, psycopg2-binary >=2.9.9, asyncpg >=0.29.0, httpx >=0.25.0, Pydantic >=2.5.0, structlog >=24.0.0, prometheus-client >=0.19.0, anthropic SDK (Claude Haiku), PostgREST v12.2.3 (016-cms-puf-datasource-integration)
- PostgreSQL 16.4 via CloudNativePG (`postgresql.infra.svc.cluster.local:5432`, database `dk_data`). Schemas: `raw`, `bronze`, `silver`, `gold` (new exposure), `meta`, `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `xenon`, `api`, `mol_api`. Range partitioning for high-volume tables (Part D, Physician PUF). (016-cms-puf-datasource-integration)

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
- 016-cms-puf-datasource-integration: Added Python 3.11+ (existing codebase), SQL (PostgreSQL 16.4) + FastAPI >=0.109.0, SQLMesh >=0.90.0, psycopg2-binary >=2.9.9, asyncpg >=0.29.0, httpx >=0.25.0, Pydantic >=2.5.0, structlog >=24.0.0, prometheus-client >=0.19.0, anthropic SDK (Claude Haiku), PostgREST v12.2.3
- 015-assessment-dashboard-integration: Added Python 3.11+, SQL (PostgreSQL 16.4) + FastAPI >=0.109.0, SQLMesh >=0.90.0, asyncpg >=0.29.0, psycopg2-binary >=2.9.9, httpx >=0.25.0, pyjwt >=2.8.0, Pydantic >=2.5.0, structlog >=24.0.0, OpenTelemetry (tracing+metrics), prometheus-client >=0.19.0, responses >=0.25.0 (test)
- 014-uspto-euipo-model-datasource: Added Python 3.11+ + FastAPI, SQLMesh, Pydantic, psycopg2-binary, requests, responses (test), structlog, OpenTelemetry, prometheus-client, kubernetes


<!-- MANUAL ADDITIONS START -->

## Feature 005: Prioritized Issue Resolution (Completed 2026-01-30)

Security and infrastructure improvements addressing critical GitHub issues:

### Key Changes
- **Security**: JWT secret validation (min 256-bit), restricted `web_anon` role permissions
- **Database**: API views (`api.health`, `api.data_catalog`, `api.targets`, `api.scoring`, `api.data_sources`)
- **CI/CD**: New PR testing workflow (`.github/workflows/ci.yaml`), branch+SHA image tags
- **Health**: HTTP readiness probe on PostgREST `/health`, job-trigger enabled (staging:1, prod:2)
- **Observability**: ServiceMonitor and PrometheusRule ready (require Prometheus Operator CRDs)

### Testing
```bash
# Run security and API tests
pytest tests/test_security.py tests/test_api.py -v

# Validate manifests
kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null
```

### Verification
```bash
# Anonymous access test
curl https://data.preview.behaviorlabs.ai/health  # Should succeed
curl https://data.preview.behaviorlabs.ai/targets # Should return 401/403

# Authenticated access
export TOKEN=$(python3 -c "import jwt; print(jwt.encode({'role':'analyst','exp':...}, 'secret'))")
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/targets
```

<!-- MANUAL ADDITIONS END -->
