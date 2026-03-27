# Tasks: CMS PUF & Platform Data Reconciliation

**Input**: Design documents from `specs/019-cms-puf-platform-reconciliation/`
**Branch**: `019-cms-puf-platform-reconciliation`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared state dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- File paths are relative to `src/dk_data/` unless otherwise noted

---

## Phase 1: Setup (Migration & Schema Foundation)

**Purpose**: Apply the consolidated schema delta to staging. Nothing else can begin until the target tables exist.

**Checkpoint**: `085_cms_puf_platform_reconciliation.sql` applied cleanly to staging; all existing tests pass.

- [ ] T001 Audit all 57 016-branch migration files against current main-branch schema — document in `specs/019-cms-puf-platform-reconciliation/research.md` which objects already exist and which are genuinely new
- [ ] T002 Write `src/dk_data/sql/migrations/085_cms_puf_platform_reconciliation.sql` — delta-only: new `hcs_raw` tables (7 core + 21 additional), `mol_silver.publication_evidence`, `mol_silver.publication_evidence_staging` (same schema as live table; `content_hash` is merge key), `mol_silver.physician_payments`, `mol_silver.research_grants`, `mol_silver.agent_quarantine`, `mol_silver.europepmc` (silver normalization table per data-model.md), skeleton DDL for 6 CMS agent silver tables (`hcs_silver.service_lines`, `hcs_silver.idn_hierarchy`, `hcs_silver.referral_network`, `hcs_silver.verified_contacts`, `hcs_silver.staffing_decomposition`, `hcs_silver.equipment_inventory`), `hcs_bronze/hcs_silver/hcs_gold` schema creation, and `INSERT INTO meta.data_sources` rows for all 28 new CMS sources + 6 new API sources
- [ ] T003 Apply migration 085 to staging database and run `pytest tests/test_migration_runner.py tests/test_imports.py tests/test_api.py -v` — confirm zero regressions

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infrastructure shared by all user stories — BaseFetcher retry config, HCS model directory, agent base class.

**⚠️ CRITICAL**: Complete before any user story work begins.

- [ ] T004 Extend `ingestion/main.py` `run_ingestion()` to read `max_retries` and `retry_base_delay_seconds` from SOURCES entry and reconfigure `BaseFetcher.session` Retry adapter before calling `fetcher.fetch()` — default: `max_retries=3`, `retry_base_delay_seconds=2` (~15 lines)
- [ ] T005 [P] Create `sqlmesh/models/hcs/bronze/`, `sqlmesh/models/hcs/silver/`, `sqlmesh/models/hcs/gold/` directories with `.gitkeep` placeholders — parallel safe (filesystem only)
- [ ] T006 [P] Write `agents/base_agent.py` — abstract base class with: `__init__(self, litellm_url, model)`, `_call_llm(prompt) -> str`, `run(scope, limit) -> AgentResult`, `_write_quarantine(record)` for confidence < 0.5, and `_flag_needs_review(record)` for 0.5–0.79 — routes all LLM calls through LiteLLM proxy URL from env; no direct provider calls

**Checkpoint**: Retry config live in `main.py`; HCS model dirs exist; `base_agent.py` importable with `from dk_data.agents.base_agent import BaseAgent`

---

## Phase 3: User Story 1 — CMS PUF Data for Drug Market Analysis (Priority: P1)

**Goal**: 28 CMS PUF file-based sources ingested to `hcs_raw`, normalized through `hcs_bronze`/`hcs_silver`/`hcs_gold`, queryable via PostgREST.

**Independent Test**: Run `python -m dk_data.ingestion.main --source cms_part_d_spending --file /tmp/PartD_2023.csv`; verify row in `hcs_raw.cms_part_d_spending`; re-run with same file and confirm zero new inserts (hash-skip); query `meta.refresh_log` and confirm entry exists.

- [ ] T007 [US1] Implement 7 core CMS PUF loader modules in `ingestion/sources/`: `cms_part_d_spending.py`, `cms_part_b_spending.py`, `cms_open_payments.py`, `cms_nppes.py`, `cms_inpatient_puf.py`, `cms_physician_puf.py`, `cms_hospital_general_info.py` — each loader: (1) computes MD5 of file, (2) checks `hcs_raw.{table} WHERE _source_hash = %s`, (3) skips and returns success if > 0 rows, (4) bulk-inserts with `_source_hash` and `_loaded_at`, (5) calls `log_to_meta(source_name, result)` — follow `ingestion/sources/cms_inpatient.py` as the reference pattern
- [ ] T008 [P] [US1] Implement remaining 21 CMS PUF loader modules in `ingestion/sources/` (cms_medicare_advantage, cms_medicaid_drug_spending, cms_dme_puf, cms_home_health, cms_hospice_puf, cms_snf_puf, cms_outpatient_puf, cms_referring_providers, cms_ordering_providers, cms_lab_services, cms_imaging_puf, cms_mental_health_puf, cms_opioid_puf, cms_telehealth_puf, cms_geographic_variation, cms_chronic_conditions, cms_dual_eligible, cms_enrollment_puf, cms_claim_type_puf, cms_utilization_puf, cms_cost_reports_puf) — same hash-skip + log_to_meta pattern as T007
- [ ] T009 [P] [US1] Implement 7 core CMS PUF fetcher subclasses in `ingestion/fetchers/`: `cms_part_d_spending.py`, `cms_part_b_spending.py`, `cms_open_payments.py`, `cms_nppes.py`, `cms_inpatient_puf.py`, `cms_physician_puf.py`, `cms_hospital_general_info.py` — extend `BaseFetcher`; `__init__(self, data_dir=None)`; `fetch()` returns `{status, records: [], hash: str}` where hash is MD5 of downloaded file; `get_latest_url()` returns the CMS data.gov URL for each dataset
- [ ] T010 [P] [US1] Implement remaining 21 CMS PUF fetcher subclasses in `ingestion/fetchers/` (matching the 21 loaders from T008) — same `BaseFetcher` pattern; `requires_file: True` in SOURCES entry
- [ ] T011 [US1] Register all 28 new CMS PUF sources in the `SOURCES` dict in `ingestion/main.py` — each entry has: `name`, `description`, `loader` (callable), `requires_file: True`, `default_days_back: None`; no `fetcher` key for file-based sources; `meta_name` matching the `source_name` inserted in migration 085
- [ ] T012 [US1] Write 7 SQLMesh bronze models in `sqlmesh/models/hcs/bronze/`: `cms_part_d_spending.sql`, `cms_part_b_spending.sql`, `cms_open_payments.sql`, `cms_nppes.sql`, `cms_inpatient_puf.sql`, `cms_physician_puf.sql`, `cms_hospital_general_info.sql` — kind `INCREMENTAL_BY_TIME_RANGE` on `_source_year`; columns are typed pass-through from `hcs_raw` table matching spec data-model; column names exactly as per `data-model.md` Bronze section
- [ ] T013 [US1] Write `sqlmesh/models/hcs/silver/cms_drug_market.sql` — kind `FULL`; grain `ndc`; joins `hcs_bronze.cms_part_d_spending` and `hcs_bronze.cms_part_b_spending` on `generic_name`/`ndc`; computes `part_d_spending`, `part_b_spending`, `total_spending`, `total_beneficiaries`, `usp_category` (join to USP classification reference), `rbcs_category` per `data-model.md`
- [ ] T014 [US1] Write `sqlmesh/models/hcs/gold/cms_drug_market_profile.sql` — kind `FULL`; grain `ndc`; extends silver with `market_share_pct` (spending / SUM OVER generic_name group), `spending_rank_in_category` using `RANK() OVER (PARTITION BY usp_category ORDER BY total_spending DESC NULLS LAST)` per `data-model.md` Gold section
- [ ] T015 [US1] Write 28 K8s CronJob manifests in `k8s/apps/cronjobs/base/` — one per CMS source; follow `cronjob-fetch-ema-reg.yaml` template: `restartPolicy: Never`, `backoffLimit: 2`, `securityContext.runAsNonRoot: true`, `runAsUser: 1000`, `seccompProfile.RuntimeDefault`, `concurrencyPolicy: Forbid`; schedule monthly (first Sunday of month, staggered by 15 min per source to avoid thundering herd)
- [ ] T016 [US1] Update PostgREST exposure: add `hcs_bronze`, `hcs_silver`, `hcs_gold` to `PGRST_DB_SCHEMAS` in the PostgREST K8s manifest or Doppler config — confirm `mol_raw` and `hcs_raw` are absent
- [ ] T017 [US1] Write 28 individual fetcher/loader test files — one per CMS source (e.g., `tests/test_cms_part_d_fetcher.py`, `tests/test_cms_part_b_fetcher.py`, …, `tests/test_cms_cost_reports_fetcher.py`); each test file covers: (1) happy-path file ingestion with source-specific mock CSV (correct column names), (2) hash-skip on second identical run returns `records_inserted: 0`, (3) `log_to_meta` called once per run, (4) `meta.refresh_log` entry exists after run, (5) `BaseFetcher` session retry adapter present — 28 test files total, not a shared file, so failures isolate to the specific source

---

## Phase 4: User Story 2 — Regulatory & Clinical Evidence Sources (Priority: P2)

**Goal**: EuropePMC, NIH Reporter, EMA, Cochrane, DrugBank, and PubChem sources ingested to `mol_raw`/bronze; silver models entity-link to `mol_silver.molecules`; gold `market_summary` aggregates all six.

**Independent Test**: Run `python -m dk_data.ingestion.main --source europepmc`; verify rows in `mol_raw.europepmc_raw` with `processed_to_bronze = FALSE`; run SQLMesh for `mol_bronze.europepmc`; verify rows appear with `pmid` and `title` columns populated.

- [ ] T018 [US2] Implement `ingestion/fetchers/europepmc.py` — extend `BaseFetcher`; `fetch(**kwargs)` accepts `days_back=int`; calls EuropePMC REST API (`https://www.ebi.ac.uk/europepmc/webservices/rest/search`) paginating with `cursorMark`; returns `{status, records: List[Dict], hash: None}`; `get_latest_url()` returns base API URL; write `ingestion/sources/europepmc.py` loader: bulk-insert to `mol_raw.europepmc_raw` deduped by `pmid`; call `log_to_meta('europepmc', result)`
- [ ] T019 [P] [US2] Implement `ingestion/fetchers/nih_reporter.py` — extend `BaseFetcher`; calls NIH Reporter API (`https://api.reporter.nih.gov/v2/projects/search`) with `date_added` filter; returns `{status, records, hash: None}`; write `ingestion/sources/nih_reporter.py` loader: bulk-insert to `mol_raw.nih_reporter_raw` deduped by `project_number`; call `log_to_meta`
- [ ] T020 [P] [US2] Verify existing `ingestion/fetchers/ema_regulatory.py` and `ingestion/sources/ema_regulatory.py` use the canonical `BaseFetcher` pattern and call `log_to_meta` — if missing, add `log_to_meta` call and `default_days_back` to SOURCES entry; if `fetcher` key is missing from SOURCES, add `EMARegulatoryCIFetcher`
- [ ] T021 [P] [US2] Verify existing Cochrane, DrugBank, PubChem fetchers and loaders call `log_to_meta` and are registered in SOURCES with `default_days_back` — patch any gaps; these sources already exist on main, so this is an alignment check not a rewrite
- [ ] T022 [US2] Write `sqlmesh/models/molecules/bronze/europepmc.sql` — kind `INCREMENTAL_BY_TIME_RANGE` on `publication_date`; grain `pmid`; extracts typed fields from `mol_raw.europepmc_raw.response_body` JSONB: `pmid`, `title`, `abstractText` → `abstract_text`, `journalInfo->>'journal'` → `journal_title`, `firstPublicationDate` → `publication_date`, `authorList->'author'` → `author_list` (kept as JSONB array), `doi`; sets `processed_to_bronze = TRUE` on raw record after extraction
- [ ] T023 [P] [US2] Write `sqlmesh/models/molecules/bronze/nih_reporter.sql` — kind `INCREMENTAL_BY_TIME_RANGE` on `start_date`; grain `project_number`; extracts from `mol_raw.nih_reporter_raw.response_body`: `project_num`, `project_title`, `fiscal_year`, `principal_investigators` → `pi_names` JSONB, `organization.org_name`, `award_amount`, `abstract_text`, `terms`, `project_start_date`, `project_end_date`
- [ ] T024 [US2] Write `sqlmesh/models/molecules/silver/ema_regulatory.sql` — kind `FULL`; grain `product_number`; joins `mol_bronze.ema_regulatory` to `mol_silver.molecules` using dual-strategy: first `LOWER(active_substance) = LOWER(m.canonical_name)`, fallback `LOWER(inn) = LOWER(m.canonical_name)`; outputs `molecule_id` (NULL if unlinked), `link_strategy` ('exact_name', 'inn_match', 'unlinked'), and all EMA fields per `data-model.md`
- [ ] T025 [P] [US2] Write `sqlmesh/models/molecules/silver/drug_spending.sql` — kind `FULL`; grain `(generic_name, program, year)`; UNIONs `hcs_bronze.cms_part_d_spending` (program='part_d') and `hcs_bronze.cms_part_b_spending` (program='part_b'); links to `mol_silver.molecules` on `LOWER(generic_name) = LOWER(m.canonical_name)` with brand_name fallback; computes `avg_spending_per_claim`
- [ ] T026 [US2] Write `sqlmesh/models/molecules/gold/market_summary.sql` — kind `FULL`; grain `molecule_id`; 10-way LEFT JOIN from `mol_silver.molecules` to: drug_spending (Part D + Part B aggregated), ema_regulatory (latest authorisation_status + date), cochrane review count, europepmc publication count, nih grant count + total funding, trial outcomes count, publication evidence count — all joins are LEFT so model degrades gracefully when any source is absent; per `data-model.md` Gold section
- [ ] T027 [P] [US2] Write CronJob manifests for EuropePMC (`k8s/apps/cronjobs/base/cronjob-fetch-europepmc.yaml`) and NIH Reporter (`k8s/apps/cronjobs/base/cronjob-fetch-nih-reporter.yaml`) — weekly schedule (Sunday UTC), same security template as existing CronJobs
- [ ] T028 [P] [US2] Write `tests/test_europepmc_fetcher.py` and `tests/test_nih_reporter_fetcher.py` — cover: happy-path API response with mocked `responses` library, pagination cursor handling, empty result set, 429 retry behaviour

---

## Phase 5: User Story 3 — Full Refresh History (Priority: P3)

**Goal**: Every new source produces `meta.refresh_log` entries and updates `meta.data_sources.last_successful_refresh` after each run — zero silent sources.

**Independent Test**: After completing Phase 3 and Phase 4 integration tasks, run `SELECT source_name, last_successful_refresh, last_refresh_status FROM meta.data_sources ORDER BY source_name` — all 34 new sources (28 CMS + 6 API) must have non-NULL `last_successful_refresh` after their first successful run.

- [ ] T029 [US3] Audit all 28 CMS loader files (T007 + T008) and all 6 API loader files (T018–T021): verify each calls `log_to_meta(source_name, result)` exactly once per run with a correctly-shaped result dict (`status`, `records_fetched`, `records_inserted`, `records_updated`, `errors: List[str]`) — fix any missing calls in-place
- [ ] T030 [P] [US3] Write `tests/test_log_to_meta_integration.py` — tests: (1) `log_to_meta` writes to `meta.refresh_log` with correct source_id, (2) successful run updates `last_successful_refresh`, (3) failed run does NOT update `last_successful_refresh`, (4) `_compute_days_back` returns `default_days_back` on first run (NULL last_refresh), (5) `_compute_days_back` returns elapsed_days + 1 on subsequent run

---

## Phase 6: User Story 4 — Agent System (Priority: P4)

**Goal**: 7 agents operational; publication evidence agent writes to `mol_silver.publication_evidence_staging`; SQLMesh merges staging → live; `mol_gold.trial_outcomes` no longer references `xenon`; quarantine captures sub-0.5 confidence records.

**Independent Test**: Run `python -m dk_data.agents.publication_evidence_extractor --limit 10`; verify rows appear in `mol_silver.publication_evidence_staging` with `content_hash` and `confidence_score`; run SQLMesh for `mol_silver.publication_evidence` and verify records merge into the live table; query `mol_gold.trial_outcomes WHERE evidence_source = 'publication'` — must return rows with no `xenon` schema in query path.

- [ ] T031 [US4] Write `agents/service_line_inference.py` — **first**: confirm `hcs_silver.service_lines` DDL in migration 085 matches columns the agent will write (`npi`, `service_line`, `confidence_score`, `needs_review`, `agent_output JSONB`, `_loaded_at`); extend DDL in migration if columns differ; then implement: extends `BaseAgent`; reads `hcs_bronze.cms_inpatient_puf` DRG claims per NPI; calls LiteLLM to infer clinical service lines; writes to `hcs_silver.service_lines` with `confidence_score`; records < 0.5 written via `_write_quarantine()`; records 0.5–0.79 written with `needs_review = TRUE`
- [ ] T032 [P] [US4] Write `agents/idn_hierarchy.py` — **first**: confirm `hcs_silver.idn_hierarchy` DDL matches columns this agent writes (`child_npi`, `parent_organization`, `confidence_score`, `needs_review`, `agent_output`, `_loaded_at`); extend DDL if needed; then implement: extends `BaseAgent`; groups facilities by organization name similarity + geographic proximity; infers IDN parent-child relationships; writes to `hcs_silver.idn_hierarchy` with confidence score
- [ ] T033 [P] [US4] Write `agents/referral_network.py` — **first**: confirm `hcs_silver.referral_network` DDL matches columns this agent writes (`referring_npi`, `receiving_npi`, `referral_volume`, `confidence_score`, `needs_review`, `agent_output`, `_loaded_at`); extend DDL if needed; then implement: extends `BaseAgent`; analyzes `hcs_bronze.cms_referring_providers` + `cms_ordering_providers`; infers referring patterns; writes referral graph edges to `hcs_silver.referral_network`
- [ ] T034 [P] [US4] Write `agents/contact_verification.py` — **first**: confirm `hcs_silver.verified_contacts` DDL matches columns this agent writes (`npi`, `verified_phone`, `verified_email`, `verification_status`, `confidence_score`, `needs_review`, `agent_output`, `_loaded_at`); extend DDL if needed; then implement: extends `BaseAgent`; validates NPI contact data from `hcs_raw.cms_nppes`; writes verified/flagged records to `hcs_silver.verified_contacts`
- [ ] T035 [P] [US4] Write `agents/staffing_decomposition.py` — **first**: confirm `hcs_silver.staffing_decomposition` DDL matches columns this agent writes (`provider_id`, `role_category`, `fte_estimate`, `confidence_score`, `needs_review`, `agent_output`, `_loaded_at`); extend DDL if needed; then implement: extends `BaseAgent`; reads cost report staffing data; decomposes into clinical role categories; writes to `hcs_silver.staffing_decomposition`
- [ ] T036 [P] [US4] Write `agents/equipment_inventory.py` — **first**: confirm `hcs_silver.equipment_inventory` DDL matches columns this agent writes (`npi`, `equipment_category`, `hcpcs_evidence JSONB`, `confidence_score`, `needs_review`, `agent_output`, `_loaded_at`); extend DDL if needed; then implement: extends `BaseAgent`; infers equipment inventory from HCPCS procedure codes in physician PUF; writes to `hcs_silver.equipment_inventory`
- [ ] T037 [US4] Write `agents/publication_evidence_extractor.py` — extends `BaseAgent`; reads `mol_silver.europepmc` abstracts not yet in `mol_silver.publication_evidence_staging` (check by pmid+endpoint_name hash); calls LiteLLM to extract: `endpoint_name`, `endpoint_type`, `hazard_ratio`, `p_value`, `response_rate`, `median_survival_months`, `sample_size`; computes `content_hash = md5(pmid + endpoint_name)`; writes to `mol_silver.publication_evidence_staging` (skips if content_hash already exists); quarantines confidence < 0.5; does NOT write to `mol_silver.publication_evidence` directly — the SQLMesh model handles promotion from staging
- [ ] T038 [US4] Write `sqlmesh/models/molecules/silver/publication_evidence.sql` — kind `INCREMENTAL_BY_UNIQUE_KEY` with unique key `content_hash`; reads from `mol_silver.publication_evidence_staging`; merges new/updated staging rows into `mol_silver.publication_evidence` (INSERT new content_hash; UPDATE if confidence_score changed); ensures agent writes cannot be silently overwritten by a full SQLMesh re-run; this model owns the staging→live promotion and schema contract enforcement
- [ ] T039 [US4] Update `sqlmesh/models/molecules/gold/trial_outcomes.sql` — replace `FROM xenon.publication_evidence pe` CTE with `FROM mol_silver.publication_evidence pe WHERE pe.confidence_score >= 0.40 AND pe.needs_review = FALSE`; extend grain from `(molecule_id, trial_nct_id, evidence_source)` to `(molecule_id, trial_nct_id, endpoint_name, evidence_source)` per spec FR-033
- [ ] T040 [US4] Write `api/routes/agents.py` — FastAPI router at `/api/v1/agents`; implement all 4 endpoints per `contracts/api.md`: `GET /agents`, `POST /agents/{agent_id}/run`, `GET /agents/{agent_id}/runs`, `GET /agents/quarantine`; on-demand run triggers agent in background task; reads run history from `meta.refresh_log`
- [ ] T041 [US4] Register `agents.py` router in the main FastAPI app entry point
- [ ] T042 [P] [US4] Write `tests/test_publication_evidence_agent.py` — cover: (1) endpoint extraction writes to `mol_silver.publication_evidence_staging` (not the live table directly), (2) duplicate content_hash in staging is skipped (no duplicate insert), (3) confidence < 0.5 goes to quarantine not staging, (4) confidence 0.5–0.79 sets `needs_review = TRUE` in staging, (5) all LLM calls go through mocked LiteLLM URL (no direct provider calls), (6) SQLMesh model correctly promotes from staging to live on merge
- [ ] T043 [P] [US4] Write `tests/test_agents_router.py` — cover: `GET /agents` returns all 7 agents, `POST /agents/publication_evidence_extractor/run` returns 202, `GET /agents/quarantine` returns paginated results

---

## Phase 7: User Story 5 — Data Tools Gateway (Priority: P5)

**Goal**: `/api/v1/data-tools` registry and backfill endpoints operational; freshness check prevents redundant external fetches.

**Independent Test**: `GET /api/v1/data-tools/registry` returns 54+ tools with `last_refresh` metadata; `POST /api/v1/data-tools/backfill {source_name: "cms_part_d_spending", force: false}` returns `skipped: true` if recently ingested, or `202` and triggers ingestion if stale.

- [ ] T044 [US5] Write `services/data_tools/registry.py` — `DataToolRegistry` class: reads all sources from `meta.data_sources`, enriches with `SOURCES` dict metadata (category, supported_query_keys, requires_file), caches result for 5 minutes; method `get_all() -> List[DataTool]`, `get(source_name) -> DataTool | None`
- [ ] T045 [US5] Write `services/data_tools/data_registry.py` — `DataFreshnessChecker` class: `is_fresh(source_name, max_age_hours) -> bool` reads `last_successful_refresh` from `meta.data_sources`; returns False if NULL or older than `max_age_hours`; default threshold per source category (CMS bulk: 720h, API: 24h)
- [ ] T046 [P] [US5] Write 54 source adapter files in `services/data_tools/adapters/` — 28 CMS bulk adapters (one per source, e.g., `cms_part_d.py`) + 6 API source adapters (europepmc, nih_reporter, ema_regulatory, cochrane, drugbank, pubchem) + ~20 CMS sub-query adapters (one per meaningful query facet such as cms_part_d_by_drug, cms_open_payments_by_physician, etc.); each adapter wraps the source's `loader` callable and provides metadata: `category` (cms_bulk / mol_api / cms_subquery), `supported_query_keys` list, `description`; sub-query adapters are thin wrappers over the base CMS loader with a pre-applied filter; follow the pattern from existing `services/data_tools/adapters/` if any exist
- [ ] T047 [US5] Write `api/routes/data_tools.py` — FastAPI router at `/api/v1/data-tools`; implement 3 endpoints per `contracts/api.md`: `GET /registry`, `POST /backfill`, `GET /{source_name}/status`; backfill calls `DataFreshnessChecker.is_fresh()` before triggering fetch; returns 202 if fetch queued, 200 if skipped
- [ ] T048 [US5] Register `data_tools.py` router in the main FastAPI app entry point
- [ ] T049 [P] [US5] Write `tests/test_data_tools_gateway.py` — cover: (1) registry lists all 54+ tools, (2) backfill skips when data is fresh, (3) backfill triggers fetch when data is stale, (4) `POST /backfill` with unknown source_name returns 404, (5) concurrent backfill returns 409

---

## Phase 8: User Story 6 — SEC EDGAR Intelligence (Priority: P6)

**Goal**: EDGAR 10-K/20-F filings for configured pharmaceutical companies stored with full text (inline TEXT, PostgreSQL TOAST); silver model flags drug-revenue disclosures via keyword detection.

**Independent Test**: Run `python -m dk_data.ingestion.main --source sec_edgar`; verify most recent 10-K for at least one company (e.g., Pfizer CIK `0000078003`) appears in raw table with full document text; run SQLMesh for EDGAR silver model; confirm `has_drug_revenue_disclosure` flag is set where filing contains "revenue" + drug name keywords.

- [ ] T050 [US6] Verify and extend `ingestion/fetchers/sec_edgar.py` — confirm it fetches 10-K and 20-F for configured CIK list, stores 3 fiscal years, returns `{status, records: List[Dict], hash: None}`; update loader `ingestion/sources/sec_edgar.py` to: store full filing text in inline `TEXT` column (PostgreSQL TOAST handles compression — no chunking), call `log_to_meta('sec_edgar', result)`, deduplicate by `(cik, accession_number)`
- [ ] T051 [US6] Register `sec_edgar` in `SOURCES` dict in `ingestion/main.py` — `fetcher: SECEdgarFetcher`, `loader: load_sec_edgar_data`, `requires_file: False`, `default_days_back: 365`; add to `meta.data_sources` via migration 085 if not already present
- [ ] T052 [P] [US6] Verify `sqlmesh/models/molecules/bronze/sec_edgar.sql` declares correct `MODEL(name mol_bronze.sec_edgar)` namespace and grain `(cik, accession_number)` — update if namespace or grain is incorrect
- [ ] T053 [US6] Add silver-layer EDGAR transformation — write or extend a silver model for EDGAR keyword detection: flag `has_drug_revenue_disclosure = TRUE` when `LOWER(document_text) LIKE ANY(ARRAY['%revenue from%', '%product revenue%', '%net sales%'])` AND filing contains at least one canonical drug name from `mol_silver.molecules.canonical_name`; store normalized fields per FR-018/FR-019

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Grafana alerting, full regression run, and final verification of all success criteria.

- [ ] T054 Write `monitoring/provisioning/alerts/pipeline-source-failures.yaml` — Grafana alert group: one rule per `source_id` firing when `COUNT(*) FILTER (WHERE status = 'failed')` in the 3 most-recent `meta.refresh_log` rows for that source equals 3; alert labels include `source_name`; routed to existing notification policy per FR-034 and SC-013
- [ ] T055 [P] Run full test suite and verify all SC-001 through SC-013 acceptance criteria are met: `pytest tests/ -v --cov=src/dk_data`; confirm SC-002 (hash-skip zero-insert), SC-007 (incremental window used after first run), SC-009 (no direct LLM API calls in agents), SC-012 (trial_outcomes queryable without xenon reference)
- [ ] T056 [P] Verify all 34 new sources appear in the Data Tools Gateway registry (`GET /api/v1/data-tools/registry`) with correct `last_refresh` metadata after integration run; confirm `test_postgrest_schema_access.py` covers `hcs_bronze`, `hcs_silver`, `hcs_gold` and excludes `mol_raw`, `hcs_raw`
- [ ] T057 [P] Write `src/dk_data/sql/migrations/085_rollback.sql` — DROP-reverses every object created by migration 085 in reverse dependency order: DROP the 6 agent silver tables (`hcs_silver.service_lines`, etc.), DROP `mol_silver.publication_evidence_staging`, DROP `mol_silver.publication_evidence`, DROP `mol_silver.europepmc`, DROP `mol_silver.physician_payments`, DROP `mol_silver.research_grants`, DROP `mol_silver.agent_quarantine`, DROP all 28 `hcs_raw` tables, DELETE `meta.data_sources` rows for all 34 new sources, DROP `hcs_bronze/hcs_silver/hcs_gold` schemas (CASCADE); include a header comment warning that rollback is destructive and irreversible
- [ ] T058 [P] Write `sqlmesh/models/molecules/silver/europepmc.sql` — kind `INCREMENTAL_BY_TIME_RANGE` on `publication_date`; grain `pmid`; reads from `mol_bronze.europepmc`; outputs typed normalized fields: `molecule_id` (FK via `mol_silver.molecules` name match), `pmid`, `title`, `abstract_text`, `journal_title`, `publication_date`, `author_list` JSONB, `doi`, `link_strategy`, `_loaded_at`; this table is the source for T037 (publication evidence extractor reads abstracts from here); column names and types must match `data-model.md` `mol_silver.europepmc` definition exactly
- [ ] T059 Write K8s CronJob manifests for all 7 agents in `k8s/apps/cronjobs/base/` — `cronjob-agent-service-line-inference.yaml`, `cronjob-agent-idn-hierarchy.yaml`, `cronjob-agent-referral-network.yaml`, `cronjob-agent-contact-verification.yaml`, `cronjob-agent-staffing-decomposition.yaml`, `cronjob-agent-equipment-inventory.yaml`, `cronjob-agent-publication-evidence.yaml`; monthly schedule (first Monday of month); command: `python -m dk_data.agents.{agent_module} --limit 10000`; same security context template as CMS CronJobs (runAsNonRoot, seccompProfile.RuntimeDefault, concurrencyPolicy: Forbid)

---

## Dependency Graph

```
Phase 1 (Migration 085)
  └── Phase 2 (Foundational)
        ├── Phase 3 (US1 — CMS PUF) ──────────────────────────────┐
        │     └── T007–T017                                        │
        ├── Phase 4 (US2 — Regulatory/Clinical) ─────────────────┤
        │     └── T018–T028                                        │
        ├── Phase 5 (US3 — Refresh History) — validates 3 + 4     │
        │     └── T029–T030                                        │
        ├── Phase 6 (US4 — Agents) — depends on US2 for abstracts │
        │     ├── T031–T036 [P with each other]                    │
        │     ├── T037 (publication evidence extractor)            │
        │     ├── T038–T039 (SQLMesh + trial_outcomes update)      │
        │     └── T040–T043                                        │
        ├── Phase 7 (US5 — Data Tools) — depends on US1 complete  │
        │     └── T044–T049                                        │
        ├── Phase 8 (US6 — EDGAR) — independent                   │
        │     └── T050–T053                                        │
        └── Phase 9 (Polish) — depends on all phases complete ────┘
            ├── T057 (085_rollback.sql) — parallel, no code dependencies
            ├── T058 (mol_silver.europepmc SQLMesh) — depends on T022 (mol_bronze.europepmc) in Phase 4
            └── T059 (agent CronJob manifests) — depends on Phase 6 agents complete
```

US3 (Refresh History) is a verification phase, not a blocker — it runs once US1 and US2 are done.
US4 (Agents) depends on US2 being complete (needs abstracts in `mol_silver.europepmc` via T058).
US5 (Data Tools) depends on US1 being complete (registry needs CMS sources registered in `meta.data_sources`).
US6 (EDGAR) is independent of all other user stories.
T057 (rollback SQL) can be written in parallel with any phase.
T058 (mol_silver.europepmc) must follow T022 (mol_bronze.europepmc) — move to Phase 4 execution order after T022.
T059 (agent CronJobs) must follow all 7 agents in Phase 6.

---

## Parallel Execution Opportunities

Within Phase 3 (US1):
- T008 (remaining 21 CMS loaders) and T009 (7 core fetchers) and T010 (21 fetchers) can run in parallel once T007 is done
- T012 (HCS bronze SQLMesh) and T015 (CronJob manifests) can run in parallel once T011 (SOURCES) is done

Within Phase 4 (US2):
- T019 (NIH Reporter fetcher), T020 (EMA verify), T021 (Cochrane/DrugBank/PubChem verify), T023 (NIH bronze SQLMesh), T025 (drug_spending silver), T027 (CronJobs), T028 (tests) all independently parallelizable

Within Phase 6 (US4):
- T032, T033, T034, T035, T036 (the 5 CMS domain agents) can all run in parallel after T031 demonstrates the agent base pattern; T037 (publication evidence extractor) should come last as it depends on T058 (mol_silver.europepmc)
- T059 (agent CronJob manifests) can run in parallel with T040–T043 once all 7 agent modules are written

---

## Implementation Strategy

All phases are in scope for this PR. Implement in phase order:

1. Phase 1: Migration 085 (unblocks everything)
2. Phase 2: Foundational infrastructure (BaseFetcher retry, HCS dirs, agent base)
3. Phase 3: CMS PUF — 28 sources end-to-end (raw → hcs_gold, PostgREST exposed)
4. Phase 4: Regulatory/clinical sources + market_summary
5. Phase 5: Refresh history audit (verification pass over Phase 3 + 4 work)
6. Phase 6: Agent system + xenon removal from trial_outcomes
7. Phase 7: Data Tools Gateway
8. Phase 8: SEC EDGAR
9. Phase 9: Grafana alert + full regression

**Total tasks**: 59
**Parallelizable tasks**: 29 (marked [P])
