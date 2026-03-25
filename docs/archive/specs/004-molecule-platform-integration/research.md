# Research: Molecule Platform Integration

**Feature**: 004-molecule-platform-integration
**Date**: 2026-01-28

## Decision Log

### D1: Selective Merge Strategy

**Decision**: Use `git checkout origin/Philipp-working -- <path>` to selectively bring files, not `git merge`.

**Rationale**: The source branch has 274 files changed including `.gitops/`, `docker-compose.yml`, `nginx/`, `frontend/`, and `.env` files that conflict with the dk-alchemy GitOps structure established in feature 003. A full merge would require reverting ~40% of the diff.

**Alternatives considered**:
- `git merge` with manual conflict resolution — too many conflicts in GitOps files
- Cherry-pick individual commits — commits are not cleanly separated by concern
- Patch files — fragile and hard to review

### D2: Schema Naming Convention

**Decision**: All molecule schemas use `mol_` prefix: `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_app`, `mol_api`. Plus shared `meta` schema (already exists from TAVR init).

**Rationale**: The existing db-init-job creates schemas `raw`, `staging`, `mart`, `scoring`, `meta`, `api`. The source branch migration 020 already creates `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_app`, `mol_api`. The `mol_` prefix avoids collision with the existing `raw` schema. The `meta` schema is shared for pipeline metadata (batch_job_runs, batch_jobs).

**Alternatives considered**:
- Bare names (`raw`, `bronze`, `silver`, `gold`) — collides with existing `raw` schema
- Separate database — breaks single-instance convention and complicates PostgREST routing

### D3: Database Name

**Decision**: Use `dk_data` (from db-init-job.yaml), not `edwards_tavr` (from legacy code defaults).

**Rationale**: Feature 003 already created the db-init-job targeting `dk_data`. The Philipp-working branch defaults to `edwards_tavr` in several places (SQLMesh config, database.py). All hardcoded references to `edwards_tavr` must be updated to use the `POSTGRES_DB` environment variable.

**Impact**: Update `src/dk_data/sqlmesh/config.yaml` to read from env or use `dk_data`. Update `src/dk_data/core/config.py` default from `edwards_tavr` to `dk_data`.

### D4: Router Integration Pattern

**Decision**: Use try/except import pattern from the Philipp-working branch — gracefully skip molecule routers if imports fail.

**Rationale**: The source branch uses `try: from api.routes import ...; app.include_router(...) except ImportError: logger.warning(...)`. This allows the API to start even if molecule-specific dependencies are missing, maintaining backward compatibility.

**Impact**: Import paths must be corrected from `from api.routes import ...` to `from dk_data.api.routes import ...` to match the installed package structure (`PYTHONPATH=/app` in Dockerfile).

### D5: New Python Dependencies

**Decision**: Add `httpx>=0.25.0` and `pyjwt>=2.8.0` to `pyproject.toml`. Do NOT add `rdkit` (heavy C dependency, not used in core path).

**Rationale**: The Philipp-working branch external API clients use `httpx` for async HTTP. The JWT service uses `pyjwt`. RDKit is referenced in comments but not imported — molecule identification uses InChI Key strings, not chemical structure computation.

**Alternatives considered**:
- `aiohttp` instead of `httpx` — httpx is already used in source branch, more modern API
- Skip JWT entirely — needed for PostgREST authenticated endpoints in mol_api schema

### D6: CronJob Architecture

**Decision**: Three new CronJobs in `k8s/base/ingestion/`, same GHCR image as job-trigger with different command entrypoints.

**Rationale**: Existing CronJobs (cms-all, refresh) use the same pattern — GHCR image with `command:` override. Molecule CronJobs follow the same convention. Resource limits are higher for molecule transform (512Mi/1Gi) due to cross-source aggregation.

**CronJobs**:
- `cronjob-mol-fetch-daily.yaml` — 2 AM UTC daily, fetches ClinicalTrials.gov + OpenFDA Labels
- `cronjob-mol-fetch-weekly.yaml` — Sunday 3 AM UTC, fetches FAERS + ChEMBL + PubChem
- `cronjob-mol-transform.yaml` — 6 AM UTC daily, runs bronze→silver→gold pipeline

### D7: Database Init Extension

**Decision**: Extend existing `k8s/base/db-init-job.yaml` SQL inline block to add molecule schemas, rather than creating separate migration jobs.

**Rationale**: The current db-init-job already creates 6 schemas, 5 roles, and grants in a single idempotent SQL block. Adding molecule schemas to the same block keeps the pattern consistent and ensures all schemas exist before any ArgoCD-managed workload starts. Individual migration files (020–051) from the source branch are too granular for K8s Job execution — they're better suited for SQLMesh or a migration runner within the application.

**Impact**: The db-init-job SQL block grows from ~130 lines to ~250 lines. Molecule-specific tables are created by the application (via migration files) on first run, not by the init job — the init job only creates schemas, extensions, and roles.

### D8: PostgREST Schema Exposure

**Decision**: Add `mol_api` to `PGRST_DB_SCHEMAS`, not the internal schemas.

**Rationale**: PostgREST exposes all tables/views in configured schemas as REST endpoints. Internal schemas (`mol_raw`, `mol_bronze`, `mol_silver`) should not be directly queryable. Only `mol_api` (which contains curated views) should be exposed alongside the existing `api` schema.

**Updated value**: `PGRST_DB_SCHEMAS: "api,mol_api"`

### D9: Import Path Correction

**Decision**: All imports from the Philipp-working branch must use the full package path `dk_data.` prefix.

**Rationale**: The Dockerfile sets `PYTHONPATH=/app` and copies the package to `/app/dk_data/`. The source branch uses relative imports in some places (e.g., `from api.routes import ...` instead of `from dk_data.api.routes import ...`). All imports must be normalized to the installed package path.

**Files affected**: `api.py` router imports, `fetch_molecules.py`, `transform_molecules.py`, `run_molecule_pipeline.py`, all service cross-references.

### D10: Observability Integration

**Decision**: New services use the existing `dk_data.observability` module — no parallel logging/metrics setup.

**Rationale**: The source branch's `core/logging.py` duplicates functionality already in `observability/logging.py`. The existing module provides structlog + OTLP + Prometheus metrics. New molecule services should import from `dk_data.observability` rather than introducing `dk_data.core.logging`.

**Impact**: Remove or redirect `core/logging.py` imports to `observability`. Keep `core/config.py` for molecule-specific configuration (EnrichmentSettings, etc.).

## External API Research

### Core 5 Sources — Access Patterns

| Source | Base URL | Auth | Rate Limit | Response Format |
|--------|----------|------|-----------|-----------------|
| ClinicalTrials.gov | `https://clinicaltrials.gov/api/v2/` | None (public) | 3 req/sec | JSON |
| OpenFDA Labels | `https://api.fda.gov/drug/label.json` | Optional API key | 40/min (no key), 240/min (with key) | JSON |
| OpenFDA FAERS | `https://api.fda.gov/drug/event.json` | Optional API key | 40/min (no key), 240/min (with key) | JSON |
| ChEMBL | `https://www.ebi.ac.uk/chembl/api/data/` | None (public) | 10 req/sec | JSON |
| PubChem | `https://pubchem.ncbi.nlm.nih.gov/rest/pug/` | None (public) | 5 req/sec | JSON |

All 5 core sources are freely accessible without API keys. Rate limiting is enforced client-side via the `base_client.py` async HTTP wrapper with exponential backoff.

## Risk Research

### R1: Import Path Breakage

**Risk**: After selective checkout, imports may reference modules not yet copied.
**Mitigation**: Copy in dependency order — models first, then services, then API routes, then ingestion CLI modules. Run `ruff check` after each batch.

### R2: SQLMesh Config Hardcoded Credentials

**Risk**: `sqlmesh/config.yaml` has hardcoded `password: postgres`.
**Mitigation**: SQLMesh config must be updated to read from environment variables or use a `.env` file. For K8s, SQLMesh runs inside pods that have env vars injected via Doppler.

### R3: Circular Dependencies

**Risk**: `services/data_platform/` modules import from `models/`, `api/`, and each other.
**Mitigation**: Review import graph during selective checkout. Use lazy imports where circular references exist.
