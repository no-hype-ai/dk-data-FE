# Research: Platform Hardening

## R1: CronJob Container Image Failure (Issue #88)

**Decision**: Fix the Dockerfile by removing the redundant source copy and PYTHONPATH override
**Rationale**: The Dockerfile has a multi-stage build that correctly installs `dk_data` via `pip install .` into `/install/lib/python3.11/site-packages/dk_data/`. However, line 26 (`COPY --from=builder /build/src/dk_data /app/dk_data`) creates a duplicate copy at `/app/dk_data/`, and line 29 (`ENV PYTHONPATH=/app`) causes Python to find the raw source directory instead of the properly installed package. Additionally, `fetch_data.py` uses `sys.path.insert()` with relative imports instead of absolute `dk_data.*` imports.
**Alternatives considered**:
- Option A (chosen): Fix Dockerfile — remove redundant COPY and PYTHONPATH, let `pip install .` handle it
- Option B: Fix all script imports to use absolute paths — higher risk, touches more files, same root cause exists

**Root cause details**:
- `Dockerfile` line 14: `RUN pip install --no-cache-dir --prefix=/install .` — correctly installs package
- `Dockerfile` line 25: `COPY --from=builder /install /usr/local` — correctly copies installed packages
- `Dockerfile` line 26: `COPY --from=builder /build/src/dk_data /app/dk_data` — **BUG**: redundant copy
- `Dockerfile` line 29: `ENV PYTHONPATH=/app` — **BUG**: overrides installed package resolution
- `fetch_data.py` lines 16-19: `sys.path.insert()` + relative imports — should use absolute imports

## R2: Downstream API Views Status (Issue #81)

**Decision**: Create/update API views in db-init-job.yaml; create backing tables only where missing
**Rationale**: 15 API views already exist in db-init-job.yaml. Of the 8 target views from the spec:

| View | API View Exists? | Backing Table? | Action Needed |
|------|-----------------|----------------|---------------|
| competitive_landscape | Yes (line 302) | mol_gold.competitive_landscape | None — already complete |
| molecule_properties | Yes (line 310) | mol_gold.molecule_profiles | None — already complete |
| company_pipeline | Yes (line 324) | None | Create backing table + update view |
| patents | Yes (line 371) | silver.patents exists | Update view to reference silver.patents |
| trial_publication_features | Yes (line 362) | None | Create backing table + update view |
| sider | No | bronze.sider exists | Create API view |
| bioactivity | No | silver.bioactivity exists | Create API view |
| targets | Yes (line 240) | None (TAVR placeholder) | Create mol targets table + update view |

**Alternatives considered**:
- Compute-on-demand for mol_gold views — rejected per FR-006 (out of scope)
- Create all 20+ views from Issue #81 — rejected, scoped to the 8 specified in FR-003

## R3: Data Source Integration Pattern

**Decision**: Use the BaseFetcher pattern (not the legacy external_apis/RawIngestionService pattern)
**Rationale**: The BaseFetcher pattern (`src/dk_data/ingestion/fetchers/base.py`) is the canonical pattern used by all 14 CI sources in PR #87. It provides: requests session with retry, streaming download, JSON fetch, hash calculation, logging. The legacy `RawIngestionService` + `BaseAPIClient` pattern is async (aiohttp/httpx) and stores raw HTTP responses — this is heavier than needed.

**What exists per source**:

| Source | API Client | Data Loader | Raw Table | Bronze Table | DataSource Enum | BaseFetcher |
|--------|-----------|-------------|-----------|-------------|-----------------|-------------|
| UniProt | Yes (uniprot_client.py) | Yes (load_uniprot.py) | Yes (raw.uniprot) | Yes (bronze.uniprot) | Yes | **Missing** |
| PDB | Yes (rcsb_pdb_client.py) | Yes (load_pdb.py) | Yes (raw.pdb) | Yes (bronze.pdb) | Yes | **Missing** |
| ORCID | Yes (orcid_client.py) | No | **Missing** | **Missing** | **Missing** | **Missing** |

**Alternatives considered**:
- Reuse existing BaseAPIClient subclasses directly — rejected, doesn't fit CronJob execution model
- Create RawIngestionService subclasses — rejected, legacy pattern with more complexity than needed

## R4: Dependency Management Tool

**Decision**: Use `uv` for dependency locking
**Rationale**: pyproject.toml already exists with hatchling build backend. `uv` is the modern standard for Python dependency resolution — faster than pip-compile, native pyproject.toml support, generates `uv.lock`. The Dockerfile already references `uv.lock*` (line 8: `COPY pyproject.toml uv.lock* ./`), indicating uv was intended but never fully adopted.
**Alternatives considered**:
- pip-tools (pip-compile) — slower, requires separate .in files
- Poetry — requires migration from hatchling, different lock format
- uv (chosen) — fastest, native pyproject.toml support, already partially referenced in Dockerfile

## R5: Secret Audit

**Decision**: Document all secrets by auditing CronJob manifests and application code
**Rationale**: Secrets are referenced across multiple files — CronJob env vars, Doppler config, and Python code. A comprehensive audit is needed.

**Known secrets from CronJob manifests and code**:
- `POSTGRES_HOST`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PORT`, `POSTGRES_DB` — database connection
- `JWT_SECRET` — PostgREST authentication
- `NCBI_API_KEY` — PubMed fetcher
- `DRUGBANK_API_KEY` — DrugBank fetcher
- `EPO_CONSUMER_KEY`, `EPO_CONSUMER_SECRET` — EPO OPS OAuth2
- `PATENTSVIEW_API_KEY` — USPTO Patents fetcher
- `SEC_EDGAR_USER_AGENT` — SEC EDGAR (required User-Agent header)
- `ANTHROPIC_API_KEY` — Claude SDK enrichment/scoring
- `OTEL_EXPORTER_OTLP_ENDPOINT` — OpenTelemetry (optional)
