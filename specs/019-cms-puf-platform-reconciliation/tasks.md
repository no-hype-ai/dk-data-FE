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
- [ ] T002 Write `src/dk_data/sql/migrations/085_cms_puf_platform_reconciliation.sql` — delta-only: new `hcs_raw` tables (7 core + 21 additional), `mol_silver.publication_evidence`, `mol_silver.publication_evidence_staging` (same schema as live table; `content_hash` is merge key), `mol_silver.physician_payments`, `mol_silver.research_grants`, `mol_silver.agent_quarantine`, skeleton DDL for 6 CMS agent silver tables (`hcs_silver.service_lines`, `hcs_silver.idn_hierarchy`, `hcs_silver.referral_network`, `hcs_silver.verified_contacts`, `hcs_silver.staffing_decomposition`, `hcs_silver.equipment_inventory`), `hcs_bronze/hcs_silver/hcs_gold` schema creation, and `INSERT INTO meta.data_sources` rows for all 28 new CMS sources + 6 new API sources — all new source INSERTs use `ON CONFLICT (source_name) DO NOTHING` for idempotency; migration 083 already has rows for EMA, Cochrane, DrugBank, PubChem, PubMed — only INSERT the 30 truly new rows (28 CMS PUF + europepmc + nih_reporter); do NOT add `default_days_back` column to `meta.data_sources` — it does not exist in the schema and is managed in the Python SOURCES dict; **CRITICAL name alignment**: the `source_name` value in each `INSERT INTO meta.data_sources` MUST be byte-for-byte identical to the key used in the `SOURCES` dict in `ingestion/main.py` — `_meta_name()` falls back to the SOURCES dict key when no `meta_name` override exists; a mismatch causes `log_to_meta()` to silently skip the log write with "Source not found" warning
- [ ] T003 Apply migration 085 to staging database and run `pytest tests/test_migration_runner.py tests/test_imports.py tests/test_api.py -v` — confirm zero regressions
- [ ] T060 Add `hcs_raw`, `hcs_bronze`, `hcs_silver`, `hcs_gold` to `physical_schema_mapping` in `src/dk_data/sqlmesh/config.yaml` — 4 lines, one per schema, each mapping to itself (e.g., `hcs_raw: hcs_raw`); this must be done before writing any HCS SQLMesh model file or `sqlmesh run` will fail to resolve HCS schema targets

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infrastructure shared by all user stories — BaseFetcher retry config, HCS model directory, agent base class.

**⚠️ CRITICAL**: Complete before any user story work begins.

- [ ] T004 Extend `ingestion/main.py` `run_ingestion()` to read `max_retries` and `retry_base_delay_seconds` from SOURCES entry and reconfigure `BaseFetcher.session` Retry adapter before calling `fetcher.fetch()` — default: `max_retries=3`, `retry_base_delay_seconds=2` (~15 lines)
- [ ] T005 [P] Create `sqlmesh/models/hcs/bronze/`, `sqlmesh/models/hcs/silver/`, `sqlmesh/models/hcs/gold/` directories with `.gitkeep` placeholders — parallel safe (filesystem only)
- [ ] T006 [P] Write `agents/base_agent.py` — abstract base class. Implementation requirements: (1) `__init__(self, model="pharma-llm")` — reads `LITELLM_PROXY_URL` and `LITELLM_API_KEY` from env (Doppler `dk-data-fe` project); creates `openai.OpenAI(base_url=LITELLM_PROXY_URL, api_key=LITELLM_API_KEY)` client — NOT `anthropic.Anthropic()`; (2) `_call_llm(prompt, record_id) -> str` — calls LiteLLM via openai SDK; uses `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30), retry=retry_if_exception_type(RateLimitError))` for 429 handling; (3) `_call_llm_with_escalation(prompt, record_id) -> tuple[str, float]` — calls `pharma-llm` first; if returned confidence_score < 0.6, re-calls with `claude-sonnet-4-20250514` (one escalation maximum per record); (4) `_process_batch(records: list) -> list[AgentResult]` — uses `asyncio.gather(*tasks, return_exceptions=True)`; failed records go to quarantine, NOT exception propagation (one failed record must not abort the batch); (5) max 5 concurrent LLM calls per agent run (semaphore-guarded); (6) `run(scope, limit=50) -> AgentResult` — `limit` caps records processed per run (default 50 per ARCHITECTURE-BEST-PRACTICES.md MAX_EVIDENCE cap); (7) `_write_quarantine(record)` for confidence < 0.5; `_flag_needs_review(record)` for 0.5–0.79; (8) use `structlog.get_logger()` — NOT `from loguru import logger`; (9) **DB writes for silver tables must use asyncpg** — agents are async (`asyncio.gather`) and CANNOT reuse the synchronous psycopg2 utilities in `ingestion/utils/database.py` (e.g., `get_cursor()`, `upsert_records()`); `base_agent.py` must establish its own asyncpg connection pool (`asyncpg.create_pool(dsn=os.environ["DATABASE_URL"])`) in `__init__` and expose `_db_pool` for subclass use in silver writes

**Checkpoint**: Retry config live in `main.py`; HCS model dirs exist; `base_agent.py` importable with `from dk_data.agents.base_agent import BaseAgent`

---

## Phase 3: User Story 1 — CMS PUF Data for Drug Market Analysis (Priority: P1)

**Goal**: 28 CMS PUF file-based sources ingested to `hcs_raw`, normalized through `hcs_bronze`/`hcs_silver`/`hcs_gold`, queryable via PostgREST.

**Independent Test**: Run `python -m dk_data.ingestion.main --source cms_part_d_spending --file /tmp/PartD_2023.csv`; verify row in `hcs_raw.cms_part_d_spending`; re-run with same file and confirm zero new inserts (hash-skip); query `meta.refresh_log` and confirm entry exists.

- [ ] T007 [US1] Implement 7 core CMS PUF loader modules in `ingestion/sources/`: `cms_part_d_spending.py`, `cms_part_b_spending.py`, `cms_open_payments.py`, `cms_nppes.py`, `cms_inpatient_puf.py`, `cms_physician_puf.py`, `cms_hospital_general_info.py` — **First**: add Pydantic validator classes to `ingestion/utils/validators.py` for each source (e.g., `CMSPartDSpendingRecord` with typed fields matching the raw table schema — follow the existing `CMSMedicareInpatientRecord` / `CMSHospitalInfoRecord` / `CMSCostReportRecord` patterns already present in that file; do NOT duplicate these 3 classes); each loader: (1) computes MD5 of file, (2) checks `hcs_raw.{table} WHERE _source_hash = %s`, (3) skips and returns `{"status": "skipped", "records_inserted": 0, "records_updated": 0}` if > 0 rows, (4) uses `upsert_records(schema="hcs_raw", table=..., records=..., conflict_columns=["_source_hash"], update_columns=[...])` from `ingestion/utils/database.py` instead of manual INSERT; (5) returns result dict `{"status": "success"/"error", "records_fetched": int, "records_inserted": int, "records_updated": int, "errors": List[str]}` — **DO NOT call `log_to_meta()` from the loader**; `run_ingestion()` in `main.py` calls `log_to_meta()` after the loader returns; calling it from inside the loader causes duplicate log entries — follow `ingestion/sources/cms_inpatient.py` as the reference pattern
- [ ] T008 [P] [US1] Implement remaining 21 CMS PUF loader modules in `ingestion/sources/` (cms_medicare_advantage, cms_medicaid_drug_spending, cms_dme_puf, cms_home_health, cms_hospice_puf, cms_snf_puf, cms_outpatient_puf, cms_referring_providers, cms_ordering_providers, cms_lab_services, cms_imaging_puf, cms_mental_health_puf, cms_opioid_puf, cms_telehealth_puf, cms_geographic_variation, cms_chronic_conditions, cms_dual_eligible, cms_enrollment_puf, cms_claim_type_puf, cms_utilization_puf, cms_cost_reports_puf) — **First**: add Pydantic validator classes to `ingestion/utils/validators.py` for all 21 sources following the same pattern as T007 (append only — do not duplicate any of the 3 CMS classes already present); same hash-skip + `upsert_records()` pattern as T007; loaders return result dict but do NOT call `log_to_meta()` — that is `run_ingestion()`'s responsibility
- [ ] T009 [P] [US1] Implement 7 core CMS PUF fetcher subclasses in `ingestion/fetchers/`: `cms_part_d_spending.py`, `cms_part_b_spending.py`, `cms_open_payments.py`, `cms_nppes.py`, `cms_inpatient_puf.py`, `cms_physician_puf.py`, `cms_hospital_general_info.py` — extend `BaseFetcher`; `__init__(self, data_dir=None)`; `fetch()` returns `{status, records: [], hash: str}` where hash is MD5 of downloaded file; `get_latest_url()` returns the CMS data.gov URL for each dataset
- [ ] T010 [P] [US1] Implement remaining 21 CMS PUF fetcher subclasses in `ingestion/fetchers/` (matching the 21 loaders from T008) — same `BaseFetcher` pattern; `requires_file: True` in SOURCES entry
- [ ] T011 [US1] Register all 28 new CMS PUF sources in the `SOURCES` dict in `ingestion/main.py` — each entry MUST have: `name` (display name string), `description` (short string), `loader` (callable), `requires_file: True`, `default_days_back: None`; no `fetcher` key for file-based sources; **also add `accepts_file: True`** — `run_ingestion()` checks `accepts_file` separately from `requires_file` to gate the file-path argument; do NOT include `requires_fiscal_year` (that key is only for `cms_inpatient` which embeds fiscal year in a separate file dimension — new CMS PUF annual sources encode year in `_source_year` column); **CRITICAL**: the top-level dict key (e.g., `"cms_part_d_spending"`) is used by `_meta_name()` as the fallback `source_name` — this key MUST be byte-for-byte identical to the `source_name` value inserted into `meta.data_sources` in migration 085; if they differ, `log_to_meta()` silently fails with "Source not found" and no refresh log entry is written; only add a `meta_name` key if the SOURCES dict key differs from the DB source_name (prefer matching them exactly to avoid the override)
- [ ] T012 [US1] Write 7 SQLMesh bronze models in `sqlmesh/models/hcs/bronze/`: `cms_part_d_spending.sql`, `cms_part_b_spending.sql`, `cms_open_payments.sql`, `cms_nppes.sql`, `cms_inpatient_puf.sql`, `cms_physician_puf.sql`, `cms_hospital_general_info.sql` — kind `INCREMENTAL_BY_TIME_RANGE` on `_source_year`; each model's FROM clause MUST read from `hcs_raw.{table_name}` (e.g., `FROM hcs_raw.cms_part_d_spending`) — **NOT** `FROM raw.{table_name}`; the `raw` schema is the legacy mol-CI schema; HCS raw tables live in `hcs_raw`; columns are typed pass-through from `hcs_raw` table matching spec data-model; column names exactly as per `data-model.md` Bronze section
- [ ] T013 [US1] Write `sqlmesh/models/hcs/silver/cms_drug_market.sql` — kind `FULL`; grain `ndc`; FROM clause reads from `hcs_bronze.cms_part_d_spending` and `hcs_bronze.cms_part_b_spending` — **NOT** `raw.*` or `bronze.*`; joins on `generic_name`/`ndc`; computes `part_d_spending`, `part_b_spending`, `total_spending`, `total_beneficiaries`, `usp_category` (join to USP classification reference), `rbcs_category` per `data-model.md`
- [ ] T014 [US1] Write `sqlmesh/models/hcs/gold/cms_drug_market_profile.sql` — kind `FULL`; grain `ndc`; FROM clause reads from `hcs_silver.cms_drug_market` — **NOT** `raw.*` or `silver.*` without schema prefix; extends silver with `market_share_pct` (spending / SUM OVER generic_name group), `spending_rank_in_category` using `RANK() OVER (PARTITION BY usp_category ORDER BY total_spending DESC NULLS LAST)` per `data-model.md` Gold section
- [ ] T015 [US1] Write 28 K8s CronJob manifests in `k8s/apps/cronjobs/base/` — one per CMS source; open an existing manifest (e.g., `cronjob-fetch-ema-reg.yaml`) and copy its exact structure including: `restartPolicy` value, `backoffLimit`, `securityContext` block, `imagePullPolicy`, `concurrencyPolicy: Forbid`; schedule monthly (first Sunday of month, staggered by 15 min per source to avoid thundering herd); **image tag MUST be `<branch>-<short-sha>` format — `:latest` is FORBIDDEN per CANON**; also audit existing CronJob manifests to confirm they call `python -m dk_data.ingestion.main` (not `fetch_data`) as the entrypoint — all new manifests MUST use `ingestion.main`
- [ ] T016 [US1] Update PostgREST exposure: add ONLY `hcs_silver` and `hcs_gold` to `PGRST_DB_SCHEMAS` in `k8s/apps/postgrest/base/configmap.yaml` — `hcs_bronze` is NOT added (follows existing pattern: `mol_bronze` is not in the current exposure list, only `mol_silver` and `mol_gold` are exposed); confirm `mol_raw` and `hcs_raw` are absent; if restructuring or adding any connection-related vars, place `PGRST_DB_URI` AFTER all `POSTGRES_*` vars per CANON ordering constraint; **T062 MUST be completed before T016 is deployed** (db-init must create hcs_silver/hcs_gold API views before PostgREST is restarted)
- [ ] T017 [US1] Write 28 individual fetcher/loader test files — one per CMS source (e.g., `tests/test_cms_part_d_fetcher.py`, `tests/test_cms_part_b_fetcher.py`, …, `tests/test_cms_cost_reports_fetcher.py`); each test file covers: (1) happy-path file ingestion with source-specific mock CSV (correct column names), (2) hash-skip on second identical run returns `records_inserted: 0`, (3) `log_to_meta` called once per run, (4) `meta.refresh_log` entry exists after run, (5) `BaseFetcher` session retry adapter present — 28 test files total, not a shared file, so failures isolate to the specific source

---

## Phase 4: User Story 2 — Regulatory & Clinical Evidence Sources (Priority: P2)

**Goal**: EuropePMC, NIH Reporter, EMA, Cochrane, DrugBank, and PubChem sources ingested to `mol_raw`/bronze; silver models entity-link to `mol_silver.molecules`; gold `market_summary` aggregates all six.

**Independent Test**: Run `python -m dk_data.ingestion.main --source europepmc`; verify rows in `mol_raw.europepmc_raw` with `processed_to_bronze = FALSE`; run SQLMesh for `mol_bronze.europepmc`; verify rows appear with `pmid` and `title` columns populated.

- [ ] T018 [US2] Implement `ingestion/fetchers/europepmc.py` — extend `BaseFetcher`; `fetch(**kwargs)` accepts `days_back=int`; calls EuropePMC REST API (`https://www.ebi.ac.uk/europepmc/webservices/rest/search`) paginating with `cursorMark`; returns `{status, records: List[Dict], hash: None}`; `get_latest_url()` returns base API URL; write `ingestion/sources/europepmc.py` loader: bulk-insert to `mol_raw.europepmc_raw` (NOT `raw.europepmc` — existing mol-CI sources follow MCP tool registry convention of `mol_raw` schema, not the legacy `raw` schema) deduped by `pmid`; loader returns result dict `{"status": ..., "records_fetched": int, "records_inserted": int, "records_updated": int, "errors": List[str]}` — **DO NOT call `log_to_meta()` from inside the loader**; `run_ingestion()` in `main.py` calls it after the loader returns
- [ ] T019 [P] [US2] Implement `ingestion/fetchers/nih_reporter.py` — extend `BaseFetcher`; calls NIH Reporter API (`https://api.reporter.nih.gov/v2/projects/search`) with `date_added` filter; returns `{status, records, hash: None}`; write `ingestion/sources/nih_reporter.py` loader: bulk-insert to `mol_raw.nih_reporter_raw` (NOT `raw.nih_reporter_raw` — existing mol-CI sources follow MCP tool registry convention of `mol_raw` schema, not the legacy `raw` schema) deduped by `project_number`; loader returns result dict — **DO NOT call `log_to_meta()` from inside the loader**; `run_ingestion()` handles it
- [ ] T020 [P] [US2] Verify existing `ingestion/fetchers/ema_regulatory.py` and `ingestion/sources/ema_regulatory.py` use the canonical `BaseFetcher` pattern — confirm the loader returns a correctly-shaped result dict (`{"status", "records_fetched", "records_inserted", "records_updated", "errors"}`) so `run_ingestion()` can pass it to `log_to_meta()`; verify `default_days_back` is set in the SOURCES entry; if `fetcher` key is missing from SOURCES, add `EMARegulatoryCIFetcher`; do NOT add a `log_to_meta()` call inside the loader — `run_ingestion()` owns that call
- [ ] T021 [P] [US2] Verify existing Cochrane, DrugBank, PubChem fetchers and loaders return correctly-shaped result dicts (`{"status", "records_fetched", "records_inserted", "records_updated", "errors"}`) and are registered in SOURCES with `default_days_back` — if a loader does NOT return this dict shape, `run_ingestion()` cannot call `log_to_meta()` correctly; patch any gaps; do NOT add `log_to_meta()` calls inside the loaders themselves; these sources already exist on main, so this is an alignment check not a rewrite
- [ ] T022 [US2] Write `sqlmesh/models/molecules/bronze/europepmc.sql` — kind `INCREMENTAL_BY_TIME_RANGE` on `publication_date`; grain `pmid`; extracts typed fields from `mol_raw.europepmc_raw.response_body` JSONB: `pmid`, `title`, `abstractText` → `abstract_text`, `journalInfo->>'journal'` → `journal_title`, `firstPublicationDate` → `publication_date`, `authorList->'author'` → `author_list` (kept as JSONB array), `doi`; sets `processed_to_bronze = TRUE` on raw record after extraction
- [ ] T023 [P] [US2] Write `sqlmesh/models/molecules/bronze/nih_reporter.sql` — kind `INCREMENTAL_BY_TIME_RANGE` on `start_date`; grain `project_number`; extracts from `mol_raw.nih_reporter_raw.response_body`: `project_num`, `project_title`, `fiscal_year`, `principal_investigators` → `pi_names` JSONB, `organization.org_name`, `award_amount`, `abstract_text`, `terms`, `project_start_date`, `project_end_date`
- [ ] T024 [US2] Write `sqlmesh/models/molecules/silver/ema_regulatory.sql` — kind `FULL`; grain `product_number`; joins `mol_bronze.ema_regulatory` to `mol_silver.molecules` using dual-strategy: first `LOWER(active_substance) = LOWER(m.canonical_name)`, fallback `LOWER(inn) = LOWER(m.canonical_name)`; outputs `molecule_id` (NULL if unlinked), `link_strategy` ('exact_name', 'inn_match', 'unlinked'), and all EMA fields per `data-model.md`
- [ ] T025 [P] [US2] Write `sqlmesh/models/molecules/silver/drug_spending.sql` — kind `FULL`; grain `(generic_name, program, year)`; UNIONs `hcs_bronze.cms_part_d_spending` (program='part_d') and `hcs_bronze.cms_part_b_spending` (program='part_b'); links to `mol_silver.molecules` on `LOWER(generic_name) = LOWER(m.canonical_name)` with brand_name fallback; computes `avg_spending_per_claim`
- [ ] T026 [US2] Write `sqlmesh/models/molecules/gold/market_summary.sql` — kind `FULL`; grain `molecule_id`; 10-way LEFT JOIN from `mol_silver.molecules` to: drug_spending (Part D + Part B aggregated), ema_regulatory (latest authorisation_status + date), cochrane review count, europepmc publication count, nih grant count + total funding, trial outcomes count, publication evidence count — all joins are LEFT so model degrades gracefully when any source is absent; per `data-model.md` Gold section
- [ ] T027 [P] [US2] Write CronJob manifests for EuropePMC (`k8s/apps/cronjobs/base/cronjob-fetch-europepmc.yaml`) and NIH Reporter (`k8s/apps/cronjobs/base/cronjob-fetch-nih-reporter.yaml`) — weekly schedule (Sunday UTC), same security template as existing CronJobs; **image MUST use exact base `ghcr.io/data-kinetic/dk-data-fe/job-trigger` with `<branch>-<short-sha>` tag** — `:latest` is FORBIDDEN per CANON
- [ ] T028 [P] [US2] Write `tests/test_europepmc_fetcher.py` and `tests/test_nih_reporter_fetcher.py` — cover: happy-path API response with mocked `responses` library, pagination cursor handling, empty result set, 429 retry behaviour

---

## Phase 5: User Story 3 — Full Refresh History (Priority: P3)

**Goal**: Every new source produces `meta.refresh_log` entries and updates `meta.data_sources.last_successful_refresh` after each run — zero silent sources.

**Independent Test**: After completing Phase 3 and Phase 4 integration tasks, run `SELECT source_name, last_successful_refresh, last_refresh_status FROM meta.data_sources ORDER BY source_name` — all 30 new sources (28 CMS PUF + europepmc + nih_reporter) must have non-NULL `last_successful_refresh` after their first successful run — EMA, Cochrane, DrugBank, PubChem already had rows in `meta.data_sources` from migration 083 and are not new.

- [ ] T029 [US3] Audit all 28 CMS loader files (T007 + T008) and all 2 new API loader files (T018–T019); also verify EMA, Cochrane, DrugBank, PubChem (T020–T021) which already exist on main: **loaders do NOT call `log_to_meta()` — `run_ingestion()` in `main.py` calls it after the loader returns**; verify each loader returns a correctly-shaped result dict: keys must be `status` (str), `records_fetched` (int), `records_inserted` (int), `records_updated` (int), `errors` (List[str]) — note `records_updated` not `records_failed`; `log_to_meta()` extracts these keys and silently uses 0-fallbacks for missing ones; fix any loader returning wrong keys or not returning a dict at all
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
- [ ] T037 [US4] Write `agents/publication_evidence_extractor.py` — extends `BaseAgent`; reads `silver.publications` abstracts (the canonical publication consolidation table — EuropePMC records are included here after T058 extends the model) not yet in `mol_silver.publication_evidence_staging` (check by pmid+endpoint_name hash); uses `_process_batch(records)` from `BaseAgent` to call LiteLLM in batches of 50 max (MAX_EVIDENCE_PER_PILLAR cap from ARCHITECTURE-BEST-PRACTICES.md); extracts: `endpoint_name`, `endpoint_type`, `hazard_ratio`, `p_value`, `response_rate`, `median_survival_months`, `sample_size`; uses `_call_llm_with_escalation()` for quality escalation (pharma-llm first, frontier on confidence < 0.6); computes `content_hash = md5(pmid + endpoint_name)`; writes to `mol_silver.publication_evidence_staging` (skips if content_hash already exists); quarantines confidence < 0.5; does NOT write to `mol_silver.publication_evidence` directly — the SQLMesh model handles promotion from staging; accepts `--limit` CLI arg (default 50) controlling max abstracts processed per run
- [ ] T038 [US4] Write `sqlmesh/models/molecules/silver/publication_evidence.sql` — kind `INCREMENTAL_BY_UNIQUE_KEY` with unique key `content_hash`; reads from `mol_silver.publication_evidence_staging`; merges new/updated staging rows into `mol_silver.publication_evidence` (INSERT new content_hash; UPDATE if confidence_score changed); ensures agent writes cannot be silently overwritten by a full SQLMesh re-run; this model owns the staging→live promotion and schema contract enforcement
- [ ] T039 [US4] Update `sqlmesh/models/molecules/gold/trial_outcomes.sql` — **FIRST**: read `src/dk_data/api/routes/data_platform.py` (the 133KB file that queries `mol_gold.trial_outcomes`) and identify any column aliases or result shapes that depend on the current grain `(molecule_id, trial_nct_id, evidence_source)`; adding `endpoint_name` to the grain produces more rows per trial — any API route that returns a single row per trial will now return multiple rows (one per endpoint); document this in a comment and align the route if needed; THEN update `trial_outcomes.sql`: replace `FROM xenon.publication_evidence pe` CTE with `FROM mol_silver.publication_evidence pe WHERE pe.confidence_score >= 0.40 AND pe.needs_review = FALSE`; extend grain from `(molecule_id, trial_nct_id, evidence_source)` to `(molecule_id, trial_nct_id, endpoint_name, evidence_source)` per spec FR-033
- [ ] T040 [US4] Write `api/routes/agents.py` — FastAPI router at `/api/v1/agents`; implement all 4 endpoints per `contracts/api.md`: `GET /agents`, `POST /agents/{agent_id}/run`, `GET /agents/{agent_id}/runs`, `GET /agents/quarantine`; **async execution**: `POST /agents/{agent_id}/run` MUST return `202 Accepted` immediately and spawn the agent as a K8s Job (preferred — create Job from CronJob template via kubernetes client) OR use FastAPI `BackgroundTasks` with a timeout guard; return `{"run_id": str, "status": "queued"}` in the 202 body; client polls `GET /agents/{agent_id}/runs` for completion using the `run_id`; reads run history from `meta.refresh_log`; do NOT block the HTTP worker thread for the duration of an agent run (agents can take minutes)
- [ ] T041 [US4] Register `agents.py` router in the main FastAPI app at `src/dk_data/ingestion/batch/api.py` — this is the actual app entry point (`app = FastAPI(title="DK Data Platform API", version="2.0.0")`); add `app.include_router(agents_router, prefix="/api/v1")` following the pattern of existing router registrations in that file; **do NOT create or edit `src/dk_data/api/main.py`** — that path does not exist in the codebase
- [ ] T042 [P] [US4] Write `tests/test_publication_evidence_agent.py` — cover: (1) endpoint extraction writes to `mol_silver.publication_evidence_staging` (not the live table directly), (2) duplicate content_hash in staging is skipped (no duplicate insert), (3) confidence < 0.5 goes to quarantine not staging, (4) confidence 0.5–0.79 sets `needs_review = TRUE` in staging, (5) all LLM calls go through mocked LiteLLM URL (no direct provider calls), (6) SQLMesh model correctly promotes from staging to live on merge
- [ ] T043 [P] [US4] Write `tests/test_agents_router.py` — cover: `GET /agents` returns all 7 agents, `POST /agents/publication_evidence_extractor/run` returns 202, `GET /agents/quarantine` returns paginated results

---

## Phase 7: User Story 5 — Data Tools Gateway (Priority: P5)

**Goal**: `/api/v1/data-tools` registry and backfill endpoints operational; freshness check prevents redundant external fetches.

**Independent Test**: `GET /api/v1/data-tools/registry` returns 54+ tools with `last_refresh` metadata; `POST /api/v1/data-tools/backfill {source_name: "cms_part_d_spending", force: false}` returns `skipped: true` if recently ingested, or `202` and triggers ingestion if stale.

- [ ] T044 [US5] Extend `services/mcp/tool_registry.py` — add 28 new `ToolDefinition` entries for all CMS PUF sources (e.g., `"cms-part-d-spending": ToolDefinition(name="cms-part-d-spending", tier="supplementary", raw_table="cms_part_d_spending", raw_schema="hcs_raw", adapter_module="dk_data.services.mcp.adapters.cms_part_d_spending", ...)`) following the existing `ToolDefinition` dataclass pattern; **new CMS PUF tools use `raw_schema="hcs_raw"`** — existing CMS tools in the registry (e.g., `cms-cost-reports`, `cms-hospital-info`, `cms-inpatient`) use the legacy `raw_schema="raw"`; do NOT change the existing tools' `raw_schema`; do NOT create a new `services/data_tools/registry.py` — that would duplicate the existing TOOL_REGISTRY
- [ ] T045 [US5] Extend `services/data_platform/data_freshness_monitor.py` — add `async def is_fresh(self, source_name: str, max_age_hours: int) -> bool` method; **MUST be async** — `DataFreshnessMonitor` uses an asyncpg connection pool (`async with self.db_pool.acquire()`) and cannot use psycopg2 `get_cursor()`; reads `last_successful_refresh` from `meta.data_sources` (NOT from `raw.ingestion_jobs` or `raw.api_responses` — those are separate legacy tracking tables for the MCP tool registry system); returns `False` if NULL or older than `max_age_hours`; default thresholds: CMS bulk = 720h, API = 24h; **scope limitation**: `is_fresh()` covers only sources tracked in `meta.data_sources` (new CMS PUF + API sources added by this feature, plus existing EMA/Cochrane/DrugBank/PubChem/PubMed); legacy MCP-managed sources (tracked in `raw.ingestion_jobs`) are NOT covered and MUST NOT be queried through this method; do NOT create `services/data_tools/data_registry.py` — that would duplicate the existing `DataFreshnessMonitor` class
- [ ] T046 [P] [US5] Add 28 new CMS PUF adapter files to `services/mcp/adapters/` — one per CMS source (e.g., `cms_part_d_spending.py`); each adapter extends the existing `base.py` adapter pattern in that directory; 28 CMS bulk adapters (one per source) + 6 API source adapters (europepmc, nih_reporter, ema_regulatory, cochrane, drugbank, pubchem) + ~20 CMS sub-query adapters (one per meaningful query facet such as cms_part_d_by_drug, cms_open_payments_by_physician, etc.); each adapter wraps the source's `loader` callable and provides metadata: `category` (cms_bulk / mol_api / cms_subquery), `supported_query_keys` list, `description`; sub-query adapters are thin wrappers over the base CMS loader with a pre-applied filter; follow the pattern from existing `services/mcp/adapters/` (30 adapters already present including `cms_cost_reports.py`, `cms_hospital_info.py`, `cms_inpatient.py`)
- [ ] T047 [US5] Write `api/routes/data_tools.py` — FastAPI router at `/api/v1/data-tools`; implement 3 endpoints per `contracts/api.md`: `GET /registry`, `POST /backfill`, `GET /{source_name}/status`; backfill calls `data_freshness_monitor.is_fresh()` before triggering fetch; returns 202 if fetch queued, 200 if skipped; the router imports `TOOL_REGISTRY` from `services/mcp/tool_registry.py` for the registry endpoint and `DataFreshnessMonitor.is_fresh()` from `services/data_platform/data_freshness_monitor.py` for freshness checks; **scope**: `DataFreshnessMonitor.is_fresh()` only covers sources in `meta.data_sources` (new CMS PUF and API sources tracked by this feature); legacy MCP-managed sources tracked in `raw.ingestion_jobs` are NOT available via this freshness check — the backfill endpoint should return 404 or a descriptive error if a requested source_name is not found in `meta.data_sources`; **caching**: `GET /registry` response MUST be cached in Redis (TTL=60s) — use the existing Redis client from `api/dependencies.py`; `GET /{source_name}/status` result MUST be cached per source_name (TTL = min refresh frequency for that source, e.g. 3600s for CMS bulk, 300s for API sources) to prevent unbounded DB queries under load
- [ ] T048 [US5] Register `data_tools.py` router in the main FastAPI app at `src/dk_data/ingestion/batch/api.py` — add `app.include_router(data_tools_router, prefix="/api/v1")` following the existing router registration pattern; **do NOT create or edit `src/dk_data/api/main.py`** — that path does not exist
- [ ] T049 [P] [US5] Write `tests/test_data_tools_gateway.py` — cover: (1) registry lists all 54+ tools, (2) backfill skips when data is fresh, (3) backfill triggers fetch when data is stale, (4) `POST /backfill` with unknown source_name returns 404, (5) concurrent backfill returns 409

---

## Phase 8: User Story 6 — SEC EDGAR Intelligence (Priority: P6)

**Goal**: EDGAR 10-K/20-F filings for configured pharmaceutical companies stored with full text (inline TEXT, PostgreSQL TOAST); silver model flags drug-revenue disclosures via keyword detection.

**Independent Test**: Run `python -m dk_data.ingestion.main --source sec_edgar`; verify most recent 10-K for at least one company (e.g., Pfizer CIK `0000078003`) appears in raw table with full document text; run SQLMesh for EDGAR silver model; confirm `has_drug_revenue_disclosure` flag is set where filing contains "revenue" + drug name keywords.

- [ ] T050 [US6] Verify and extend `ingestion/fetchers/sec_edgar.py` — confirm it fetches 10-K and 20-F for configured CIK list, stores 3 fiscal years, returns `{status, records: List[Dict], hash: None}`; update loader `ingestion/sources/sec_edgar.py` to: store full filing text in inline `TEXT` column (PostgreSQL TOAST handles compression — no chunking), call `log_to_meta('sec_edgar', result)`, deduplicate by `(cik, accession_number)`
- [ ] T051 [US6] Register `sec_edgar` in `SOURCES` dict in `ingestion/main.py` — `fetcher: SECEdgarFetcher`, `loader: load_sec_edgar_data`, `requires_file: False`, `default_days_back: 90 (existing value — current value is already set to 90 in SOURCES; only update to 365 if a full 3-year filing history backfill is explicitly required and the existing value has been confirmed insufficient)`; add to `meta.data_sources` via migration 085 if not already present
- [ ] T052 [P] [US6] Verify `sqlmesh/models/molecules/bronze/sec_edgar.sql` declares correct `MODEL(name mol_bronze.sec_edgar)` namespace and grain `(cik, accession_number)` — update if namespace or grain is incorrect
- [ ] T053 [US6] Add silver-layer EDGAR transformation — write or extend a silver model for EDGAR keyword detection: flag `has_drug_revenue_disclosure = TRUE` when `LOWER(document_text) LIKE ANY(ARRAY['%revenue from%', '%product revenue%', '%net sales%'])` AND filing contains at least one canonical drug name from `mol_silver.molecules.canonical_name`; store normalized fields per FR-018/FR-019

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Grafana alerting, full regression run, and final verification of all success criteria.

- [ ] T054 Write `monitoring/provisioning/alerts/pipeline-source-failures.yaml` — Grafana alert group: one rule per `source_id` firing when `COUNT(*) FILTER (WHERE status = 'failed')` in the 3 most-recent `meta.refresh_log` rows for that source equals 3; alert labels include `source_name`; routed to existing notification policy per FR-034 and SC-013
- [ ] T055 [P] Run full test suite and verify all SC-001 through SC-013 acceptance criteria are met: `pytest tests/ -v --cov=src/dk_data`; confirm SC-002 (hash-skip zero-insert), SC-007 (incremental window used after first run), SC-009 (no direct LLM API calls in agents), SC-012 (trial_outcomes queryable without xenon reference)
- [ ] T056 [P] Verify all 30 new sources appear in the Data Tools Gateway registry (`GET /api/v1/data-tools/registry`) with correct `last_refresh` metadata after integration run; confirm `test_postgrest_schema_access.py` covers `hcs_silver` and `hcs_gold` (exposed) and excludes `hcs_bronze`, `mol_raw`, `hcs_raw` (not exposed)
- [ ] T057 [P] Write `src/dk_data/sql/migrations/085_rollback.sql` — DROP-reverses every object created by migration 085 in reverse dependency order: DROP the 6 agent silver tables (`hcs_silver.service_lines`, etc.), DROP `mol_silver.publication_evidence_staging`, DROP `mol_silver.publication_evidence`, DROP `mol_silver.physician_payments`, DROP `mol_silver.research_grants`, DROP `mol_silver.agent_quarantine`, DROP all 28 `hcs_raw` tables, DELETE `meta.data_sources` rows for all 30 new sources (28 CMS PUF + europepmc + nih_reporter), DROP `hcs_bronze/hcs_silver/hcs_gold` schemas (CASCADE); revert `silver.publications` EuropePMC CTE extension (T058); include a header comment warning that rollback is destructive and irreversible
- [ ] T058 [P] Extend `src/dk_data/sqlmesh/models/molecules/silver/publications.sql` — add EuropePMC as a fifth CTE (`europepmc_pubs`) reading from `mol_bronze.europepmc`; map fields: `'europepmc:' || pmid AS openalex_id`, `doi`, `pmid`, title, `abstract AS abstract` (from `abstractText` field), `pub_year::INTEGER AS publication_year`, `publication_date`, `journal_name` (from `journalInfo`), `authors_jsonb AS authorships`, `source = 'europepmc'`; add to the final `UNION ALL` in combined_pubs; add `'europepmc' THEN 5` to the source precedence ORDER BY; do NOT create a new standalone `mol_silver.europepmc` model — this table does not exist in this feature
- [ ] T059 Write K8s CronJob manifests for all 7 agents in `k8s/apps/cronjobs/base/` — `cronjob-agent-service-line-inference.yaml`, `cronjob-agent-idn-hierarchy.yaml`, `cronjob-agent-referral-network.yaml`, `cronjob-agent-contact-verification.yaml`, `cronjob-agent-staffing-decomposition.yaml`, `cronjob-agent-equipment-inventory.yaml`, `cronjob-agent-publication-evidence.yaml`; monthly schedule (first Monday of month); command: `python -m dk_data.agents.{agent_module} --limit 50` (default 50 per MAX_EVIDENCE cap — adjust per agent if batch size differs); same security context template as CMS CronJobs (runAsNonRoot, seccompProfile.RuntimeDefault, concurrencyPolicy: Forbid); **image MUST use exact base `ghcr.io/data-kinetic/dk-data-fe/job-trigger` with `<branch>-<short-sha>` tag — `:latest` is FORBIDDEN per CANON**; do NOT hardcode namespace in manifest metadata — namespace is injected at deploy time via Kustomize (canonical namespaces: `dk-data-staging`, `dk-data-prod`)
- [ ] T061 Update `scripts/validate-staging-ingestion.sh` — line 82 currently has `if [ "$count" = "22" ]` (exact match); the current SOURCES dict has 17 entries, not 22; this check was stale before this feature; post-feature SOURCES will have 47 entries (17 current + 30 new: 28 CMS PUF + europepmc + nih_reporter); change the check to `if [ "$count" -ge 47 ]` (numeric comparison, not string match); update CronJob count floor from `>= 17` to `>= 47` (17 existing + 30 new); add the 30 new source names (`cms_part_d_spending`, `cms_part_b_spending`, `cms_open_payments`, `cms_nppes`, `cms_inpatient_puf`, `cms_physician_puf`, `cms_hospital_general_info`, and the remaining 21 CMS PUF sources, plus `europepmc`, `nih_reporter`) to the known-sources validation list (lines 120–127 of the current script); without this fix the validation script fails immediately post-deploy even when everything is correct
- [ ] T062 Update db-init SQL — add `CREATE VIEW` statements (or equivalent grants) for `hcs_silver` and `hcs_gold` schemas so that PostgREST's `web_anon` role has SELECT access; follow the existing db-init pattern for `mol_silver` and `mol_gold`; CANON requires db-init to create API views (≥7) and set permissions for every exposed schema; **this task MUST complete before T016 is deployed** (PostgREST restart on T016 requires views to exist)
- [ ] T063 [P] Run Ruff lint and mypy type check on all new Python files introduced by this feature — `ruff check src/dk_data/agents/ src/dk_data/ingestion/fetchers/cms_*.py src/dk_data/ingestion/sources/cms_*.py src/dk_data/api/routes/data_tools.py src/dk_data/api/routes/agents.py src/dk_data/services/mcp/adapters/cms_*.py`; then `mypy src/dk_data/agents/ src/dk_data/api/routes/`; zero errors required before PR merge; this enforces CANON Python stack (Ruff, mypy) and confirms no `import anthropic` leaked into new files

---

## Dependency Graph

```
Phase 1 (Migration 085)
  └── Phase 2 (Foundational)
        ├── T060 (sqlmesh/config.yaml hcs_* schemas) — must complete before any HCS SQLMesh model
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
            ├── T058 (silver.publications EuropePMC CTE) — depends on T022 (mol_bronze.europepmc) in Phase 4
            ├── T059 (agent CronJob manifests) — depends on Phase 6 agents complete
            ├── T061 (validate-staging-ingestion.sh update) — parallel, no code dependencies
            ├── T062 (db-init hcs_silver/hcs_gold views) — must complete BEFORE T016 (PostgREST restart)
            └── T063 (Ruff + mypy clean pass) — depends on all new Python files written
```

US3 (Refresh History) is a verification phase, not a blocker — it runs once US1 and US2 are done.
US4 (Agents) depends on US2 being complete (needs abstracts in `silver.publications` — populated after T058 extends the model with EuropePMC 5th CTE).
US5 (Data Tools) depends on US1 being complete (registry needs CMS sources registered in `meta.data_sources`).
US6 (EDGAR) is independent of all other user stories.
T057 (rollback SQL) can be written in parallel with any phase.
T058 (`silver.publications` EuropePMC extension) must follow T022 (mol_bronze.europepmc) — move to Phase 4 execution order after T022.
T059 (agent CronJobs) must follow all 7 agents in Phase 6.
T061 (validation script update) can be written in parallel with any phase.
T062 (db-init views) MUST precede T016 (PostgREST exposure) — PostgREST restart without views causes web_anon permission errors.
T063 (Ruff + mypy) is a final gate — runs after all new Python files are written.

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
- T037 (publication evidence extractor) depends on T058 (`silver.publications` extension) being complete — T037 reads from `silver.publications`, not a standalone `mol_silver.europepmc` table

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

**Total tasks**: 63
**Parallelizable tasks**: 30 (marked [P])
