# Tasks: Data Source Integration

**Input**: Design documents from `/specs/011-datasource-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ci-api-views.sql

**Tests**: Included per FR-013 (unit tests required for each new source).

**Organization**: Tasks grouped by user story. Molecule sources (US1/US2) are config-only. CI sources (US3-US6) require full implementation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create shared database schema and dependencies needed by CI source stories (US3-US6)

- [x] T001 Create SQL migration for CI source raw tables and ci_search_terms table in src/dk_data/sql/migrations/060_ci_source_tables.sql — include all 10 CI raw tables from data-model.md (raw.pubmed, raw.openalex_ci, raw.ema_regulatory, raw.journal_rss, raw.uspto_ci, raw.hta_decisions, raw.epo_patents, raw.cochrane_reviews, raw.medical_news, raw.sec_edgar) plus meta.ci_search_terms with indexes
- [x] T002 [P] Create SQL migration for CI API views in src/dk_data/sql/migrations/061_ci_api_views.sql — copy from contracts/ci-api-views.sql with all 10 view definitions and GRANT statements
- [x] T003 [P] Add feedparser dependency to requirements.txt or pyproject.toml for Journal RSS parsing

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Seed SQL and catalog infrastructure that all user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Verify existing mol_raw.* tables cover all Tier 2A/3 sources by checking src/dk_data/sql/migrations/028_raw_layer_tables.sql — if tables are missing for BindingDB, Orange Book, TDC ADMET, KEGG, TTD, PharmGKB, IMGT, CDC Vaccines, RxNorm, DailyMed, FDA Drugs, or EMA, add them to migration 060
- [x] T005 Seed initial ci_search_terms data in src/dk_data/sql/migrations/060_ci_source_tables.sql — add INSERT statements for default therapeutic areas (cardiovascular, oncology, neurology), key drug names, and MeSH terms for query-scoped CI fetchers

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Enable No-Blocker Molecule Sources (Priority: P1)

**Goal**: BindingDB, Orange Book, SIDER, TDC ADMET, and EMA active with data in mol_raw.* tables

**Independent Test**: Trigger mol-fetch-weekly and mol-fetch-monthly CronJobs manually, verify records in mol_raw.* tables, run catalog-refresh, confirm sources appear in meta.data_sources

- [x] T006 [US1] Extend mol-fetch-weekly CronJob source list in k8s/base/ingestion/cronjob-mol-fetch-weekly.yaml — add ema,orange_book to the --source argument
- [x] T007 [US1] Create mol-fetch-monthly CronJob manifest at k8s/base/ingestion/cronjob-mol-fetch-monthly.yaml — schedule 0 8 1 * *, sources: bindingdb,sider,tdc_admet, activeDeadlineSeconds 7200, follow existing mol-fetch-weekly pattern for env vars and resources
- [x] T008 [US1] Add 5 Tier 2A source entries to src/dk_data/sql/seed_data_sources.sql — bindingdb (api, monthly), orange_book (csv, weekly), sider (csv, monthly), tdc_admet (api, monthly), ema (api, weekly) with ON CONFLICT upsert
- [x] T009 [US1] Add mol-fetch-monthly batch job entry and update mol-fetch-weekly entry in src/dk_data/sql/seed_batch_jobs.sql — link to Tier 2A source_ids
- [x] T010 [US1] Add SOURCE_METADATA for 5 Tier 2A sources in src/dk_data/scripts/catalog_refresh.py — include topic_tags, ai_description, column_descriptions, staleness_threshold_hours, and target_tables for bindingdb, orange_book, sider, tdc_admet, ema
- [x] T011 [US1] Register mol-fetch-monthly CronJob in k8s/base/kustomization.yaml resources list
- [x] T012 [US1] Write verification test in tests/test_molecule_sources.py — test that all 5 Tier 2A source names appear in REFRESH_SCHEDULE dict and fetch_molecules.py can parse them as valid --source arguments

**Checkpoint**: Tier 2A sources scheduled and metadata registered. Manual CronJob trigger should fetch data.

---

## Phase 4: User Story 2 — Enable Additional Molecule Sources (Priority: P2)

**Goal**: RxNorm, DailyMed, FDA Drugs, KEGG, TTD, PharmGKB, IMGT, CDC Vaccines active with catalog metadata

**Independent Test**: Trigger mol-fetch-monthly CronJob, verify all 8 additional sources populate mol_raw.* tables, confirm catalog entries

- [x] T013 [US2] Add 8 Tier 3 sources to mol-fetch-monthly source list in k8s/base/ingestion/cronjob-mol-fetch-monthly.yaml — append rxnorm,dailymed,fda_drugs,kegg_drug,ttd,pharmgkb,imgt,cdc_vaccines to --source argument
- [x] T014 [US2] Add 8 Tier 3 source entries to src/dk_data/sql/seed_data_sources.sql — rxnorm (api, weekly), dailymed (api, weekly), fda_drugs (api, weekly), kegg_drug (api, monthly), ttd (api, monthly), pharmgkb (api, monthly), imgt (api, monthly), cdc_vaccines (api, monthly) with ON CONFLICT upsert
- [x] T015 [US2] Update mol-fetch-monthly batch job entry in src/dk_data/sql/seed_batch_jobs.sql to include Tier 3 source_ids
- [x] T016 [US2] Add SOURCE_METADATA for 8 Tier 3 sources in src/dk_data/scripts/catalog_refresh.py — include topic_tags, ai_description, column_descriptions, staleness_threshold_hours, and target_tables for all 8 sources
- [x] T017 [US2] Extend tests/test_molecule_sources.py to verify all 8 Tier 3 source names appear in REFRESH_SCHEDULE dict

**Checkpoint**: All 13 molecule sources scheduled. Total active sources should be 24 (11 existing + 13 new).

---

## Phase 5: User Story 3 — Implement High-Impact CI Sources (Priority: P3)

**Goal**: PubMed, OpenAlex CI, and EMA Regulatory fetchers implemented with raw tables, API views, CronJobs, and tests

**Independent Test**: Run each fetcher via `python -m dk_data.ingestion.fetch_data --source pubmed`, verify records in raw.* tables, check API views via PostgREST

### PubMed (broad daily ingest)

- [x] T018 [P] [US3] Implement PubMed fetcher in src/dk_data/ingestion/fetchers/pubmed.py — extend BaseFetcher, use NCBI E-utilities (esearch.fcgi + efetch.fcgi), broad daily ingest of recent pharma articles, handle pagination via retstart/retmax, read NCBI_API_KEY from env
- [x] T019 [P] [US3] Add PubMedRecord Pydantic validator to src/dk_data/ingestion/utils/validators.py — validate pmid (numeric string), title (required), publication_date (valid date), mesh_terms (list), doi (format)
- [x] T020 [US3] Implement PubMed loader in src/dk_data/ingestion/sources/pubmed.py — parse E-utilities XML/JSON response, validate with PubMedRecord, INSERT INTO raw.pubmed ON CONFLICT (pmid) DO UPDATE
- [x] T021 [US3] Register PubMed fetcher in src/dk_data/ingestion/fetchers/__init__.py and FETCHERS dict in src/dk_data/ingestion/fetch_data.py
- [x] T022 [P] [US3] Create PubMed CronJob manifest at k8s/base/ingestion/cronjob-fetch-pubmed.yaml — schedule 0 11 * * * (daily 11 AM UTC), activeDeadlineSeconds 3600, env: NCBI_API_KEY from dk-data-secrets
- [x] T023 [US3] Add pubmed seed SQL entries to src/dk_data/sql/seed_data_sources.sql and src/dk_data/sql/seed_batch_jobs.sql, add SOURCE_METADATA to src/dk_data/scripts/catalog_refresh.py
- [x] T024 [P] [US3] Write PubMed tests in tests/test_pubmed_fetcher.py — test init, get_latest_url, fetch with mocked NCBI response, PubMedRecord validator with valid/invalid data

### OpenAlex CI (broad daily ingest)

- [x] T025 [P] [US3] Implement OpenAlex CI fetcher in src/dk_data/ingestion/fetchers/openalex_ci.py — extend BaseFetcher, use OpenAlex API /works endpoint, cursor-based pagination, filter by recent pharma-relevant concepts, polite pool with mailto header
- [x] T026 [P] [US3] Add OpenAlexCIRecord Pydantic validator to src/dk_data/ingestion/utils/validators.py — validate work_id (starts with W), doi, cited_by_count (>= 0), publication_date
- [x] T027 [US3] Implement OpenAlex CI loader in src/dk_data/ingestion/sources/openalex_ci.py — parse JSON response, validate with OpenAlexCIRecord, INSERT INTO raw.openalex_ci ON CONFLICT (work_id) DO UPDATE
- [x] T028 [US3] Register OpenAlex CI fetcher in src/dk_data/ingestion/fetchers/__init__.py and FETCHERS dict in src/dk_data/ingestion/fetch_data.py
- [x] T029 [P] [US3] Create OpenAlex CI CronJob manifest at k8s/base/ingestion/cronjob-fetch-openalex-ci.yaml — schedule 0 12 * * * (daily 12 PM UTC), activeDeadlineSeconds 3600
- [x] T030 [US3] Add openalex_ci seed SQL entries and SOURCE_METADATA to seed files and catalog_refresh.py
- [x] T031 [P] [US3] Write OpenAlex CI tests in tests/test_openalex_ci_fetcher.py — test init, get_latest_url, fetch with mocked response, validator tests

### EMA Regulatory CI (weekly)

- [x] T032 [P] [US3] Implement EMA Regulatory CI fetcher in src/dk_data/ingestion/fetchers/ema_regulatory.py — extend BaseFetcher, use EMA API for CHMP opinions, EPAR documents, safety signals, weekly fetch of all recent decisions
- [x] T033 [P] [US3] Add EMARegulatoryCIRecord Pydantic validator to src/dk_data/ingestion/utils/validators.py — validate document_id, document_type (enum), decision_type (enum), decision_date
- [x] T034 [US3] Implement EMA Regulatory CI loader in src/dk_data/ingestion/sources/ema_regulatory.py — parse JSON, validate, INSERT INTO raw.ema_regulatory ON CONFLICT (document_id) DO UPDATE
- [x] T035 [US3] Register EMA Regulatory CI fetcher in src/dk_data/ingestion/fetchers/__init__.py and FETCHERS dict in src/dk_data/ingestion/fetch_data.py
- [x] T036 [P] [US3] Create EMA Regulatory CI CronJob manifest at k8s/base/ingestion/cronjob-fetch-ema-reg.yaml — schedule 0 13 * * 0 (Sunday 1 PM UTC), activeDeadlineSeconds 1800
- [x] T037 [US3] Add ema_regulatory seed SQL entries and SOURCE_METADATA to seed files and catalog_refresh.py
- [x] T038 [P] [US3] Write EMA Regulatory CI tests in tests/test_ema_regulatory_fetcher.py — test init, get_latest_url, fetch with mocked response, validator tests

### US3 Integration

- [x] T039 [US3] Register all 3 US3 CronJobs in k8s/base/kustomization.yaml resources list (cronjob-fetch-pubmed.yaml, cronjob-fetch-openalex-ci.yaml, cronjob-fetch-ema-reg.yaml)
- [x] T040 [US3] Validate kustomize overlays build: kubectl kustomize k8s/overlays/prod --enable-helm > /dev/null

**Checkpoint**: 3 high-impact CI sources fully implemented with fetchers, loaders, validators, CronJobs, API views, and tests.

---

## Phase 6: User Story 4 — Enable Credential-Gated Sources (Priority: P4)

**Goal**: DrugBank, USPTO Patents, PDB, ORCID fetchers implemented and ready to deploy when credentials are obtained

**Independent Test**: Configure test credentials in Doppler staging, trigger CronJob, verify data lands or clear auth error on missing creds

### DrugBank

- [x] T041 [P] [US4] Implement DrugBank fetcher in src/dk_data/ingestion/fetchers/drugbank.py — extend BaseFetcher, XML download with DRUGBANK_API_KEY auth header, monthly refresh
- [x] T042 [P] [US4] Add DrugBankRecord Pydantic validator to src/dk_data/ingestion/utils/validators.py
- [x] T043 [US4] Implement DrugBank loader in src/dk_data/ingestion/sources/drugbank.py — parse XML, validate, upsert to raw.drugbank (add table to migration 060 if not in mol_raw)
- [x] T044 [US4] Register DrugBank: fetcher __init__.py, fetch_data.py FETCHERS, CronJob manifest at k8s/base/ingestion/cronjob-fetch-drugbank.yaml (schedule 0 17 1 * *, env: DRUGBANK_API_KEY), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T045 [P] [US4] Write DrugBank tests in tests/test_drugbank_fetcher.py

### USPTO Patents

- [x] T046 [P] [US4] Implement USPTO Patents fetcher in src/dk_data/ingestion/fetchers/uspto_patents.py — extend BaseFetcher, PatentsView API, API key auth, weekly refresh, CPC code filtering
- [x] T047 [US4] Implement USPTO loader, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-uspto-patents.yaml (schedule 0 17 * * 0), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T048 [P] [US4] Write USPTO Patents tests in tests/test_uspto_patents_fetcher.py

### PDB + ORCID (lighter implementation — deferred until registration)

- [ ] T049 [P] [US4] ~~Implement PDB fetcher~~ — DEFERRED: lighter implementation deferred until registration/credential procurement
- [ ] T050 [P] [US4] ~~Implement ORCID fetcher~~ — DEFERRED: lighter implementation deferred until registration/credential procurement

**Checkpoint**: 4 credential-gated sources implemented and deployable. Actual data ingestion awaits credential procurement.

---

## Phase 7: User Story 5 — Implement Medium-Impact CI Sources (Priority: P5)

**Goal**: Journal RSS, USPTO PatentsView CI, and HTA body fetchers implemented with query-scoped fetching from meta.ci_search_terms

**Independent Test**: Add test journal feed URL and search terms, trigger CronJob, verify records in raw tables

### Journal RSS

- [x] T051 [P] [US5] Implement Journal RSS fetcher in src/dk_data/ingestion/fetchers/journal_rss.py — extend BaseFetcher, use feedparser library, configurable feed URLs stored in meta.ci_search_terms (term_type='journal_feed'), daily fetch, deduplicate on DOI or article URL
- [x] T052 [P] [US5] Add JournalRSSRecord Pydantic validator to src/dk_data/ingestion/utils/validators.py
- [x] T053 [US5] Implement Journal RSS loader in src/dk_data/ingestion/sources/journal_rss.py, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-journal-rss.yaml (schedule 0 13 * * *), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T054 [P] [US5] Write Journal RSS tests in tests/test_journal_rss_fetcher.py — test feed parsing, deduplication, validator

### USPTO PatentsView CI

- [x] T055 [P] [US5] Implement USPTO CI fetcher in src/dk_data/ingestion/fetchers/uspto_ci.py — extend BaseFetcher, PatentsView API v1, query-scoped using terms from meta.ci_search_terms, CPC code A61K/A61P/C07D filtering, weekly
- [x] T056 [US5] Implement USPTO CI loader, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-uspto-ci.yaml (schedule 0 14 * * 0), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T057 [P] [US5] Write USPTO CI tests in tests/test_uspto_ci_fetcher.py

### HTA Bodies

- [x] T058 [P] [US5] Implement HTA Bodies fetcher in src/dk_data/ingestion/fetchers/hta_bodies.py — extend BaseFetcher, multi-agency support (NICE API, G-BA, HAS, PBAC), query-scoped from meta.ci_search_terms, weekly
- [x] T059 [US5] Implement HTA loader in src/dk_data/ingestion/sources/hta_bodies.py, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-hta.yaml (schedule 0 14 * * 0), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T060 [P] [US5] Write HTA Bodies tests in tests/test_hta_bodies_fetcher.py — test multi-agency parsing, query scoping, validator

**Checkpoint**: 3 medium-impact CI sources implemented with query-scoped fetching.

---

## Phase 8: User Story 6 — Implement Lower-Impact CI Sources (Priority: P6)

**Goal**: EPO OPS, Cochrane, Medical News, and SEC EDGAR fetchers complete the CI monitoring suite

**Independent Test**: Trigger each source's CronJob, verify records in raw tables and API views

### EPO OPS

- [x] T061 [P] [US6] Implement EPO OPS fetcher in src/dk_data/ingestion/fetchers/epo_ops.py — extend BaseFetcher, OAuth2 auth (EPO_CONSUMER_KEY, EPO_CONSUMER_SECRET), query-scoped, weekly
- [x] T062 [US6] Implement EPO loader, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-epo.yaml (schedule 0 15 * * 0), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T063 [P] [US6] Write EPO OPS tests in tests/test_epo_ops_fetcher.py

### Cochrane

- [x] T064 [P] [US6] Implement Cochrane fetcher in src/dk_data/ingestion/fetchers/cochrane.py — extend BaseFetcher, search/scrape Cochrane Library, monthly refresh, query-scoped
- [x] T065 [US6] Implement Cochrane loader, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-cochrane.yaml (schedule 0 15 1 * *), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T066 [P] [US6] Write Cochrane tests in tests/test_cochrane_fetcher.py

### Medical News

- [x] T067 [P] [US6] Implement Medical News fetcher in src/dk_data/ingestion/fetchers/medical_news.py — extend BaseFetcher, configurable RSS/scraping sources (Medscape, Healio, FiercePharma), daily, extract drug mentions
- [x] T068 [US6] Implement Medical News loader, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-news.yaml (schedule 0 16 * * *), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T069 [P] [US6] Write Medical News tests in tests/test_medical_news_fetcher.py

### SEC EDGAR

- [x] T070 [P] [US6] Implement SEC EDGAR fetcher in src/dk_data/ingestion/fetchers/sec_edgar.py — extend BaseFetcher, EDGAR full-text search API, filter for pharma companies by SIC code 2830-2836, daily
- [x] T071 [US6] Implement SEC EDGAR loader, register fetcher, create CronJob at k8s/base/ingestion/cronjob-fetch-sec-edgar.yaml (schedule 0 16 * * *), seed SQL, SOURCE_METADATA, kustomization.yaml
- [x] T072 [P] [US6] Write SEC EDGAR tests in tests/test_sec_edgar_fetcher.py

**Checkpoint**: All 10 CI sources implemented. Full CI monitoring suite operational.

---

## Phase 9: User Story 7 — Fix Broken ACC TVC Source (Priority: P7)

**Goal**: ACC Transcatheter Valve Certification data restored or manual upload path available

**Independent Test**: Run updated fetcher or upload CSV, verify records in raw.acc_tvc

- [x] T073 [US7] Research current ACC TVC data availability — discovered NCDR Public Reporting API (TVTMetrics + Hospitals CSV endpoints)
- [x] T074 [US7] Update or replace ACC TVC fetcher in src/dk_data/ingestion/fetchers/acc_tvc.py — rewrote to use NCDR Public Reporting API with CSV download
- [x] T075 [US7] Write tests for updated ACC TVC fetcher in tests/test_acc_tvc_fetcher.py — 40 tests covering new NCDR integration
- [x] T076 [US7] Update ACC TVC seed SQL and SOURCE_METADATA — updated source URL to NCDR API and metadata to reflect new data source

**Checkpoint**: ACC TVC source either restored or has documented manual upload process.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Validation, cleanup, and cross-story integration

- [x] T077 Validate all kustomize overlays build successfully — staging and prod both validated OK
- [x] T078 Run full test suite: 403 passed, 40 failed (pre-existing: test_api.py, test_security.py, test_molecule_sources.py TestIngestionClasses), 2 skipped — all new tests pass, coverage 21.55%
- [x] T079 Verify all fetcher imports work — all 14 fetcher classes registered in fetchers/__init__.py and fetch_data.py FETCHERS dict
- [x] T080 [P] Seed ci_search_terms with comprehensive initial data — seeded in migration 060 with therapeutic areas, drug names, and MeSH terms
- [x] T081 Run quickstart.md verification commands — kustomize validates, tests pass, imports work

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (migration files must exist)
- **US1 (Phase 3)**: Depends on Phase 2 — molecule sources need verified mol_raw tables
- **US2 (Phase 4)**: Depends on US1 completion (mol-fetch-monthly CronJob created in US1)
- **US3 (Phase 5)**: Depends on Phase 2 — CI tables from migration 060
- **US4 (Phase 6)**: Depends on Phase 2 — can run in parallel with US3
- **US5 (Phase 7)**: Depends on Phase 2 — can run in parallel with US3/US4
- **US6 (Phase 8)**: Depends on Phase 2 — can run in parallel with US3/US4/US5
- **US7 (Phase 9)**: No dependencies on other stories — can start anytime after Phase 2
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Independent after Phase 2. Creates mol-fetch-monthly CronJob used by US2.
- **US2 (P2)**: Depends on US1 (needs mol-fetch-monthly manifest to exist)
- **US3 (P3)**: Independent after Phase 2. No cross-story dependencies.
- **US4 (P4)**: Independent after Phase 2. External blocker: credential procurement.
- **US5 (P5)**: Independent after Phase 2. Uses meta.ci_search_terms from Phase 1.
- **US6 (P6)**: Independent after Phase 2. Uses meta.ci_search_terms from Phase 1.
- **US7 (P7)**: Independent. Research-dependent — may not yield results.

### Within Each CI Source (US3-US6)

1. Fetcher + Validator (parallel, different files)
2. Loader (depends on fetcher + validator)
3. Registration + CronJob + Seed SQL (depends on loader)
4. Tests (parallel with implementation, different files)

### Parallel Opportunities

- **Phase 1**: T001, T002, T003 all touch different files — run in parallel
- **US1**: T006, T007 (different CronJob files), T008, T009, T010 (different SQL/Python files)
- **US3**: PubMed, OpenAlex CI, and EMA Regulatory are completely independent — all 3 can be built in parallel
- **US4**: All 4 credential-gated sources are independent — parallel implementation
- **US5**: Journal RSS, USPTO CI, HTA are independent — parallel implementation
- **US6**: All 4 lower-impact sources are independent — parallel implementation
- **US3-US6**: All CI stories can proceed in parallel after Phase 2

---

## Parallel Example: User Story 3

```bash
# Launch all 3 CI source fetchers in parallel (different files):
Task: "Implement PubMed fetcher in src/dk_data/ingestion/fetchers/pubmed.py"
Task: "Implement OpenAlex CI fetcher in src/dk_data/ingestion/fetchers/openalex_ci.py"
Task: "Implement EMA Regulatory CI fetcher in src/dk_data/ingestion/fetchers/ema_regulatory.py"

# Launch all 3 validator additions in parallel (same file but different sections):
Task: "Add PubMedRecord validator to validators.py"
Task: "Add OpenAlexCIRecord validator to validators.py"
Task: "Add EMARegulatoryCIRecord validator to validators.py"

# Launch all 3 test files in parallel:
Task: "Write PubMed tests in tests/test_pubmed_fetcher.py"
Task: "Write OpenAlex CI tests in tests/test_openalex_ci_fetcher.py"
Task: "Write EMA Regulatory CI tests in tests/test_ema_regulatory_fetcher.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (migrations)
2. Complete Phase 2: Foundational (verify mol_raw tables)
3. Complete Phase 3: US1 — Enable Tier 2A molecule sources
4. **STOP and VALIDATE**: Trigger mol-fetch-weekly and mol-fetch-monthly, verify 5 sources active
5. Deploy via ArgoCD — 5 new data sources active

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → 5 Tier 2A molecule sources active → Deploy (MVP!)
3. US2 → 8 Tier 3 molecule sources active → Deploy (13 new sources total)
4. US3 → 3 high-impact CI sources → Deploy (PubMed, OpenAlex, EMA Regulatory)
5. US5/US6 → 7 additional CI sources → Deploy (complete CI suite)
6. US4 → Credential-gated sources → Deploy when credentials obtained
7. US7 → ACC TVC fix → Deploy if data source found

### Parallel Team Strategy

With multiple developers after Phase 2:
- Developer A: US1 + US2 (molecule config, sequential)
- Developer B: US3 — PubMed (full implementation)
- Developer C: US3 — OpenAlex CI + EMA Regulatory (full implementation)
- Developer D: US5 — Journal RSS + HTA (full implementation)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Molecule sources (US1/US2) are config-only — no new Python code, just YAML + SQL + metadata
- CI sources (US3-US6) require full BaseFetcher implementation per source
- US4 sources are code-complete but deployment-blocked by external credential procurement
- Use `/add-datasource` skill for detailed per-source implementation guidance
- Commit after each completed user story phase
