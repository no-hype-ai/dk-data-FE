# Task Breakdown — Silver Medallion Rebuild

**Branch**: `feature/001-silver-medallion-rebuild`
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)

## Task Format

`- [ ] [ID] [P?] [Story?] Description — \`file/path.ext\``

- `[P]` parallelizable (different files, no dependencies on incomplete tasks)
- `[USn]` user story phase membership (US1–US5)

## Phase 1 — Setup

- [ ] T001 Add `meta` schema migration scaffold and the connection-string helper module — `src/dk_data/sql/migrations/031_silver_hub_rebuild/`, `src/dk_data/ingestion/utils/database.py`
- [ ] T002 [P] Create `tests/conftest.py` fixtures for a real CNPG postgres test database (no DB mocks) — `tests/conftest.py`
- [ ] T003 [P] Add CI grep job for `psycopg2.connect(` outside `database.py` (FR-030, `[DSN]` tag). **Verifies SC-015**: 100% of dk-data Python entry points obtain their DSN from `dk_data.ingestion.utils.database.build_dsn()` — any direct `psycopg2.connect(` call outside `database.py` is a CI failure. — `.github/workflows/ci.yaml`
- [ ] T004 [P] Add CI grep job for the 5 silver antipattern signatures FR-015 / FR-016 / FR-017 / FR-018 / FR-019 (FR-020 is the CI gate, `[SVANT]` tag enforces) — `.github/workflows/ci.yaml`, `tests/test_silver_antipatterns.py`
- [ ] T005 [P] Add `Makefile` targets for hub bootstrap (`make sqlmesh-bootstrap-silver-hubs`) and contract tests — `Makefile`

## Phase 2 — Foundational

*Blocking prerequisites for every user story. Schema for the meta tables, the column-retention contract test, and the connection helper.*

- [ ] T010 [US3] Implement `dk_data.ingestion.utils.database.build_dsn()` enforcing FR-022 / FR-023 / FR-030 / FR-021c (5-min statement timeout for fetchers, 10-min for SQLMesh) / FR-021d (5-min idle in transaction) — `src/dk_data/ingestion/utils/database.py`
- [ ] T011 [US3] Unit test `build_dsn()` — verify `statement_timeout`, keepalives, `application_name` are set; verify it throws on missing required env — `tests/test_build_dsn.py`
- [ ] T012 [US3] Migration: create `meta.job_locks` per FR-025 — `src/dk_data/sql/migrations/031_silver_hub_rebuild/001_meta_job_locks.sql`
- [ ] T013 [US3] Migration: create `meta.refresh_state` per FR-026 — `src/dk_data/sql/migrations/031_silver_hub_rebuild/002_meta_refresh_state.sql`
- [ ] T014 [US3] Migration: create `meta.linkage_conflicts` per FR-026a — `src/dk_data/sql/migrations/031_silver_hub_rebuild/003_meta_linkage_conflicts.sql`
- [ ] T015 [US3] Migration: create `meta.transform_runs` for WAL accounting per research Topic 5 — `src/dk_data/sql/migrations/031_silver_hub_rebuild/003a_meta_transform_runs.sql`
- [ ] T016 [P] [US3] Concurrency test for `meta.job_locks` (acquire / release / TTL expiration / contention) — `tests/test_meta_job_locks.py`
- [ ] T017 [US1] Implement the column-retention contract test using SQLMesh DAG introspection per FR-005 — `tests/test_silver_column_retention.py`
- [ ] T018 [P] [US1] Wire `system_columns` constant from FR-001 into the contract test — `tests/test_silver_column_retention.py`

## Phase 3 — US-1: Silver carries forward every bronze column (P1)

*The contract test from Phase 2 will start failing immediately on every silver model that drops bronze columns. This phase fixes them.*

- [ ] T020 [US1] Run contract test against current main; capture the failing-model report and write it to the PR description — `(no file — output capture only)`
- [ ] T021 [P] [US1] Fix `mol_silver` model column drops (FR-001 carry-forward + FR-002 source-prefix on collisions + FR-003 JSONB preservation + FR-004 detail-level columns in aggregation models) — `src/dk_data/sqlmesh/models/molecules/silver/*.sql`
- [ ] T022 [P] [US1] Fix `hcs_silver` model column drops (FR-001 / FR-002 / FR-003 / FR-004) — `src/dk_data/sqlmesh/models/hcs/silver/*.sql`
- [ ] T023 [P] [US1] Fix `ind_silver` AND `ip_silver` AND `hcp_silver` model column drops (FR-001 / FR-002 / FR-003 / FR-004) — `src/dk_data/sqlmesh/models/{ind,ip,hcp}/silver/*.sql`
- [ ] T024 [US1] Run contract test against the fixed branch; verify zero failing models (FR-005 / SC-001) — `tests/test_silver_column_retention.py`
- [ ] T025 [P] [US1] Document JSONB carry-forward (FR-003) and column-name disambiguation (FR-002) in the silver-models README — `src/dk_data/sqlmesh/models/README.md`

## Phase 3b — Full `ip_*` domain stack creation and migration (US-2 / FR-006a–FR-006h)

*Hard prerequisite for Phase 4. Phase 4 task T040–T042 (the new IP hub schemas) land files in `src/dk_data/sqlmesh/models/ip/silver/` and reference the `ip_silver` postgres schema — neither exists today, both are created here. The `ip_silver` name currently appears only as a SQLMesh transform-layer name in `transform_molecules.py`; the actual IP models all live in `mol_*`. This phase creates the full `ip_*` medallion stack and migrates every IP-related fetcher, raw table, bronze model, silver model, gold model, and CronJob from `mol_*` to `ip_*`.*

### 3b.1 — Schema registration

- [ ] T100 [US2] Migration: `CREATE SCHEMA IF NOT EXISTS ip_raw; ip_bronze; ip_silver; ip_gold;` plus PostgREST role grants matching the existing `mol_*`/`hcs_*`/`ind_*` pattern (FR-006a) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/050_create_ip_schemas.sql`
- [ ] T101 [US2] Update `src/dk_data/sqlmesh/config.yaml` `physical_schema_mapping` to add `ip_raw`, `ip_bronze`, `ip_silver`, `ip_gold` entries; update the schema-domain comment block to add the 5th line `ip_*  — Intellectual property` (FR-006b) — `src/dk_data/sqlmesh/config.yaml`
- [ ] T101a [US2] Create the `src/dk_data/sqlmesh/models/ip/{bronze,silver,gold}/` directory tree with placeholder `__init__.py` or empty README so SQLMesh discovers the new domain — `src/dk_data/sqlmesh/models/ip/`

### 3b.2 — Fetcher migration to `ip_raw`

- [ ] T102 [P] [US2] Update `src/dk_data/ingestion/fetchers/uspto_patents.py` to write to `ip_raw.uspto_patents` instead of `mol_raw.uspto_patents` (FR-006c) — `src/dk_data/ingestion/fetchers/uspto_patents.py`
- [ ] T103 [P] [US2] Update `src/dk_data/ingestion/fetchers/uspto_ci.py` → `ip_raw.uspto_ci` — `src/dk_data/ingestion/fetchers/uspto_ci.py`
- [ ] T104 [P] [US2] Update `src/dk_data/ingestion/fetchers/uspto_trademarks.py` → `ip_raw.uspto_trademarks` — `src/dk_data/ingestion/fetchers/uspto_trademarks.py`
- [ ] T105 [P] [US2] Update `src/dk_data/ingestion/fetchers/epo_ops.py` → `ip_raw.epo_patents` — `src/dk_data/ingestion/fetchers/epo_ops.py`
- [ ] T106 [P] [US2] Update `src/dk_data/ingestion/fetchers/euipo_trademarks.py` → `ip_raw.euipo_trademarks` — `src/dk_data/ingestion/fetchers/euipo_trademarks.py`
- [ ] T107 [P] [US2] Update `src/dk_data/ingestion/fetchers/euipo_designs.py` → `ip_raw.euipo_designs` — `src/dk_data/ingestion/fetchers/euipo_designs.py`
- [ ] T107a [US2] Update `src/dk_data/sql/seed_data_sources.sql` rows for the 6 migrated IP fetchers — change `silver_schema` from `mol_silver` to `ip_silver` — `src/dk_data/sql/seed_data_sources.sql`
- [ ] T107b [US2] Note: `orange_book.py` and `purple_book.py` fetchers **stay in `mol_raw`** because Orange Book is the FDA-drug↔patent crosswalk and Purple Book is the biologic registry; both are drug-domain entities even though they reference patents. The patent linkage join (FR-034) reads `mol_bronze.orange_book` and joins to `ip_silver.patents` cross-schema. — `(no file change, documentation only)`

### 3b.3 — Bronze model migration to `ip_bronze`

- [ ] T108 [P] [US2] Move `src/dk_data/sqlmesh/models/molecules/bronze/uspto_patents.sql` → `src/dk_data/sqlmesh/models/ip/bronze/uspto_patents.sql` and update `MODEL (name mol_bronze.uspto_patents, ...)` → `MODEL (name ip_bronze.uspto_patents, ...)` (FR-006d) — file move + content edit
- [ ] T109 [P] [US2] Move `mol_bronze.uspto_ci` → `ip_bronze.uspto_ci` — `src/dk_data/sqlmesh/models/{molecules→ip}/bronze/uspto_ci.sql`
- [ ] T110a [P] [US2] Move `mol_bronze.uspto_trademarks` → `ip_bronze.uspto_trademarks` — `src/dk_data/sqlmesh/models/{molecules→ip}/bronze/uspto_trademarks.sql`
- [ ] T110b [P] [US2] Move `mol_bronze.epo_patents` → `ip_bronze.epo_patents` — `src/dk_data/sqlmesh/models/{molecules→ip}/bronze/epo_patents.sql`
- [ ] T110c [P] [US2] Move `mol_bronze.euipo_trademarks` → `ip_bronze.euipo_trademarks` — `src/dk_data/sqlmesh/models/{molecules→ip}/bronze/euipo_trademarks.sql`
- [ ] T110d [P] [US2] Move `mol_bronze.euipo_designs` → `ip_bronze.euipo_designs` — `src/dk_data/sqlmesh/models/{molecules→ip}/bronze/euipo_designs.sql`
- [ ] T110e [P] [US2] Move `mol_bronze.trademark_status_history` → `ip_bronze.trademark_status_history` — `src/dk_data/sqlmesh/models/{molecules→ip}/bronze/trademark_status_history.sql`

### 3b.4 — Legacy silver model migration to `ip_silver` (preserves data, replaced by hub-architecture in Phase 4)

- [ ] T110f [US2] Move `src/dk_data/sqlmesh/models/molecules/silver/patents.sql` → `src/dk_data/sqlmesh/models/ip/silver/patents.sql` and update `MODEL (name mol_silver.patents, ...)` → `MODEL (name ip_silver.patents, ...)` (FR-006e). This preserves the legacy patents model — to be REPLACED by the new hub-architecture `ip_silver.patents` from T040, but the migration step preserves the data via INSERT-SELECT in T110o.
- [ ] T110g [US2] Move `mol_silver.trademarks` → `ip_silver.trademarks` — `src/dk_data/sqlmesh/models/{molecules→ip}/silver/trademarks.sql`
- [ ] T110h [US2] Move `mol_silver.patent_exclusivities` → `ip_silver.patent_exclusivities` — `src/dk_data/sqlmesh/models/{molecules→ip}/silver/patent_exclusivities.sql`
- [ ] T110i [US2] Move `mol_silver.trademark_status_changes` → `ip_silver.trademark_status_changes` — `src/dk_data/sqlmesh/models/{molecules→ip}/silver/trademark_status_changes.sql`
- [ ] T110j [US2] Move `mol_silver.euipo_designs` → `ip_silver.designs` (rename for hub consistency — the new hub is `ip_silver.designs`, not `euipo_designs`) — `src/dk_data/sqlmesh/models/{molecules→ip}/silver/designs.sql`

### 3b.5 — Gold model and dependent-model updates

- [ ] T110k [US2] Update `src/dk_data/sqlmesh/models/molecules/gold/company_pipeline.sql` to read from `ip_silver.patents` and `ip_silver.trademarks` instead of `mol_silver.*` (FR-006f) — `src/dk_data/sqlmesh/models/molecules/gold/company_pipeline.sql`
- [ ] T110l [US2] Grep the entire `src/dk_data/sqlmesh/models/` tree for any other reference to `mol_silver.patents`, `mol_silver.trademarks`, `mol_silver.patent_exclusivities`, `mol_silver.trademark_status_changes`, `mol_silver.euipo_designs`, `mol_bronze.uspto_*`, `mol_bronze.epo_patents`, `mol_bronze.euipo_*`, `mol_bronze.trademark_status_history`; update each to `ip_*.*` — `src/dk_data/sqlmesh/models/**/*.sql`

### 3b.6 — Data migration (chunked PL/pgSQL — FR-006h, FR-021)

- [ ] T110m [US2] Chunked data migration `INSERT INTO ip_bronze.uspto_patents SELECT * FROM mol_bronze.uspto_patents` via PL/pgSQL procedure with ≤50K row chunks / ≤200 MB WAL per chunk + `meta.transform_runs` accounting; verify row count + 1% sample after migration; drop `mol_bronze.uspto_patents` once verified — `src/dk_data/sql/migrations/031_silver_hub_rebuild/051_migrate_uspto_patents_data.sql`
- [ ] T110n [P] [US2] Same chunked migration for the other 6 bronze tables: `uspto_ci`, `uspto_trademarks`, `epo_patents`, `euipo_trademarks`, `euipo_designs`, `trademark_status_history` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/052_migrate_ip_bronze_data.sql`
- [ ] T110o [US2] Same chunked migration for the 5 silver tables: `patents`, `trademarks`, `patent_exclusivities`, `trademark_status_changes`, `designs` (renamed from `euipo_designs`) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/053_migrate_ip_silver_data.sql`

### 3b.7 — CronJob, transform orchestrator, and observability updates

- [ ] T110p [P] [US2] Update CronJob env/args for `cronjob-fetch-uspto-patents.yaml`, `cronjob-fetch-uspto-ci.yaml`, `cronjob-fetch-uspto-trademarks.yaml`, `cronjob-fetch-epo.yaml`, `cronjob-fetch-euipo.yaml`, `cronjob-fetch-euipo-designs.yaml` to point at `ip_raw.*` (FR-006g) — `k8s/apps/cronjobs/base/cronjob-fetch-{uspto,epo,euipo}*.yaml`
- [ ] T110q [US2] Update `src/dk_data/ingestion/transform_molecules.py` `LAYERS` dict — change the model names listed under `'ip_bronze'`, `'ip_silver'`, `'ip_gold'` keys from `mol_*.*` to `ip_*.*`. Update the `_get_marker_table()` map similarly. (FR-006g) — `src/dk_data/ingestion/transform_molecules.py`
- [ ] T110r [US2] PostgREST migration: GRANT SELECT on `ip_silver.*` and `ip_gold.*` to `analyst`, `mol_data_ops`, `mol_admin` roles; REVOKE access to `mol_silver.patents` etc once data migration is verified — `src/dk_data/sql/migrations/031_silver_hub_rebuild/054_postgrest_ip_grants.sql`
- [ ] T110s [US2] Add `ip_*` schemas to the metering proxy schema list — `src/dk_data/metering_proxy/schemas.py`
- [ ] T110t [US2] Update `CLAUDE.md` schema list under "Active Technologies" to add `ip_raw, ip_bronze, ip_silver, ip_gold` — `CLAUDE.md`
- [ ] T110u [US2] End-to-end verification: trigger one IP fetcher (e.g., `cronjob-fetch-uspto-patents`), confirm row lands in `ip_raw.uspto_patents`, run the transform layer `--layer ip_bronze`, confirm row lands in `ip_bronze.uspto_patents`, run `--layer ip_silver`, confirm row lands in `ip_silver.patents` (the legacy model — to be replaced by the new hub-architecture model from T040 in Phase 4) — `(operational verification)`

## Phase 4 — US-2: Entity resolution lives in canonical hubs (P1)

*Builds the 10 hubs, their crosswalks, name indexes, and resolve functions. Tasks ordered smallest-first per the Phase 0 research decision.*

### 4.1 — Hub schemas (parallel within each hub group; FR-006 — 10 hubs across 3 schemas; FR-007 — synthetic PK + first/last seen + canonical only; FR-008 — paired crosswalk and name index per hub; FR-010 — bootstraps read existing bronze, no raw modifications)

- [ ] T030 [P] [US2] Create `mol_silver.molecules` hub schema — `src/dk_data/sqlmesh/models/molecules/silver/molecules.sql`
- [ ] T031 [P] [US2] Create `mol_silver.molecule_identifiers` crosswalk — `src/dk_data/sqlmesh/models/molecules/silver/molecule_identifiers.sql`
- [ ] T032 [P] [US2] Create `mol_silver.molecule_names` index with `display_name` per FR-008 — `src/dk_data/sqlmesh/models/molecules/silver/molecule_names.sql`
- [ ] T033 [P] [US2] Create `mol_silver.drug_products` hub at SCD/SBD level per FR-012 — `src/dk_data/sqlmesh/models/molecules/silver/drug_products.sql`
- [ ] T034 [P] [US2] Create `mol_silver.drug_product_identifiers`, `drug_product_names`, `drug_product_ingredients` — `src/dk_data/sqlmesh/models/molecules/silver/drug_product_*.sql`
- [ ] T035 [P] [US2] Create `mol_silver.targets`, `target_identifiers`, `target_names`, `target_sequences` — `src/dk_data/sqlmesh/models/molecules/silver/target*.sql`
- [ ] T036 [P] [US2] Create `ind_silver.conditions`, `condition_identifiers`, `condition_names` — `src/dk_data/sqlmesh/models/ind/silver/condition*.sql`
- [ ] T037 [P] [US2] Create `mol_silver.companies`, `company_identifiers`, `company_names` — `src/dk_data/sqlmesh/models/molecules/silver/compan*.sql`
- [ ] T038 [P] [US2] Create `hcs_silver.providers`, `provider_identifiers`, `provider_names` — `src/dk_data/sqlmesh/models/hcs/silver/provider*.sql`
- [ ] T039 [P] [US2] Create `hcs_silver.facilities`, `facility_identifiers`, `facility_names` — `src/dk_data/sqlmesh/models/hcs/silver/facilit*.sql`
- [ ] T039a [P] [US2] Create `hcp_silver.researchers`, `researcher_identifiers`, `researcher_names`, `researcher_provider_crosswalk`, `researcher_publications`, `researcher_affiliations` (FR-011b) — `src/dk_data/sqlmesh/models/hcp/silver/researcher*.sql`
- [ ] T040 [P] [US2] Create `ip_silver.patents`, `patent_identifiers`, `patent_names` — `src/dk_data/sqlmesh/models/ip/silver/patent*.sql`
- [ ] T041 [P] [US2] Create `ip_silver.trademarks`, `trademark_identifiers`, `trademark_names` — `src/dk_data/sqlmesh/models/ip/silver/trademark*.sql`
- [ ] T042 [P] [US2] Create `ip_silver.designs`, `design_identifiers`, `design_names` — `src/dk_data/sqlmesh/models/ip/silver/design*.sql`

### 4.2 — Resolve functions (parallel)

- [ ] T050 [P] [US2] `mol_silver.resolve_molecule()` per FR-009 / FR-013, full priority tree — `src/dk_data/sql/migrations/031_silver_hub_rebuild/004_resolve_molecule.sql`
- [ ] T051 [P] [US2] `mol_silver.resolve_drug_product()` 11-step priority tree per FR-013 — `src/dk_data/sql/migrations/031_silver_hub_rebuild/005_resolve_drug_product.sql`
- [ ] T052 [P] [US2] `mol_silver.resolve_target()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/006_resolve_target.sql`
- [ ] T053 [P] [US2] `ind_silver.resolve_condition()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/007_resolve_condition.sql`
- [ ] T054 [P] [US2] `mol_silver.resolve_company()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/008_resolve_company.sql`
- [ ] T055 [P] [US2] `hcs_silver.resolve_provider()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/009_resolve_provider.sql`
- [ ] T056 [P] [US2] `hcs_silver.resolve_facility()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/010_resolve_facility.sql`
- [ ] T056a [P] [US2] `hcp_silver.resolve_researcher()` (FR-011b) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/010a_resolve_researcher.sql`
- [ ] T057 [P] [US2] `ip_silver.resolve_patent()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/011_resolve_patent.sql`
- [ ] T058 [P] [US2] `ip_silver.resolve_trademark()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/012_resolve_trademark.sql`
- [ ] T059 [P] [US2] `ip_silver.resolve_design()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/013_resolve_design.sql`

### 4.3 — Resolve function unit tests (parallel)

- [ ] T060 [P] [US2] Unit test `resolve_molecule` — verify InChIKey, ChEMBL, DrugBank, PubChem, UNII, name, fuzzy ≥0.85, NULL <0.85 (FR-013a). Verify gold-layer test fixtures filter on `confidence ≥ 0.95` (FR-013b). — `tests/test_resolve_molecule.py`
- [ ] T061 [P] [US2] Unit test `resolve_drug_product` — verify NDC, RxCUI SCD/SBD, BLA, NDA, ingredients hash, brand, NULL on IN/PIN/BN RxCUI — `tests/test_resolve_drug_product.py`
- [ ] T062 [P] [US2] Unit test the other 9 resolve functions including `resolve_researcher` (target, condition, company, provider, facility, researcher, patent, trademark, design) — `tests/test_resolve_*.py`

### 4.4 — Bootstrap procedures (sequential — strict dependency tier order from plan.md Phase 0 Topic 1, then smallest-first within each tier; FR-006, FR-007, FR-010, FR-011, FR-021, FR-026, FR-028 enforced via the chunked-COMMIT template)

- [ ] T070 [US2] **Tier 0** — `hcs_silver.bootstrap_facilities()` PL/pgSQL procedure with chunked COMMITs (smallest hub, ~6K rows; validates the chunked pattern; FR-021 ≤2 GB WAL ceiling, FR-026 resumability, FR-028 `pg_sleep`) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/014_bootstrap_facilities.sql`
- [ ] T071 [US2] **Tier 0** — `mol_silver.bootstrap_companies()` (~10K rows from SEC + sponsor name fuzzy; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/015_bootstrap_companies.sql`
- [ ] T072 [US2] **Tier 0** — `ind_silver.bootstrap_conditions()` (~50K rows from ICD + MeSH + MedDRA PT; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/016_bootstrap_conditions.sql`
- [ ] T073 [US2] **Tier 0** — `mol_silver.bootstrap_targets()` (~500K rows from UniProt + ChEMBL targets; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/017_bootstrap_targets.sql`
- [ ] T074 [US2] **Tier 1** — `mol_silver.bootstrap_molecules()` (~500K rows; FR-011 supports biologics + salts + combos via `inchi_key NULL`, `sequence_hash`, `is_biologic`, `parent_molecule_id`; depends on conditions for indication crosswalks; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/018_bootstrap_molecules.sql`
- [ ] T075 [US2] **Tier 1** — `ip_silver.bootstrap_designs()` (~3M rows; depends on companies for holder; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/019_bootstrap_designs.sql`
- [ ] T076 [US2] **Tier 2** — `mol_silver.bootstrap_drug_products()` (~300K rows from RxNorm SCD/SBD + drugs@FDA + Purple Book; FR-012 SCD/SBD level only — NDC moves to crosswalk; depends on molecules for ingredient links; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/020_bootstrap_drug_products.sql`
- [ ] T077 [US2] **Tier 2** — `ip_silver.bootstrap_trademarks()` (~12M rows; depends on companies for owner; FR-021/026/028 — largest in Tier 2, validate WAL accounting carefully) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/021_bootstrap_trademarks.sql`
- [ ] T078 [US2] **Tier 3** — `ip_silver.bootstrap_patents()` (~5M rows; depends on companies + molecules via Orange Book; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/022_bootstrap_patents.sql`
- [ ] T079 [US2] **Tier 3** — `hcs_silver.bootstrap_providers()` (~10M NPPES rows — riskiest, run last; depends on facilities; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/023_bootstrap_providers.sql`
- [ ] T079a [US2] **Tier 3** — `hcp_silver.bootstrap_researchers()` (~2M PubMed-derived author signatures + ORCID/Scopus crosswalks; depends on `mol_silver.companies` for industry affiliations and on `hcs_silver.providers` for the researcher↔provider crosswalk; FR-011b, FR-036e — read PubMed `AuthorList` + `AffiliationInfo` + `Identifier[@Source='ORCID']`, OpenAlex `authorships[].author.scopus_id` + `.orcid` + `.institutions[].ror`; FR-036g — also populate `researcher_publications` and `researcher_affiliations`; FR-021/026/028) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/023a_bootstrap_researchers.sql`
- [ ] T079b [US2] **Tier 3** — `hcp_silver.bootstrap_researcher_provider_crosswalk()` populates the matched links between researchers and prescriber-providers via name+institution+state matching against NPPES practice locations; FR-011b, FR-036f. Match confidence ≥0.85 to insert; gold consumers must filter ≥0.95 (FR-013b) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/023b_bootstrap_researcher_provider_crosswalk.sql`

### 4.5 — Bootstrap end-to-end smoke tests

- [ ] T080 [US2] Run all 10 bootstraps end-to-end against staging; verify SC-002, SC-003, SC-004, SC-006, SC-007, SC-008 pass; capture `meta.transform_runs` summary — `(no file — operational verification)`
- [ ] T081 [US2] Verify FR-026a — kill any bootstrap mid-run, restart, confirm zero duplicate rows and `meta.refresh_state.last_chunk_position` resumed correctly. **Verifies SC-010**: killing any dk-data bootstrap or CronJob mid-run and restarting it produces the same final state as a single uninterrupted run, with zero duplicate rows. Test on at least 3 different bootstrap procedures (small + medium + large) to cover the full range. — `(operational verification)`

## Phase 5 — US-3: Transformations fit inside the cluster's fixed budget (P1)

*The reliability principles applied to fetchers and transform pods. Mostly file-by-file connection-string fixes.*

- [ ] T090 [P] [US3] Migrate every fetcher in `src/dk_data/ingestion/fetchers/` to call `build_dsn()` — `src/dk_data/ingestion/fetchers/*.py`
- [ ] T091 [P] [US3] Migrate every CronJob env block to set both `POSTGRES_HOST` (PgBouncer) and `POSTGRES_HOST_DIRECT` per FR-024; add concurrency labels so the 10-fetcher / 3-transform cap (FR-021e) is queryable from `pg_stat_activity`. **Verifies SC-011**: at least 90% of dk-data pod connections (excluding SQLMesh and PL/pgSQL procedure callers) terminate at PgBouncer rather than the postgres primary, measured by `pg_stat_activity.client_addr` after the migration. — `k8s/apps/cronjobs/base/*.yaml`
- [ ] T092 [P] [US3] Add HTTP range / resume support to the CMS PUF fetcher per FR-027 — `src/dk_data/ingestion/fetchers/cms_puf.py`
- [ ] T093 [P] [US3] Stagger the monthly stampede of `0 0 1 * *` CronJobs across hours per FR-029 — `k8s/apps/cronjobs/base/*.yaml`
- [ ] T094 [P] [US3] Stagger the April-15 CMS PUF refresh across April 15-21 per FR-029 — `k8s/apps/cronjobs/base/cronjob-fetch-cms-puf-*.yaml`
- [ ] T095 [P] [US3] Migrate `pg_try_advisory_lock` callers to `meta.job_locks` (FR-025, `[JOBLK]` tag) — grep `src/` and `sql/` for matches
- [ ] T096 [P] [US3] Add `pg_sleep(0.05)` between chunks in every bootstrap procedure (already done in T070–T079, this task is the audit) — `(verification of T070–T079)`
- [ ] T097 [US3] Add prometheus exporter for `meta.transform_runs` per research Topic 5; emits `dk_data_transform_chunk_wal_bytes` and `dk_data_transform_chunk_rows` per `(procedure_name, chunk_position)` (verifies FR-021 ≤2 GB WAL per chunk) — `src/dk_data/services/observability/transform_run_metrics.py`
- [ ] T098 [US3] Add a grafana dashboard panel + Mimir alert rule on `dk_data_transform_chunk_wal_bytes > 2e9` — fires on any FR-021 violation; this is the runtime gate for SC-006 (zero exceedances per week) — `k8s/apps/observability/dashboards/dk-data-transforms.json`, `k8s/apps/observability/alert-rules/dk-data-wal.yaml`

## Phase 6 — US-4: The worst silver models are rewritten (P2)

> ⚠️ **Execution gate**: Phases 5b through 5j (defined later in this file, lines ~210–298) MUST complete BEFORE this phase begins. Phase 5 in this document is split across non-contiguous sections — Phase 5 is the umbrella US-3 work, and Phases 5b–5j are sub-phases of US-3 that were appended later for organizational reasons. **Do not execute Phase 6 by reading top-to-bottom**: read all of Phase 5 (lines 167–179), then jump to Phases 5b–5j (lines 210–298), then return here. Phase 5b (tray pattern) and Phase 5c (BRIN + partitioning) are particularly important to complete first because the silver model rewrites in this phase touch the same heavy bronze tables. Phase 5i (application-side monitoring) provides the WAL accounting and slow-query log that the rewrite verification depends on.

*Priority order from the source linkage doc — biggest blast radius first.*

- [ ] T110 [US4] Rewrite `mol_silver.bioactivity` to use indexed hub joins per FR-014 (umbrella rule: every silver model obtains entity IDs by indexed equi-join to a hub crosswalk or by calling a resolve function); replaces S3 correlated-subquery antipattern — `src/dk_data/sqlmesh/models/molecules/silver/bioactivity.sql`
- [ ] T111 [US4] Rewrite `mol_silver.adverse_events` with FAERS structured-field linking (FR-031, FR-036) — `src/dk_data/sqlmesh/models/molecules/silver/adverse_events.sql`
- [ ] T112 [US4] Rewrite `mol_silver.molecule_publications` to use `MeshHeadingList` / `ChemicalList` joins per FR-033 — `src/dk_data/sqlmesh/models/molecules/silver/molecule_publications.sql`
- [ ] T113 [US4] Rewrite `mol_silver.pubmed_articles` similarly — `src/dk_data/sqlmesh/models/molecules/silver/pubmed_articles.sql`
- [ ] T114 [US4] Rewrite `mol_silver.hcpcs_molecule_bridge` — `src/dk_data/sqlmesh/models/molecules/silver/hcpcs_molecule_bridge.sql`
- [ ] T115 [US4] Rewrite `mol_silver.clinical_trials` with `derivedSection.*MeshList` joins per FR-032 — `src/dk_data/sqlmesh/models/molecules/silver/clinical_trials.sql`
- [ ] T116 [US4] Rewrite `hcs_silver.drug_utilization` — `src/dk_data/sqlmesh/models/hcs/silver/drug_utilization.sql`
- [ ] T117 [US4] Rewrite `ip_silver.patents` with Orange Book join per FR-034 — `src/dk_data/sqlmesh/models/ip/silver/patents.sql`
- [ ] T118 [US4] Sample comparison + row-count delta verification for each rewritten model (≤1% delta or documented explanation). **Verifies SC-005**: every one of the 10 worst silver models completes in <10 min on full production data after rewrite — record runtime + WAL produced for each rewritten model in the PR description. — `(operational verification, recorded in PR description)`
- [ ] T119 [US4] Delete `mol_silver.molecule_aliases` per FR-037 (verified empty in cluster pre-merge; consumer-repo grep clean). **Verifies SC-014 (part 1 of 2)**: `mol_silver.molecule_aliases` removed from the SQLMesh project in the same PR as the molecule hub bootstrap. — `src/dk_data/sqlmesh/models/molecules/silver/molecule_aliases.sql` (deleted)
- [ ] T120 [US4] Delete `mol_silver.identifier_mappings` per FR-037. **Verifies SC-014 (part 2 of 2)**: `mol_silver.identifier_mappings` removed in the same PR; both tables verified empty in the cluster pre-merge; consumer-repo grep across `dk-data-FE`, `dk-flux`, `behavior-labs-web`, `xenon-repo`, `dk-alchemy` complete with zero unresolved hits. — `src/dk_data/sqlmesh/models/molecules/silver/identifier_mappings.sql` (deleted)
- [ ] T121 [US4] Run `[SVANT]` antipattern grep on the rewritten silver tree; assert zero matches of FR-015 / FR-016 / FR-017 / FR-018 / FR-019 per SC-012 — `tests/test_silver_antipatterns.py`

## Phase 7 — US-5: Free-text source linking via structured sibling fields (P3)

*All work is structured-field reads — no LLM, no extraction CronJob.*

- [ ] T130 [P] [US5] Wire FAERS `openfda.*` arrays + `reactionmeddrapt` into `mol_silver.adverse_events` (overlaps T111 — completes the FR-031 / FR-036 linkage) — `src/dk_data/sqlmesh/models/molecules/silver/adverse_events.sql`
- [ ] T131 [P] [US5] Wire ClinicalTrials.gov `derivedSection.*MeshList` per FR-032 (overlaps T115) — `src/dk_data/sqlmesh/models/molecules/silver/clinical_trials.sql`
- [ ] T132 [P] [US5] Wire PubMed / EuropePMC `MeshHeadingList` + `ChemicalList` + cross-reference regexes per FR-033; also extract `AuthorList` + `AffiliationInfo` + `Identifier[@Source='ORCID']` to populate `hcp_silver.researcher_publications` per FR-036e/g (overlaps T112, T113, T079a) — `src/dk_data/sqlmesh/models/molecules/silver/{pubmed_articles,molecule_publications}.sql`
- [ ] T133 [P] [US5] Wire openFDA labels / DailyMed `openfda.*` arrays for drug + product ID — `src/dk_data/sqlmesh/models/molecules/silver/openfda_labels.sql`
- [ ] T134 [P] [US5] Wire patent → drug linkage via Orange Book join per FR-034 (overlaps T117) — `src/dk_data/sqlmesh/models/ip/silver/patents.sql`
- [ ] T135 [P] [US5] Implement WHO INN regex compilation at startup + apply to medical_news + journal_rss enrichment models per FR-035 — `src/dk_data/sqlmesh/models/molecules/silver/medical_news.sql`, `journal_rss.sql`, plus a Python helper to build the regex from `mol_bronze.who_inn`
- [ ] T136 [US5] Verify SC-013 — FAERS adverse_events ≥70% non-null `molecule_id` and ≥85% non-null `condition_id` after the rewritten model runs on full backlog — `(operational verification)`

## Phase 5b — Tray pattern (UNLOGGED staging) for the 5 heaviest bronze tables (US-3 / FR-037a/b)

*Reliability doc §4. Converts ~100 GB single-transaction WAL to ~5 GB total WAL for bulk bronze rebuilds. Invoked via dedicated CronJobs through `POSTGRES_HOST_DIRECT`, NOT through the daily SQLMesh CronJob.*

- [ ] T150 [P] [US3] Implement `mol_bronze.refresh_chembl_activities_via_tray()` PL/pgSQL procedure (UNLOGGED staging → chunked load → `SET LOGGED` → atomic swap, includes drop-recreate of non-essential indexes per FR-039) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/030_tray_chembl_activities.sql`
- [ ] T151 [P] [US3] Implement `mol_bronze.refresh_bindingdb_via_tray()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/031_tray_bindingdb.sql`
- [ ] T152 [P] [US3] Implement `mol_bronze.refresh_clinicaltrials_via_tray()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/032_tray_clinicaltrials.sql`
- [ ] T153 [P] [US3] Implement `mol_bronze.refresh_pubchem_via_tray()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/033_tray_pubchem.sql`
- [ ] T154 [P] [US3] Implement `mol_bronze.refresh_chembl_molecules_via_tray()` — `src/dk_data/sql/migrations/031_silver_hub_rebuild/034_tray_chembl_molecules.sql`
- [ ] T155 [P] [US3] Add 5 dedicated CronJobs that invoke each tray procedure via `psql` against `POSTGRES_HOST_DIRECT` (FR-037b) — `k8s/apps/cronjobs/base/cronjob-tray-*.yaml`
- [ ] T156 [US3] Verify each tray procedure produces ≤5 GB total WAL (FR-021a) on staging before merging to main — capture `meta.wal_usage` row for each — `(operational verification)`

## Phase 5c — BRIN + drop-recreate + partitioning for write amplification (US-3 / FR-038, FR-039, FR-040)

*Reliability doc §6. Reduces index write amplification from ~30x to ~1x for bulk bronze loads.*

- [ ] T160 [US3] Migration: BRIN indexes on `ingested_at` / `request_timestamp` for the 5 heaviest bronze tables; drop the existing btree indexes on the same columns (FR-038) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/035_brin_indexes.sql`
- [ ] T161 [US3] Audit each bronze table's existing indexes; identify which are essential (unique constraints supporting `ON CONFLICT`) vs non-essential (lookup indexes); document in PR description — `(audit, captured in PR)`
- [ ] T162 [P] [US3] Add drop-recreate-non-essential-indexes phase to each tray procedure T150–T154 (FR-039) — modifies `src/dk_data/sql/migrations/031_silver_hub_rebuild/030_tray_*.sql`
- [ ] T163 [US3] Migration: partition `mol_bronze.chembl_activities` by month on `ingested_at` — atomic ATTACH after backfill via tray (FR-040) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/036_partition_chembl_activities.sql`
- [ ] T164 [P] [US3] Partition `mol_bronze.bindingdb` by month — `src/dk_data/sql/migrations/031_silver_hub_rebuild/037_partition_bindingdb.sql`
- [ ] T165 [P] [US3] Partition `mol_bronze.clinicaltrials` by month — `src/dk_data/sql/migrations/031_silver_hub_rebuild/038_partition_clinicaltrials.sql`
- [ ] T166 [P] [US3] Partition `mol_bronze.pubchem` by month — `src/dk_data/sql/migrations/031_silver_hub_rebuild/039_partition_pubchem.sql`
- [ ] T167 [P] [US3] Partition `mol_bronze.chembl_molecules` by month — `src/dk_data/sql/migrations/031_silver_hub_rebuild/040_partition_chembl_molecules.sql`

## Phase 5d — SQLMesh transform fixes (US-3 / FR-046–FR-052)

- [ ] T170 [US3] Audit every silver and gold model for `INCREMENTAL_BY_TIME_RANGE` against tables >1M rows; convert to `INCREMENTAL_BY_UNIQUE_KEY` or replace with chunked PL/pgSQL procedure (FR-046, source doc T1) — `src/dk_data/sqlmesh/models/molecules/{silver,gold}/*.sql`
- [ ] T171 [P] [US3] Wrap source data in deduplicating CTE (`SELECT DISTINCT ON (key) ... ORDER BY key, ingested_at DESC`) for every `INCREMENTAL_BY_UNIQUE_KEY` model (FR-047, source doc T3) — `src/dk_data/sqlmesh/models/**/*.sql`
- [ ] T172 [P] [US3] Add `SET LOCAL work_mem = '128MB'` at the start of every transform that does heavy JSONB extraction or large sort/hash (FR-048, source doc T4); cap at 256 MB per session (FR-021b) — `src/dk_data/sqlmesh/models/**/*.sql`
- [ ] T173 [P] [US3] Convert FULL gold models to `INCREMENTAL_BY_UNIQUE_KEY` with `last_modified` watermark wherever possible (FR-049, source doc T5) — `src/dk_data/sqlmesh/models/**/gold/*.sql`
- [ ] T174 [P] [US3] Add explicit staleness check at the start of every silver model that depends on freshly-loaded bronze (raises exception if upstream `max(ingested_at) < now() - interval '6 hours'`) (FR-050, source doc T6) — `src/dk_data/sqlmesh/models/**/silver/*.sql`
- [ ] T175 [US3] Bump `activeDeadlineSeconds` for `mol-transform-bronze-ext` to 14400 (4h) (FR-051, source doc T7) — `k8s/apps/cronjobs/base/cronjob-mol-transform-bronze-ext.yaml`
- [ ] T176 [US3] Delete or fix the dead `mol-transform` patch in the prod overlay that targets a no-longer-existing CronJob (FR-052, source doc T8) — `k8s/overlays/prod/kustomization.yaml`

## Phase 5e — PostgREST API fixes (US-3 / FR-053–FR-057)

- [ ] T180 [US3] Migration: per-role `statement_timeout` and `idle_in_transaction_session_timeout` for all PostgREST roles (web_anon 30 s, analyst 5 min, mol_admin 1 h, etc.) (FR-053, source doc A1) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/041_role_timeouts.sql`
- [ ] T181 [US3] Migration: revoke `web_anon` access to all non-`api` schemas; grant only `USAGE ON SCHEMA api` + `SELECT ON ALL TABLES IN SCHEMA api` (FR-054, source doc A2) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/042_restrict_web_anon.sql`
- [ ] T182 [US3] PostgREST configmap: bump `PGRST_DB_POOL` from 10 to 30; set `PGRST_DB_STATEMENT_TIMEOUT=30s` (FR-055, source doc A3) — `k8s/apps/postgrest/base/configmap.yaml`
- [ ] T183 [US3] Switch PostgREST liveness/readiness probes from HTTP `/health` (which queries DB) to TCP socket on port 3000 (FR-056, source doc A4) — `k8s/apps/postgrest/base/deployment.yaml`
- [ ] T184 [P] [US3] Build materialized views in `api` schema for hot dashboard queries (`api.facility_summary`, `api.molecule_summary`, `api.trial_summary`); add nightly refresh CronJob (FR-057, source doc A5). All gold-grade joins in these views MUST filter `confidence ≥ 0.95` per FR-013b. — `src/dk_data/sql/migrations/031_silver_hub_rebuild/043_api_materialized_views.sql`, `k8s/apps/cronjobs/base/cronjob-refresh-api-views.yaml`

## Phase 5f — job-trigger fixes (US-3 / FR-058–FR-060)

- [ ] T190 [US3] Scale `job-trigger` Deployment from 1 to 2 replicas (FR-058, source doc J1) — `k8s/apps/job-trigger/base/deployment.yaml`
- [ ] T191 [US3] Migration: `meta.job_runs` table for in-flight job tracking (FR-059, source doc J2) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/044_meta_job_runs.sql`
- [ ] T192 [US3] `job-trigger` service: write `meta.job_runs` row on every fetcher/transform invocation; mark complete/failed/killed at end — `src/dk_data/services/job_trigger/handlers.py`
- [ ] T193 [US3] `job-trigger` service: add connection TTL — recycle DB connections every 1000 requests or 1 hour (FR-060, source doc J3) — `src/dk_data/services/job_trigger/db.py`

## Phase 5g — Backup CronJob fixes (US-3 / FR-061–FR-065)

- [ ] T200 [US3] Move `pg_dump` backup CronJob from 02:00 UTC to 12:00 UTC to avoid overlap with overnight fetchers (FR-061, source doc B1) — `k8s/apps/infrastructure/base/backup/cronjob-pg-dump.yaml`
- [ ] T201 [US3] Bump `pg_dump` and other backup CronJob `activeDeadlineSeconds` from 3600 to 14400 (FR-062, source doc B2) — `k8s/apps/infrastructure/base/backup/*.yaml`
- [ ] T202 [US3] Switch primary backup from `pg_dump` to `pg_basebackup` with a dedicated replication slot (FR-063, source doc B3) — `k8s/apps/infrastructure/base/backup/cronjob-pg-basebackup.yaml`
- [ ] T203 [US3] Eliminate the parallel barman-cloud → SeaweedFS backup path (or keep barman-cloud as the secondary, with `pg_dump`/`pg_basebackup` → MinIO as primary) (FR-064, source doc B4) — `k8s/apps/infrastructure/base/backup/`
- [ ] T204 [US3] Add automated restore testing CronJob — spin up temp postgres pod, restore latest backup, run sanity row counts on major tables, tear down (FR-065, source doc B5) — `k8s/apps/cronjobs/base/cronjob-pg-backup-verify.yaml`, `src/dk_data/sql/backup_verify_queries.sql`

## Phase 5h — Fetcher pool tuning + heavy fetcher splitting (US-3 / FR-066, FR-067)

- [ ] T210 [US3] Tune PgBouncer pool sizes per database in the configmap: `dk_data` 80, `behavior_labs` 50, `litellm` 20; set `max_client_conn=1000`, `default_pool_size=20`, `reserve_pool_size=5`, `reserve_pool_timeout=3` (FR-066, source doc F9) — `k8s/apps/infrastructure/base/pgbouncer-configmap.yaml`
- [ ] T211 [P] [US3] Split `cronjob-fetch-chembl-activities` into per-year CronJobs (2010–2026, ~17 jobs) staggered across hours, each running <2 hours (FR-067, source doc F10) — `k8s/apps/cronjobs/base/cronjob-fetch-chembl-activities-{YYYY}.yaml`
- [ ] T212 [P] [US3] Split `cronjob-fetch-pubchem` similarly — `k8s/apps/cronjobs/base/cronjob-fetch-pubchem-{range}.yaml`

## Phase 5i — Application-side monitoring (US-3 / FR-041–FR-045)

- [ ] T220 [US3] Migration: `meta.slow_query_log` table (FR-041) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/045_meta_slow_query_log.sql`
- [ ] T221 [US3] Migration: `meta.wal_usage` table (FR-042) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/046_meta_wal_usage.sql`
- [ ] T222 [US3] Migration: `meta.activity_log` table (FR-043) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/047_meta_activity_log.sql`
- [ ] T223 [US3] Migration: `meta.wal_status` table (FR-044) — `src/dk_data/sql/migrations/031_silver_hub_rebuild/048_meta_wal_status.sql`
- [ ] T224 [P] [US3] Implement `dk_data.ingestion.utils.db_timing.timed_query()` Python context manager that logs operations exceeding 1000 ms to `meta.slow_query_log` (FR-041) — `src/dk_data/ingestion/utils/db_timing.py`
- [ ] T225 [P] [US3] Wire `timed_query()` into every fetcher's batch insert call (replaces existing `cur.execute()` wrappers) — `src/dk_data/ingestion/fetchers/base.py`
- [ ] T226 [P] [US3] Implement `measure_wal()` helper that brackets a CronJob run with `pg_current_wal_lsn() - '0/0'::pg_lsn` and writes a row to `meta.wal_usage` at the end (FR-042) — `src/dk_data/ingestion/utils/wal_metrics.py`
- [ ] T227 [P] [US3] Wire `measure_wal()` into the fetcher and transform CronJob entry points — `src/dk_data/ingestion/fetchers/base.py`, `src/dk_data/ingestion/transform_molecules.py`
- [ ] T228 [US3] CronJob: snapshot `pg_stat_activity` every 60 s to `meta.activity_log` (FR-043). Snapshot query MUST flag any dk-data transaction with `xact_start < now() - interval '30 minutes'` per FR-021d — `k8s/apps/cronjobs/base/cronjob-activity-log-snapshot.yaml`
- [ ] T229 [US3] CronJob: snapshot WAL accumulation to `meta.wal_status` every 5 min (FR-044) — `k8s/apps/cronjobs/base/cronjob-wal-status-snapshot.yaml`
- [ ] T230 [US3] Grafana alert rules: `dk_data_slow_query` (>10 s), `dk_data_wal_explosion` (>5 GB CronJob), `dk_data_long_transaction` (>1 h), `dk_data_activity_pile_up` (>50 active queries) (FR-045); add `dk_data_cpu_starvation` alert when sustained dk-data CPU >80% over 5 min (FR-021f) — `k8s/apps/observability/alert-rules/dk-data-app-side.yaml`

## Phase 5j — Tier 2 free-text source linking (US-5 / FR-068)

- [ ] T240 [P] [US5] Wire `cms_open_payments` drug name → `mol_silver.molecule_names` direct alias lookup — `src/dk_data/sqlmesh/models/hcs/silver/cms_open_payments.sql`
- [ ] T241 [P] [US5] Wire `cms_part_d_prescriber` brand+generic → RxNorm BN/IN lookup — `src/dk_data/sqlmesh/models/hcs/silver/cms_part_d_prescriber.sql`
- [ ] T242 [P] [US5] Wire `cms_opioid_puf` NDC → canonical NDC link — `src/dk_data/sqlmesh/models/hcs/silver/cms_opioid_puf.sql`
- [ ] T243 [P] [US5] Wire `cms_ddinter` drug names → generic name lookup — `src/dk_data/sqlmesh/models/hcs/silver/cms_ddinter.sql`
- [ ] T244 [P] [US5] Wire `cms_stabilis` drug name → generic name lookup — `src/dk_data/sqlmesh/models/hcs/silver/cms_stabilis.sql`
- [ ] T245 [P] [US5] Wire `cms_usp` USP class → class canonical link — `src/dk_data/sqlmesh/models/hcs/silver/cms_usp.sql`
- [ ] T246 [P] [US5] Wire `cms_magnet` hospital name + state → trigram fuzzy → CCN crosswalk — `src/dk_data/sqlmesh/models/hcs/silver/cms_magnet.sql`
- [ ] T247 [P] [US5] Wire `hrsa` facility name + address → fuzzy/geocode → CCN+NPI — `src/dk_data/sqlmesh/models/hcs/silver/hrsa.sql`
- [ ] T248 [P] [US5] Wire `acc_tvc` facility identifiers → fuzzy → CCN — `src/dk_data/sqlmesh/models/hcs/silver/acc_tvc.sql`

## Phase 8 — Polish & Cross-Cutting

- [ ] T140 [P] Update `CLAUDE.md` "Active Technologies" and "Recent Changes" sections to mention the silver hub architecture and the new tags — `CLAUDE.md`
- [ ] T141 [P] Update `Cross-Project-Planning/dk data fe/01-architecture-and-reliability/silver-linkage-reference.md` and `transformation-reliability-low-tech-solutions.md` to reflect the final implementation if it diverges from the spec — `Cross-Project-Planning/dk data fe/01-architecture-and-reliability/*.md`
- [ ] T142 [P] Add per-resolve-function latency benchmark suite; verify SC-004 (<10 ms p99) on staging — `tests/perf/test_resolve_latency.py`
- [ ] T143 [P] Add multi-tenant impact verification: capture BLAI/litellm p95 baseline, run a hub bootstrap, verify ≤10% p95 increase per SC-009 — `tests/perf/test_multi_tenant_impact.py`
- [ ] T144 [P] Add a runbook for hub bootstrap incident response (stuck `meta.job_locks`, runaway `transform_runs.wal_bytes`, mid-bootstrap pod kill) — `docs/runbooks/silver-hub-bootstrap.md`
- [ ] T145 Update PostgREST role permissions so `web_anon` and `analyst` roles have `SELECT` on the new hub, crosswalk, and name-index tables — `k8s/apps/postgrest/base/postgrest-roles.sql`
- [ ] T146 Final end-to-end check: run the contract test, the antipattern grep, the build_dsn enforcement test, and a sample silver model rewrite against staging; capture metrics; close the feature — `(operational verification)`

---

## Dependencies & Execution Order

```
Phase 1 (Setup, ~1 day)
   ↓
Phase 2 (Foundational — meta tables, helper, contract test, ~2 days)
   ↓
Phase 3 (US-1: column retention rewrite, ~3 days, parallel by schema)
   ↓
Phase 4 (US-2: 10 hubs + crosswalks + name indexes + resolve functions, ~5 days)
   ├─ 4.1 Schemas (parallel within group)
   ├─ 4.2 Resolve functions (parallel within group)
   ├─ 4.3 Resolve function tests (parallel)
   ├─ 4.4 Bootstrap procedures (sequential — smallest-first, same dependency chain)
   └─ 4.5 End-to-end smoke (sequential, after 4.4)
   ↓
Phase 5 (US-3: reliability principles applied, ~2 days, parallel file-by-file)
   ↓
Phase 6 (US-4: silver model rewrites in priority order, ~5 days)
   ↓
Phase 7 (US-5: structured-field linking, ~1 day; partially overlaps Phase 6)
   ↓
Phase 8 (Polish, ~2 days, parallel)
```

**Total estimated effort**: ~3–4 weeks of focused work (matches the source linkage doc's estimate).

**Parallel opportunities**: Phases 3, 5, 7, 8 are heavily parallel (file-by-file). Phase 4.1, 4.2, 4.3 are parallel within their groups. Phase 4.4 is sequential by design (smallest-first dependency chain). Phase 6 must be sequential because each rewrite depends on the previous hub being populated.

## Implementation Strategy

- **MVP-first**: Phase 3 (US-1) alone delivers a usable improvement — every silver model carries forward every bronze column. This can ship before Phase 4 if needed.
- **Bootstrap before rewrites**: Phase 4.4 (bootstrap procedures) MUST complete before Phase 6 (silver rewrites) because the rewrites join to the hub crosswalks.
- **Parallel sub-agent friendly**: Phase 3 (~80 silver models across 3 schemas), Phase 4.1 (10 hub schemas), Phase 4.2 (10 resolve functions), Phase 5 (fetcher migrations), and Phase 7 (free-text linking) are all amenable to `/dk.swarm` parallel execution because each file is independent.
- **Validation gates**: After Phase 3, the column-retention test must pass on every silver model. After Phase 4.5, every bootstrap must complete within budget. After Phase 6, the antipattern grep must return zero matches. These are hard gates — fail on any one means stop and fix.
