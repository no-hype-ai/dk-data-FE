# Research: Assessment Dashboard Integration

**Branch**: `015-assessment-dashboard-integration` | **Date**: 2026-02-25
**Purpose**: Resolve all technical unknowns before implementation planning

## R-001: MCP Server Implementation Pattern

**Decision**: Mount MCP tools as a new FastAPI router at `/mcp` using the existing router registration pattern (try/except graceful degradation in `api.py`).

**Rationale**: The codebase has no existing MCP implementation. The closest analog is the data_platform router (3166 lines, 20+ endpoints). The MCP protocol requires tool registration with input/output schemas — this maps naturally to FastAPI endpoints with Pydantic models. Each tool becomes a POST endpoint under `/mcp/tools/{tool_name}/invoke`.

**Alternatives considered**:
- Standalone MCP server process: Rejected — adds operational complexity with separate deployment, auth config, and service mesh entry.
- SSE-based MCP transport: Rejected for MVP — the xenon dashboard calls tools via HTTP; SSE streaming adds complexity without immediate benefit.
- Mounting on existing data_platform router: Rejected — data_platform is already 3166 lines; MCP tools should be a separate concern.

**Key files**:
- `src/dk_data/ingestion/batch/api.py` — FastAPI app entry, router registration pattern
- `src/dk_data/api/routes/data_platform.py` — largest router, pattern reference
- `src/dk_data/api/middleware/rbac.py` — `require_analyst` dependency for auth

---

## R-002: Per-Source Adapter Architecture

**Decision**: Each MCP tool has a dedicated adapter module under `src/dk_data/services/mcp/adapters/{source}.py`. The adapter implements a `normalize(api_response) -> dict` method that transforms the external API response into the canonical `response_body` JSONB structure.

**Rationale**: Bronze SQLMesh models extract fields via specific JSONB paths (e.g., `response_body->>'molecule_chembl_id'`, `response_body->'protocolSection'->'identificationModule'->>'briefTitle'`). MCP tools calling different API endpoints (search vs bulk) will receive differently-structured responses. The adapter bridges this gap.

**Alternatives considered**:
- Generic response passthrough: Rejected — bronze models would fail on unexpected JSONB structure.
- Modify bronze models to handle both formats: Rejected — violates Constraint 4 (same SQLMesh models for batch and on-demand).
- Single shared adapter base class: Adopted as complement — `BaseAdapter` provides common patterns (response wrapping, metadata injection), each source overrides `normalize()`.

**Key patterns from bronze models**:
- ChEMBL: `response_body->>'molecule_chembl_id'`, `response_body->'molecule_properties'->>'full_molformula'`
- ClinicalTrials: `raw_data->'protocolSection'->'identificationModule'->>'briefTitle'`
- USPTO Patents: Flat structure from PatentSearch API, CPC code arrays
- DrugBank: XML dump → JSONB (highest adapter complexity)

---

## R-003: Rate Limit Registry Design

**Decision**: YAML-based configuration file at `src/dk_data/config/rate_limits.yaml` loaded at startup. Each source entry defines `requests_per_second`, `timeout_seconds`, and `burst_limit`.

**Rationale**: The codebase already has per-source rate limiters (SEC: `SECRateLimiter` at 10 req/sec, PubChem: 5 req/sec in `EnrichmentSettings`). A unified registry consolidates these disparate configs. YAML is updateable without code changes (FR-026).

**Alternatives considered**:
- Database-stored config: Rejected — adds query overhead per request, over-engineering for ~28 static entries.
- Environment variables: Rejected — too many variables (28 sources × 3 params = 84 env vars).
- Python dict in code: Rejected — violates FR-026 requirement for no-code-change updates.

**Existing rate limiter patterns**:
- `src/dk_data/services/external_apis/sec_rate_limiter.py` — token bucket, `SECRateLimiter(requests_per_second=10.0)`
- `src/dk_data/services/external_apis/base_client.py` — `RateLimiter(requests_per_second=float)` with `async acquire()`
- `src/dk_data/core/config.py` — `EnrichmentSettings` with per-source limits

---

## R-004: On-Demand Transform Concurrency Control

**Decision**: PostgreSQL advisory locks per source key. The on-demand transform endpoint acquires `pg_advisory_xact_lock(source_hash)` before invoking SQLMesh. If the lock is held (batch job running), the request returns 409 Conflict with retry-after header.

**Rationale**: The existing `transform_molecules.py` uses `sqlmesh run --select-model {model_name}` which is a CLI invocation. Two concurrent `sqlmesh run` commands targeting the same model can cause state corruption. Advisory locks are lightweight, session-scoped, and automatically released on transaction end.

**Alternatives considered**:
- Redis distributed lock: Rejected — Redis is in dependencies but not deployed in current K8s manifests.
- File-based lock: Rejected — doesn't work across K8s pods.
- Queue-based serialization (Celery/RQ): Rejected — adds operational complexity; advisory locks are sufficient.
- Skip if batch running: Rejected — FR-015 says prevent conflicts, not silently skip.

**Key files**:
- `src/dk_data/ingestion/transform_molecules.py` — `transform_model()`, `run_sqlmesh_command()`, `LAYER_MODELS`
- CronJob `cronjob-mol-transform.yaml` — daily batch schedule

---

## R-005: SQLMesh Model Organization for 15 New Sources

**Decision**: New bronze models go under `src/dk_data/sqlmesh/models/molecules/bronze/` following existing naming. New silver models under `src/dk_data/sqlmesh/models/molecules/silver/`. Models follow existing patterns: `INCREMENTAL_BY_TIME_RANGE` for bronze, `INCREMENTAL_BY_UNIQUE_KEY` for silver.

**Rationale**: The codebase has 17 bronze models, 13 silver models, and 6 gold models already organized under `src/dk_data/sqlmesh/models/molecules/`. The SQLMesh config (`config.yaml`) maps physical schemas (mol_bronze, bronze, silver, etc.) so new models automatically get the correct schema.

**Key patterns**:
- Bronze: `WHERE response_status = 200 AND processed_to_bronze = FALSE AND request_timestamp BETWEEN @start_dt AND @end_dt`
- Silver: `SELECT DISTINCT ON (unique_key) ... ORDER BY unique_key, source_precedence ASC, source_updated_at DESC`
- Gold: CTE-heavy with multiple LEFT JOINs, `INCREMENTAL_BY_UNIQUE_KEY` or `FULL`

**Existing model file counts**: 17 bronze + 13 silver + 6 gold + 5 TAVR = 41 total → expanding to ~62

---

## R-006: PostgREST Schema Exposure Security

**Decision**: Expand `PGRST_DB_SCHEMAS` to `"api,mol_api,mol_gold,mol_silver,xenon,meta"`. Access control via GRANT/REVOKE on individual tables. No row-level security needed for this feature (xenon reads entire tables).

**Rationale**: PostgREST exposes ALL tables in listed schemas by default. The `analyst` role already exists and is granted to `authenticator`. Adding schema-level USAGE + table-level SELECT grants is the standard PostgREST access pattern already used for `api.*` and `mol_api.*`.

**Alternatives considered**:
- API views wrapping gold/silver tables: Rejected — adds indirection without benefit; PostgREST handles filtering/pagination natively.
- Row-level security per molecule: Rejected — xenon needs broad read access, not molecule-scoped restrictions.
- Separate PostgREST instance for xenon: Rejected — over-engineering; single instance with schema routing is standard.

**Security considerations**:
- `web_anon` gets NO grants on new schemas (only `api.health`, `api.data_catalog`)
- `analyst` gets SELECT on mol_gold, mol_silver, meta; SELECT+INSERT+UPDATE on xenon
- `PGRST_DB_SCHEMAS` order matters for default schema resolution — keep `api` first

---

## R-007: Xenon Schema vs mol_app Schema

**Decision**: New `xenon` schema for xenon application data. Existing `mol_app` schema is untouched.

**Rationale**: `mol_app` serves dk-data-FE internal features (user tracking, annotations, alerts with row-level security — see migration `035_application_schema.sql`). Xenon data (assessment content, publication evidence) has different ownership and access patterns. Separate schemas prevent accidental cross-contamination.

**Key files**:
- `src/dk_data/sql/migrations/035_application_schema.sql` — existing mol_app schema
- `k8s/base/db-init-job.yaml` — schema creation, lines defining mol_app

---

## R-008: Gold View Implementation Strategy

**Decision**: KOL/advocacy/trial_outcomes views implemented as SQL views in migration files AND as SQLMesh gold models for automated refresh. The regulatory_timeline and financial_summary views are SQLMesh gold models only (they depend on new silver tables that don't exist yet).

**Rationale**: Existing gold models (molecule_profile, safety_signals, etc.) are SQLMesh models that write to `mol_gold.*` tables. New views should follow the same pattern for consistency and automated refresh via the transform pipeline.

**Key patterns from existing gold models**:
- `molecule_profile.sql`: 11 CTEs, LEFT JOINs to silver tables, `INCREMENTAL_BY_UNIQUE_KEY(unique_key=molecule_id)`
- `safety_signals.sql`: Risk scoring with CASE WHEN, percentile calculations, `INCREMENTAL_BY_UNIQUE_KEY`
- `lifecycle_stages.sql`: `FULL` rebuild each run (complex multi-condition logic)

---

## R-009: Testing Strategy for New Components

**Decision**: Three test tiers: (1) unit tests for adapters using `responses` library mocking, (2) contract tests for SQLMesh models using static SQL parsing, (3) integration tests for MCP tools and transform endpoint using TestClient with mocked DB.

**Rationale**: The codebase has established patterns for all three tiers:
- HTTP mocking: `@responses.activate` in `test_fetchers.py`
- Contract tests: SQL file parsing in `test_bronze_model_contracts.py`
- FastAPI testing: `TestClient` with mocked psycopg2 in `test_fastapi_endpoints.py`
- Security tests: JWT validation in `test_security.py`

**Test targets**:
- 28 adapter unit tests (one per MCP tool source)
- 15 bronze model contract tests
- 6 silver model contract tests
- 8 gold view contract tests
- MCP endpoint integration tests (auth, tool invocation, error handling)
- Transform endpoint integration tests (rate limiting, concurrency, pipeline execution)
- PostgREST schema access tests (analyst role grants, web_anon restrictions)

---

## R-010: KOL Service Integration

**Decision**: Existing KOL router (`src/dk_data/api/routes/kols.py`) and `KOLIntelligenceService` are already functional. The new mol_gold views provide PostgREST-native access to the same data. Both access patterns coexist.

**Rationale**: The KOL router has 4 endpoints already mounted:
- `GET /api/v1/kols/{therapeutic_area}` — KOLs by area
- `GET /api/v1/kols/{kol_id}/network` — KOL network
- `GET /api/v1/advocacy/{indication}` — Advocacy groups
- `POST /api/v1/advocacy/{molecule_id}/sentiment` — Sentiment analysis

The new mol_gold views (`kol_profiles`, `kol_network`, `kol_drug_associations`, `advocacy_groups`, `advocacy_sentiment`) provide equivalent data via PostgREST for the xenon dashboard to consume directly, without going through FastAPI.

**Key files**:
- `src/dk_data/api/routes/kols.py` — existing 4 endpoints
- `src/dk_data/services/kol/` — KOLIntelligenceService (singleton pattern)
