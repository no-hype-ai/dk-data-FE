# Tasks: Assessment Dashboard Integration

**Input**: Design documents from `/specs/015-assessment-dashboard-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are included inline where they provide critical safety (regression, contract validation, adapter correctness). The spec requires adapter integration tests (FR-025, SC-012) and schema access tests (SC-008).

**Organization**: Tasks grouped by user story in priority order. Pipeline expansion is a cross-cutting prerequisite extracted into its own phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Migration framework and shared infrastructure files

- [x] T001 Create migration file `src/dk_data/sql/migrations/074_xenon_schema.sql` with CREATE SCHEMA xenon, CREATE TABLE xenon.assessment_generated (columns per data-model.md: id UUID PK, molecule_id, section_type, content JSONB, version, generation_source, generation_metadata, created_at, updated_at; UNIQUE on molecule_id+section_type+version), CREATE TABLE xenon.publication_evidence (columns per data-model.md: id UUID PK, molecule_id, trial_nct_id, endpoint_name, endpoint_type, hazard_ratio, p_value, response_rate, median_survival_months, sample_size, confidence_score CHECK 0-1, evidence_source, doi, pmid, extraction_metadata, content_hash UNIQUE, created_at)
- [x] T002 [P] Create migration file `src/dk_data/sql/migrations/075_pdb_who_raw_tables.sql` with CREATE TABLE raw.pdb_structures and raw.who_icd following standard raw schema pattern (id UUID, request_id, request_timestamp, api_endpoint, api_version, request_params JSONB, request_headers JSONB, response_status, response_headers JSONB, response_body JSONB, response_body_hash, response_size_bytes, response_time_ms, processed_to_bronze BOOLEAN DEFAULT FALSE, processed_at, processing_error, ingested_at, source_id) with indexes on request_id, request_timestamp, processed_to_bronze, response_body_hash
- [x] T003 [P] Create migration file `src/dk_data/sql/migrations/076_analyst_grants.sql` with GRANT USAGE ON SCHEMA mol_gold/mol_silver/xenon/meta TO analyst, GRANT SELECT ON ALL TABLES IN SCHEMA mol_gold/mol_silver/meta TO analyst, GRANT SELECT+INSERT+UPDATE ON ALL TABLES IN SCHEMA xenon TO analyst, ALTER DEFAULT PRIVILEGES for future tables in each schema
- [x] T004 [P] Create rate limit registry file `src/dk_data/config/rate_limits.yaml` with defaults section (timeout_seconds=30, base_delay_seconds=1, max_delay_seconds=30, max_retries=3, jitter=true) and per-source entries for all 28 sources (requests_per_second, timeout_seconds, burst_limit, optional per-source overrides for backoff params) based on upstream API published limits — see data-model.md for initial values
- [x] T005 [P] Create MCP service package `src/dk_data/services/mcp/__init__.py` and adapter package `src/dk_data/services/mcp/adapters/__init__.py` (empty init files establishing package structure)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: PostgREST schema expansion and database role grants — MUST complete before any user story

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Update `k8s/base/db-init-job.yaml` to add xenon schema creation (`CREATE SCHEMA IF NOT EXISTS xenon;`) in the schema creation block alongside existing schemas, and add all GRANT statements from migration 076 in the grants block (USAGE + SELECT on mol_gold/mol_silver/meta to analyst, USAGE + SELECT/INSERT/UPDATE on xenon to analyst)
- [x] T007 Update `k8s/base/postgrest/configmap.yaml` to change `PGRST_DB_SCHEMAS` from `"api,mol_api"` to `"api,mol_api,mol_gold,mol_silver,xenon,meta"` — keep api first for default schema resolution
- [x] T008 Update `k8s/overlays/staging/kustomization.yaml` if it patches PostgREST configmap — verify the PGRST_DB_SCHEMAS patch is consistent with the new base value or remove the patch if base now includes the correct value
- [x] T009 Update CI workflow `.github/workflows/ci.yaml` test job to add xenon schema creation and grants in the database initialization step, and add mol_gold/mol_silver/xenon/meta to PGRST_DB_SCHEMAS in the PostgREST startup command
- [x] T010 Add error codes TIMEOUT and EXTERNAL_API_UNAVAILABLE to the ErrorCode enum in `src/dk_data/api/errors.py`, and add corresponding exception classes (TimeoutError, ExternalAPIUnavailableError) with appropriate HTTP status codes (408, 502)

**Checkpoint**: Foundation ready — PostgREST exposes new schemas, analyst role has correct grants, CI reflects changes

---

## Phase 3: User Story 1 — Xenon Dashboard Reads Molecule Data (Priority: P1) MVP

**Goal**: Authenticated analyst users can query mol_gold, mol_silver, xenon, and meta tables via PostgREST

**Independent Test**: Issue authenticated requests against molecule profile tables and verify data is returned. Issue unauthenticated requests and verify 401/403. Verify existing api/mol_api endpoints unchanged.

- [x] T011 [US1] Create test file `tests/test_postgrest_schema_access.py` with TestAnalystSchemaAccess class testing: analyst can SELECT from mol_gold (molecule_profile), analyst can SELECT from mol_silver, analyst can SELECT from meta, web_anon CANNOT access mol_gold/mol_silver/xenon/meta. Use conftest.py postgrest_client fixture and create_jwt_token helper pattern from test_security.py
- [x] T012 [US1] Create test file `tests/test_regression_existing_endpoints.py` verifying SC-008: existing api.health and api.data_catalog endpoints return same structure, existing mol_api endpoints (if any data) continue functioning, web_anon access to api.health still works — all after PGRST_DB_SCHEMAS expansion
- [x] T013 [US1] Document environment-specific PostgREST base URLs (FR-019) by updating `specs/015-assessment-dashboard-integration/quickstart.md` with verified URLs: local (localhost:3000), staging (data.staging.behaviorlabs.ai), production (data.behaviorlabs.ai)

**Checkpoint**: PostgREST serves new schemas. Existing endpoints unchanged. SC-001, SC-007, SC-008 verifiable.

---

## Phase 4: User Story 2 + User Story 7 — Assessment Content & Publication Evidence Storage (Priority: P1+P3)

**Goal**: xenon.assessment_generated and xenon.publication_evidence tables are writable and readable via PostgREST with analyst JWT

**Independent Test**: Write an assessment record via PostgREST POST, read it back, verify integrity. Write a publication evidence record, verify content_hash dedup. Test all 10 section types.

- [x] T014 [US2] Create test file `tests/test_xenon_tables.py` with: TestAssessmentGenerated — write/read round-trip for all 10 section types, unique constraint violation on duplicate (molecule_id, section_type, version), version incrementing; TestPublicationEvidence — write/read round-trip, content_hash dedup prevents duplicates, confidence_score CHECK constraint rejects values outside 0-1 range. Use postgrest_client with analyst JWT.
- [x] T015 [US2] Verify xenon tables are accessible via PostgREST by running migration 074 against test database and confirming analyst role can INSERT and SELECT on xenon.assessment_generated and xenon.publication_evidence through PostgREST

**Checkpoint**: xenon tables operational. SC-002 verifiable. Publication evidence ready for US5 trial outcomes UNION.

---

## Phase 5: Pipeline Expansion — Bronze Models (Cross-Cutting Prerequisite)

**Purpose**: Create 14 new bronze SQLMesh models (bronze.ema already exists). Required by US3 (KOL/advocacy views need silver.researchers, silver.news_signals), US4 (MCP tools need complete pipeline), US5 (trial_outcomes needs data), US6 (transform needs models to invoke).

### Clinical/Regulatory Bronze Models

- [x] T016 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/pubmed.sql` — INCREMENTAL_BY_TIME_RANGE on request_timestamp, extract from raw.pubmed: pmid (response_body->>'uid'), title, abstract, authors (jsonb), journal, pub_date, mesh_terms (jsonb), doi. Filter: response_status=200 AND processed_to_bronze=FALSE. Output: processed_to_silver=FALSE
- [x] T017 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/hta_decisions.sql` — extract from raw.hta_decisions: agency, drug_name, indication, decision, decision_date, recommendation, therapeutic_area. Same incremental pattern.
- [x] T018 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/cochrane_reviews.sql` — extract from raw.cochrane_reviews: review_id, title, authors, abstract, pub_date, doi, review_type. Same incremental pattern.

### Financial/Competitive Bronze Models

- [x] T019 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/sec_edgar.sql` — extract from raw.sec_edgar: cik, company_name, filing_type, filing_date, revenue, net_income, total_assets. Same incremental pattern.

### Research/KOL Bronze Models

- [x] T020 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/orcid.sql` — extract from raw.orcid: orcid_id, given_name, family_name, affiliations (jsonb), works_count, research_areas. Same incremental pattern.

### Literature/News Bronze Models

- [x] T021 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/journal_rss.sql` — extract from raw.journal_rss: title, link, pub_date, journal_name, summary, authors, doi. Same incremental pattern.
- [x] T022 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/medical_news.sql` — extract from raw.medical_news: title, link, pub_date, source_name, summary, drug_mentions (jsonb), sentiment. Same incremental pattern.

### Healthcare Infrastructure Bronze Models

- [x] T023 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/cms_inpatient.sql` — extract from raw.cms_medicare_inpatient: provider_id, drg_code, total_discharges, avg_charges, avg_payments, fiscal_year. Same incremental pattern.
- [x] T024 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/cms_hospital_info.sql` — extract from raw.cms_hospital_info: provider_id, hospital_name, city, state, hospital_type, ownership, rating. Same incremental pattern.
- [x] T025 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/cms_cost_reports.sql` — extract from raw.cms_cost_reports: provider_id, fiscal_year, total_costs, net_revenue, operating_margin, bed_count. Same incremental pattern.
- [x] T026 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/acc_tvc.sql` — extract from raw.acc_tvc_certification: facility_id, facility_name, city, state, certification_type, cert_date, volumes. Same incremental pattern.
- [x] T027 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/hrsa.sql` — extract from raw.hrsa_shortage_areas: hpsa_id, designation_type, state, county, discipline, score, status. Same incremental pattern.

### New Source Bronze Models

- [x] T028 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/pdb_structures.sql` — extract from raw.pdb_structures: pdb_id, title, resolution, method, organism, ligand_id, ligand_name, uniprot_id. Same incremental pattern.
- [x] T029 [P] Create bronze model `src/dk_data/sqlmesh/models/molecules/bronze/who_icd.sql` — extract from raw.who_icd: icd_code, title, chapter, block_id, category, includes, excludes. Same incremental pattern.

### Bronze Contract Tests

- [x] T030 Extend `tests/test_bronze_model_contracts.py` with contract tests for all 14 new bronze models (bronze.ema already exists) — verify model name, kind (INCREMENTAL_BY_TIME_RANGE), time_column, grain, processed_to_silver output field. Follow existing TestBronzeUSPTOPatents pattern using _read_model_sql() and _extract_model_block() helpers.

**Checkpoint**: All 14 new bronze models created and validated via contract tests. sqlmesh plan --no-prompts compiles without errors.

---

## Phase 6: Pipeline Expansion — Silver Models (Cross-Cutting Prerequisite)

**Purpose**: Create 6 new silver models and extend 3 existing ones. Required by gold views and MCP tools.

### New Silver Models

- [x] T031 [P] Create silver model `src/dk_data/sqlmesh/models/molecules/silver/regulatory_decisions.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(agency, drug_name, indication, decision_date)), UNION from bronze.ema + bronze.hta_decisions with source attribution. DISTINCT ON dedup with source precedence.
- [x] T032 [P] Create silver model `src/dk_data/sqlmesh/models/molecules/silver/financial_data.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(cik, filing_type, filing_date)), from bronze.sec_edgar. Fields: cik, company_name, filing_type, filing_date, revenue, net_income, total_assets.
- [x] T033 [P] Create silver model `src/dk_data/sqlmesh/models/molecules/silver/researchers.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=orcid_id), from bronze.orcid. Fields: orcid_id, given_name, family_name, affiliation, country, works_count, h_index, research_areas, therapeutic_areas.
- [x] T034 [P] Create silver model `src/dk_data/sqlmesh/models/molecules/silver/news_signals.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(source_url, pub_date)), from bronze.medical_news. Fields: title, source_name, pub_date, source_url, drug_mentions, sentiment_polarity, sentiment_score, therapeutic_area, signal_type.
- [x] T035 [P] Create silver model `src/dk_data/sqlmesh/models/molecules/silver/healthcare_facilities.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(provider_id, source)), UNION from bronze.cms_inpatient + bronze.cms_hospital_info + bronze.cms_cost_reports + bronze.acc_tvc + bronze.hrsa with source attribution. Consolidate per provider_id.
- [x] T036 [P] Create silver model `src/dk_data/sqlmesh/models/molecules/silver/icd_codes.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=icd_code), from bronze.who_icd. Fields: icd_code, title, chapter, block_id, category, parent_code, is_leaf.

### Extend Existing Silver Models

- [x] T037 Extend `src/dk_data/sqlmesh/models/molecules/silver/publications.sql` by adding UNION ALL blocks for bronze.pubmed, bronze.cochrane_reviews, and bronze.journal_rss alongside existing OpenAlex source. Maintain existing DISTINCT ON dedup and source precedence logic.
- [x] T038 [P] Extend `src/dk_data/sqlmesh/models/molecules/silver/patents.sql` by adding UNION ALL block for bronze.orange_book alongside existing USPTO/EPO/DrugBank sources. Add source='orange_book' and appropriate precedence ranking.
- [x] T039 [P] Extend `src/dk_data/sqlmesh/models/molecules/silver/targets.sql` by adding UNION ALL block for bronze.pdb_structures alongside existing UniProt source. Map pdb_id, ligand info, resolution to target fields.

### Silver Contract Tests

- [x] T040 Create `tests/test_silver_model_contracts.py` with contract tests for 6 new silver models — verify model name, kind (INCREMENTAL_BY_UNIQUE_KEY), unique_key fields, source UNION blocks where applicable. Follow bronze contract test pattern.

**Checkpoint**: All silver models created/extended. Pipeline: raw → bronze → silver complete for all 28 sources.

---

## Phase 7: Pipeline Expansion — Gold Models + Registry (Cross-Cutting Prerequisite)

**Purpose**: Create gold models for regulatory timeline and financial summary. Register all new models in LAYER_MODELS.

- [x] T041 [P] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/regulatory_timeline.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(molecule_id, agency, decision_date)), cross-join silver.regulatory_decisions with mol_silver.molecules_from_bronze (via drug_name/active_substance matching). Output: molecule_id, drug_name, agency, decision, decision_date, indication, recommendation_details.
- [x] T042 [P] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/financial_summary.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(molecule_id, cik)), cross-join silver.financial_data with mol_silver.molecules_from_bronze (via company_name linkage). Output: molecule_id, company_name, cik, latest_revenue, latest_net_income, total_assets, filing_count, latest_filing_date.
- [x] T043 Update LAYER_MODELS dictionary in `src/dk_data/ingestion/transform_molecules.py` to add all new models: 15 entries to ip_bronze (bronze.pubmed, bronze.ema, bronze.hta_decisions, bronze.cochrane_reviews, bronze.sec_edgar, bronze.orcid, bronze.journal_rss, bronze.medical_news, bronze.cms_inpatient, bronze.cms_hospital_info, bronze.cms_cost_reports, bronze.acc_tvc, bronze.hrsa, bronze.pdb_structures, bronze.who_icd), 8 entries to ip_silver (silver.publications, silver.targets, silver.regulatory_decisions, silver.financial_data, silver.researchers, silver.news_signals, silver.healthcare_facilities, silver.icd_codes), 8 entries to gold+ip_gold (mol_gold.kol_profiles, kol_network, kol_drug_associations, advocacy_groups, advocacy_sentiment, trial_outcomes, regulatory_timeline, financial_summary). Follow existing list format.
- [x] T044 Validate all new SQLMesh models compile by running `sqlmesh -p src/dk_data/sqlmesh plan --no-prompts` and verifying zero compilation errors for all new bronze, silver, and gold models

**Checkpoint**: Complete medallion pipeline for all 28 sources. LAYER_MODELS registry expanded. SC-013 verifiable.

---

## Phase 8: User Story 5 — Combined Trial Outcomes (Priority: P2)

**Goal**: Unified mol_gold.trial_outcomes view combining structured registry data and publication-extracted evidence

**Independent Test**: Query trial_outcomes for a molecule and verify rows from both evidence sources appear with appropriate confidence scores.

- [x] T045 [US5] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/trial_outcomes.sql` — FULL model (rebuilt each run). UNION ALL of: (1) SELECT from mol_silver.clinical_trials WHERE results data is not null → evidence_source='clinicaltrials_gov', confidence_score=1.0; (2) SELECT from xenon.publication_evidence WHERE confidence_score >= 0.40 → evidence_source='publication'. Output fields: molecule_id, trial_nct_id, evidence_source, endpoint_name, hazard_ratio, p_value, response_rate, sample_size, confidence_score, evidence_date.
- [x] T046 [US5] Add mol_gold.trial_outcomes to LAYER_MODELS gold list in `src/dk_data/ingestion/transform_molecules.py` (if not already added in T043)
- [x] T047 [US5] Add trial_outcomes contract test to `tests/test_gold_view_contracts.py` — verify UNION ALL structure, confidence threshold filter (>=0.40), both evidence sources present, model kind is FULL

**Checkpoint**: Trial outcomes view returns combined evidence. SC-005 verifiable.

---

## Phase 9: User Story 3 — KOL and Advocacy Data (Priority: P2)

**Goal**: mol_gold KOL and advocacy views accessible via PostgREST for xenon dashboard

**Independent Test**: Query kol_profiles filtered by therapeutic area and verify researcher records with all influence metrics. Query advocacy_sentiment by molecule and verify sentiment signals.

**Dependencies**: Requires silver.researchers (T033) and silver.news_signals (T034) from Phase 6.

- [x] T048 [P] [US3] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/kol_profiles.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=researcher_id). JOIN silver.researchers + silver.publications (COUNT) + mol_silver.clinical_trials (COUNT). Compute influence_score = h_index*0.3 + publications*0.2 + citations*0.25 + trials*0.15 + grants*0.1. Compute influence_tier via PERCENT_RANK(): >=0.95 'Global', >=0.80 'National', >=0.50 'Regional', else 'Rising'. FR-018.
- [x] T049 [P] [US3] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/kol_network.sql` — FULL model. Self-join silver.publications on shared publications to build co-authorship edges. Output: source_researcher_id, target_researcher_id, shared_publications COUNT, connection_type='co_author'.
- [x] T050 [P] [US3] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/kol_drug_associations.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(researcher_id, molecule_id)). JOIN silver.researchers with mol_silver.clinical_trials (investigator) + silver.publications (author) + grants. Output: researcher_id, molecule_id, drug_name, association_types (array), evidence_count.
- [x] T051 [P] [US3] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/advocacy_groups.sql` — FULL model. Aggregate silver.news_signals by disease/indication focus. Output: group_id, organization_name, disease_focus, size_estimate, activities, indication.
- [x] T052 [P] [US3] Create gold model `src/dk_data/sqlmesh/models/molecules/gold/advocacy_sentiment.sql` — INCREMENTAL_BY_UNIQUE_KEY(unique_key=(molecule_id, source)). Aggregate silver.news_signals per molecule (via drug_mentions linkage). Output: molecule_id, source, sentiment_polarity, signal_count, recent_signals (jsonb_agg top 10), time_period.
- [x] T053 [US3] Add all 5 KOL/advocacy gold models to LAYER_MODELS in `src/dk_data/ingestion/transform_molecules.py` (if not already added in T043) and add contract tests for each in `tests/test_gold_view_contracts.py` — verify influence formula, tier thresholds, UNION/JOIN structure

**Checkpoint**: KOL and advocacy views queryable via PostgREST. SC-003 verifiable.

---

## Phase 10: User Story 6 — On-Demand Transform Endpoint (Priority: P3)

**Goal**: POST endpoint triggers raw→bronze→silver→gold pipeline for a specific source using same SQLMesh models as batch

**Independent Test**: Insert a raw record, trigger transform via POST, verify record appears in bronze/silver within 3 minutes.

**Dependencies**: Requires LAYER_MODELS expansion (T043) from Phase 7.

- [x] T054 [US6] Implement on-demand transform endpoint in `src/dk_data/api/routes/data_platform.py` — add POST /api/v1/data-platform/transform-raw/{source} per contracts/transform-api.yaml. Auth: require_analyst dependency. Accepts optional molecule_id in body. Returns per-layer results with rows_processed and duration.
- [x] T055 [US6] Implement source→model routing logic in transform endpoint: look up source name in LAYER_MODELS to find bronze/silver/gold model names, determine schema path (mol_raw sources → mol_bronze/mol_silver/mol_gold vs raw sources → bronze/silver/gold), invoke transform_model() for each layer sequentially. Handle sources that span both pipelines. If optional molecule_id is provided in request body, filter unprocessed raw rows to only those matching the molecule before invoking SQLMesh models (FR-013).
- [x] T056 [US6] Implement rate limiting for transform endpoint: in-memory counter per source, limit 10 requests/min/source (FR-014). Return 429 with retry_after header when exceeded.
- [x] T057 [US6] Implement PostgreSQL advisory lock concurrency control: acquire pg_advisory_xact_lock(hashtext(source)) before invoking SQLMesh. If lock acquisition fails (batch job running), return 409 Conflict with retry_after header (FR-015). Use asyncpg connection from dependency pool.
- [x] T058 [US6] Create test file `tests/test_transform_endpoint.py` with: test_auth_required (401 without JWT), test_analyst_can_trigger (200 with analyst JWT), test_rate_limit_enforced (429 after 10 rapid requests), test_source_routing_mol_raw (clinicaltrials routes to mol_bronze), test_source_routing_raw (pubmed routes to bronze), test_unknown_source_404, test_molecule_id_scoping (optional molecule_id filters raw rows before transform). Use TestClient with mocked transform_model().

**Checkpoint**: On-demand transform functional. SC-006, SC-010 verifiable.

---

## Phase 11: User Story 4 — On-Demand MCP Data Retrieval (Priority: P2)

**Goal**: 28 MCP tools fetch drug-specific data from external APIs, persist to raw tables via adapters, trigger transform

**Independent Test**: Invoke clinicaltrials-search with drug_name="durvalumab", verify results returned, data persisted to mol_raw.clinicaltrials, data available in silver within 5 minutes.

**Dependencies**: Requires transform endpoint (Phase 10) and pipeline models (Phases 5-7).

### MCP Framework

- [x] T059 [US4] Create base adapter class in `src/dk_data/services/mcp/adapters/base.py` — BaseAdapter with abstract normalize(api_response: dict) -> dict method, validate_against_bronze(normalized: dict) -> bool method stub, source_name property, raw_table property, raw_schema property ('mol_raw' or 'raw').
- [x] T060 [US4] Create unified rate limiter in `src/dk_data/services/mcp/rate_limiter.py` — load rate_limits.yaml at startup, expose async acquire(source: str) method using token bucket algorithm (extend existing RateLimiter pattern from base_client.py), expose get_timeout(source: str) -> float method. Fail-fast with clear error if YAML is malformed.
- [x] T061 [US4] Create base MCP tool class in `src/dk_data/services/mcp/base_tool.py` — BaseMCPTool with: async invoke(input: dict) -> dict method implementing the flow: rate_limit_check → fetch_external_api (httpx with per-source timeout) → adapter.normalize() → insert_raw_record() → trigger_transform() → return_results. Handle timeout (408), rate limit (429), external API error (502). Use structured error responses per contracts/mcp-tools.yaml ErrorResponse schema.
- [x] T062 [US4] Create tool registry in `src/dk_data/services/mcp/tool_registry.py` — ToolDefinition dataclass (name, description, tier, raw_table, adapter_class, input_schema dict), TOOL_REGISTRY dict mapping tool_name → ToolDefinition for all 28 tools. Group by tier: 19 direct_query, 4 fetch_filter, 5 supplementary.
- [x] T063 [US4] Create MCP router in `src/dk_data/api/routes/mcp.py` — GET /api/v1/mcp/tools (list tools from registry), POST /api/v1/mcp/tools/{tool_name}/invoke (validate tool exists, auth require_analyst, instantiate tool, call invoke, return ToolInvocationResponse). Per contracts/mcp-tools.yaml.
- [x] T064 [US4] Register MCP router in `src/dk_data/ingestion/batch/api.py` — add try/except import and app.include_router for mcp_router with prefix="/api/v1" and tags=["mcp"]. Follow existing router registration pattern.

### Tier 1 Adapters — High Priority (molecule-specific sources)

- [x] T065 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/clinicaltrials.py` — normalize ClinicalTrials.gov v2 search API response to match mol_raw.clinicaltrials response_body format (protocolSection nesting). Substantial adapter: search endpoint returns different structure than bulk study endpoint.
- [x] T066 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/chembl.py` — normalize ChEMBL REST search response to match mol_raw.chembl response_body format (molecule_chembl_id, molecule_properties nesting). Moderate adapter.
- [x] T067 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/openfda_faers.py` — normalize OpenFDA drug/event search response to match mol_raw.openfda_faers response_body format. Moderate adapter.
- [x] T068 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/openfda_labels.py` — normalize OpenFDA drug/label search response to match mol_raw.openfda_labels response_body format. Shared table with openfda-approvals tool.
- [x] T069 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/drugbank.py` — normalize DrugBank REST API JSON response to match mol_raw.drugbank response_body format (XML dump structure). SUBSTANTIAL adapter: fundamentally different format (REST JSON vs XML).
- [x] T070 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/pubmed.py` — normalize PubMed eutils esearch+efetch response to match raw.pubmed response_body format. Minimal adapter: same eutils API.
- [x] T071 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/openalex.py` — normalize OpenAlex works search response to match mol_raw.openalex response_body format. Minimal adapter: same search API.
- [x] T072 [P] [US4] Create adapter `src/dk_data/services/mcp/adapters/uniprot.py` — normalize UniProt REST search response to match mol_raw.uniprot response_body format. Minimal adapter: same REST query.

### Tier 1 Adapters — Regulatory/IP Sources

- [x] T073 [P] [US4] Create adapters for regulatory sources in `src/dk_data/services/mcp/adapters/`: ema.py (raw.ema, moderate), hta_decisions.py (raw.hta_decisions, minimal), cochrane.py (raw.cochrane_reviews, minimal), orange_book.py (raw.orange_book, moderate). Each normalizes search response to match corresponding raw table response_body format.
- [x] T074 [P] [US4] Create adapters for IP sources in `src/dk_data/services/mcp/adapters/`: uspto_patents.py (raw.uspto_patents, minimal), epo_patents.py (raw.epo_patents, minimal), sec_edgar.py (raw.sec_edgar, moderate — full-text search vs SIC-code bulk). Each normalizes response to match raw table format.

### Tier 1 Adapters — Remaining Direct Query

- [x] T075 [P] [US4] Create adapters for remaining Tier 1 tools in `src/dk_data/services/mcp/adapters/`: who_icd.py (raw.who_icd, new table), pdb_structures.py (raw.pdb_structures, new table), orcid.py (raw.orcid, minimal). Each normalizes response to match raw table format.

### Tier 2+3 Adapters — Fetch/Filter and Supplementary

- [x] T076 [P] [US4] Create adapters for Tier 2 fetch+filter tools in `src/dk_data/services/mcp/adapters/`: journal_rss.py (raw.journal_rss, minimal), medical_news.py (raw.medical_news, minimal), uspto_trademarks.py (raw.uspto_trademarks, minimal), euipo_trademarks.py (raw.euipo_trademarks, minimal).
- [x] T077 [P] [US4] Create adapters for Tier 3 supplementary tools in `src/dk_data/services/mcp/adapters/`: cms_inpatient.py (raw.cms_medicare_inpatient, minimal), cms_hospital_info.py (raw.cms_hospital_info, minimal), cms_cost_reports.py (raw.cms_cost_reports, minimal), acc_tvc.py (raw.acc_tvc_certification, minimal), hrsa.py (raw.hrsa_shortage_areas, minimal).

### MCP Tests

- [x] T078 [US4] Create test file `tests/test_mcp_tools.py` with: test_list_tools_returns_28 (GET /mcp/tools), test_invoke_requires_auth (401 without JWT), test_invoke_requires_analyst (403 with viewer JWT), test_invoke_unknown_tool_404, test_invoke_clinicaltrials_success (mock external API with @responses.activate, verify response structure matches ToolInvocationResponse), test_invoke_timeout_returns_408 (mock slow API), test_invoke_rate_limited_429. Use TestClient.
- [x] T079 [US4] Create test file `tests/test_mcp_adapters.py` with adapter unit tests for high-complexity adapters: test_clinicaltrials_adapter_normalize (verify JSONB paths match bronze model expectations), test_chembl_adapter_normalize, test_drugbank_adapter_normalize (most critical — XML vs REST), test_openfda_faers_adapter_normalize. Use @responses.activate to mock external APIs. Verify FR-025 (adapter output parseable by bronze model).

**Checkpoint**: All 28 MCP tools operational. SC-004, SC-009, SC-011, SC-012 verifiable.

---

## Phase 12: User Story 8 — Cross-Service Authentication (Priority: P3)

**Goal**: Verify JWT auth flow works from xenon containers to dk-data-FE PostgREST and MCP endpoints

**Independent Test**: Generate analyst JWT, make authenticated request from xenon container environment, verify data returned.

- [x] T080 [US8] Add staging connectivity verification test to `tests/test_security.py` — new TestCrossServiceAuth class testing: analyst JWT grants access to mol_gold tables, analyst JWT grants read+write on xenon schema, analyst JWT grants access to MCP tools endpoint. Mark with @pytest.mark.integration for selective CI execution.
- [x] T081 [US8] Create environment connectivity documentation in `specs/015-assessment-dashboard-integration/quickstart.md` — add section documenting JWT token generation pattern for xenon (role=analyst, secret from Doppler), base URL per environment, curl examples for PostgREST and MCP endpoints

**Checkpoint**: Cross-service auth verified. SC-007 verifiable across environments.

---

## Phase 13: User Story 9 — Financial Data Pipeline (Priority: P4)

**Goal**: Financial data ingestion and mol_gold.financial_summary view operational

**Independent Test**: Query financial_summary for a company and verify structured financial metrics returned.

- [x] T082 [US9] Verify SEC EDGAR fetcher (`src/dk_data/ingestion/fetchers/sec_edgar.py`) writes response_body in format compatible with bronze.sec_edgar model (T019). If format mismatch, update adapter or document required fetcher changes.
- [x] T083 [US9] Run end-to-end test: trigger sec_edgar ingestion → verify bronze.sec_edgar processes records → verify silver.financial_data populated → verify mol_gold.financial_summary returns data for known companies

**Checkpoint**: Financial pipeline operational. Contributes to SC-004 for sec-edgar tool.

---

## Phase 14: User Story 10 — Data Field Verification (Priority: P4)

**Goal**: Clinical trial end_date and company pipeline detail fields exist and are populated

**Independent Test**: Query mol_silver.clinical_trials and verify end_date field present. Query mol_gold.company_pipeline and verify indication, mechanism_of_action, enrollment, expected_completion fields present.

- [x] T084 [US10] Verify end_date field exists in silver clinical_trials model `src/dk_data/sqlmesh/models/molecules/silver/clinical_trials.sql` — check for extraction from raw_data->'protocolSection'->'statusModule'->'completionDateStruct'->>'date'. If missing, add the extraction with appropriate date parsing.
- [x] T085 [US10] Verify mol_gold.company_pipeline model `src/dk_data/sqlmesh/models/molecules/gold/company_pipeline.sql` includes fields: indication, mechanism_of_action, enrollment, expected_completion. If missing, add extraction from appropriate silver sources and update gold model.

**Checkpoint**: Dashboard can render trial duration bars and pipeline detail views.

---

## Phase 15: User Story 11 — Developer Tooling (Priority: P4)

**Goal**: Claude skill for streamlined MCP tool creation

**Independent Test**: Invoke skill with a hypothetical data source description and verify all generated files have correct structure.

- [x] T086 [US11] Create Claude skill file `.claude/skills/create-mcp-tool.md` with instructions for: (1) creating adapter file from template (src/dk_data/services/mcp/adapters/{source}.py), (2) adding tool to TOOL_REGISTRY in tool_registry.py, (3) creating adapter unit test, (4) creating bronze model contract test, (5) checklist: raw table exists, bronze model exists, silver model exists, adapter tested against bronze, tool registered. Include inline code templates for each file.

**Checkpoint**: Developer experience skill available for extending MCP tools.

---

## Phase 16: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, validation, and cross-story integration

- [x] T087 Run full SQLMesh validation: `sqlmesh -p src/dk_data/sqlmesh plan --no-prompts` — verify all ~62 models compile without errors
- [x] T088 Run full test suite: `pytest tests/ -v` — verify all new and existing tests pass, coverage meets 15% threshold
- [x] T089 Verify PostgREST regression: run existing test_security.py and test_api.py tests to confirm SC-008 (no regression in existing endpoints after PGRST_DB_SCHEMAS expansion)
- [x] T090 [P] Update `src/dk_data/sqlmesh/config.yaml` if xenon schema needs physical schema mapping for SQLMesh (check if any model references xenon tables and needs schema resolution)
- [x] T091 [P] Validate Kubernetes manifests: `kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null` — ensure staging overlay builds with updated PostgREST configmap
- [x] T092 Run quickstart.md validation — follow setup steps on clean local environment to verify developer onboarding works

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1)**: Depends on Phase 2
- **Phase 4 (US2+US7)**: Depends on Phase 2 — can run in parallel with Phase 3
- **Phase 5 (Bronze Models)**: Depends on Phase 2 — can run in parallel with Phases 3-4
- **Phase 6 (Silver Models)**: Depends on Phase 5
- **Phase 7 (Gold Models + Registry)**: Depends on Phase 6
- **Phase 8 (US5 Trial Outcomes)**: Depends on Phase 4 (xenon.publication_evidence) + Phase 7 (LAYER_MODELS)
- **Phase 9 (US3 KOL/Advocacy)**: Depends on Phase 6 (silver.researchers, silver.news_signals)
- **Phase 10 (US6 Transform)**: Depends on Phase 7 (LAYER_MODELS expansion)
- **Phase 11 (US4 MCP Tools)**: Depends on Phase 10 (transform endpoint) + Phase 7 (pipeline models)
- **Phase 12 (US8 Auth)**: Depends on Phase 3 (schema access) + Phase 11 (MCP endpoint)
- **Phase 13 (US9 Financial)**: Depends on Phase 7 (financial models)
- **Phase 14 (US10 Fields)**: Depends on Phase 2 only — can start early
- **Phase 15 (US11 Tooling)**: Depends on Phase 11 (MCP framework exists)
- **Phase 16 (Polish)**: Depends on all desired phases being complete

### Critical Path

```
Phase 1 → Phase 2 → Phase 5 → Phase 6 → Phase 7 → Phase 10 → Phase 11
(Setup)   (Found.)  (Bronze)   (Silver)   (Gold+Reg) (Transform) (MCP)
```

### Parallel Opportunities

After Phase 2 completes, these can run in parallel:
- **Track A**: Phase 3 (US1) + Phase 4 (US2+US7)
- **Track B**: Phase 5 → Phase 6 → Phase 7 (pipeline expansion)
- **Track C**: Phase 14 (US10 field verification)

After Phase 7 completes:
- **Track D**: Phase 8 (US5) + Phase 9 (US3) + Phase 10 (US6) in parallel

After Phase 10 completes:
- **Track E**: Phase 11 (US4 MCP) → Phase 12 (US8) → Phase 15 (US11)
- **Track F**: Phase 13 (US9)

---

## Parallel Example: Phase 5 (Bronze Models)

```bash
# All 14 new bronze models can be written in parallel (different files, no dependencies):
T016: pubmed.sql
T017: hta_decisions.sql
T018: cochrane_reviews.sql
T019: sec_edgar.sql
T020: orcid.sql
T021: journal_rss.sql
T022: medical_news.sql
T023: cms_inpatient.sql
T024: cms_hospital_info.sql
T025: cms_cost_reports.sql
T026: acc_tvc.sql
T027: hrsa.sql
T028: pdb_structures.sql
T029: who_icd.sql
```

## Parallel Example: Phase 11 MCP Adapters

```bash
# All adapter files can be written in parallel (different files):
T065-T077: 28 adapter files in src/dk_data/services/mcp/adapters/

# Framework files must be sequential:
T059 (base adapter) → T060 (rate limiter) → T061 (base tool) → T062 (registry) → T063 (router) → T064 (register)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T010)
3. Complete Phase 3: US1 Schema Access (T011-T013)
4. Complete Phase 4: US2+US7 xenon Tables (T014-T015)
5. **STOP and VALIDATE**: PostgREST serves mol_gold/mol_silver/xenon/meta, analyst can read/write xenon tables
6. Deploy to staging — xenon dashboard can start integrating

### Incremental Delivery

1. MVP (Phases 1-4) → Schema access + xenon tables → Deploy
2. Pipeline (Phases 5-7) → 15 new bronze+silver models → Validate sqlmesh plan
3. Gold Views (Phases 8-9) → KOL/advocacy/trial outcomes → Deploy
4. Transform (Phase 10) → On-demand pipeline trigger → Deploy
5. MCP Tools (Phase 11) → 28 retrieval tools → Deploy
6. Verification (Phases 12-15) → Auth, financial, fields, tooling → Deploy
7. Polish (Phase 16) → Full validation → Final deploy

---

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 92 |
| Phase 1 (Setup) | 5 tasks |
| Phase 2 (Foundational) | 5 tasks |
| Phase 3 (US1 Schema Access) | 3 tasks |
| Phase 4 (US2+US7 xenon Tables) | 2 tasks |
| Phases 5-7 (Pipeline Expansion) | 19 tasks |
| Phase 8 (US5 Trial Outcomes) | 3 tasks |
| Phase 9 (US3 KOL/Advocacy) | 6 tasks |
| Phase 10 (US6 Transform) | 5 tasks |
| Phase 11 (US4 MCP Tools) | 21 tasks |
| Phase 12 (US8 Auth) | 2 tasks |
| Phase 13 (US9 Financial) | 2 tasks |
| Phase 14 (US10 Fields) | 2 tasks |
| Phase 15 (US11 Tooling) | 1 task |
| Phase 16 (Polish) | 6 tasks |
| Parallel tasks (marked [P]) | 48 |
| Suggested MVP scope | Phases 1-4 (15 tasks) |

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in same phase
- [Story] label maps task to specific user story for traceability
- Each user story checkpoint includes verifiable success criteria reference (SC-xxx)
- Bronze models (Phase 5) are the largest parallel opportunity — all 14 can be written simultaneously
- MCP adapters (Phase 11) are the second largest — all 28 adapter files are independent
- DrugBank adapter (T069) is flagged as SUBSTANTIAL complexity — allocate extra review time
- On-demand transform (Phase 10) is on the critical path — blocks all MCP tool functionality
