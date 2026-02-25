# Implementation Plan: Assessment Dashboard Integration

**Branch**: `015-assessment-dashboard-integration` | **Date**: 2026-02-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/015-assessment-dashboard-integration/spec.md`

## Summary

Expand the dk-data-FE platform to serve the xenon assessment dashboard by: (1) exposing mol_gold, mol_silver, xenon, and meta schemas via PostgREST with GRANT-based access control, (2) creating application tables for AI-generated assessment content and publication evidence, (3) building 8 new gold-layer views for KOL/advocacy/trial outcomes/regulatory/financial data, (4) implementing 28 MCP on-demand data retrieval tools with per-source adapters that write to existing raw tables, (5) creating 15 new bronze+silver SQLMesh models to fill pipeline gaps, and (6) adding an on-demand transform endpoint that invokes the same SQLMesh models as the daily batch pipeline.

## Technical Context

**Language/Version**: Python 3.11+, SQL (PostgreSQL 16.4)
**Primary Dependencies**: FastAPI >=0.109.0, SQLMesh >=0.90.0, asyncpg >=0.29.0, psycopg2-binary >=2.9.9, httpx >=0.25.0, pyjwt >=2.8.0, Pydantic >=2.5.0, structlog >=24.0.0, OpenTelemetry (tracing+metrics), prometheus-client >=0.19.0, responses >=0.25.0 (test)
**Storage**: PostgreSQL 16.4 via CloudNativePG (`postgresql.infra.svc.cluster.local:5432`, database `dk_data`). Schemas: 15 existing + 1 new (`xenon`). PostgREST v12.2.3 for REST API exposure.
**Testing**: pytest >=8.0 with pytest-cov, pytest-postgresql, responses (HTTP mocking), FastAPI TestClient. Coverage threshold: 15% minimum. CI: GitHub Actions with PostgreSQL service container + PostgREST container.
**Target Platform**: Kubernetes (CloudNativePG cluster, Kustomize overlays for staging/production)
**Project Type**: Single Python backend (FastAPI + SQLMesh + K8s manifests)
**Performance Goals**: <2s standard PostgREST queries (SC-001), <3min on-demand transform (SC-006), <5min MCP tool → refined data availability (SC-004)
**Constraints**: Medallion architecture compliance (7 constraints in spec), per-source rate limits matching upstream APIs, 10 transforms/min/source limit, advisory lock concurrency control
**Scale/Scope**: 28 MCP tools, 15 new SQLMesh models, 8 new gold views, 4 new tables, 28 per-source adapters, ~62 total SQLMesh models after completion

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution file is template-only (not configured for this project). No gates to enforce. Proceeding.

**Post-Phase 1 re-check**: No violations. The design follows existing codebase patterns (FastAPI routers, SQLMesh models, K8s manifests, pytest testing).

## Project Structure

### Documentation (this feature)

```text
specs/015-assessment-dashboard-integration/
├── spec.md              # Feature specification (29 FRs, 13 SCs, 7 constraints)
├── plan.md              # This file
├── research.md          # Phase 0: Technical research & decisions
├── data-model.md        # Phase 1: Entity definitions & relationships
├── quickstart.md        # Phase 1: Developer setup guide
├── contracts/
│   ├── mcp-tools.yaml       # OpenAPI contract for MCP tool endpoints
│   ├── transform-api.yaml   # OpenAPI contract for on-demand transform
│   └── postgrest-schemas.yaml  # PostgREST schema access contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/dk_data/
├── api/
│   ├── routes/
│   │   ├── data_platform.py     # MODIFY: Add transform-raw endpoint
│   │   ├── mcp.py               # NEW: MCP tools router (28 tools)
│   │   └── kols.py              # VERIFY: Existing KOL endpoints
│   ├── middleware/
│   │   └── rbac.py              # EXISTING: require_analyst dependency
│   ├── dependencies.py          # EXISTING: DB pool, service factories
│   └── errors.py                # MODIFY: Add TIMEOUT, EXTERNAL_API_UNAVAILABLE codes
├── ingestion/
│   ├── batch/
│   │   └── api.py               # MODIFY: Register MCP router
│   ├── fetchers/                # EXISTING: 20+ batch fetchers (reference only)
│   └── transform_molecules.py   # MODIFY: Expand LAYER_MODELS registry
├── services/
│   ├── mcp/                     # NEW: MCP tool service layer
│   │   ├── __init__.py
│   │   ├── tool_registry.py     # Tool definitions and registry
│   │   ├── base_tool.py         # Base MCP tool class
│   │   ├── adapters/            # Per-source response normalizers
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # BaseAdapter class
│   │   │   ├── clinicaltrials.py
│   │   │   ├── chembl.py
│   │   │   ├── drugbank.py
│   │   │   └── ... (28 adapter files)
│   │   └── rate_limiter.py      # Unified rate limiter using registry
│   ├── auth/
│   │   └── jwt_service.py       # EXISTING: JWT validation
│   └── external_apis/
│       └── base_client.py       # EXISTING: RateLimiter base class
├── config/
│   └── rate_limits.yaml         # NEW: Per-source rate limits & timeouts
├── sqlmesh/
│   ├── config.yaml              # MODIFY: Add xenon schema mapping if needed
│   └── models/molecules/
│       ├── bronze/
│       │   ├── [existing 17 models]
│       │   ├── pubmed.sql       # NEW
│       │   ├── hta_decisions.sql # NEW
│       │   ├── cochrane_reviews.sql # NEW
│       │   ├── sec_edgar.sql    # NEW
│       │   ├── orcid.sql        # NEW
│       │   ├── journal_rss.sql  # NEW
│       │   ├── medical_news.sql # NEW
│       │   ├── cms_inpatient.sql # NEW
│       │   ├── cms_hospital_info.sql # NEW
│       │   ├── cms_cost_reports.sql # NEW
│       │   ├── acc_tvc.sql      # NEW
│       │   ├── hrsa.sql         # NEW
│       │   ├── pdb_structures.sql # NEW
│       │   └── who_icd.sql      # NEW
│       ├── silver/
│       │   ├── [existing 13 models]
│       │   ├── publications.sql  # MODIFY: Add PubMed/Cochrane/journal UNION blocks
│       │   ├── patents.sql       # MODIFY: Add Orange Book UNION block
│       │   ├── targets.sql       # MODIFY: Add PDB structures UNION block
│       │   ├── regulatory_decisions.sql # NEW
│       │   ├── financial_data.sql # NEW
│       │   ├── researchers.sql   # NEW
│       │   ├── news_signals.sql  # NEW
│       │   ├── healthcare_facilities.sql # NEW
│       │   └── icd_codes.sql    # NEW
│       └── gold/
│           ├── [existing 6 models]
│           ├── kol_profiles.sql         # NEW
│           ├── kol_network.sql          # NEW
│           ├── kol_drug_associations.sql # NEW
│           ├── advocacy_groups.sql       # NEW
│           ├── advocacy_sentiment.sql    # NEW
│           ├── trial_outcomes.sql        # NEW
│           ├── regulatory_timeline.sql   # NEW
│           └── financial_summary.sql     # NEW
└── sql/migrations/
    ├── 074_xenon_schema.sql          # NEW: xenon schema + tables
    ├── 075_pdb_who_raw_tables.sql    # NEW: raw.pdb_structures, raw.who_icd
    └── 076_analyst_grants.sql        # NEW: GRANT statements for new schemas

k8s/
├── base/
│   ├── postgrest/
│   │   └── configmap.yaml            # MODIFY: PGRST_DB_SCHEMAS expansion
│   └── db-init-job.yaml              # MODIFY: Add xenon schema, grants
└── overlays/staging/
    └── kustomization.yaml            # VERIFY: PostgREST config patch

tests/
├── test_mcp_tools.py                 # NEW: MCP endpoint tests
├── test_mcp_adapters.py              # NEW: Per-source adapter unit tests
├── test_transform_endpoint.py        # NEW: On-demand transform tests
├── test_postgrest_schema_access.py   # NEW: Schema grant verification
├── test_xenon_tables.py              # NEW: xenon table contract tests
├── test_bronze_model_contracts.py    # MODIFY: Add 15 new model contracts
├── test_silver_model_contracts.py    # MODIFY: Add 6 new model contracts
└── test_gold_view_contracts.py       # NEW: 8 gold view contract tests
```

**Structure Decision**: Single Python backend project. All new code extends existing directory structure. No new top-level directories. MCP tools are a new service module under `src/dk_data/services/mcp/`. SQLMesh models extend existing `models/molecules/` tree. New migrations follow sequential numbering (074+).

## Implementation Phases

### Phase A: Infrastructure Foundation (Tasks 1, 4) — Blocks everything

**Goal**: Enable PostgREST access to new schemas; verify cross-service connectivity.

**Changes**:
1. Create migration `074_xenon_schema.sql`:
   - `CREATE SCHEMA IF NOT EXISTS xenon`
   - `CREATE TABLE xenon.assessment_generated` (see data-model.md)
   - `CREATE TABLE xenon.publication_evidence` (see data-model.md)
2. Create migration `075_pdb_who_raw_tables.sql`:
   - `CREATE TABLE raw.pdb_structures` (standard raw schema)
   - `CREATE TABLE raw.who_icd` (standard raw schema)
3. Create migration `076_analyst_grants.sql`:
   - GRANT USAGE + SELECT on mol_gold, mol_silver, meta to analyst
   - GRANT USAGE + SELECT/INSERT/UPDATE on xenon to analyst
   - ALTER DEFAULT PRIVILEGES for future tables
4. Update `k8s/base/db-init-job.yaml`:
   - Add xenon schema creation in schema creation block
   - Add GRANT statements in grants block
5. Update `k8s/base/postgrest/configmap.yaml`:
   - Change `PGRST_DB_SCHEMAS: "api,mol_api"` → `"api,mol_api,mol_gold,mol_silver,xenon,meta"`
6. Verify PostgREST accessibility from xenon containers (staging environment)
7. Document environment base URLs in quickstart.md

**Tests**: `test_postgrest_schema_access.py` — analyst can read mol_gold/mol_silver/meta, analyst can write xenon, web_anon cannot access new schemas.

**Acceptance**: SC-001, SC-007, SC-008

---

### Phase B: Application Tables (Tasks 2, 11a) — Blocks AI generation, trial outcomes

**Goal**: xenon tables available for read/write via PostgREST.

**Changes**:
1. `xenon.assessment_generated` already created in Phase A migration
2. `xenon.publication_evidence` already created in Phase A migration
3. Verify tables are accessible via PostgREST with analyst JWT

**Tests**: `test_xenon_tables.py` — write/read round-trip for assessment_generated (all 10 section types), deduplication constraint on (molecule_id, section_type, version), content_hash dedup on publication_evidence.

**Acceptance**: SC-002

---

### Phase C: Gold Views (Tasks 5, 6, 7) — Blocks NestJS endpoints

**Goal**: KOL, advocacy, and trial outcomes views accessible via PostgREST.

**Note**: In tasks.md, gold views are split for dependency management: regulatory_timeline + financial_summary in Phase 7, trial_outcomes in Phase 8, KOL/advocacy in Phase 9.

**Changes**:
1. Create SQLMesh gold models:
   - `gold/kol_profiles.sql` — JOIN silver.researchers + publications + clinical_trials
   - `gold/kol_network.sql` — co-authorship self-join on publications
   - `gold/kol_drug_associations.sql` — researcher-molecule linkage
   - `gold/advocacy_groups.sql` — news_signals aggregation by disease
   - `gold/advocacy_sentiment.sql` — news_signals per molecule
   - `gold/trial_outcomes.sql` — UNION of mol_silver.clinical_trials + xenon.publication_evidence
2. Register in LAYER_MODELS
3. KOL influence formula: `h_index * 0.3 + publications * 0.2 + citations * 0.25 + trials * 0.15 + grants * 0.1`
4. Tier thresholds: PERCENT_RANK() → 95th Global, 80th National, 50th Regional, <50th Rising

**Dependencies**: Phase A (schema access), Phase B (xenon.publication_evidence for trial_outcomes). Note: trial_outcomes UNION from xenon.publication_evidence may have zero rows initially — this is expected.

**Tests**: `test_gold_view_contracts.py` — SQL file parsing for model structure, field presence, JOIN correctness.

**Acceptance**: SC-003, SC-005

---

### Phase D: Pipeline Expansion (15 new bronze+silver models) — Blocks MCP tools

**Goal**: Complete medallion pipeline for all 28 sources.

**Changes**:
1. Create 14 new bronze models (bronze.ema already exists):
   - `bronze/pubmed.sql`, `bronze/hta_decisions.sql`, `bronze/cochrane_reviews.sql`
   - `bronze/sec_edgar.sql`, `bronze/orcid.sql`, `bronze/journal_rss.sql`
   - `bronze/medical_news.sql`, `bronze/cms_inpatient.sql`, `bronze/cms_hospital_info.sql`
   - `bronze/cms_cost_reports.sql`, `bronze/acc_tvc.sql`, `bronze/hrsa.sql`
   - `bronze/pdb_structures.sql`, `bronze/who_icd.sql`
2. Create 6 new silver models:
   - `silver/regulatory_decisions.sql`, `silver/financial_data.sql`
   - `silver/researchers.sql`, `silver/news_signals.sql`
   - `silver/healthcare_facilities.sql`, `silver/icd_codes.sql`
3. Extend 3 existing silver models:
   - `silver/publications.sql` — add PubMed, Cochrane, journal_rss UNION blocks
   - `silver/patents.sql` — add Orange Book UNION block
   - `silver/targets.sql` — add PDB structures UNION block
4. Create 2 remaining gold models:
   - `gold/regulatory_timeline.sql` — cross-join regulatory_decisions + molecules
   - `gold/financial_summary.sql` — cross-join financial_data + molecules
5. Register all in LAYER_MODELS (expand from ~21 to ~44 entries)
6. Validate all models compile: `sqlmesh plan --no-prompts`

**Pattern**: Each bronze model follows `INCREMENTAL_BY_TIME_RANGE`, extracts JSONB fields via `response_body->>'field'`, filters `processed_to_bronze = FALSE AND response_status = 200`. Each silver model uses `INCREMENTAL_BY_UNIQUE_KEY` with `DISTINCT ON` deduplication.

**Tests**: Expand `test_bronze_model_contracts.py` (15 new tests), create `test_silver_model_contracts.py` (6 new tests), `test_gold_view_contracts.py` (2 more tests). CI sqlmesh-validate job covers compilation.

**Acceptance**: SC-013

---

### Phase E: On-Demand Transform Endpoint (Task 14) — Blocks MCP tools

**Goal**: POST endpoint triggers source-specific pipeline transformation.

**Changes**:
1. Add endpoint to data_platform router:
   - `POST /api/v1/data-platform/transform-raw/{source}`
   - Auth: `require_analyst` dependency
   - Rate limit: 10 requests/min/source (in-memory counter)
   - Concurrency: `pg_advisory_xact_lock(hash(source))` before SQLMesh invocation
2. Source → model routing:
   - Look up source in LAYER_MODELS to find bronze/silver/gold model names
   - Determine schema path (mol_raw → mol_bronze or raw → bronze)
   - Invoke `transform_model()` for each layer sequentially
3. Optional `molecule_id` scoping: if provided in request body, filter raw rows to only those matching the molecule before invoking SQLMesh models
4. Return per-layer results with rows_processed and duration

**Tests**: `test_transform_endpoint.py` — rate limit enforcement, advisory lock behavior (mock), model routing correctness, auth requirement.

**Acceptance**: SC-006, SC-010

---

### Phase F: MCP Server (Task 11) — Core feature

**Goal**: 28 on-demand data retrieval tools with adapter-based raw persistence.

**Changes**:
1. Create `src/dk_data/services/mcp/`:
   - `base_tool.py` — BaseMCPTool class with fetch→adapt→persist→transform flow
   - `tool_registry.py` — Tool definitions, input schemas, metadata
   - `rate_limiter.py` — Unified rate limiter loading from `rate_limits.yaml`
   - `adapters/base.py` — BaseAdapter with `normalize()` interface
   - `adapters/{source}.py` — 28 adapter implementations
2. Create `src/dk_data/api/routes/mcp.py`:
   - `GET /api/v1/mcp/tools` — list available tools
   - `POST /api/v1/mcp/tools/{tool_name}/invoke` — invoke a tool
   - Auth: `require_analyst`
   - Error handling: structured responses for timeout, rate limit, external API errors
3. Register MCP router in `api.py`
4. Create `src/dk_data/config/rate_limits.yaml` — per-source limits + timeouts
5. Add error codes to `errors.py`: `TIMEOUT`, `EXTERNAL_API_UNAVAILABLE`

**Tool invocation flow**:
```
Client → POST /mcp/tools/{name}/invoke {drug_name}
  → JWT auth check (analyst role)
  → Rate limit check (per-source, from registry)
  → Fetch from external API (with per-source timeout)
  → Adapter normalizes response → canonical response_body
  → INSERT into raw table (correct schema: mol_raw or raw)
  → Trigger on-demand transform (Phase E endpoint, internal call)
  → Return results + persistence metadata
```

**Priority order for adapter implementation**:
1. High-priority (most used by dashboard): clinicaltrials, chembl, openfda (faers + labels), pubmed, openalex
2. Medium (clinical/regulatory): ema, hta-decisions, cochrane, drugbank, uniprot
3. Medium (IP): uspto-patents, epo-patents, orange-book, uspto-trademarks, euipo-trademarks
4. Lower (supplementary): orcid, sec-edgar, journal-articles, medical-news, who-icd, pdb-structures
5. Context tools: cms-inpatient, cms-hospital-info, cms-cost-reports, acc-tvc, hrsa-hpsa

**Tests**: `test_mcp_tools.py` — endpoint auth, tool listing, invocation flow (mocked external API). `test_mcp_adapters.py` — 28 adapter unit tests verifying `normalize()` output matches bronze model JSONB expectations.

**Acceptance**: SC-004, SC-009, SC-011, SC-012

---

### Phase G: Verification & Auth (Tasks 12, 9, 10)

**Goal**: Cross-service auth validation, data field completeness.

**Changes**:
1. MCP auth verification from xenon containers:
   - Test JWT auth flow end-to-end in staging
   - Document token generation and refresh pattern
2. Verify `mol_silver.clinical_trials` has `end_date` field:
   - Check silver model SQL for end_date extraction
   - If missing, add extraction from `protocolSection.statusModule.completionDateStruct`
3. Verify `mol_gold.company_pipeline` has required fields:
   - indication, mechanism_of_action, enrollment, expected_completion
   - If missing, update gold model to include them

**Tests**: Existing `test_security.py` covers JWT validation. Add field presence assertions to silver/gold contract tests.

**Acceptance**: SC-007

---

### Phase H: Financial Pipeline (Task 8)

**Goal**: Financial data ingestion and gold view.

**Changes**:
1. Bronze model `bronze/sec_edgar.sql` (already created in Phase D)
2. Silver model `silver/financial_data.sql` (already created in Phase D)
3. Gold model `gold/financial_summary.sql` (already created in Phase D)
4. Verify SEC EDGAR fetcher writes compatible `response_body` JSONB
5. Create MCP adapter `adapters/sec_edgar.py` (already part of Phase F)

**Note**: Phase H is largely covered by Phases D and F. This phase is primarily verification that the end-to-end financial pipeline works.

**Acceptance**: SC-004 (for sec-edgar tool specifically)

---

### Phase I: Developer Tooling (Task 13)

**Goal**: Claude skill for adding new MCP tools.

**Changes**:
1. Create `.claude/skills/create-mcp-tool.md`:
   - Template for new adapter file
   - Template for tool registration
   - Template for adapter test
   - Template for bronze model contract test
   - Checklist: raw table exists, bronze model exists, silver model exists, adapter tested

**Acceptance**: Qualitative — developer can use skill to generate tool scaffolding.

---

## Dependency Graph

```
Phase A (Infrastructure) ──────────────────────────────────────────────┐
    │                                                                   │
    ├── Phase B (Application Tables) ───── Phase C (Gold Views) ────┐  │
    │                                          │                     │  │
    │                                          │                     │  │
    ├── Phase D (Pipeline Expansion) ──────────┘                     │  │
    │       │                                                        │  │
    │       └── Phase E (On-Demand Transform) ──┐                    │  │
    │                                            │                   │  │
    │                                            └── Phase F (MCP) ──┤  │
    │                                                    │           │  │
    │                                                    ├── Phase G │  │
    │                                                    ├── Phase H │  │
    │                                                    └── Phase I │  │
    │                                                                │  │
    └────────────────────────────────────────────────────────────────┘  │
```

**Critical path**: A → D → E → F (infrastructure → pipeline models → transform endpoint → MCP tools)

**Parallel opportunities**:
- Phase B and Phase D can proceed in parallel after Phase A
- Phase C can start once Phase B completes (needs xenon.publication_evidence)
- Phase G, H, I can proceed in parallel after Phase F

## Complexity Tracking

No constitution violations to justify. All changes follow existing patterns:
- FastAPI routers (existing pattern in 10 routers)
- SQLMesh models (existing pattern in 41 models)
- K8s manifests (existing Kustomize structure)
- pytest tests (existing 37 test files)
- SQL migrations (existing 36 migration files)

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| DrugBank adapter complexity (XML vs REST) | High — fundamentally different response format | Allocate extra time; adapter is substantial, not minimal |
| SQLMesh model compilation failures at scale (15 new models) | Medium — blocks transform pipeline | Validate incrementally; CI sqlmesh-validate catches regressions |
| PostgREST schema expansion breaks existing queries | High — SC-008 regression | Test existing api/mol_api endpoints before and after schema expansion |
| Advisory lock contention during batch+on-demand overlap | Medium — transforms block each other | 409 Conflict response with retry-after; batch runs at 6 AM UTC (CronJob `mol-transform` schedule `0 6 * * *`) |
| Rate limit registry YAML parsing errors | Low — misconfigured limits | Validate YAML at startup; fail-fast with clear error |
