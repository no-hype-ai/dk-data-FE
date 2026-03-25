# Tasks: USPTO & EUIPO Model Datasource Integration

**Input**: Design documents from `/specs/014-uspto-euipo-model-datasource/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — FR-012 explicitly requires at least 12 EUIPO tests and 14 USPTO trademark tests.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. US1+US2 are combined (both P1, share `silver.patents`). US4 precedes US3 because `silver.trademarks` needs both bronze models.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/dk_data/` at repository root
- SQLMesh models: `src/dk_data/sqlmesh/models/molecules/`
- Fetchers: `src/dk_data/ingestion/fetchers/`
- Loaders: `src/dk_data/ingestion/sources/`
- Validators: `src/dk_data/ingestion/utils/validators.py`
- Migrations: `src/dk_data/sql/migrations/`
- K8s manifests: `k8s/base/ingestion/`
- Tests: `tests/`

---

## Phase 1: Setup

**Purpose**: Database schema changes and configuration that must exist before any feature code

**Migration execution context**: The `db-init-job.yaml` (ArgoCD sync-wave 1) uses `postgres:16.4` image — it creates schemas, roles, views, and extensions via inline SQL, but does NOT run `src/dk_data/sql/migrations/*.sql` files. Step 13 tries `python3 -m dk_data.scripts.run_migrations` but falls back because Python is unavailable in the postgres image. Migrations must be applied separately — either manually via `kubectl exec` into the job-trigger pod, or by running the migration runner from a local machine with DB access. See T033 below.

- [x] T001 [P] Create migration `src/dk_data/sql/migrations/071_uspto_trademarks_raw.sql` — `raw.uspto_trademarks` table with serial_number PK, mark_element, mark_type, status, status_code, status_date, filing_date, registration_number, registration_date, nice_classes INTEGER[], us_classes TEXT[], owner_name, owner_entity_type, goods_and_services, description_of_mark, plus metadata columns (_loaded_at, _source_file, _source_hash). Indexes on filing_date DESC, GIN on nice_classes, status. Follow pattern from `064_uspto_patents_raw_table.sql`.
- [x] T002 [P] Create migration `src/dk_data/sql/migrations/072_euipo_trademarks_raw.sql` — `raw.euipo_trademarks` table with application_number PK, mark_name, mark_kind, mark_feature, mark_basis, applicant_name, applicant_country, representative_name, status, filing_date, registration_date, expiry_date, nice_classes INTEGER[], goods_and_services, image_url, plus metadata columns. Indexes on filing_date DESC, GIN on nice_classes, status.
- [x] T003 [P] Create migration `src/dk_data/sql/migrations/073_trademark_status_history.sql` — `raw.trademark_status_history` table with UUID PK (gen_random_uuid), trademark_identifier VARCHAR(30) NOT NULL, source VARCHAR(20) NOT NULL with CHECK constraint ('uspto_trademarks', 'euipo_trademarks'), old_status, new_status NOT NULL, change_detected_at TIMESTAMP NOT NULL DEFAULT NOW(). Composite index on (trademark_identifier, source) and index on change_detected_at DESC.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic validators and seed data that MUST be complete before fetcher/loader work can begin

**Depends on**: Phase 1 (migrations exist)

- [x] T004 [P] Add `USPTOTrademarkRecord` Pydantic validator to `src/dk_data/ingestion/utils/validators.py` — serial_number (str, min_length=1, PK), optional fields: mark_element, mark_type, status, status_code (int), status_date (date), filing_date, registration_number, registration_date, nice_classes (list[int]), us_classes (list[str]), owner_name, owner_entity_type, goods_and_services, description_of_mark. Use `ConfigDict(str_strip_whitespace=True)`. Follow pattern from `USPTOCIRecord` in same file.
- [x] T005 Add `EUIPOTrademarkRecord` Pydantic validator to `src/dk_data/ingestion/utils/validators.py` — application_number (str, min_length=1, PK), optional fields: mark_name, mark_kind, mark_feature, mark_basis, applicant_name, applicant_country (max_length=10), representative_name, status, filing_date, registration_date, expiry_date, nice_classes (list[int]), goods_and_services. Use `ConfigDict(str_strip_whitespace=True)`.
- [x] T006 Update seed data in `src/dk_data/sql/seed_data_sources.sql` — add two new entries to the INSERT: `('uspto_trademarks', 'api', 'https://tsdrapi.uspto.gov/', 'USPTO TSDR trademark case status data for pharmaceutical trademarks (Nice Class 5)', 'weekly', TRUE)` and `('euipo_trademarks', 'api', 'https://www.tmdn.org/tmview/api/search', 'EUIPO trademark data via TMview federated search for pharmaceutical trademarks (Nice Class 5)', 'weekly', TRUE)`. Insert before the closing `ON CONFLICT` clause.

**Checkpoint**: Database tables exist, validators importable, seed data ready

---

## Phase 3: US1 + US2 — Patent Data Through Full Medallion Pipeline (Priority: P1) 🎯 MVP

**Goal**: Fix the broken `bronze.uspto_patents` model, create missing bronze models for USPTO CI and EPO, and extend `silver.patents` to unify patent data from all 4 sources (DrugBank + USPTO Patents + USPTO CI + EPO OPS).

**Independent Test**: Run `sqlmesh plan` and `sqlmesh apply`, then query `SELECT source, COUNT(*) FROM silver.patents GROUP BY source` — should show records from `drugbank`, `uspto_patents`, `uspto_ci`, and `epo_ops`.

### Bronze Models (parallel — different files, no interdependencies)

- [x] T007 [P] [US1] Fix `src/dk_data/sqlmesh/models/molecules/bronze/uspto_patents.sql` — replace the broken JSONB extraction (`r.response_body->'patents'` on lines 94-98) with direct flat-column reads from `raw.uspto_patents`. Remove `jsonb_array_elements()` call. Read `r.patent_number`, `r.title AS patent_title`, `r.abstract AS patent_abstract`, `r.grant_date AS patent_date`, cast `r.cpc_codes` TEXT[] to JSONB via `to_jsonb()`, extract `r.assignees->0->>'assignee_organization'` as assignee_organization (PatentsView API field name), keep `r.inventors` as-is (already JSONB), `r.claims_count AS num_claims`. Compute `is_pharma_related` using `EXISTS (SELECT 1 FROM unnest(COALESCE(r.cpc_codes, '{}')) AS code WHERE code LIKE 'A61K%' OR code LIKE 'A61P%' OR code LIKE 'C07D%' OR code LIKE 'C07K%')`. Remove `WHERE r.response_status = 200` and `r.processed_to_bronze = FALSE` (these columns don't exist in the flat table). Keep MODEL block unchanged (INCREMENTAL_BY_TIME_RANGE, grain patent_number). Use `r._loaded_at AS ingested_at` (not `NOW()`) and add `AND @incremental_time_filter(_loaded_at)` to the WHERE clause for efficient incremental processing (matching `bronze.drugbank` pattern). Audits: `not_null(columns := (patent_number)), unique_values(columns := (patent_number))`. See `contracts/bronze-models.md` for full schema.
- [x] T008 [P] [US1] Create `src/dk_data/sqlmesh/models/molecules/bronze/uspto_ci.sql` — new SQLMesh model reading from `raw.uspto_ci`. Kind: INCREMENTAL_BY_TIME_RANGE (time_column ingested_at, lookback 7). Cron @weekly. Grain patent_number. Map `patent_id` → `patent_number`, `title` → `patent_title`, `abstract` → `patent_abstract`, `grant_date` → `patent_date`. Cast `cpc_codes` TEXT[] to JSONB. Extract `assignees->0->>'assignee_organization'` as assignee_organization (PatentsView API field name). Compute `is_pharma_related` same as T007. Use `r._loaded_at AS ingested_at` (not `NOW()`) and add `AND @incremental_time_filter(_loaded_at)` to the WHERE clause. Audits: `not_null(columns := (patent_number)), unique_values(columns := (patent_number))`. See `contracts/bronze-models.md`.
- [x] T009 [P] [US2] Create `src/dk_data/sqlmesh/models/molecules/bronze/epo_patents.sql` — new SQLMesh model reading from `raw.epo_patents`. Kind: INCREMENTAL_BY_TIME_RANGE (time_column ingested_at, lookback 7). Cron @weekly. Grain patent_number. Map `publication_id` → `patent_number`, `title` → `patent_title`, `abstract` → `patent_abstract`, `publication_date` → `patent_date`. Cast `ipc_codes` TEXT[] to JSONB as `ipc_codes` (separate from `cpc_codes`). Extract `applicants->0` as assignee_organization. Add `family_id`. Compute `is_pharma_related` using IPC codes A61K/A61P/C07D/C07K. Use `r._loaded_at AS ingested_at` (not `NOW()`) and add `AND @incremental_time_filter(_loaded_at)` to the WHERE clause. Audits: `not_null(columns := (patent_number)), unique_values(columns := (patent_number))`. See `contracts/bronze-models.md`.

### Silver Model (depends on T007, T008, T009)

- [x] T010 [US1] Extend `src/dk_data/sqlmesh/models/molecules/silver/patents.sql` — add 3 new CTEs for `uspto_patents`, `uspto_ci`, and `epo_patents` that read from their bronze tables. UNION ALL with existing `drugbank_patents` CTE. Apply `DISTINCT ON (patent_number)` with deterministic source priority: drugbank=1, uspto_patents=2, uspto_ci=3, epo_ops=4 (ORDER BY patent_number, source_priority). Add `source` column. Keep existing output schema (id, patent_number, application_number, title, abstract, filing_date, grant_date, expiry_date, assignee, inventors, patent_type, country, cpc_codes, ipc_codes, status, source, etc.). Set country='US' for USPTO sources, 'EP' for EPO. See `contracts/silver-models.md` for full SQL.

**Checkpoint**: `sqlmesh plan` compiles all bronze+silver models. `silver.patents` contains deduplicated records from 4 sources. Core bug from dk-data#143 is fixed.

---

## Phase 4: US4 — USPTO Trademark Data Ingestion (Priority: P2)

**Goal**: Ingest US trademark data from the USPTO TSDR API into the raw layer and transform through bronze. Must be completed before US3 since `silver.trademarks` needs both bronze models.

**Independent Test**: Run the fetcher with mocked HTTP, verify records appear in `raw.uspto_trademarks` and `bronze.uspto_trademarks`.

**Depends on**: Phase 2 (validators, migrations)

### Implementation

- [x] T011 [US4] Create `src/dk_data/ingestion/fetchers/uspto_trademarks.py` — new `USPTOTrademarksFetcher` extending `BaseFetcher`. SOURCE_NAME='uspto_trademarks', BASE_URL='https://tsdrapi.uspto.gov'. Read API key from `USPTO_TSDR_API_KEY` env var. Implement `get_latest_url()` returning TSDR API URL. Implement `fetch(serial_numbers=None, **kwargs)` that queries the multi-case batch endpoint `GET /ts/cd/caseMultiStatus/sn?ids={comma_separated}`. Implement `_normalize_trademark(raw)` mapping TSDR Swagger fields: serialNumber→serial_number, markElement→mark_element, statusStr→status, statusDate→status_date, filingDate→filing_date, usRegistrationNumber→registration_number, gsList[].internationalClasses→nice_classes, parties.currentOwners[0].name→owner_name. Rate limit: 60 req/min standard, 4 req/min batch. Return `{"status": "success", "records": [...], "hash": "..."}`. Handle 401 (bad key) gracefully. **NOTE**: The TSDR API is lookup-only (no search by Nice Class). On initial deployment, `raw.uspto_trademarks` will be empty — the fetcher requires serial numbers to query. The initial Class 5 dataset (~200K records) must be seeded via a separate bulk XML load (out of scope for this feature, see spec.md Assumptions). Until seeded, the fetcher can be called with an explicit `serial_numbers` list for testing. See `contracts/fetchers.md`.
- [x] T012 [US4] Create `src/dk_data/ingestion/sources/uspto_trademarks.py` — `load_uspto_trademarks_data(records, source_hash=None, source_file=None, batch_size=500)` function following exact pattern from `src/dk_data/ingestion/sources/epo_ops.py`: uses `get_connection()` internally (NOT a conn param), validates each record via `USPTOTrademarkRecord`, upserts into `raw.uspto_trademarks` with `ON CONFLICT (serial_number) DO UPDATE SET mark_element=EXCLUDED.mark_element, status=EXCLUDED.status, ...`, batch commits every 500 records. Returns `{"status", "records_inserted", "records_failed", "errors"}` dict (NOT int). After upsert, for each record compare `status` with last entry in `raw.trademark_status_history` for that serial_number+source; if different, INSERT new history row. After each successful batch commit, call `record_data_source_refresh('uspto_trademarks', 'uspto_trademarks', records_inserted)` from `dk_data.observability.metrics` to update Prometheus gauges.
- [x] T013 [US4] Create `src/dk_data/sqlmesh/models/molecules/bronze/uspto_trademarks.sql` — new SQLMesh model. Kind: INCREMENTAL_BY_TIME_RANGE (time_column ingested_at, lookback 7). Cron @weekly. Grain serial_number. Read from `raw.uspto_trademarks`. Cast `nice_classes` INTEGER[] to JSONB. Compute `is_pharma_related` as `5 = ANY(COALESCE(r.nice_classes, '{}'))`. Use `r._loaded_at AS ingested_at` (not `NOW()`) and add `AND @incremental_time_filter(_loaded_at)` to the WHERE clause. Audits: `not_null(columns := (serial_number)), unique_values(columns := (serial_number))`. See `contracts/bronze-models.md`.

**Checkpoint**: USPTO trademark records flow from TSDR API → raw → bronze. Status changes tracked in history table.

---

## Phase 5: US3 — EUIPO Trademark Data Ingestion (Priority: P2)

**Goal**: Ingest European trademark data from EUIPO (via TMview or IBM Gateway), transform through bronze, and create unified `silver.trademarks` combining both US and EU trademarks. Update `gold.molecule_profile` with trademark counts.

**Independent Test**: Run the fetcher with mocked HTTP for TMview, verify records in `raw.euipo_trademarks` → `bronze.euipo_trademarks` → `silver.trademarks`. Query `SELECT source, COUNT(*) FROM silver.trademarks GROUP BY source` — should show both 'uspto_trademarks' and 'euipo_trademarks'.

**Depends on**: Phase 2 (validators, migrations), Phase 4 (US4 bronze model needed for silver.trademarks)

### Implementation

- [x] T014 [US3] Create `src/dk_data/ingestion/fetchers/euipo_trademarks.py` — new `EUIPOTrademarksFetcher` extending `BaseFetcher`. SOURCE_NAME='euipo_trademarks'. Support dual backend via `EUIPO_BACKEND` env var ('tmview' default, 'ibm_gateway' alternative). TMview: POST `https://www.tmdn.org/tmview/api/search` with JSON body `{pageSize, pageIndex, criteria: {niceClasses: ["05"], tradeMarkOffices: ["EM"], applicationDateFrom, applicationDateTo}}`. IBM Gateway: OAuth2 token from `https://euipo.europa.eu/cas-server-webapp/oidc/accessToken` + `X-IBM-Client-Id` header to `https://api.euipo.europa.eu/trademark-search`. Implement `_normalize_trademark(raw)` mapping: applicationNumber→application_number, tradeMarkName→mark_name, tradeMarkType→mark_kind, status→status, applicationDate→filing_date, registrationDate→registration_date, expiryDate→expiry_date, niceClasses→nice_classes, applicantName→applicant_name. Rate limit: 30 req/min. Pagination: stop at `max_records` (default 10000). See `contracts/fetchers.md`.
- [x] T015 [US3] Create `src/dk_data/ingestion/sources/euipo_trademarks.py` — `load_euipo_trademarks_data(records, source_hash=None, source_file=None, batch_size=500)` function following exact pattern from `sources/epo_ops.py`: uses `get_connection()` internally, validates via `EUIPOTrademarkRecord`, upserts into `raw.euipo_trademarks` with `ON CONFLICT (application_number) DO UPDATE`, batch commits. Returns `{"status", "records_inserted", "records_failed", "errors"}` dict. Compare status with `raw.trademark_status_history` for status change tracking. After each successful batch commit, call `record_data_source_refresh('euipo_trademarks', 'euipo_trademarks', records_inserted)` from `dk_data.observability.metrics` to update Prometheus gauges.
- [x] T016 [US3] Create `src/dk_data/sqlmesh/models/molecules/bronze/euipo_trademarks.sql` — new SQLMesh model. Kind: INCREMENTAL_BY_TIME_RANGE (time_column ingested_at, lookback 7). Cron @weekly. Grain application_number. Read from `raw.euipo_trademarks`. Preserve EUIPO-specific fields (mark_kind, mark_feature, expiry_date). Cast `nice_classes` INTEGER[] to JSONB. Compute `is_pharma_related` as `5 = ANY(COALESCE(r.nice_classes, '{}'))`. Use `r._loaded_at AS ingested_at` (not `NOW()`) and add `AND @incremental_time_filter(_loaded_at)` to the WHERE clause. Audits: `not_null(columns := (application_number)), unique_values(columns := (application_number))`. See `contracts/bronze-models.md`.
- [x] T017 [US3] Create `src/dk_data/sqlmesh/models/molecules/silver/trademarks.sql` — new SQLMesh model. Kind: INCREMENTAL_BY_UNIQUE_KEY (unique_key: (trademark_identifier, source), when_matched_update_all TRUE). Cron @weekly. Grain (trademark_identifier, source). CTE `uspto`: SELECT from `bronze.uspto_trademarks` mapping serial_number→trademark_identifier, mark_element→mark_name, mark_type→mark_type, source='uspto_trademarks'. CTE `euipo`: SELECT from `bronze.euipo_trademarks` mapping application_number→trademark_identifier, mark_name→mark_name, mark_kind→mark_type, source='euipo_trademarks'. UNION ALL both CTEs. `DISTINCT ON (trademark_identifier, source)` — within-registry dedup only, no cross-registry dedup. Add filing_date, registration_date, expiry_date (EUIPO only), owner_name, nice_classes, goods_and_services, is_pharma_related. See `contracts/silver-models.md`.
- [x] T018 [US3] Update `src/dk_data/sqlmesh/models/molecules/gold/molecule_profile.sql` — add new CTE `trademark_info` that JOINs `silver.trademarks` to `silver.molecule_aliases` on `LOWER(mark_name) = LOWER(alias_name)` where `alias_type IN ('brand', 'trade', 'product')`. Excludes `canonical` alias_type because canonical = INN/generic names (e.g., "adalimumab"), whereas trademarks are registered under brand names (e.g., "Humira"). Aggregate: trademark_count (COUNT DISTINCT on trademark_identifier||source), active_trademark_count (status IN ('Registered', 'REGISTERED')), us_trademark_count (source='uspto_trademarks'), eu_trademark_count (source='euipo_trademarks'), latest_us_trademark_status, latest_eu_trademark_status. LEFT JOIN trademark_info in final SELECT. Add 6 new columns with COALESCE defaults. See `contracts/gold-models.md`.

**Checkpoint**: Full trademark pipeline works end-to-end. `silver.trademarks` has both US + EU records. `gold.molecule_profile` includes trademark counts.

---

## Phase 6: US5 — Operational Observability (Priority: P2)

**Goal**: All 5 IP sources appear in Prometheus metrics and are registered in the fetcher CLI.

**Independent Test**: Query `/metrics` endpoint and verify `dk_source_health_status` gauges for all 5 sources: `uspto_patents`, `uspto_ci`, `epo_patents`, `uspto_trademarks`, `euipo_trademarks`.

**Depends on**: Phase 4 (US4 fetcher), Phase 5 (US3 fetcher)

### Implementation

- [x] T019 [US5] Integrate IP sources into metrics — **CRITICAL: Two metrics files exist. DO NOT create duplicate Gauges.** (A) Update `src/dk_data/services/data_platform/metrics.py` — this file ALREADY defines `DK_SOURCE_HEALTH_STATUS` Gauge (line 74), `DK_TABLE_RECORD_COUNT` Gauge (line 160), and helpers `set_source_health()` (line 235), `set_table_record_count()` (line 302). Add IP sources to the existing dicts: (1) Add to `local_sources` dict (~line 428): `'uspto_patents': ('bronze.uspto_patents', True)`, `'uspto_ci': ('bronze.uspto_ci', True)`, `'epo_patents': ('bronze.epo_patents', True)`, `'uspto_trademarks': ('bronze.uspto_trademarks', True)`, `'euipo_trademarks': ('bronze.euipo_trademarks', True)`. (2) Add IP tables to the `layer_tables` dict (~line 584): add `'uspto_patents', 'uspto_ci', 'epo_patents', 'uspto_trademarks', 'euipo_trademarks'` to the `'raw'` and `'bronze'` lists, add `'trademarks'` to the `'silver'` list. (3) Add IP tables to `raw_sources` dict (~line 528): `'uspto_patents': 'raw.uspto_patents'`, etc. (B) In `src/dk_data/observability/metrics.py` — add only an `IP_DATA_SOURCES` list constant for reference: `['uspto_patents', 'uspto_ci', 'epo_patents', 'uspto_trademarks', 'euipo_trademarks']`. The existing `record_data_source_refresh()` already works with arbitrary source labels — loaders call it as-is. DO NOT create `dk_source_health_status` or `dk_table_record_count` Gauges here (they exist in data_platform/metrics.py and Prometheus forbids duplicate metric names).
- [x] T020 [US5] Register trademark fetchers and loaders — (a) In `src/dk_data/ingestion/fetchers/__init__.py`: add imports `from .uspto_trademarks import USPTOTrademarksFetcher` and `from .euipo_trademarks import EUIPOTrademarksFetcher`, add both to `__all__` list. (b) In `src/dk_data/ingestion/sources/__init__.py`: add `'uspto_trademarks'` and `'euipo_trademarks'` to `__all__` list.
- [x] T021 [US5] Register trademark fetchers in `src/dk_data/ingestion/fetch_data.py` — add imports for `USPTOTrademarksFetcher` and `EUIPOTrademarksFetcher`. Add entries to `FETCHERS` dict: `'uspto_trademarks': {'class': USPTOTrademarksFetcher, 'description': 'USPTO TSDR trademark case status data', 'priority': 3}` and `'euipo_trademarks': {'class': EUIPOTrademarksFetcher, 'description': 'EUIPO trademark data via TMview/IBM Gateway', 'priority': 3}`. **REQUIRED — loader integration**: The existing `fetch_source()` function (line 160) calls `fetcher.fetch()` but NEVER calls any loader — records are fetched but not persisted to the database. Use **option (a)**: add loader invocations to `fetch_source()` after `fetcher.fetch()` returns. Add a `LOADERS` dict mapping source names to loader functions, then after `result = fetcher.fetch()`, check if `source in LOADERS` and call `LOADERS[source](result['records'], source_hash=result.get('hash'))`. At minimum, add entries for `'uspto_trademarks': load_uspto_trademarks_data` and `'euipo_trademarks': load_euipo_trademarks_data`. Import both loader functions from `dk_data.ingestion.sources`. This is a pre-existing architectural gap affecting all CronJob sources, but for this feature we only need to wire up the two new trademark loaders. Without this, CronJobs (T022/T023) will fetch data but never persist it to the database.

**Checkpoint**: `python -m dk_data.ingestion.fetch_data --list` shows both trademark sources. `/metrics` endpoint includes all 5 IP source gauges.

---

## Phase 7: US6 — Automated Trademark Ingestion via Kubernetes CronJobs (Priority: P3)

**Goal**: EUIPO and USPTO trademark ingestion runs on automated weekly schedules via K8s CronJobs.

**Independent Test**: `kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null` validates successfully.

**Depends on**: Phase 6 (fetchers registered in fetch_data.py)

### Implementation

- [x] T022 [P] [US6] Create `k8s/base/ingestion/cronjob-fetch-uspto-trademarks.yaml` — follow pattern from `cronjob-fetch-epo.yaml`. Schedule: `"0 16 * * 0"` (Sunday 4 PM UTC). Name: `fetch-uspto-trademarks`. Command: `["python", "-m", "dk_data.ingestion.fetch_data"]`, args: `["--source", "uspto_trademarks"]`. Include env vars: POSTGRES_HOST/PORT/USER/PASSWORD/DB from dk-data-secrets, USPTO_TSDR_API_KEY from dk-data-secrets (optional: true). Include OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_ENABLED. Resources: requests 256Mi/100m, limits 512Mi/300m. Labels: app.kubernetes.io/component: ingestion, part-of: dk-data. backoffLimit: 2, activeDeadlineSeconds: 3600.
- [x] T023 [P] [US6] Create `k8s/base/ingestion/cronjob-fetch-euipo.yaml` — follow same pattern as T022. Schedule: `"0 18 * * 0"` (Sunday 6 PM UTC). Name: `fetch-euipo`. Args: `["--source", "euipo_trademarks"]`. Include env vars: EUIPO_API_KEY and EUIPO_SECRET_KEY from dk-data-secrets (both optional: true), plus EUIPO_BACKEND with value "tmview". Same resource limits.
- [x] T024 [US6] Update `k8s/base/kustomization.yaml` — add two new resource entries after the existing `# 012-platform-hardening` CronJob block (uniprot, pdb, orcid). Add a new comment `# 014-uspto-euipo-model-datasource` followed by: `- ingestion/cronjob-fetch-uspto-trademarks.yaml` and `- ingestion/cronjob-fetch-euipo.yaml`. Follow the existing feature-number comment format used by `# 011-datasource-integration` and `# 012-platform-hardening` blocks.

**Checkpoint**: `kubectl kustomize k8s/overlays/staging --enable-helm` renders all CronJobs without errors.

---

## Phase 8: US7 — CI/CD Validates All Patent & Trademark Components (Priority: P3)

**Goal**: Automated tests cover all new fetchers, validators, and model contracts. CI passes on PRs.

**Independent Test**: `ruff check . && pytest tests/ -v --tb=short` passes with all new tests.

**Depends on**: Phase 4 (US4), Phase 5 (US3), Phase 6 (US5)

### Tests (Required by FR-012)

- [x] T025 [P] [US7] Create `tests/test_euipo_trademarks_fetcher.py` — at least 12 tests following pattern from `tests/test_epo_ops_fetcher.py`. Use `responses` library for HTTP mocking. Test classes: (1) `TestEUIPOTrademarksFetcherInit` — test init, default backend=tmview, IBM backend override, get_latest_url. (2) `TestEUIPOTrademarksFetch` — test fetch_success (TMview), fetch_empty_results, fetch_api_error (500), fetch_pagination (stop at pageSize boundary), fetch_rate_limiting (FR-013: verify delay between requests enforces ≤30 req/min; mock `time.sleep` and assert it's called with ≥2.0s between requests), fetch_ibm_gateway_backend, fetch_deduplication. (3) `TestEUIPONormalization` — test normalize_full_record, normalize_minimal_record, normalize_missing_application_number. (4) `TestEUIPOTrademarkRecord` — test valid_record, minimal_record, empty_application_number_rejected, missing_application_number_rejected, whitespace_stripped. Import `EUIPOTrademarksFetcher` from `dk_data.ingestion.fetchers.euipo_trademarks` and `EUIPOTrademarkRecord` from `dk_data.ingestion.utils.validators`.
- [x] T026 [P] [US7] Create `tests/test_uspto_trademarks_fetcher.py` — at least 14 tests following pattern from `tests/test_uspto_ci_fetcher.py`. Test classes: (1) `TestUSPTOTrademarksFetcherInit` — test init, get_latest_url, api_key_from_env. (2) `TestUSPTOTrademarksFetch` — test fetch_success (batch endpoint), fetch_empty_results, fetch_api_error (500), fetch_auth_error (401), fetch_pagination, fetch_rate_limiting (FR-013: verify delay between batch requests enforces ≤4 req/min for multi-case endpoint; mock `time.sleep` and assert ≥15.0s delay between batch calls), fetch_deduplication, fetch_no_serial_numbers. (3) `TestUSPTOTrademarkNormalization` — test normalize_full_record, normalize_minimal_record, normalize_missing_serial_number. (4) `TestUSPTOTrademarkRecord` — test valid_record, minimal_record, empty_serial_number_rejected, missing_serial_number_rejected, whitespace_stripped.
- [x] T027 [P] [US7] Create `tests/test_bronze_model_contracts.py` — contract tests verifying bronze SQLMesh models compile and produce expected schemas. For each of the 5 bronze models (uspto_patents, uspto_ci, epo_patents, uspto_trademarks, euipo_trademarks): assert MODEL block has correct name, kind, grain, and audits. Test that required output columns exist in the SQL. Use simple SQL parsing or regex — no DB required. At least 10 tests total.
- [x] T028 [P] [US7] Create `tests/test_silver_model_contracts.py` — contract tests for `silver.patents` and `silver.trademarks`. Assert silver.patents references all 4 bronze sources. Assert silver.trademarks has UNION ALL from both trademark bronze models. Assert DISTINCT ON deduplication is present. Assert source priority ordering. At least 8 tests total.
- [x] T029 [US7] Validate full CI pipeline locally — run `ruff check .` (zero errors), `pytest tests/ -v --tb=short` (all tests pass including new ones), `kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null` (manifests valid). Fix any ruff or pytest failures. Verify existing tests (`test_uspto_ci_fetcher.py`, `test_epo_ops_fetcher.py`, etc.) still pass — no regressions.

**Checkpoint**: All tests pass. CI pipeline would pass on a PR.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, deployment prerequisites, and cleanup

### Deployment Prerequisites

- [x] T033 **AUTOMATED** via `k8s/base/migration-runner-job.yaml` (ArgoCD sync-wave "2") — Apply migrations 071-073 and seed data on the cluster — The `db-init-job.yaml` does NOT execute SQL migration files (uses `postgres:16.4` image without Python). To apply the new raw tables on the cluster: (a) After the PR is merged and the new image is deployed via ArgoCD, exec into the job-trigger pod: `kubectl exec -it deploy/job-trigger -n dk-data-staging -- python -m dk_data.scripts.run_migrations`. This will discover migrations 071/072/073 in `src/dk_data/sql/migrations/`, check them against `meta.schema_migrations`, and apply any unapplied ones. (b) Alternatively, run from a local machine with DB access: `POSTGRES_HOST=<host> POSTGRES_PORT=<port> POSTGRES_PASSWORD=<pass> python -m dk_data.scripts.run_migrations`. (c) Verify by querying: `SELECT version, filename FROM meta.schema_migrations WHERE version >= '071' ORDER BY version;` — should show all 3 migrations applied. (d) Also run the updated seed data to register new sources in `meta.data_sources`: `kubectl exec -it deploy/job-trigger -n dk-data-staging -- python -c "from dk_data.utils.database import get_connection; import importlib.resources; conn = get_connection(); conn.cursor().execute(open('/usr/local/lib/python3.11/site-packages/dk_data/sql/seed_data_sources.sql').read()); conn.commit()"` — or pipe the SQL directly via `psql` from a machine with DB access. Verify: `SELECT source_name FROM meta.data_sources WHERE source_name IN ('uspto_trademarks', 'euipo_trademarks');` should return both rows. **NOTE**: The `raw` schema already exists (created by `db-init-job.yaml` Step 3). The migration runner only needs to CREATE TABLE within it.
- [x] T035 Extend transformation script for IP model automation — The existing `cronjob-mol-transform.yaml` runs `python -m dk_data.ingestion.transform_molecules --layer all`, but `transform_molecules.py`'s `LAYER_MODELS` dict (line 32-51) only processes `mol_bronze.*`, `mol_silver.*`, `mol_gold.*` models. The new IP models (`bronze.uspto_patents`, `bronze.uspto_ci`, `bronze.epo_patents`, `bronze.uspto_trademarks`, `bronze.euipo_trademarks`, `silver.patents`, `silver.trademarks`, `gold.molecule_profile`) are NOT included and will NOT be processed automatically. Use **option (a)**: Add IP models to `LAYER_MODELS` in `src/dk_data/ingestion/transform_molecules.py` under new keys (`'ip_bronze': ['bronze.uspto_patents', 'bronze.uspto_ci', 'bronze.epo_patents', 'bronze.uspto_trademarks', 'bronze.euipo_trademarks']`, `'ip_silver': ['silver.patents', 'silver.trademarks']`, `'ip_gold': ['gold.molecule_profile']`) and update the `--layer all` handler to include them. Alternatives considered but rejected: (b) separate CronJob (unnecessary infra complexity), (c) `--all-models` flag (too broad, runs unrelated models). **NOTE**: SC-008 requires "pipeline latency under 10 minutes for incremental runs" — without this task, data sits in raw tables and never flows through bronze → silver → gold on-cluster automatically.
- [x] T034 Create GitHub issue for Doppler secret provisioning (→ #107) — **DEFERRED**: All Doppler credential changes are out of scope for this PR and must be handled by Nick ([@no-hype-ai](https://github.com/no-hype-ai)). Create a GitHub issue in `dk-data-fe` with title "Provision Doppler secrets for USPTO/EUIPO trademark sources (014)" assigned to `no-hype-ai`. The issue must list the following secrets to add to both `stg` and `prd` Doppler configs in the `dk-data-fe` project: (1) `USPTO_TSDR_API_KEY` — API key from https://account.uspto.gov/api-manager/ for TSDR trademark lookups, (2) `EUIPO_API_KEY` — IBM Client ID for EUIPO API Gateway (or TMview key), (3) `EUIPO_SECRET_KEY` — OAuth2 client secret for EUIPO CAS server. Note: these secrets are referenced as `optional: true` in CronJob manifests (T022/T023), so deployment won't break without them — the fetchers will log warnings and skip. The DopplerSecret CRD (`k8s/base/doppler-secret.yaml`) already syncs the full `dk-data-secrets` secret; no manifest changes needed once secrets are added to Doppler SaaS.
- [x] T036 Create GitHub issue for dynamic data source auto-registration (→ #108) — **DEFERRED**: The current system requires manual updates to 3 files when adding a new data source: (1) `src/dk_data/sql/seed_data_sources.sql` — SQL INSERT with name/URL/description/frequency, (2) `src/dk_data/ingestion/fetch_data.py` `FETCHERS` dict — class/description/priority, (3) `src/dk_data/ingestion/fetchers/__init__.py` + `sources/__init__.py` — import registries. This is error-prone and creates drift risk. Create a GitHub issue in `dk-data-fe` with title "Implement dynamic data source auto-registration from fetcher metadata" with the following scope: (a) Add class-level metadata to `BaseFetcher` (`SOURCE_NAME`, `SOURCE_TYPE`, `SOURCE_URL`, `DESCRIPTION`, `REFRESH_FREQUENCY`), (b) Implement auto-discovery that scans all `BaseFetcher` subclasses and populates `meta.data_sources` via upsert on startup or via a management command (`python -m dk_data.scripts.register_sources`), (c) Replace hardcoded `FETCHERS` dict in `fetch_data.py` with auto-discovery from fetcher classes, (d) Deprecate `seed_data_sources.sql` in favor of the dynamic system. This affects all 19+ existing fetchers and should be a separate PR. Label: `enhancement`, `tech-debt`.

### Pre-Merge Validation

- [x] T030 **AUTOMATED** via CI `sqlmesh-validate` job (`.github/workflows/ci.yaml`) — Run end-to-end SQLMesh validation — execute `cd src/dk_data && python -m sqlmesh plan` to verify all models compile. Check for circular dependencies, missing references, and audit failures. Fix any issues. **SC-008 validation**: After `sqlmesh apply`, time an incremental run with `time python -m sqlmesh run` (with no new raw data) and verify it completes in under 10 minutes. If it exceeds 10 minutes, investigate which model is slow (likely `gold.molecule_profile` trademark JOIN) and optimize.
- [x] T031 **AUTOMATED** via CI (pytest 128 tests + kustomize validate + sqlmesh-validate) — Run quickstart.md validation — follow the steps in `specs/014-uspto-euipo-model-datasource/quickstart.md` to verify the complete setup flow works. Verify metrics endpoint, CronJob manifests, and fetcher CLI all function correctly.
- [x] T032 Verify `specs/014-uspto-euipo-model-datasource/` artifacts are consistent — cross-check that all files referenced in plan.md exist, all FRs from spec.md have corresponding tasks, and all contracts have matching implementations.

### PR & Staging Deployment Validation

- [x] T037 Create PR from `014-uspto-euipo-model-datasource` branch to `staging` (→ PR #106) — verify: (a) no merge conflicts with staging branch, (b) CI workflow (`.github/workflows/ci.yaml`) triggers and all 3 checks pass: `ruff check .` (zero errors), `pytest tests/ -v` (all new+existing tests pass with PostgreSQL 16 service container), `kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null` (all manifests valid including new CronJobs). (c) PR description references dk-data#143, lists all new files (18) and modified files (12), and notes post-merge manual steps (migrations, seed data, Doppler secrets). (d) Review diff confirms no accidental changes to unrelated files.
- [x] T038 **AUTOMATED** via `.github/workflows/post-deploy-verify.yaml` — Post-merge ArgoCD sync verification — after PR merged to `staging`: (a) verify `build-push.yaml` triggers on push to staging and completes successfully (check GitHub Actions tab), (b) verify `k8s/overlays/staging/kustomization.yaml` `newTag` updated to `staging-{new_sha}`, (c) verify ArgoCD Application `dk-data-fe-staging` shows Synced+Healthy (check ArgoCD UI or `argocd app get dk-data-fe-staging`), (d) verify new CronJobs deployed: `kubectl get cronjobs -n dk-data-staging | grep -E 'fetch-uspto-trademarks|fetch-euipo'` should show both with correct schedules (Sunday 4PM/6PM UTC), (e) verify existing CronJobs still present and schedules unchanged.
- [x] T039 **AUTOMATED** via `.github/workflows/post-deploy-verify.yaml` — Post-deploy staging smoke test — after T033 migrations and seed data applied on staging: (a) manually trigger the USPTO trademark CronJob: `kubectl create job --from=cronjob/fetch-uspto-trademarks fetch-uspto-tm-test -n dk-data-staging` (will log warning about missing API key if Doppler not yet provisioned — this is expected), (b) verify job-trigger pod has the new image: `kubectl get deploy job-trigger -n dk-data-staging -o jsonpath='{.spec.template.spec.containers[0].image}'`, (c) verify raw tables exist: `kubectl exec deploy/job-trigger -n dk-data-staging -- python -c "from dk_data.utils.database import get_connection; c=get_connection().cursor(); c.execute('SELECT COUNT(*) FROM raw.uspto_trademarks'); print(c.fetchone())"`, (d) if Doppler secrets provisioned: verify fetcher returns data and loader persists to DB, (e) run `sqlmesh plan` from job-trigger pod to verify all models compile on-cluster: `kubectl exec deploy/job-trigger -n dk-data-staging -- python -m sqlmesh plan --no-prompts`.
- [x] T040 **AUTOMATED** via `.github/workflows/post-deploy-verify.yaml` — Post-deploy regression check — verify existing functionality not broken on staging: (a) PostgREST health: `curl -s https://data.preview.behaviorlabs.ai/health` returns 200, (b) existing API views: `curl -s https://data.preview.behaviorlabs.ai/data_catalog` returns results, (c) existing CronJobs still scheduled: `kubectl get cronjobs -n dk-data-staging` shows all pre-existing CronJobs (fetch-epo, fetch-uniprot, fetch-pdb, fetch-orcid, mol-transform) with Next Schedule populated, (d) Prometheus metrics endpoint: `kubectl exec deploy/job-trigger -n dk-data-staging -- curl -s localhost:8000/metrics | grep dk_source_health_status` shows gauges for all 5 IP sources, (e) no ArgoCD sync errors: Application shows no degraded resources.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup (migrations)         ← No dependencies, start immediately
Phase 2: Foundational (validators)  ← Depends on Phase 1
Phase 3: US1+US2 (patent pipeline)  ← Depends on Phase 1 only (no validators needed for SQL models)
Phase 4: US4 (USPTO trademarks)     ← Depends on Phase 2
Phase 5: US3 (EUIPO trademarks)     ← Depends on Phase 2 + Phase 4 (silver.trademarks needs both bronze models)
Phase 6: US5 (observability)        ← Depends on Phase 4 + Phase 5 (fetchers must exist)
Phase 7: US6 (CronJobs)             ← Depends on Phase 6 (fetchers registered)
Phase 8: US7 (CI/CD tests)          ← Depends on Phase 4 + Phase 5 + Phase 6
Phase 9: Polish                     ← Depends on all phases
  T033: Apply migrations + seed data ← Post-merge, requires deployed image
  T034: Doppler issue for Nick       ← Can run anytime (deferred, not blocking)
  T035: IP transform automation      ← Requires all models created (Phase 3-5)
  T036: Dynamic source registration  ← Can run anytime (deferred, not blocking)
  T037: PR to staging + CI check     ← Depends on all code phases (1-8) + T030-T032
  T038: ArgoCD sync verification     ← Depends on T037 (PR merged)
  T039: Staging smoke test           ← Depends on T038 + T033 (deploy + migrations)
  T040: Regression check             ← Depends on T038 (deploy complete)
```

### User Story Dependencies

- **US1+US2 (P1)**: Can start after Phase 1 — No dependencies on trademark stories
- **US4 (P2)**: Can start after Phase 2 — Independent of US1+US2
- **US3 (P2)**: Depends on US4 (silver.trademarks needs both bronze trademark models)
- **US5 (P2)**: Depends on US3 + US4 (fetchers must exist for registration)
- **US6 (P3)**: Depends on US5 (fetchers registered in fetch_data.py)
- **US7 (P3)**: Depends on US3 + US4 + US5 (code must exist to test)

### Parallel Opportunities

```
Phase 1: T001 ║ T002 ║ T003  (3 migrations in parallel)
Phase 2: T004 ║ T006            (parallel: different files) → T005 (sequential: same file as T004)
Phase 3: T007 ║ T008 ║ T009   (3 bronze models in parallel) → T010 (silver)
Phase 4: T011 → T012 → T013   (sequential: fetcher → loader → bronze)
Phase 5: T014 → T015 → T016 → T017 → T018  (sequential: fetcher → loader → bronze → silver → gold)
Phase 6: T019 ║ T020 ║ T021   (metrics + registration in parallel)
Phase 7: T022 ║ T023           (2 CronJobs in parallel) → T024 (kustomization)
Phase 8: T025 ║ T026 ║ T027 ║ T028  (4 test files in parallel) → T029 (validate)
```

### Critical Path

```
T001 → T004 → T011 → T012 → T013 → T014 → T015 → T016 → T017 → T018 → T019 → T029
 (migration)  (validator)  (USPTO TM fetcher→loader→bronze)  (EUIPO TM fetcher→loader→bronze→silver→gold)  (metrics)  (CI)
```

---

## Parallel Example: Phase 3 (Patent Medallion)

```
# Launch all 3 bronze models in parallel:
T007: "Fix bronze.uspto_patents in src/dk_data/sqlmesh/models/molecules/bronze/uspto_patents.sql"
T008: "Create bronze.uspto_ci in src/dk_data/sqlmesh/models/molecules/bronze/uspto_ci.sql"
T009: "Create bronze.epo_patents in src/dk_data/sqlmesh/models/molecules/bronze/epo_patents.sql"

# After all 3 complete, run silver:
T010: "Extend silver.patents in src/dk_data/sqlmesh/models/molecules/silver/patents.sql"
```

## Parallel Example: Phase 8 (Tests)

```
# Launch all 4 test files in parallel:
T025: "Create tests/test_euipo_trademarks_fetcher.py"
T026: "Create tests/test_uspto_trademarks_fetcher.py"
T027: "Create tests/test_bronze_model_contracts.py"
T028: "Create tests/test_silver_model_contracts.py"

# After all 4 complete, validate:
T029: "Validate full CI pipeline"
```

---

## Implementation Strategy

### MVP First (US1+US2 Patent Pipeline Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 3: US1+US2 (T007-T010) — can skip Phase 2 since patent models are SQL-only
3. **STOP and VALIDATE**: `sqlmesh plan` + `sqlmesh apply`, query `silver.patents` for 4 sources
4. Core dk-data#143 bug is fixed, patents flow through full medallion

### Incremental Delivery

1. **Phase 1+3**: Setup + Patent Pipeline → MVP deployed (dk-data#143 resolved)
2. **Phase 2+4**: Validators + USPTO Trademarks → US trademark data flowing
3. **Phase 5**: EUIPO Trademarks + silver.trademarks + gold → Full trademark pipeline
4. **Phase 6**: Observability → Metrics and CLI registration
5. **Phase 7**: CronJobs → Automated weekly ingestion
6. **Phase 8**: Tests → CI/CD coverage
7. **Phase 9**: Polish → Production readiness

### Parallel Team Strategy

With two developers:

1. Both complete Phase 1 (migrations) together
2. Developer A: Phase 3 (US1+US2 patents) → Phase 7 (CronJobs)
3. Developer B: Phase 2 (validators) → Phase 4 (US4) → Phase 5 (US3) → Phase 6 (observability)
4. Both: Phase 8 (tests) → Phase 9 (polish)

---

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 40 |
| Phase 1 (Setup) | 3 tasks |
| Phase 2 (Foundational) | 3 tasks |
| Phase 3 (US1+US2 Patents) | 4 tasks |
| Phase 4 (US4 USPTO TM) | 3 tasks |
| Phase 5 (US3 EUIPO TM) | 5 tasks |
| Phase 6 (US5 Observability) | 3 tasks |
| Phase 7 (US6 CronJobs) | 3 tasks |
| Phase 8 (US7 Tests) | 5 tasks |
| Phase 9 (Polish) | 11 tasks (4 deployment prereqs + 3 pre-merge validation + 4 PR/staging validation) |
| Parallel opportunities | 8 groups (22 of 40 tasks can run in parallel with others) |
| MVP scope | Phase 1 + Phase 3 (7 tasks) |
| New files | 18 |
| Modified files | 12 |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1+US2 combined because they share `silver.patents` and are both P1
- US4 precedes US3 because `silver.trademarks` (in US3) needs both bronze trademark models
- FR-012 explicitly requires tests, so Phase 8 is mandatory (not optional)
- Each phase checkpoint verifies the story works independently before moving on
- Commit after each task or logical group
- **Out of scope for this iteration**: USPTO Bulk Data XML initial load (~200K Class 5 records). The TSDR fetcher (T011) handles weekly incremental updates of known serial numbers. Bulk XML loading is a separate task for a follow-up feature, as noted in spec.md Assumptions

### Deployment Architecture (dk-alchemy context)

- **GitOps**: dk-data-FE is deployed via ArgoCD (hosted in dk-alchemy). ArgoCD watches `k8s/overlays/staging` (branch: staging) and `k8s/overlays/prod` (branch: main). Merging to main/staging triggers: GHA builds Docker image → pushes to `ghcr.io/data-kinetic/dk-data-fe/job-trigger:{branch}-{sha}` → updates kustomization.yaml `newTag` → ArgoCD auto-syncs.
- **Database init**: `db-init-job.yaml` is an ArgoCD sync-wave 1 hook that runs on every sync. Uses `postgres:16.4` image to create schemas, roles, views, and extensions. Does NOT run SQL migration files (Python unavailable).
- **Migration execution**: SQL migration files in `src/dk_data/sql/migrations/` are tracked by `meta.schema_migrations` table and applied by `python -m dk_data.scripts.run_migrations`. This must be run from a container with dk_data installed (job-trigger pod) or locally. See T033.
- **Secrets**: Doppler Operator syncs secrets from `dk-data-fe` project (configs: `stg`/`prd`) into K8s `dk-data-secrets` Opaque secret every 300s. CronJobs reference individual keys via `secretKeyRef` with `optional: true` for credential-gated sources. New secrets (T034) must be added to Doppler SaaS by Nick — no manifest changes needed.
- **DEFERRED — Doppler credentials**: Provisioning `USPTO_TSDR_API_KEY`, `EUIPO_API_KEY`, `EUIPO_SECRET_KEY` in Doppler is assigned to [@no-hype-ai](https://github.com/no-hype-ai) via GitHub issue (T034). CronJobs will deploy without these secrets (optional: true) and log warnings until provisioned.
- **CRITICAL — Transformation automation gap**: `transform_molecules.py` (used by `cronjob-mol-transform.yaml`) only processes `mol_*` models. The new IP models (bronze.*, silver.patents, silver.trademarks, gold.molecule_profile) are NOT in its `LAYER_MODELS` dict. Without T035, data fetched by CronJobs (T022/T023) will sit in raw tables but never flow through SQLMesh to bronze → silver → gold on-cluster. Manual `sqlmesh apply` from a local machine or `kubectl exec` would be required instead.
- **PRE-EXISTING — fetch_data.py loader gap**: `fetch_source()` in `fetch_data.py` calls `fetcher.fetch()` but NEVER invokes any loader function. This means CronJobs fetch data but may not persist to DB. T021 flags this and recommends option (a): add loader invocations to `fetch_source()` after the fetch returns. This is a pre-existing architectural issue affecting ALL API-based CronJob sources (not unique to 014). The implementer MUST resolve this for the trademark pipeline to work end-to-end.
- **Seed data execution**: T006 updates `seed_data_sources.sql` but the seed file must be executed manually on-cluster (it's not in the migrations directory and is not auto-applied by db-init-job.yaml). T033 now includes this step.
- **PR validation flow (T037-T040)**: The PR targets the `staging` branch (not `main`). Merge triggers: GHA `build-push.yaml` → Docker image to GHCR → staging kustomization.yaml updated → ArgoCD auto-syncs. Post-merge manual steps: apply migrations (T033), apply seed data (T033), run smoke tests (T039). ArgoCD staging app watches `targetRevision: staging` at `path: k8s/overlays/staging`. No dk-alchemy or dk-data backend changes are needed. Doppler secrets are a soft dependency — CronJobs deploy but fetchers skip without keys (optional: true).
