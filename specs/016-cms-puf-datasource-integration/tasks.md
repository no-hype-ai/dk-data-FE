# Tasks: CMS PUF Data Source Integration

**Input**: Design documents from `/specs/016-cms-puf-datasource-integration/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the feature specification. Test tasks omitted.

**Organization**: Tasks grouped by user story to enable independent implementation and testing. User stories US1 and US2 are combined (US2 is a search variant of US1's NPPES infrastructure). US6 shares Open Payments infrastructure with US1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- **[Audit §X]**: Cross-reference to Integration Audit finding in spec.md
- Include exact file paths in descriptions

## Path Conventions

- **Python package root**: `src/dk_data/`
- **SQL migrations**: `src/dk_data/sql/migrations/`
- **SQLMesh models**: `src/dk_data/sqlmesh/models/molecules/` (`bronze/`, `silver/`, `gold/`)
- **MCP adapters**: `src/dk_data/services/mcp/adapters/`
- **Fetchers**: `src/dk_data/ingestion/fetchers/`
- **Loaders**: `src/dk_data/ingestion/sources/`
- **Agents**: `src/dk_data/claude_sdk/agents/`
- **CronJobs**: `k8s/base/ingestion/`
- **Config**: `src/dk_data/config/`
- **Tests**: `tests/`

---

## Phase 1: Setup

**Purpose**: Project initialization — no code changes, just verifying prerequisites

- [ ] T001 Verify branch `016-cms-puf-datasource-integration` is up to date with `main`
- [ ] T002 [P] Verify existing MCP tool count baseline by running `python -c "from dk_data.services.mcp.tool_registry import TOOL_REGISTRY; print(len(TOOL_REGISTRY))"` (expect 28)
- [ ] T003 [P] Verify existing SQLMesh models compile with `cd src && python -m sqlmesh plan --no-prompts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure changes that MUST be complete before ANY user story. All modifications to shared base classes and cross-cutting infrastructure.

**CRITICAL**: No user story work can begin until this phase is complete.

### Migration 083: Foundation Tables

- [ ] T004 Create migration `src/dk_data/sql/migrations/083_cms_puf_foundation.sql` — silver entity tables (9: `silver.providers`, `silver.healthcare_facilities`, `silver.prescribing_profiles`, `silver.procedure_profiles`, `silver.open_payments`, `silver.health_systems`, `silver.facility_service_lines`, `silver.drug_market`, `silver.geographic_analytics`), reference tables (3: `silver.drg_service_line_mapping` — 772 DRGs → ~30 service lines, `silver.hcpcs_equipment_mapping` — HCPCS → equipment categories, `silver.nucc_taxonomy` — ~900 NUCC codes → specialties; per Audit §0.4 — PostgreSQL lookup tables replace ontology YAML for healthcare taxonomies), gold aggregate tables (5: `gold.provider_profile`, `gold.facility_profile`, `gold.drug_market_profile`, `gold.market_analytics`, `gold.provider_network`), agent infrastructure (2: `meta.agent_execution_log`, `meta.agent_quarantine`), RBAC grants (analyst SELECT on gold, NO web_anon access). All gold tables include `_generation_source TEXT`, `_refreshed_at TIMESTAMPTZ`, `_source_freshness JSONB`. See data-model.md for full column definitions.

### API Route Modification

- [ ] T004a [P] Modify `src/dk_data/api/routes/mcp.py` [Audit §A] — make `drug_name` Optional in `ToolInvokeRequest`, add `npi: Optional[str] = Field(None, pattern=r'^\d{10}$')`, `ccn: Optional[str] = Field(None, pattern=r'^[A-Z0-9]{6}$')`, and `params: Optional[Dict[str, Any]] = None`. Add `@model_validator` requiring at least one query key (`drug_name`, `npi`, `ccn`, or `params`). Route handler builds `input_params` dict from all fields. Backward-compatible: existing callers sending `{"drug_name": "atorvastatin"}` still work.

### Base Class Modifications

- [ ] T005 [P] Modify `src/dk_data/services/mcp/base_tool.py` [Audit §B] — update `_fetch_external()` to extract `primary_query` from `params.get("drug_name", "") or params.get("npi", "") or params.get("ccn", "")` instead of hardcoded `drug_name`. Add dispatch to `refresh_provider()`/`refresh_facility()` in `_refresh_silver_gold()` based on source type using `_PROVIDER_SOURCES` / `_FACILITY_SOURCES` / default-molecule frozensets. Must be backward-compatible with existing 28 tools.
- [ ] T006 [P] Modify `src/dk_data/services/mcp/adapters/base.py` — update `build_url()` signature to accept generic `primary_query` alongside `drug_name` positional arg for backward compatibility. New adapters ignore `drug_name` positional and pull typed keys from `params` dict. Existing 28 adapters must continue working unchanged.
- [ ] T007 [P] Modify `src/dk_data/services/mcp/silver_gold_refresher.py` [Audit §C] — add `refresh_provider(npi, source_name, api_response)`, `refresh_facility(ccn, source_name, api_response)`, `_resolve_provider(npi)` (canonical NPI lookup, no fuzzy matching — unlike `_resolve_molecule`, NPI is a deterministic 10-digit identifier), `_resolve_facility(ccn)` (canonical CCN lookup). Add empty silver handler and gold refresh method stubs for provider/facility sources to be filled in later phases.

### Shared Configuration & Fetcher Infrastructure

- [ ] T007a [P] Create `src/dk_data/config/cms_datasets.py` [Audit §0.5] — shared CMS Socrata dataset ID constants used by both MCP adapters (async) and batch fetchers (sync). Centralizes dataset IDs to prevent duplication between `CMSMedicareClient` (`services/external_apis/cms_medicare_client.py`) and `CMSSocrataFetcher` subclasses. Contains dataset title → dataset ID mappings for all ~15 Socrata-pattern sources.
- [ ] T008 Create `src/dk_data/ingestion/fetchers/cms_socrata_base.py` — `CMSSocrataFetcher(BaseFetcher)` with `DATASET_TITLE`, `AVAILABLE_YEARS`, `get_latest_url()`, paginated `fetch()` (limit=1000 per page, offset-based), bulk CSV download fallback, `Retry-After` header handling for 429 responses. Imports dataset IDs from `config/cms_datasets.py`. Used by ~15 CMS Socrata-pattern sources (Part D, Physician PUF, PECOS, Inpatient/Outpatient PUF, Hospital Quality, Part D/B Spending, Price Lookup, Geographic Variation, Chronic Conditions, Post-Acute, DMEPOS).

### Agent Infrastructure

- [ ] T009 [P] Create `src/dk_data/claude_sdk/base_agent.py` — `BaseAgent(ABC)` with `SYSTEM_PROMPT`, `AGENT_NAME`, `DEFAULT_MODEL = "claude-haiku-4-5-20251001"`, `DEFAULT_MIN_CONFIDENCE = 0.50`. Use `litellm.completion()` via cluster LiteLLM proxy (`http://litellm.infra.svc.cluster.local:4000`) instead of direct Anthropic SDK — reads `LITELLM_API_BASE` env var (default: `http://litellm.infra.svc.cluster.local:4000`). Abstract methods: `_build_prompt(context)`, `_parse_response(raw_json, context)`. Shared methods: `process_single()`, `process_batch()`, `_extract_json()` (strip markdown fences), `_log_execution()` (writes to `meta.agent_execution_log`), `_check_quarantine()` (routes <0.50 confidence to `meta.agent_quarantine`). Extract common patterns from existing `src/dk_data/claude_sdk/enrichment.py` and `src/dk_data/claude_sdk/scoring_agent.py`, replacing `anthropic.Anthropic()` with `litellm.completion()`.
- [ ] T010 [P] Create `src/dk_data/claude_sdk/agent_registry.py` — `AgentDefinition` dataclass mirroring `ToolDefinition` pattern, with `AGENT_REGISTRY` dict. Fields: name, description, module_path, input_sources, output_targets, model, cadence, estimated_cost_per_run, product_consumers. Register 6 agents. See contracts/agent-pipeline.yaml.
- [ ] T011 [P] Create `src/dk_data/claude_sdk/runner.py` — CLI entry point `python -m dk_data.claude_sdk.runner --agent {name} --batch-size {n} --dry-run`. Imports agent from registry, instantiates, runs `process_batch()`. Handles logging, error reporting, metrics emission.
- [ ] T012 [P] Create `src/dk_data/claude_sdk/agents/__init__.py` — export all agent classes.
- [ ] T013 [P] Modify `src/dk_data/claude_sdk/__init__.py` — export `BaseAgent`, `AgentRegistry`, `AGENT_REGISTRY`, runner, and all agent classes.

### PostgREST & Observability

- [ ] T014 [P] Modify `k8s/base/postgrest/configmap.yaml` — change `PGRST_DB_SCHEMAS` from `"api,mol_api,mol_gold,mol_silver,xenon,meta"` to `"api,mol_api,mol_gold,mol_silver,xenon,meta,gold"`.
- [ ] T015 [P] Modify `src/dk_data/observability/metrics.py` — add provider/facility/agent Prometheus metrics: `dk_providers_total[entity_type]`, `dk_facilities_total[facility_type]`, `dk_provider_verification_rate[verification_type]`, `dk_idn_systems_total`, `dk_agent_executions_total[agent_name, status]`, `dk_agent_records_processed[agent_name]`, `dk_agent_quarantine_total[agent_name]`, `dk_agent_cost_usd[agent_name]`. Add helper functions: `record_agent_execution()`, `increment_agent_quarantine()`.

**Checkpoint**: Foundation ready — all base classes extended, migration 083 applied, agent infrastructure in place. User story implementation can begin.

---

## Phase 3: User Story 1 + User Story 2 — Provider Lookup by NPI + Provider Search by Name (Priority: P1) MVP

**Goal**: HCP Compass users can look up a provider by NPI (US1) or search by name/state (US2) and see a unified profile combining demographics, prescribing patterns, procedures, quality scores, and industry payments from 5+ CMS data sources via both MCP tools and gold PostgREST API.

**Independent Test**: Invoke `cms-nppes-search` MCP tool with NPI `1234567890` → verify demographics returned. Query `gold.provider_profile?npi=eq.1234567890` via PostgREST → verify all 5 data facets present.

### Migration 084: Provider Raw/Bronze Tables

- [ ] T016 Create migration `src/dk_data/sql/migrations/084_provider_raw_bronze_tables.sql` — raw + bronze tables for 7 provider sources: `raw.cms_nppes`, `raw.cms_part_d_prescribers` (PARTITION BY RANGE year, y2015-y2025), `raw.cms_part_d_prescribers_summary` (partitioned), `raw.cms_physician_puf` (partitioned), `raw.cms_physician_puf_summary` (partitioned), `raw.cms_open_payments`, `raw.cms_care_compare`. Matching bronze tables. All raw tables follow MCP JSONB pattern + direct loader columns. See data-model.md for column definitions.

### MCP Adapters (7 adapters)

- [ ] T017 [P] [US1] Create `src/dk_data/services/mcp/adapters/nppes.py` — NPPES adapter with `build_url()` for NPI Registry REST API (`https://npiregistry.cms.hhs.gov/api/?version=2.1&number={npi}`), name search (`first_name`, `last_name`, `state` params), `normalize()` to flatten API response. See contracts/mcp-tools.yaml `cms-nppes-search`.
- [ ] T018 [P] [US1] Create `src/dk_data/services/mcp/adapters/cms_partd_prescribers.py` — Part D Prescribers adapter for Socrata API. `build_url()` with NPI or drug_name filter, year param. `normalize()` extracts prescribing records.
- [ ] T019 [P] [US1] Create `src/dk_data/services/mcp/adapters/cms_partd_prescribers_summary.py` — Part D Summary adapter. Same Socrata pattern, NPI-only query.
- [ ] T020 [P] [US1] Create `src/dk_data/services/mcp/adapters/cms_physician_puf.py` — Physician PUF adapter for Socrata API. NPI or HCPCS code query.
- [ ] T021 [P] [US1] Create `src/dk_data/services/mcp/adapters/cms_physician_puf_summary.py` — Physician Summary adapter. NPI-only query.
- [ ] T022 [P] [US1] Create `src/dk_data/services/mcp/adapters/cms_open_payments.py` — Open Payments adapter for `https://openpaymentsdata.cms.gov/api/1/datastore/query/{id}`. NPI or company_name query. Normalize general/research/ownership payment types.
- [ ] T023 [P] [US1] Create `src/dk_data/services/mcp/adapters/cms_care_compare.py` — Care Compare adapter for Provider-data API. NPI or provider_name query. Extract MIPS scores, quality attestation.

### Fetchers & Loaders (5 fetcher/loader pairs + 2 summary-only)

- [ ] T024 [P] [US1] Create `src/dk_data/ingestion/fetchers/nppes.py` — NPPES fetcher extending `BaseFetcher`. Handles both bulk CSV (9.3 GB, `chunksize=50000`) and REST API single-NPI lookups. Streaming download with resume-on-failure.
- [ ] T025 [P] [US1] Create `src/dk_data/ingestion/sources/nppes.py` — NPPES loader `load_nppes_data()`. Batch upsert to `raw.cms_nppes` with `ON CONFLICT (npi) DO UPDATE`. Commit every 10K rows.
- [ ] T026 [P] [US1] Create `src/dk_data/ingestion/fetchers/cms_partd_prescribers.py` — Part D Prescribers fetcher extending `CMSSocrataFetcher`. Set `DATASET_TITLE`, `AVAILABLE_YEARS`. Handles both API pagination and bulk CSV for historical years.
- [ ] T027 [P] [US1] Create `src/dk_data/ingestion/sources/cms_partd_prescribers.py` — Part D loader. Batch insert into year-partitioned `raw.cms_part_d_prescribers`. Handle CMS suppression (<11 beneficiaries → NULL numerics + `suppressed=true`).
- [ ] T028 [P] [US1] Create fetcher+loader pairs for remaining 3 sources: `src/dk_data/ingestion/fetchers/cms_physician_puf.py` + `src/dk_data/ingestion/sources/cms_physician_puf.py`, `src/dk_data/ingestion/fetchers/cms_open_payments.py` + `src/dk_data/ingestion/sources/cms_open_payments.py`, `src/dk_data/ingestion/fetchers/cms_care_compare.py` + `src/dk_data/ingestion/sources/cms_care_compare.py`. Follow same patterns.
- [ ] T029 [P] [US1] Create summary-only fetcher+loaders: `src/dk_data/ingestion/fetchers/cms_partd_prescribers_summary.py` + `src/dk_data/ingestion/sources/cms_partd_prescribers_summary.py`, `src/dk_data/ingestion/fetchers/cms_physician_puf_summary.py` + `src/dk_data/ingestion/sources/cms_physician_puf_summary.py`.

### Registration & Config

- [ ] T030 [US1] Modify `src/dk_data/services/mcp/tool_registry.py` [Audit §D] — add 7 Tier 4 (`provider_claims`) ToolDefinitions: `cms-nppes-search`, `cms-partd-prescribers-search`, `cms-partd-prescribers-summary-search`, `cms-physician-puf-search`, `cms-physician-puf-summary-search`, `cms-open-payments-search`, `cms-care-compare-search`. Each overrides `input_schema` with custom `properties` and `required` for npi/ccn (not defaulting to `drug_name` required). Input schemas per contracts/mcp-tools.yaml.
- [ ] T031 [P] [US1] Modify `src/dk_data/ingestion/main.py` — add 7 entries to `SOURCES` dict: `cms_nppes`, `cms_part_d_prescribers`, `cms_part_d_prescribers_summary`, `cms_physician_puf`, `cms_physician_puf_summary`, `cms_open_payments`, `cms_care_compare`. Each with fetcher_class and loader function.
- [ ] T032 [P] [US1] Modify `src/dk_data/ingestion/fetchers/__init__.py` — export 7 new fetcher classes (NPPESFetcher, CMSPartDPrescribersFetcher, etc.).
- [ ] T033 [P] [US1] Modify `src/dk_data/config/rate_limits.yaml` — add 7 provider source rate limits. NPPES: 10 req/s. CMS Socrata sources: 5 req/s, 30s timeout. Open Payments: 5 req/s.
- [ ] T034 [P] [US1] Modify `src/dk_data/sql/seed_data_sources.sql` — add 7 catalog entries for provider sources to `meta.data_sources`.

### Bronze Transformer Handlers

- [ ] T035 [US1] Modify `src/dk_data/services/mcp/bronze_transformer.py` — add 7 handler methods: `_transform_cms_nppes()`, `_transform_cms_part_d_prescribers()`, `_transform_cms_part_d_prescribers_summary()`, `_transform_cms_physician_puf()`, `_transform_cms_physician_puf_summary()`, `_transform_cms_open_payments()`, `_transform_cms_care_compare()`. Register in `_HANDLERS` dict and `_RAW_SCHEMA_MAP`. Each extracts typed columns from JSONB `response_body`, inserts into bronze table with `ON CONFLICT DO UPDATE`, marks raw record `processed_to_bronze = TRUE`.

### Bronze SQLMesh Models (7 models)

- [ ] T036 [P] [US1] Create `src/dk_data/sqlmesh/models/molecules/bronze/cms_nppes.sql` — `INCREMENTAL_BY_TIME_RANGE(time_column request_timestamp, batch_size 500)`, `cron '@daily'`, `grain npi`, `audits (not_null(columns := (npi)))`. Extract: npi, entity_type, provider_name, credential, specialty_code, address fields, phone, enumeration_date, deactivation_date from `raw.cms_nppes`.
- [ ] T037 [P] [US1] Create bronze models for remaining 6 sources: `src/dk_data/sqlmesh/models/molecules/bronze/cms_part_d_prescribers.sql`, `cms_part_d_prescribers_summary.sql`, `cms_physician_puf.sql`, `cms_physician_puf_summary.sql`, `cms_open_payments.sql`, `cms_care_compare.sql`. Same INCREMENTAL_BY_TIME_RANGE pattern. Part D and Physician PUF models must handle year-partitioned source tables.

### Silver SQLMesh Models (4 models)

- [ ] T038 [P] [US1] Create `src/dk_data/sqlmesh/models/molecules/silver/providers.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key npi)`, `cron '@daily'`, `grain npi`. Union bronze.cms_nppes + bronze.cms_care_compare + bronze.cms_physician_puf_summary. `DISTINCT ON (npi) ORDER BY source_precedence ASC` (NPPES=1, CareCompare=2, PhysicianPUF=3). Columns per data-model.md silver.providers.
- [ ] T039 [P] [US1] Create `src/dk_data/sqlmesh/models/molecules/silver/prescribing_profiles.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (npi, drug_name, year))`, from bronze.cms_part_d_prescribers. Handle CMS suppression flag.
- [ ] T040 [P] [US1] Create `src/dk_data/sqlmesh/models/molecules/silver/procedure_profiles.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (npi, hcpcs_code, year))`, from bronze.cms_physician_puf.
- [ ] T041 [P] [US1] Create `src/dk_data/sqlmesh/models/molecules/silver/open_payments.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key record_id)`, from bronze.cms_open_payments. Include payment_type, dispute_status.

### Gold SQLMesh Model

- [ ] T042 [US1] Create `src/dk_data/sqlmesh/models/molecules/gold/provider_profile.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key npi)`. CTEs joining: silver.providers + silver.prescribing_profiles (top 10 drugs via ROW_NUMBER) + silver.procedure_profiles (top 10 procedures) + silver.open_payments (aggregate totals). JSONB aggregates: `top_drugs`, `top_procedures`, `top_payers`, `payment_summary`. Include `entity_type`, `_generation_source = 'sql_aggregate'`, `_refreshed_at`, `_source_freshness`.

### Silver/Gold Refresher Handlers

- [ ] T043 [US1] Modify `src/dk_data/services/mcp/silver_gold_refresher.py` — implement provider silver handler methods (`_silver_cms_nppes`, `_silver_cms_part_d_prescribers`, `_silver_cms_physician_puf`, `_silver_cms_open_payments`, `_silver_cms_care_compare`) and `_refresh_gold_provider_profile(npi)`. Each silver handler upserts into the appropriate silver table. Gold handler runs the provider_profile aggregation for a specific NPI.

**Checkpoint**: US1+US2 complete. Provider lookup by NPI returns full profile. Name/state search returns ranked provider list. `gold.provider_profile` populated. MCP tools functional. PostgREST gold queries work.

---

## Phase 4: User Story 3 — Facility Profile by CCN (Priority: P1)

**Goal**: HCO Navigator users can query a facility by CCN and see a unified profile combining demographics, DRG volumes, quality ratings, system affiliation, service lines, and Magnet status.

**Independent Test**: Query `gold.facility_profile?ccn=eq.050454` via PostgREST → verify demographics, DRG volumes, quality ratings, and system affiliation present.

### Migration 085: Facility Raw/Bronze Tables

- [ ] T044 Create migration `src/dk_data/sql/migrations/085_facility_raw_bronze_tables.sql` — raw + bronze tables for 11 facility sources: `raw.cms_provider_of_services`, `raw.cms_pecos`, `raw.cms_chow`, `raw.cms_facility_affiliation`, `raw.cms_inpatient_puf_detail`, `raw.cms_inpatient_puf_summary` (FR-043: one row per CCN — hospital demographics, chronic conditions, HCC scores), `raw.cms_outpatient_puf`, `raw.cms_hospital_quality`, `raw.cms_drg_weights`, `raw.ancc_magnet`, `raw.cms_hcpcs_level2`. Matching bronze tables. POS extraction MUST include accreditor field (TJC/DNV/HFAP) per FR-059.

### MCP Adapters (10 adapters)

- [ ] T045 [P] [US3] Create adapters for 11 facility sources in `src/dk_data/services/mcp/adapters/`: `cms_provider_of_services.py`, `cms_pecos.py`, `cms_chow.py`, `cms_facility_affiliation.py`, `cms_inpatient_puf_detail.py`, `cms_inpatient_puf_summary.py` (FR-043), `cms_outpatient_puf.py`, `cms_hospital_quality.py`, `cms_drg_weights.py`, `ancc_magnet.py`, `cms_hcpcs.py`. Each implements `build_url()` and `normalize()`. See contracts/mcp-tools.yaml for input schemas.

### Fetchers & Loaders (10 pairs)

- [ ] T046 [P] [US3] Create fetchers for 11 facility sources (including `cms_inpatient_puf_summary.py` for FR-043) in `src/dk_data/ingestion/fetchers/`: `cms_provider_of_services.py` (bulk CSV), `cms_pecos.py` (Socrata), `cms_chow.py` (bulk CSV), `cms_facility_affiliation.py` (Socrata), `cms_inpatient_puf_detail.py` (Socrata), `cms_outpatient_puf.py` (Socrata), `cms_hospital_quality.py` (Provider-data API), `cms_drg_weights.py` (direct CSV), `ancc_magnet.py` (web scrape), `cms_hcpcs.py` (direct CSV). Socrata sources extend `CMSSocrataFetcher`.
- [ ] T047 [P] [US3] Create loaders for 10 facility sources in `src/dk_data/ingestion/sources/`: matching `load_*_data()` functions for each fetcher. Batch upserts with appropriate conflict resolution.

### Registration & Config

- [ ] T048 [US3] Modify `src/dk_data/services/mcp/tool_registry.py` — add 10 Tier 5 (`facility_hospital`) ToolDefinitions per contracts/mcp-tools.yaml.
- [ ] T049 [P] [US3] Modify `src/dk_data/ingestion/main.py` — add 10 facility source entries to `SOURCES` dict.
- [ ] T050 [P] [US3] Modify `src/dk_data/ingestion/fetchers/__init__.py` — export 10 new facility fetcher classes.
- [ ] T051 [P] [US3] Modify `src/dk_data/config/rate_limits.yaml` — add 10 facility source rate limits. POS/CHOW: 5 req/s. ANCC Magnet: 1 req/s (scrape).
- [ ] T052 [P] [US3] Modify `src/dk_data/sql/seed_data_sources.sql` — add 10 facility catalog entries.

### Bronze Transformer Handlers & SQLMesh Models

- [ ] T053 [US3] Modify `src/dk_data/services/mcp/bronze_transformer.py` — add 10 facility handler methods and register in `_HANDLERS`/`_RAW_SCHEMA_MAP`.
- [ ] T054 [P] [US3] Create 10 bronze SQLMesh models in `src/dk_data/sqlmesh/models/molecules/bronze/`: `cms_provider_of_services.sql`, `cms_pecos.sql`, `cms_chow.sql`, `cms_facility_affiliation.sql`, `cms_inpatient_puf_detail.sql`, `cms_outpatient_puf.sql`, `cms_hospital_quality.sql`, `cms_drg_weights.sql`, `ancc_magnet.sql`, `cms_hcpcs_level2.sql`. All INCREMENTAL_BY_TIME_RANGE.

### Silver & Gold Models

- [ ] T055a [P] [US3] Create `src/dk_data/sqlmesh/models/molecules/silver/healthcare_facilities.sql` [Audit §E] — `INCREMENTAL_BY_UNIQUE_KEY(unique_key ccn)`, `cron '@daily'`, `grain ccn`. Schema evolution from existing `(provider_id, source)` PK to `ccn` as canonical key. From bronze.cms_provider_of_services + bronze.cms_hospital_quality + bronze.ancc_magnet. POS authoritative (source_precedence = 1). Existing `provider_id` values from CMS sources ARE CCNs (6-character), so this is mostly a rename + schema evolution. Columns per data-model.md `silver.healthcare_facilities`.
- [ ] T055b [P] [US3] Create `src/dk_data/sqlmesh/models/molecules/silver/health_systems.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key organization_npi)`. Union bronze.cms_pecos + bronze.cms_chow + bronze.cms_facility_affiliation. Build hierarchy levels.
- [ ] T056 [P] [US3] Create `src/dk_data/sqlmesh/models/molecules/silver/facility_service_lines.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (ccn, service_line, year))`. From bronze.cms_inpatient_puf_detail + bronze.cms_provider_of_services.
- [ ] T057 [US3] Create `src/dk_data/sqlmesh/models/molecules/gold/facility_profile.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key ccn)`. CTEs joining silver.healthcare_facilities + inpatient DRGs (top 10) + hospital quality (star ratings) + health_systems (parent org) + facility_service_lines + ancc_magnet. Implement discharge-date-based ownership allocation for mid-year CHOW events (EC-9: use ownership at time of discharge for DRG aggregation, not current ownership). Include `_generation_source`, `_refreshed_at`, `_source_freshness`.

### Silver/Gold Refresher

- [ ] T058 [US3] Modify `src/dk_data/services/mcp/silver_gold_refresher.py` — implement facility silver handlers and `_refresh_gold_facility_profile(ccn)`.

**Checkpoint**: US3 complete. Facility profile by CCN returns demographics, DRG volumes, quality, system affiliation. PostgREST `gold.facility_profile` queries work.

---

## Phase 5: User Story 4 — Drug Market Analysis (Priority: P1)

**Goal**: Lumina users can query a drug name and see a unified market profile combining Medicare spending, formulary coverage, drug classification, NDC details, and top prescribers.

**Independent Test**: Query `gold.drug_market_profile?drug_name=eq.atorvastatin` via PostgREST → verify spending, formulary, and classification data present.

### Migration 086: Drug/Market Raw/Bronze Tables

- [ ] T059 Create migration `src/dk_data/sql/migrations/086_drug_market_raw_bronze_tables.sql` — raw + bronze tables for 10 drug/market sources: `raw.fda_ndc`, `raw.cms_part_d_spending`, `raw.cms_part_b_spending`, `raw.cms_formulary`, `raw.cms_rbcs`, `raw.cms_price_lookup`, `raw.usp_drug_class`, `raw.cms_nucc_taxonomy`, `raw.nlm_rxnorm` (FR-044: RxNorm bulk files for drug normalization + ATC cross-walk). Matching bronze tables.

### MCP Adapters, Fetchers, Loaders (9 sources)

- [ ] T060 [P] [US4] Create 8 adapters in `src/dk_data/services/mcp/adapters/`: `fda_ndc.py`, `cms_partd_spending.py`, `cms_partb_spending.py`, `cms_partd_formulary.py`, `cms_rbcs.py`, `cms_price_lookup.py`, `usp_drug_class.py`, `cms_nucc_taxonomy.py`. See contracts/mcp-tools.yaml.
- [ ] T060a [P] [US4] Extend existing `src/dk_data/services/mcp/adapters/who_icd.py` to support WHO ATC code lookups via RxNav REST API (`https://rxnav.nlm.nih.gov/REST/`). Add `build_url()` branch for ATC queries (rxcui, drug name). Add ATC code mapping to drug_market silver model join.
- [ ] T060b [P] [US4] Create `src/dk_data/services/mcp/adapters/nlm_rxnorm.py` — RxNorm bulk adapter (FR-044). Build URL for RxNorm bulk file downloads (requires UMLS account). Normalize RxCUI-to-NDC mappings.
- [ ] T060c [P] [US4] Create `src/dk_data/ingestion/fetchers/nlm_rxnorm.py` + `src/dk_data/ingestion/sources/nlm_rxnorm.py` — RxNorm bulk fetcher (UMLS authenticated download) and loader. Monthly refresh.
- [ ] T061 [P] [US4] Create 8 fetcher+loader pairs in `src/dk_data/ingestion/fetchers/` and `src/dk_data/ingestion/sources/`: `fda_ndc`, `cms_partd_spending`, `cms_partb_spending`, `cms_partd_formulary` (bulk CSV), `cms_rbcs` (CSV), `cms_price_lookup` (Socrata), `usp_drug_class` (CMS crosswalk CSV), `cms_nucc_taxonomy` (nucc.org CSV).

### Registration & Config

- [ ] T062 [US4] Modify `src/dk_data/services/mcp/tool_registry.py` — add 9 Tier 6 (`drug_market_population`) ToolDefinitions for drug/market sources per contracts/mcp-tools.yaml.
- [ ] T063 [P] [US4] Modify `src/dk_data/ingestion/main.py` — add 8 drug/market entries to `SOURCES` dict.
- [ ] T064 [P] [US4] Modify `src/dk_data/config/rate_limits.yaml` — add 8 drug/market rate limits. FDA NDC: 40 req/min (no key), 240 req/min (with OPENFDA_API_KEY). Others: 5 req/s.
- [ ] T065 [P] [US4] Modify `src/dk_data/sql/seed_data_sources.sql` — add 8 drug/market catalog entries.

### Transformation Pipeline

- [ ] T066 [US4] Modify `src/dk_data/services/mcp/bronze_transformer.py` — add 8 drug/market handler methods.
- [ ] T067 [P] [US4] Create 8 bronze SQLMesh models in `src/dk_data/sqlmesh/models/molecules/bronze/`: `fda_ndc.sql`, `cms_part_d_spending.sql`, `cms_part_b_spending.sql`, `cms_formulary.sql`, `cms_rbcs.sql`, `cms_price_lookup.sql`, `usp_drug_class.sql`, `cms_nucc_taxonomy.sql`.
- [ ] T068 [P] [US4] Create `src/dk_data/sqlmesh/models/molecules/silver/drug_market.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (drug_name, year))`. Union bronze sources. Multi-source join on normalized drug name (lowercase).
- [ ] T069 [US4] Create `src/dk_data/sqlmesh/models/molecules/gold/drug_market_profile.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (drug_name, generic_name))`. Aggregate spending, formulary coverage, classification, top prescribers. Include spending_trend JSONB for year-over-year.

**Checkpoint**: US4 complete. Drug market profiles available via PostgREST with spending, formulary, classification, and prescriber data.

---

## Phase 6: User Story 9 — Bulk Data Refresh Pipeline (Priority: P1)

**Goal**: Platform operators run scheduled CronJobs that refresh all data sources through the full medallion pipeline with observability at each stage.

**Independent Test**: Trigger `fetch-cms-part-d` CronJob → verify records flow through raw → bronze → silver → gold with metrics updated.

### CronJob Manifests — Provider Sources (7)

- [ ] T070a [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-nppes.yaml` — monthly (`0 3 1 * *`), `activeDeadlineSeconds: 28800` (8h for 9.3GB). Follow `cronjob-fetch-pubmed.yaml` pattern (see spec.md § CronJob Manifest Template): `concurrencyPolicy: Forbid`, `backoffLimit: 2`, `restartPolicy: Never`, `successfulJobsHistoryLimit: 3`, `failedJobsHistoryLimit: 3`, `imagePullSecrets: [{name: ghcr-credentials}]`, image `ghcr.io/data-kinetic/dk-data-fe/job-trigger:main-{sha}` (exact name for kustomize), individual `secretKeyRef` per DB key (POSTGRES_HOST/PORT/USER/PASSWORD/DB — NOT `envFrom`), OTEL env as static `value:`, K8s recommended labels (`app.kubernetes.io/name`, `/component: ingestion`, `/part-of: dk-data`). Resources 256Mi/100m → 512Mi/300m. Command: `["python", "-m", "dk_data.ingestion.main"]`, args: `["nppes"]`.
- [ ] T070b [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-partd.yaml` — weekly (`0 4 * * 0`). Note: weekly schedule checks for new annual release; downloads only when new data detected.
- [ ] T070c [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-partd-summary.yaml` — weekly (`30 4 * * 0`).
- [ ] T070d [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-physician-puf.yaml` — weekly (`0 5 * * 0`). Note: weekly schedule checks for new annual release.
- [ ] T070e [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-physician-puf-summary.yaml` — weekly (`30 5 * * 0`).
- [ ] T070f [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-open-payments.yaml` — weekly (`0 6 * * 0`).
- [ ] T070g [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-care-compare.yaml` — bi-monthly (`0 3 * * 1`).

### CronJob Manifests — Facility Sources (10)

- [ ] T071a [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-pos.yaml` — quarterly (`0 3 1 */3 *`).
- [ ] T071b [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-pecos.yaml` — monthly (`0 4 1 * *`).
- [ ] T071c [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-chow.yaml` — quarterly (`0 5 1 */3 *`).
- [ ] T071d [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-facility-affiliation.yaml` — monthly (`0 6 1 * *`).
- [ ] T071e [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-inpatient-puf.yaml` — weekly (`0 2 * * 0`).
- [ ] T071f [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-outpatient-puf.yaml` — weekly (`30 2 * * 0`).
- [ ] T071g [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-hospital-quality.yaml` — quarterly (`0 7 * * 1`).
- [ ] T071h [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-drg-weights.yaml` — annual (`0 3 1 10 *`, October).
- [ ] T071i [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-ancc-magnet.yaml` — quarterly (`0 8 1 */3 *`).
- [ ] T071j [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-hcpcs.yaml` — annual (`0 3 1 1 *`, January).

### CronJob Manifests — Drug/Market Sources (8)

- [ ] T072a [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-fda-ndc.yaml` — weekly (`0 3 * * 3`).
- [ ] T072b [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-partd-spending.yaml` — weekly (`0 4 * * 3`).
- [ ] T072c [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-partb-spending.yaml` — weekly (`30 4 * * 3`).
- [ ] T072d [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-formulary.yaml` — monthly (`0 3 1 * *`).
- [ ] T072e [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-rbcs.yaml` — annual (`0 3 1 1 *`).
- [ ] T072f [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-price-lookup.yaml` — annual (`0 4 1 1 *`).
- [ ] T072g [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-usp-drug-class.yaml` — annual (`0 5 1 1 *`).
- [ ] T072h [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-nucc-taxonomy.yaml` — semi-annual (`0 3 1 */6 *`).

### CronJob Manifests — Population/Clinical Sources (8)

- [ ] T072i [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-geographic-variation.yaml` — annual (`0 3 1 1 *`).
- [ ] T072j [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-chronic-conditions.yaml` — annual (`0 4 1 1 *`).
- [ ] T072k [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-post-acute.yaml` — annual (`0 5 1 1 *`).
- [ ] T072l [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-dmepos.yaml` — annual (`0 6 1 1 *`).
- [ ] T072m [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-ddinter.yaml` — quarterly (`0 3 1 */3 *`).
- [ ] T072n [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-stabilis.yaml` — quarterly (`0 4 1 */3 *`).
- [ ] T072o [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-medicaid-pdl.yaml` — monthly (`0 5 1 * *`).
- [ ] T072p [P] [US9] Create `k8s/base/ingestion/cronjob-fetch-cms-cost-reports.yaml` — annual (`0 3 1 1 *`).

### Registration & Validation

- [ ] T073 [US9] Modify `k8s/base/kustomization.yaml` — add all ~33 new CronJob resources to the resources list (7 provider + 10 facility + 8 drug/market + 8 population/clinical).

### Pipeline Validation

- [ ] T074 [US9] Validate full K8s manifests compile: `kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null`
- [ ] T075 [US9] Modify `src/dk_data/ingestion/fetchers/__init__.py` — ensure all fetcher classes from Phases 3-5 are properly exported.

**Checkpoint**: US9 complete. All ~33 data source CronJobs defined, K8s manifests validate, pipeline observability in place.

---

## Phase 7: User Story 5 — Geographic Market Analytics (Priority: P2)

**Goal**: SageAI users can query a geographic region and see population demographics, spending patterns, chronic condition prevalence, and provider density.

**Independent Test**: Query `gold.market_analytics?geo_code=eq.TX&year=eq.2024` via PostgREST → verify population, spending, and condition data present.

### Migration 087: Population/Clinical Raw/Bronze Tables

- [ ] T076 Create migration `src/dk_data/sql/migrations/087_population_clinical_raw_bronze_tables.sql` — raw + bronze tables for population + clinical sources: `raw.cms_geographic_variation`, `raw.cms_chronic_conditions`, `raw.cms_post_acute`, `raw.cms_dmepos`, `raw.ddinter`, `raw.stabilis`, `raw.cms_medicaid_pdl`, `raw.cms_cost_reports` (HCRIS Worksheet S-3/A). Matching bronze tables.

### Geographic Sources (4 sources)

- [ ] T077 [P] [US5] Create 4 adapters: `src/dk_data/services/mcp/adapters/cms_geographic_variation.py`, `cms_chronic_conditions.py`, `cms_post_acute.py`, `cms_dmepos.py`.
- [ ] T078 [P] [US5] Create 4 fetcher+loader pairs for geographic/population sources in `src/dk_data/ingestion/fetchers/` and `src/dk_data/ingestion/sources/`.
- [ ] T079 [US5] Modify `src/dk_data/services/mcp/tool_registry.py` — add 4 Tier 6 ToolDefinitions for geographic/population sources.
- [ ] T080 [P] [US5] Modify `src/dk_data/ingestion/main.py`, `rate_limits.yaml`, `seed_data_sources.sql` — add 4 geographic/population entries.
- [ ] T081 [US5] Modify `src/dk_data/services/mcp/bronze_transformer.py` — add 4 geographic/population handlers.
- [ ] T082 [P] [US5] Create 4 bronze SQLMesh models: `cms_geographic_variation.sql`, `cms_chronic_conditions.sql`, `cms_post_acute.sql`, `cms_dmepos.sql`.

### HCRIS Cost Reports (FR-042 — input for StaffingDecomposition agent)

- [ ] T082a [P] [US5] Create `src/dk_data/ingestion/fetchers/cms_cost_reports.py` — HCRIS cost report fetcher. Bulk CSV download from CMS. Annual release. Extract Worksheet S-3/A staffing sections.
- [ ] T082b [P] [US5] Create `src/dk_data/ingestion/sources/cms_cost_reports.py` — HCRIS loader `load_cms_cost_reports_data()`. Batch upsert to `raw.cms_cost_reports` with `ON CONFLICT (ccn, report_year) DO UPDATE`.
- [ ] T082c [P] [US5] Create `src/dk_data/services/mcp/adapters/cms_cost_reports.py` — HCRIS adapter for MCP tool access to cost report data.
- [ ] T082d [US5] Modify `src/dk_data/services/mcp/bronze_transformer.py` — add `_transform_cms_cost_reports()` handler.
- [ ] T082e [P] [US5] Create `src/dk_data/sqlmesh/models/molecules/bronze/cms_cost_reports.sql` — INCREMENTAL_BY_TIME_RANGE model extracting staffing line items from raw HCRIS data.
- [ ] T082f [P] [US5] Modify `src/dk_data/ingestion/main.py`, `rate_limits.yaml`, `seed_data_sources.sql` — add HCRIS cost reports entry.

### Silver & Gold Models

- [ ] T083 [P] [US5] Create `src/dk_data/sqlmesh/models/molecules/silver/geographic_analytics.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (geo_level, geo_code, year))`. Union Geographic Variation + Chronic Conditions.
- [ ] T084 [US5] Create `src/dk_data/sqlmesh/models/molecules/gold/market_analytics.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (geo_level, geo_code, year))`. Aggregate demographics, spending_per_capita, chronic_conditions, provider_density, facility_landscape into JSONB columns.

**Checkpoint**: US5 complete. Geographic market analytics available at state/HRR/county levels via PostgREST.

---

## Phase 8: User Story 6 — Open Payments Transparency (Priority: P2)

**Goal**: HCP Compass users can query industry payments for a specific provider or company and see detailed payment records with filtering and aggregation.

**Independent Test**: Invoke `cms-open-payments-search` MCP tool with NPI → verify payment records returned with general/research/ownership categorization and aggregate totals.

- [ ] T085 [US6] Modify `src/dk_data/services/mcp/adapters/cms_open_payments.py` — enhance `normalize()` to include year-range filtering, dispute_status flagging, aggregate totals by year/payer/payment_type. Ensure disputed payments excluded from aggregates by default.
- [ ] T086 [US6] Modify `src/dk_data/services/mcp/silver_gold_refresher.py` — enhance `_silver_cms_open_payments()` to compute aggregate payment summaries per NPI and update `gold.provider_profile.payment_summary` JSONB.

**Checkpoint**: US6 complete. Open Payments queries return detailed, filterable, aggregated payment data.

---

## Phase 9: User Story 7 — Health System Hierarchy (Priority: P2)

**Goal**: HCO Navigator users can query a health system and see parent organization, affiliated facilities, M&A history, and system-level aggregates.

**Independent Test**: Query `silver.health_systems` for "HCA Healthcare" → verify hierarchy includes parent org, facilities, and CHOW events.

### IDN Hierarchy Agent

- [ ] T087 [US7] Create `src/dk_data/claude_sdk/agents/idn_hierarchy.py` — `IDNHierarchyAgent(BaseAgent)`. System prompt for resolving conflicting parent organizations in PECOS + CHOW + Facility Affiliation + SEC EDGAR (already in dk-data-fe, reference for public health system filings and organizational structure per FR-035). Input: `IDNContext` (PECOS enrollments, CHOW events, affiliation links, SEC EDGAR org data, top 50 US systems for validation). Output: `IDNHierarchyResult` per contracts/agent-pipeline.yaml. Three-stage: deterministic (~80%), heuristic, agent (~20% ambiguous).
- [ ] T088 [P] [US7] Create CronJob `k8s/base/ingestion/cronjob-agent-idn-hierarchy.yaml` — monthly Day 2, 512Mi/500m, 4h deadline. Follow agent CronJob variant of spec.md § CronJob Manifest Template: `command: ["python", "-m", "dk_data.claude_sdk.runner"]`, `args: ["--agent", "idn_hierarchy", "--batch-size", "50"]`. Set `LITELLM_API_BASE` as static `value: "http://litellm.infra.svc.cluster.local:4000"` (NOT from DopplerSecret). Include standard 5 DB `secretKeyRef` entries + OTEL static values + `imagePullSecrets: ghcr-credentials` + K8s labels.
- [ ] T089 [US7] Modify `src/dk_data/services/mcp/silver_gold_refresher.py` — add `_silver_health_systems()` handler to propagate system affiliations to `gold.facility_profile.system_affiliation`.

**Checkpoint**: US7 complete. Health system hierarchies available with parent org, facilities, CHOW history.

---

## Phase 10: User Story 8 — Drug Interaction Check (Priority: P3)

**Goal**: Clinical users can query interactions between two drugs and see severity, mechanism, clinical recommendation from DDInter 2.0. IV compatibility from Stabilis 4.0.

**Independent Test**: Invoke `ddinter-interaction-search` MCP tool with `warfarin`+`aspirin` → verify interaction severity returned.

### Clinical Sources (3 new + 2 RSS extensions)

- [ ] T090 [P] [US8] Create `src/dk_data/services/mcp/adapters/ddinter.py` — DDInter adapter for bidirectional interaction lookup. Normalize severity to standard scale (major/moderate/minor). Query local cache first, API fallback.
- [ ] T091 [P] [US8] Create `src/dk_data/services/mcp/adapters/stabilis.py` — Stabilis IV compatibility adapter. Local cache, API fallback.
- [ ] T092 [P] [US8] Create `src/dk_data/services/mcp/adapters/cms_medicaid_pdl.py` — Medicaid PDL adapter for state formulary queries.
- [ ] T093 [P] [US8] Create fetcher+loader pairs: `src/dk_data/ingestion/fetchers/ddinter.py` + `sources/ddinter.py` (full dataset cache, quarterly), `fetchers/stabilis.py` + `sources/stabilis.py` (full dataset cache, quarterly), `fetchers/cms_medicaid_pdl.py` + `sources/cms_medicaid_pdl.py` (monthly).
- [ ] T094 [US8] Modify `src/dk_data/services/mcp/tool_registry.py` — add 3 Tier 6 ToolDefinitions: `ddinter-interaction-search`, `stabilis-compatibility-search`, `cms-medicaid-pdl-search`.
- [ ] T095 [P] [US8] Modify existing `journal_rss` fetcher config to add Becker's Hospital Review and Google News (healthcare topic filter) RSS feed URLs. Modify existing `medical_news` fetcher config to add FierceHealthcare and Modern Healthcare RSS feed URLs. No new fetchers needed (FR-031 updated).
- [ ] T096 [US8] Modify `src/dk_data/services/mcp/bronze_transformer.py` — add 3 handlers for DDInter, Stabilis, Medicaid PDL.
- [ ] T097 [P] [US8] Create 3 bronze SQLMesh models: `ddinter.sql`, `stabilis.sql`, `cms_medicaid_pdl.sql`.
- [ ] T098 [P] [US8] Modify `src/dk_data/ingestion/main.py`, `rate_limits.yaml`, `seed_data_sources.sql` — add 5 clinical/news entries (DDInter, Stabilis, Medicaid PDL, Becker's, FierceHealthcare).

### Silver Models for Clinical Data

- [ ] T098a [P] [US8] Create `src/dk_data/sqlmesh/models/molecules/silver/drug_interactions.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key interaction_id)`, from bronze.ddinter. Normalize severity to standard scale (major/moderate/minor). Include bidirectional lookup support (drug_a, drug_b, and reverse).
- [ ] T098b [P] [US8] Create `src/dk_data/sqlmesh/models/molecules/silver/iv_compatibility.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key entry_id)`, from bronze.stabilis. Structured compatibility/incompatibility data.
- [ ] T098c [P] [US8] Create `src/dk_data/sqlmesh/models/molecules/silver/medicaid_pdl.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (state, drug_name, year))`, from bronze.cms_medicaid_pdl. State-level preferred drug list coverage.

**Checkpoint**: US8 complete. Drug interaction queries work. IV compatibility queries work. Medicaid PDL and healthcare news integrated.

---

## Phase 11: Agentic Processing Pipeline

**Purpose**: Implement remaining 4 Claude SDK agents (ServiceLineInference, ReferralNetwork, ContactVerification, StaffingDecomposition) and their CronJobs.

### ServiceLineInference Agent

- [ ] T099 [P] Create `src/dk_data/claude_sdk/agents/service_line_inference.py` — `ServiceLineInferenceAgent(BaseAgent)`. System prompt for DRG → service line classification. Input: `FacilityServiceLineContext` (ccn, drg_volumes, service_capabilities). Output: `ServiceLineResult`. 80% deterministic DRG mapping, 20% LLM for ambiguous. Validation: volume sums must match. See contracts/agent-pipeline.yaml.
- [ ] T100 [P] Create CronJob `k8s/base/ingestion/cronjob-agent-service-line.yaml` — monthly Day 1, 512Mi/500m, 4h deadline. Agent CronJob variant: `command: ["python", "-m", "dk_data.claude_sdk.runner"]`, `args: ["--agent", "service_line_inference", "--batch-size", "100"]`. `LITELLM_API_BASE` as static `value:`. Standard DB `secretKeyRef` + OTEL + labels per § CronJob Manifest Template.

### ReferralNetwork Agent

- [ ] T101 [P] Create `src/dk_data/claude_sdk/agents/referral_network.py` — `ReferralNetworkAgent(BaseAgent)`. Infer referral relationships from geographic proximity, Post-Acute PUF volumes, DMEPOS referring NPI, PECOS affiliations. Confidence scoring. Output to `gold.provider_network`. See contracts/agent-pipeline.yaml.
- [ ] T102 [P] Create CronJob `k8s/base/ingestion/cronjob-agent-referral-network.yaml` — monthly Day 5, 1Gi/1000m, 8h deadline (largest agent). Agent CronJob variant: `command: ["python", "-m", "dk_data.claude_sdk.runner"]`, `args: ["--agent", "referral_network", "--batch-size", "100"]`. `LITELLM_API_BASE` as static `value:`. Standard DB `secretKeyRef` + OTEL + labels per § CronJob Manifest Template.
- [ ] T103 Create `src/dk_data/sqlmesh/models/molecules/gold/provider_network.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (source_npi, dest_npi, relationship_type))`. Agent-produced referral relationships. Filter `WHERE confidence_score >= 0.50` in downstream queries.

### ContactVerification Agent

- [ ] T104 [P] Create `src/dk_data/claude_sdk/agents/contact_verification.py` — `ContactVerificationAgent(BaseAgent)`. API-only (no LLM calls). Uses Google Places API for phone verification and USPS Address Validation API for address standardization. Updates `silver.providers` with `phone_verified`, `address_verified`, `verification_date`.
- [ ] T105 [P] Create CronJob `k8s/base/ingestion/cronjob-agent-contact-verification.yaml` — monthly Day 10, 256Mi/250m, 4h deadline. Agent CronJob variant: `command: ["python", "-m", "dk_data.claude_sdk.runner"]`, `args: ["--agent", "contact_verification", "--batch-size", "200"]`. Requires `GOOGLE_PLACES_API_KEY` and `USPS_API_KEY` (via `secretKeyRef` from `dk-data-secrets`). No `LITELLM_API_BASE` (API-only agent, no LLM calls). Standard DB `secretKeyRef` + OTEL + labels per § CronJob Manifest Template.

### StaffingDecomposition Agent

- [ ] T106 [P] Create `src/dk_data/claude_sdk/agents/staffing_decomposition.py` — `StaffingDecompositionAgent(BaseAgent)`. Decompose HCRIS staffing data (Worksheet S-3/A) supplemented by BLS OEWS occupational mix ratios (FR-038) into structured categories (Nursing RN/LPN/CNA, Admin, Therapy, Lab, Pharmacy, Other). HCRIS provides ~60-70% overall coverage (~80% nursing); BLS OEWS improves departmental breakdown. Validation: decomposition sums to total_fte ± 2%.
- [ ] T107 [P] Create CronJob `k8s/base/ingestion/cronjob-agent-staffing-decomposition.yaml` — monthly Day 3, 512Mi/500m, 4h deadline. Agent CronJob variant with `LITELLM_API_BASE` as static `value:`. Standard DB `secretKeyRef` + OTEL + labels per § CronJob Manifest Template.

### EquipmentInventoryInference Agent (FR-047)

- [ ] T106a [P] Create `src/dk_data/claude_sdk/agents/equipment_inventory_inference.py` — `EquipmentInventoryInferenceAgent(BaseAgent)`. Infer binary equipment presence (MRI, CT, PET, cath lab, linear accelerator, surgical robot) from POS service capability flags + DRG volume inference (high-volume cardiac DRGs → cath lab, neuro DRGs → MRI). Target ~50-60% binary presence accuracy. Output populates `silver.equipment_inventory`, enriches `gold.facility_profile`.
- [ ] T106b [P] Create CronJob `k8s/base/ingestion/cronjob-agent-equipment-inventory.yaml` — monthly Day 4, 512Mi/500m, 4h deadline. Agent CronJob variant with `LITELLM_API_BASE` as static `value:`. Standard DB `secretKeyRef` + OTEL + labels per § CronJob Manifest Template.

### Agent CronJob Registration

- [ ] T108 Modify `k8s/base/kustomization.yaml` — add 6 agent CronJob resources.

**Checkpoint**: All 6 agents implemented with CronJobs. Monthly schedule staggered: Day 1 ServiceLine, Day 2 IDN, Day 3 Staffing, Day 4 EquipmentInventory, Day 5 Referral, Day 10 Contact.

---

## Phase 12: Contact Enrichment (Priority: P2)

**Purpose**: Enhance provider contact data with geocoding, insurer directory cross-reference, PubMed emails, and ORCID re-enablement.

**Depends on**: Phase 3 (needs silver.providers populated)

### Geocoding (FR-045)

- [ ] T116 [P] Implement NPPES address geocoding pipeline — batch geocode provider practice addresses using Nominatim (OpenStreetMap, free) or Google Geocoding API (free tier). Add `latitude` and `longitude` columns to `silver.providers`. Process during monthly NPPES refresh. Required input for ReferralNetwork agent's geographic proximity calculations.

### Insurer Provider Directories (FR-050)

- [ ] T117 [P] Create `src/dk_data/ingestion/fetchers/insurer_directories.py` — scrape publicly available provider directories from Aetna, BCBS, and UHC public search pages. Extract phone numbers and addresses for triangulation with NPPES + Google Places + USPS.
- [ ] T118 [P] Create `src/dk_data/ingestion/sources/insurer_directories.py` — loader for insurer directory data. Upsert to `raw.insurer_directories`.
- [ ] T119 [P] Create `src/dk_data/services/mcp/adapters/insurer_directories.py` — MCP adapter for insurer directory queries.

### PubMed Author Emails (FR-051)

- [ ] T120 [P] Extend existing PubMed pipeline to extract author email addresses from correspondence fields. Link emails to NPIs via author name + institutional affiliation matching against NPPES. Add `email` and `email_source` columns to `silver.providers`. Expected coverage: ~25-35% overall, ~80%+ academic physicians.

### ORCID Re-enablement (FR-057)

- [ ] T121 [P] Re-enable the existing ORCID pipeline in dk-data-fe (currently disabled). Verify API access, update fetcher config, ensure NPI linking logic works. Add ORCID identifiers to silver.providers for KOL identification.

### CronJobs & Registration

- [ ] T122 [P] Create CronJob manifests for contact enrichment: `cronjob-geocode-nppes.yaml` (monthly), `cronjob-fetch-insurer-directories.yaml` (monthly).
- [ ] T122a Modify `k8s/base/kustomization.yaml` — add 2 contact enrichment CronJob resources.
- [ ] T123 Modify `src/dk_data/ingestion/main.py`, `rate_limits.yaml`, `seed_data_sources.sql` — add insurer directories and geocoding entries.

**Checkpoint**: Phase 12 complete. Provider contact data enriched with geocoding, insurer cross-reference, PubMed emails, ORCID profiles.

---

## Phase 13: Advanced Clinical (Priority: P3)

**Purpose**: Add advanced clinical decision support data sources — drug-allergy cross-sensitivity, dose ranges, off-label indications, alert fatigue rules, and pharmacogenomics.

**Depends on**: Phase 5 (needs drug pipeline established)

### Migration 088: Advanced Clinical + Contact + Future Raw/Bronze Tables

- [ ] T124 Create migration `src/dk_data/sql/migrations/088_advanced_clinical_contact_raw_bronze_tables.sql` — raw tables: `raw.drug_allergy_crossref`, `raw.psyhamm_offlabel`, `raw.pharmgkb`, `raw.cms_synpuf`, `raw.pbm_formulary`, `raw.insurer_directories`, `raw.conference_abstracts`, `raw.state_apcd`, `raw.nlm_rxnorm` (if not in 086), `raw.cms_inpatient_puf_summary` (if not in 085), `raw.bls_oews`. Silver tables: `silver.drug_allergy_crossref`, `silver.dose_ranges`, `silver.offlabel_indications`, `silver.pharmacogenomics`, `silver.alert_rules`, `silver.equipment_inventory`, `silver.conference_activity`. Matching bronze tables.

### Drug-Allergy Cross-Sensitivity (FR-052)

- [ ] T125 [P] Create `src/dk_data/ingestion/fetchers/drug_allergy_crossref.py` — fetch published cross-reactivity tables (UC Davis, VCH, UNMC). Parse ATC hierarchy for class-level allergy mappings. ChEMBL structural similarity via API.
- [ ] T126 [P] Create `src/dk_data/ingestion/sources/drug_allergy_crossref.py` — loader for drug-allergy data.
- [ ] T127 [P] Create `src/dk_data/sqlmesh/models/molecules/silver/drug_allergy_crossref.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (drug_class, allergen_class))`.

### Dose Range Extraction (FR-053)

- [ ] T128 [P] Enable existing DailyMed SPL XML pipeline (Tier 3 in dk-data-fe). Configure for dose range extraction from structured dosing sections. For unstructured labels, implement LLM extraction (Claude Haiku) of min/max/unit from DOSAGE AND ADMINISTRATION text.
- [ ] T129 [P] Create `src/dk_data/sqlmesh/models/molecules/silver/dose_ranges.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (drug_name, indication))`.

### Off-Label Indications (FR-054)

- [ ] T130 [P] Create `src/dk_data/ingestion/fetchers/psyhamm_offlabel.py` — fetch PSYHAMM/HeTOP off-label drug-indication database (18K+ entries). Also fetch NCCN Compendium oncology off-label summaries.
- [ ] T131 [P] Create `src/dk_data/ingestion/sources/psyhamm_offlabel.py` — loader for off-label data.
- [ ] T132 [P] Create `src/dk_data/sqlmesh/models/molecules/silver/offlabel_indications.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (drug_name, indication))`. Cross-reference with ClinicalTrials.gov (AACT, already in dk-data-fe).

### Alert Fatigue Rules (FR-055)

- [ ] T133 [P] Create `src/dk_data/ingestion/fetchers/alert_rules.py` — parse ONCHigh list (15 rules) and Phansalkar list (33 rules) from published literature. Integrate FAERS signal detection via openFDA API.
- [ ] T134 [P] Create `src/dk_data/sqlmesh/models/molecules/silver/alert_rules.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key rule_id)`.

### Pharmacogenomics (FR-056)

- [ ] T135 [P] Create `src/dk_data/ingestion/fetchers/pharmgkb.py` — fetch PharmGKB data (free academic license). Extract clinically actionable gene-drug interactions.
- [ ] T136 [P] Create `src/dk_data/ingestion/sources/pharmgkb.py` — loader for PharmGKB data.
- [ ] T137 [P] Create `src/dk_data/sqlmesh/models/molecules/silver/pharmacogenomics.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (gene, drug))`.

### Bronze Transformers & Registration

- [ ] T138 Modify `src/dk_data/services/mcp/bronze_transformer.py` — add handlers for drug_allergy_crossref, psyhamm_offlabel, pharmgkb, alert_rules.
- [ ] T139 Modify `src/dk_data/ingestion/main.py`, `rate_limits.yaml`, `seed_data_sources.sql` — add advanced clinical entries.
- [ ] T140 [P] Create CronJob manifests: `cronjob-fetch-drug-allergy.yaml` (semi-annual), `cronjob-fetch-psyhamm.yaml` (semi-annual), `cronjob-fetch-alert-rules.yaml` (annual), `cronjob-fetch-pharmgkb.yaml` (quarterly).
- [ ] T140a Modify `k8s/base/kustomization.yaml` — add 4 advanced clinical CronJob resources.

**Checkpoint**: Phase 13 complete. Advanced clinical features available — drug-allergy mappings, dose ranges, off-label indications, alert rules, pharmacogenomics.

---

## Phase 14: Conference & Workforce Data (Priority: P3)

**Purpose**: Conference abstracts, PBM formularies, State APCD framework, BLS OEWS, and CMS DE-SynPUF for dev/test.

**Depends on**: Phase 11 (needs agent infrastructure for some processing)

### Conference Abstracts (FR-048)

- [ ] T141 [P] Create `src/dk_data/ingestion/fetchers/conference_abstracts.py` — fetch abstracts from ASCO Meeting Library (free account), AHA Scientific Sessions, ESMO Congress, ASH Annual Meeting. Annual per-conference.
- [ ] T142 [P] Create `src/dk_data/ingestion/sources/conference_abstracts.py` — loader with NPI linking via author name + institutional affiliation matching against NPPES (confidence scoring per EC-14).
- [ ] T143 [P] Create `src/dk_data/sqlmesh/models/molecules/silver/conference_activity.sql` — `INCREMENTAL_BY_UNIQUE_KEY(unique_key (npi, abstract_id))`.

### PBM Public Formularies (FR-046)

- [ ] T144 [P] Create `src/dk_data/ingestion/fetchers/pbm_formulary.py` — scrape/parse CVS Caremark, Express Scripts, OptumRx standard commercial formulary lists. Handle format variations (EC-13).
- [ ] T145 [P] Create `src/dk_data/ingestion/sources/pbm_formulary.py` — loader for PBM formulary data.

### State APCD Framework (FR-058)

- [ ] T146 Create State APCD ingestion framework — generic `src/dk_data/ingestion/fetchers/state_apcd.py` base class with per-state subclass pattern. Initial implementation for 2-3 pilot states (Massachusetts CHIA, Colorado CIVHC, Oregon). Handle ERISA gaps (EC-12).
- [ ] T147 [P] Create `src/dk_data/ingestion/sources/state_apcd.py` — loader for APCD data. Partition by state.

### BLS OEWS Data

- [ ] T148 [P] Create `src/dk_data/ingestion/fetchers/bls_oews.py` — fetch BLS Occupational Employment and Wage Statistics. Annual release (May). Extract occupational mix ratios for healthcare staffing decomposition.
- [ ] T149 [P] Create `src/dk_data/ingestion/sources/bls_oews.py` — loader for BLS OEWS data.

### CMS DE-SynPUF (FR-049)

- [ ] T150 [P] Create `src/dk_data/ingestion/fetchers/cms_synpuf.py` — one-time download of CMS DE-SynPUF synthetic claims data (2008-2010). OMOP format from AWS Marketplace (free).
- [ ] T151 [P] Create `src/dk_data/ingestion/sources/cms_synpuf.py` — loader for synthetic claims. One-time load.

### Registration & CronJobs

- [ ] T152 Modify `src/dk_data/ingestion/main.py`, `rate_limits.yaml`, `seed_data_sources.sql` — add conference abstracts, PBM formularies, State APCD, BLS OEWS, DE-SynPUF entries.
- [ ] T153 [P] Create CronJob manifests: `cronjob-fetch-conference-abstracts.yaml` (annual), `cronjob-fetch-pbm-formulary.yaml` (quarterly), `cronjob-fetch-bls-oews.yaml` (annual).
- [ ] T153a Modify `k8s/base/kustomization.yaml` — add 3 conference & workforce CronJob resources.

**Checkpoint**: Phase 14 complete. Conference abstracts linked to NPIs. PBM commercial formularies supplement Part D. State APCD framework ready for pilot states. BLS OEWS available for staffing agent. DE-SynPUF loaded for dev/test.

---

## Phase 15: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, cleanup, and cross-cutting improvements

- [ ] T154 Validate all SQLMesh models compile: `cd src && python -m sqlmesh plan --no-prompts`
- [ ] T155 [P] Validate MCP tool count: `python -c "from dk_data.services.mcp.tool_registry import TOOL_REGISTRY; print(f'Tools: {len(TOOL_REGISTRY)}')"` — expect ~68
- [ ] T156 [P] Validate agent registry count: `python -c "from dk_data.claude_sdk.agent_registry import AGENT_REGISTRY; print(f'Agents: {len(AGENT_REGISTRY)}')"` — expect 6
- [ ] T157 [P] Validate K8s manifests: `kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null`
- [ ] T158 [P] Verify backward compatibility — existing molecule MCP tools (DrugBank, ClinicalTrials, ChEMBL, etc.) still work with modified `base_tool.py`, `adapters/base.py`, and `api/routes/mcp.py` (Audit §A/§B backward-compat assertions)
- [ ] T159 Run quickstart.md validation end-to-end
- [ ] T159a [P] Create SC-009 verification rate tracking — add `dk_provider_verification_rate` Prometheus gauge (by state, by verification_type) that tracks progress toward >50% phone and >70% address verification targets for top 10 states by provider count. Add SQL query for dashboard reporting.
- [ ] T160 Code cleanup — ensure all new files have consistent imports, logging, error handling
- [ ] T161 [P] Verify PostgREST gold schema access: `curl -H "Authorization: Bearer $JWT" http://localhost:3000/gold/provider_profile?npi=eq.1234567890` — confirm analyst JWT required, web_anon rejected

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1+US2 Provider (Phase 3)**: Depends on Phase 2 — **MVP target**
- **US3 Facility (Phase 4)**: Depends on Phase 2 — can run parallel with Phase 3
- **US4 Drug Market (Phase 5)**: Depends on Phase 2 — can run parallel with Phases 3-4
- **US9 Pipeline (Phase 6)**: Depends on Phases 3-5 (needs sources to create CronJobs for)
- **US5 Geographic (Phase 7)**: Depends on Phase 2 — can run parallel with Phases 3-5
- **US6 Open Payments (Phase 8)**: Depends on Phase 3 (US1 creates Open Payments infrastructure)
- **US7 Health System (Phase 9)**: Depends on Phase 4 (US3 creates PECOS/CHOW/Affiliation infrastructure)
- **US8 Drug Interaction (Phase 10)**: Depends on Phase 2 — can run parallel with Phases 3-5
- **Agentic (Phase 11)**: Depends on Phases 3-5 (needs silver tables to process)
- **Contact Enrichment (Phase 12)**: Depends on Phase 3 (needs silver.providers)
- **Advanced Clinical (Phase 13)**: Depends on Phase 5 (needs drug pipeline) + migration 088
- **Conference & Workforce (Phase 14)**: Depends on Phase 11 (needs agent infrastructure)
- **Polish (Phase 15)**: Depends on all previous phases

### User Story Dependencies

```
Phase 2 (Foundation)
  ├── Phase 3 (US1+US2 Provider) ← MVP
  │   ├── Phase 8 (US6 Open Payments Detail)
  │   ├── Phase 12 (Contact Enrichment)
  │   └── Phase 6 (US9 Pipeline, partial)
  ├── Phase 4 (US3 Facility)
  │   ├── Phase 9 (US7 Health System)
  │   └── Phase 6 (US9 Pipeline, partial)
  ├── Phase 5 (US4 Drug Market)
  │   ├── Phase 13 (Advanced Clinical)
  │   └── Phase 6 (US9 Pipeline, partial)
  ├── Phase 7 (US5 Geographic)
  └── Phase 10 (US8 Drug Interaction)
      └── Phase 11 (Agentic Processing)
          └── Phase 14 (Conference & Workforce Data)
              └── Phase 15 (Polish)
```

### Within Each User Story

- Migration before adapters/fetchers/loaders
- Adapters before tool registry registration
- Fetchers/loaders before main.py registration
- Bronze models before silver models
- Silver models before gold models
- Tool registry before end-to-end testing

### Parallel Opportunities

- **Phase 2**: T004a-T015 are independent files — all [P] tasks can run in parallel (T004a mcp.py, T005-T007 base classes, T007a cms_datasets.py, T008 Socrata base, T009-T013 agent infra, T014-T015 PostgREST+observability)
- **Phase 3**: All 7 adapters (T017-T023) can run in parallel. All fetcher/loader pairs (T024-T029) in parallel. Bronze models (T036-T037) in parallel. Silver models (T038-T041) in parallel.
- **Phases 3, 4, 5, 7, 10**: Can all start simultaneously after Phase 2 completes (different files, different sources)
- **Phase 11**: All 6 agents can be developed in parallel (different files)
- **Phase 12**: Geocoding, insurer directories, PubMed emails, ORCID can develop in parallel (different files)
- **Phase 13**: All clinical adapters (drug-allergy, dose ranges, off-label, pharmacogenomics) can develop in parallel
- **Phase 14**: Conference abstracts, PBM formularies, State APCD, BLS OEWS, DE-SynPUF — all independent sources

---

## Parallel Example: User Story 1 (Phase 3)

```bash
# After Phase 2 Foundation completes:

# Parallel batch 1: All 7 adapters (different files)
Task T017: "Create NPPES adapter in src/dk_data/services/mcp/adapters/nppes.py"
Task T018: "Create Part D adapter in src/dk_data/services/mcp/adapters/cms_partd_prescribers.py"
Task T019: "Create Part D Summary adapter"
Task T020: "Create Physician PUF adapter"
Task T021: "Create Physician Summary adapter"
Task T022: "Create Open Payments adapter"
Task T023: "Create Care Compare adapter"

# Parallel batch 2: All fetcher/loader pairs (different files)
Task T024: "Create NPPES fetcher"
Task T025: "Create NPPES loader"
Task T026: "Create Part D fetcher"
# ... etc

# Sequential: Registration (modifies shared files)
Task T030: "Add 7 ToolDefinitions to tool_registry.py"
Task T031: "Add 7 SOURCES entries to main.py"

# Parallel batch 3: All bronze models (different files)
Task T036: "Create bronze/cms_nppes.sql"
Task T037: "Create 6 remaining bronze models"

# Parallel batch 4: All silver models (different files)
Task T038: "Create silver/providers.sql"
Task T039: "Create silver/prescribing_profiles.sql"
Task T040: "Create silver/procedure_profiles.sql"
Task T041: "Create silver/open_payments.sql"

# Sequential: Gold model (depends on all silver models)
Task T042: "Create gold/provider_profile.sql"
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1+US2 Provider Lookup
4. **STOP and VALIDATE**: Test provider lookup by NPI and name search independently
5. Verify `gold.provider_profile` via PostgREST: `curl -H "Authorization: Bearer $JWT" http://localhost:3000/gold/provider_profile?npi=eq.1234567890`
6. Deploy/demo if ready — this alone replaces significant IQVIA data

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1+US2 Provider → Test → Deploy (MVP! HCP Compass basic capability)
3. US3 Facility → Test → Deploy (HCO Navigator enabled)
4. US4 Drug Market → Test → Deploy (Lumina enabled)
5. US9 Pipeline → CronJobs active → Automated refresh
6. US5 Geographic → Test → Deploy (SageAI enabled)
7. US6+US7 → Enhanced features
8. US8 + Agentic → Clinical features + inference
9. Contact Enrichment → Geocoding, insurer cross-ref, PubMed emails, ORCID
10. Advanced Clinical → Drug-allergy, dose ranges, off-label, pharmacogenomics, alert fatigue
11. Conference & Workforce → Conference abstracts, PBM formularies, State APCDs, BLS OEWS, DE-SynPUF
12. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers after Phase 2:
- Developer A: Phase 3 (US1+US2 Provider) → Phase 8 (US6) → Phase 12 (Contact Enrichment) → Phase 15 (Polish)
- Developer B: Phase 4 (US3 Facility) → Phase 9 (US7) → Phase 11 (Agents)
- Developer C: Phase 5 (US4 Drug Market) → Phase 7 (US5) → Phase 13 (Advanced Clinical)
- Developer D: Phase 10 (US8 Clinical) → Phase 6 (US9 Pipeline) → Phase 14 (Conference & Workforce)

---

## Task Summary

| Phase | Tasks | Scope |
|-------|-------|-------|
| Phase 1: Setup | T001-T003 | 3 verification tasks |
| Phase 2: Foundation | T004-T015 + T004a, T007a | 14 tasks (2 new from Integration Audit) |
| Phase 3: US1+US2 Provider | T016-T043 | 28 tasks (MVP) |
| Phase 4: US3 Facility | T044-T058 | 15 tasks |
| Phase 5: US4 Drug Market | T059-T069 | 11 tasks |
| Phase 6: US9 Pipeline | T070a-T075 | ~36 tasks (CronJob manifests) |
| Phase 7: US5 Geographic | T076-T084 | 15 tasks (incl. HCRIS T082a-f) |
| Phase 8: US6 Open Payments | T085-T086 | 2 tasks |
| Phase 9: US7 Health System | T087-T089 | 3 tasks |
| Phase 10: US8 Drug Interaction | T090-T098c | 12 tasks |
| Phase 11: Agentic Processing | T099-T108 | 12 tasks |
| Phase 12: Contact Enrichment | T116-T123 | 9 tasks |
| Phase 13: Advanced Clinical | T124-T140a | 17 tasks |
| Phase 14: Conference & Workforce | T141-T153a | 14 tasks |
| Phase 15: Polish | T154-T161 | 9 tasks |
| **Total** | | **~200 tasks** |

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- [Audit §X] cross-references Integration Audit finding (see spec.md § Integration Audit)
- Each user story is independently completable and testable after Phase 2
- No test tasks generated (not explicitly requested in spec)
- **Integration Audit tasks**: T004a (mcp.py §A), T005 (base_tool.py §B), T007 (silver_gold_refresher.py §C), T007a (cms_datasets.py §0.5), T030 (tool_registry §D), T055a (healthcare_facilities §E)
- Agent CronJobs use the cluster LiteLLM proxy (`LITELLM_API_BASE=http://litellm.infra.svc.cluster.local:4000`) — no `ANTHROPIC_API_KEY` needed in agent pods (API keys managed centrally by LiteLLM in infra namespace). `LITELLM_API_BASE` is a static `value:` in the CronJob manifest (NOT from DopplerSecret — it's a cluster-internal URL). Exception: ContactVerification is API-only (needs `GOOGLE_PLACES_API_KEY` + `USPS_API_KEY` via `secretKeyRef`, no LLM calls)
- **CronJob secret access**: All CronJobs use individual `secretKeyRef` per DB key (POSTGRES_HOST/PORT/USER/PASSWORD/DB) — NOT `envFrom` with a secret ref. Source-specific API keys also via individual `secretKeyRef` with `optional: true`. See spec.md § CronJob Manifest Template for the complete mandatory structure.
- **CronJob image name**: All CronJob YAMLs MUST use `ghcr.io/data-kinetic/dk-data-fe/job-trigger` as the base image name. Kustomize overlays (staging/prod) automatically replace the tag via image transformer matching. Using a different image name breaks the tag update pipeline.
- **Deployment flow**: `build-push.yaml` only triggers on `main` and `staging` branches — feature branches do NOT build images. CronJobs are deployed to staging when the feature branch is merged to `staging`: CI builds image → auto-commits tag to overlay → ArgoCD auto-syncs new resources to `dk-data-staging` namespace. DopplerSecret project: `dk-data-fe` (config: `prd` base, patched to `stg` for staging).
- CMS data.cms.gov APIs are fully open — no API key registration needed for most sources
- Year-partitioned tables (Part D, Physician PUF) need partition creation in migration 084 for years 2015-2025
- Weekly CronJobs for annual PUF sources (Part D, Physician PUF) check for new annual releases — they download only when new data is detected. Annual PUFs use full-year replacement, not incremental within-year updates.
- Hospital counts are source-dependent: ~6K in POS, ~4K with quality ratings, ~3K with HCRIS cost reports. Not all hospitals appear in all sources.
- NPPES V2 format transition (2026-03-03): Fetcher and adapter must detect and parse both V1 and V2 CSV column layouts
- CMS Socrata API actual rate limit is ~10K req/sec (per documentation), but practical sustained throughput is ~1-5K req/sec
- POS file provides accreditor field (TJC/DNV/HFAP) but chain ID does NOT equal full IDN hierarchy — only binary chain membership
- State APCD data requires Data Use Agreements (DUAs) per state; ERISA-exempt employers are excluded (~60% of commercially insured)
- PharmGKB requires academic license for bulk data; UMLS requires free NLM account for RxNorm full dataset
- Advanced clinical features (drug-allergy, off-label, pharmacogenomics) are P3 — implement after core provider/facility/drug pipeline
- Total estimated engineering effort: ~20-27 weeks (see spec.md for breakdown)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
