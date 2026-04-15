# Tasks: claims-engine-data-gaps

## Dependency Graph

```
Phase 1 (Setup)
  T001 ──────────────────────────────────────────────┐
                                                     │
Phase 2 (Week 1 -- P0)                              │
  T002 ─► T003 (Purple Book fix + audit)             │
  T004 ─► T005 ─► T006 ─► T007 ─► T008 ─► T009     │
     (Item 1: openfda subobject ─► Rx ─► OTC ─►     │
      SPL ─► _table ─► silver sync)                  │
  T010 ─► T011 ─► T012 ─► T013                      │
     (Item 2: ATC model ─► KEGG parse ─►             │
      drug_products atc_code ─► PostgREST)           │
                                                     │
Phase 3 (Weeks 2-3 -- P1)          depends on T001 ─┘
  T014 ─► T015 (evidence tier + fixtures)
  T016 ─► T017 ─► T018 ─► T019 (Item 7: fda_drugs flags + orphan + drug_products)
  T020 (label changes)
  T021 ─► T022 ─► T023 ─► T024 (Item 25: migration + loader + bronze + backfill)
  T025 ─► T026 ─► T027 ─► T028 ─► T029 (Item 26: migration + loader + bronze + index + backfill)

Phase 4 (Weeks 4-5 -- P2)
  T030 (PRAC signals)
  T031 ─► T032 ─► T033 (Item 15: fetcher + bronze + silver)
  T034 ─► T035 (Item 16: scraper + bronze)
  T036 ─► T037 ─► T038 (Item 27a: Part D migration + loader + bronze)
  T039 ─► T040 ─► T041 (Item 27b: Hospital migration + loader + bronze)
  T042 ─► T043 ─► T044 (Item 27c: Physician PUF migration + loader + bronze)
  T045 ─► T046 ─► T047 (Item 27d: HRSA migration + loader + bronze)

Phase 5 (Weeks 6+ -- P1 large)
  T048 ─► T049 ─► T050 ─► T051 (Item 8: guidelines bronze + curation + silver + cadence)
  T052 ─► T053 ─► T054 (Item 10: SmPC parser + silver + validation)
  T055 ─► T056 ─► T057 ─► T058 (Item 28a: USPTO patents migration + loader + bronze + silver)
  T059 ─► T060 ─► T061 ─► T062 (Item 28b: EPO patents migration + loader + bronze + silver)
  T063 ─► T064 ─► T065 (Item 28c: USPTO trademarks migration + loader + bronze)
  T066 ─► T067 ─► T068 (Item 28d: EUIPO trademarks migration + loader + bronze)
  T058 + T062 ─► T069 (patent_families silver view)
  T058 + T062 ─► T070 (patent_citations silver view)
  T065 + T068 ─► T071 (trademark_oppositions silver view)
  T072 ─► T073 ─► T074 ─► T075 ─► T076 (Item 9: 5 enforcement sources)
  T077 ─► T078 ─► T079 ─► T080 (Item 13: conference abstracts bronze + scrapers + silver + embargo)

Phase 6 (Polish)
  T081 (PostgREST grants)
  T082 (post-audit queries)
  T083 (e2e validation)
```

---

## Phase 1: Setup / Foundation

- [x] T001 [P0] Confirm WAL circuit breaker infrastructure: verify `meta.transform_runs` WAL accounting is active for all write paths; confirm chunked procedure pattern is available (<=50K rows / <=200 MB WAL per chunk); verify tray pattern procedures exist for tables >1M rows. Gate for Phase 3+ loader backfills.

---

## Phase 2: Week 1 -- P0 Hotfixes + Quick Wins

### Item 24: Fix `mol_bronze.purple_book` (Option A -- direct `results[]` iteration)

- [x] T002 [P0] Rewrite the FROM clause in `src/dk_data/sqlmesh/models/molecules/bronze/purple_book.sql`: replace `jsonb_array_elements(response_body->'_normalized_products') AS prod` with `jsonb_array_elements(response_body->'results') AS app, LATERAL jsonb_array_elements(app->'products') AS prod`. Update all column projections to read from `app` (application-level: `application_number`, `sponsor_name`) and `prod` (product-level: `brand_name`, `is_biosimilar`, `is_interchangeable`, `orphan_exclusivity_end`). Add WHERE filter `app->>'application_number' LIKE 'BLA%'` to restrict to Purple Book scope. Verify `SELECT COUNT(*) FROM mol_bronze.purple_book` >= 1,000 rows.
- [x] T003 [P0] Add SQLMesh audit `row_count_at_least(1000)` to `src/dk_data/sqlmesh/models/molecules/bronze/purple_book.sql` to catch future silent regressions. Verify `mol_silver.purple_book` inherits fix automatically. Confirm Dupilumab BLA 761055 row exists with `brand_name = 'Dupixent'`, `license_type = 'BLA'`.

### Item 1: Fully unnest every openFDA drug-label field

- [x] T004 [P0] Fix `product_type` bug + add 8 missing `openfda` subobject fields in `src/dk_data/sqlmesh/models/molecules/bronze/openfda_labels.sql`: change `label->>'product_type'` to `label->'openfda'->'product_type'->>0 AS product_type`. Add `substance_name` (`label->'openfda'->'substance_name'->>0`), `product_ndc` (`label->'openfda'->'product_ndc'::JSONB`), `package_ndc` (`label->'openfda'->'package_ndc'::JSONB`), `openfda_spl_id` (`label->'openfda'->'spl_id'->>0`), `pharm_class_pe` (`label->'openfda'->'pharm_class_pe'::JSONB`), `pharm_class_cs` (`label->'openfda'->'pharm_class_cs'::JSONB`), `original_packager_product_ndc` (`label->'openfda'->'original_packager_product_ndc'::JSONB`), `upc` (`label->'openfda'->'upc'::JSONB`).
- [x] T005 [P0] Add 22 Rx label sections to `src/dk_data/sqlmesh/models/molecules/bronze/openfda_labels.sql`: `abuse`, `active_ingredient`, `animal_pharmacology_and_toxicology`, `carcinogenesis_mutagenesis_fertility`, `controlled_substance`, `dea_schedule`, `dependence`, `dosage_forms_and_strengths`, `drug_abuse_and_dependence`, `drug_or_lab_test_interactions`, `inactive_ingredient`, `information_for_patients`, `instructions_for_use`, `labor_and_delivery`, `laboratory_tests`, `microbiology`, `nonclinical_toxicology`, `nonteratogenic_effects`, `precautions`, `pregnancy_or_breast_feeding`, `recent_major_changes`, `label_references` (aliased from `references`), `teratogenic_effects`. All via `label->'<key>'->>0 AS <column_name>`.
- [x] T006 [P0] Add 7 OTC label sections to `src/dk_data/sqlmesh/models/molecules/bronze/openfda_labels.sql`: `ask_doctor`, `ask_doctor_or_pharmacist`, `do_not_use`, `keep_out_of_reach_of_children`, `purpose`, `questions`, `stop_use`. All via `label->'<key>'->>0 AS <column_name>`.
- [x] T007 [P0] Add 4 SPL structured sections to `src/dk_data/sqlmesh/models/molecules/bronze/openfda_labels.sql`: `spl_medguide`, `spl_patient_package_insert`, `spl_product_data_elements`, `spl_unclassified_section`. All via `label->'<key>'->>0 AS <column_name>`.
- [x] T008 [P0] Add 14 `_table` JSONB variants to `src/dk_data/sqlmesh/models/molecules/bronze/openfda_labels.sql`: `adverse_reactions_table`, `clinical_pharmacology_table`, `clinical_studies_table`, `description_table`, `dosage_and_administration_table`, `dosage_forms_and_strengths_table`, `drug_interactions_table`, `how_supplied_table`, `instructions_for_use_table`, `pharmacokinetics_table`, `recent_major_changes_table`, `spl_medguide_table`, `spl_patient_package_insert_table`, `spl_unclassified_section_table`. All via `label->'<key>'::JSONB AS <column_name>`.
- [x] T009 [P0] Sync `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql` SELECT list: add every new column from T004-T008 (one line per column). Verify passthrough is complete by confirming Dupilumab row has `product_type = 'HUMAN PRESCRIPTION DRUG'`, `substance_name = 'DUPILUMAB'`, non-null `product_ndc`, non-null `pharm_class_cs`, non-null `adverse_reactions_table` with >= 8 entries, non-null `clinical_studies_table` with >= 30 entries. Verify hydrocodone has `dea_schedule = 'CII'`. Verify aspirin OTC fields non-null.

### Item 2: ATC classifications hierarchy hub

- [x] T010 [P0] Create SQLMesh model `mol_silver.atc_classifications` at `src/dk_data/sqlmesh/models/molecules/silver/atc_classifications.sql` with columns: `atc_code` (VARCHAR(20) PK), `parent_atc_code` (VARCHAR(20)), `level` (INTEGER 1-5), `description` (TEXT), `source` (TEXT -- 'kegg' | 'who_cc'), `last_updated_at` (TIMESTAMPTZ). Priority resolution order: DrugBank -> ChEMBL -> KEGG.
- [x] T011 [P0] Implement KEGG `brite` field parser: extract ATC hierarchy from `src/dk_data/sqlmesh/models/molecules/bronze/kegg_drug.sql` (`mol_bronze.kegg_drug.raw_json->'brite'`). Parse indentation-based hierarchy to produce parent-child rows. Target ~6,500 rows for full ATC tree. Supplement with WHO-CC ATC bulk download if license permits.
- [x] T012 [P0] Add `atc_code` column (TEXT[]) to `mol_silver.drug_products`, populated by priority resolution: join DrugBank `atc_codes` JSONB array first, then ChEMBL `atc_classifications`, then KEGG `atc_codes`. Verify nontrivial population fraction.
- [x] T013 [P0] Expose `mol_silver.atc_classifications` via PostgREST (verify in `PGRST_DB_SCHEMAS`). Optionally create `mol_silver.resolve_atc_ancestors()` RPC for recursive CTE ancestor walks. Verify: for `atc_code = 'D11AH05'`, walking `parent_atc_code` returns D11AH -> D11A -> D11 -> D.

---

## Phase 3: Weeks 2-3 -- P1 Medium-Effort Internal

### Item 6: Publication evidence tier

- [x] T014 [P1] Add derived `evidence_tier` column (VARCHAR(1) -- A/B/C/D/U) to `src/dk_data/sqlmesh/models/molecules/silver/publications.sql` via CASE expression. Per-source fallback logic: PubMed `publication_type_list` mapping (Systematic Review/Meta-Analysis -> A; RCT/Clinical Trial -> B; Observational/Cohort/Case-Control -> C; Case Reports/Editorial/Comment/Letter -> D; else -> U). OpenAlex `type` mapping with Cochrane override. All Cochrane-sourced records -> A. Never NULL, always U for unclassifiable.
- [x] T015 [P1] Create fixture tests: 50 publications per tier covering PubMed, OpenAlex, and Cochrane sources. Verify >= 95% population rate, Cochrane review = 'A', case report = 'D', unclassifiable = 'U'.

### Item 7: FDA designation flags

- [x] T016 [P1] Update `src/dk_data/sqlmesh/models/molecules/bronze/fda_drugs.sql`: add 5 boolean designation flags from `submissions` JSONB via `EXISTS` subqueries over `jsonb_array_elements(COALESCE(rec->'submissions', '[]'::JSONB))`: `is_priority_review`, `is_orphan_designation`, `is_breakthrough_designation`, `is_fast_track`, `is_accelerated_approval`. Confirm exact `submission_class_code` strings against sample raw data before committing.
- [x] T017 [P1] Update silver passthrough for `mol_silver.fda_drugs` to include all 5 designation flags. Verify a known Breakthrough-designated drug has `is_breakthrough_designation = TRUE`.
- [x] T018 [P1] Create new bronze source `mol_bronze.fda_orphan_designation`: new fetcher/loader for FDA Orphan Drug Designation database, new migration for DDL (`designation_number`, `generic_name`, `trade_name`, `sponsor`, `designation_date`, `designated_indication`, `marketing_approval_date`), new SQLMesh bronze model. Verify >= 500 rows.
- [x] T019 [P1] Add unified `has_orphan_designation` BOOLEAN on `mol_silver.drug_products` combining Purple Book `orphan_exclusivity_end IS NOT NULL` (biologics) with `mol_bronze.fda_orphan_designation` linkage (small molecules). Verify TRUE for both a known biologic orphan and a known small-molecule orphan.

### Item 11: Drug label changes

- [x] T020 [P2] Create materialized view `mol_silver.drug_label_changes` at `src/dk_data/sqlmesh/models/molecules/silver/drug_label_changes.sql` with columns: `set_id`, `from_version`, `to_version`, `section_name`, `change_type` ('added'|'removed'|'modified'), `diff_text`, `detected_at`. Compute section-level diffs between consecutive (set_id, version) pairs. Expose via PostgREST. Verify a known boxed-warning change produces a row with `section_name = 'boxed_warning'`, `change_type = 'modified'`.

### Item 25: CMS Open Payments expansion

- [x] T021 [P1] New migration `src/dk_data/sql/migrations/232_cms_open_payments_loader_expansion.sql`: add ~37 new columns to `hcs_raw.cms_open_payments` DDL -- physician NPI, teaching hospital fields, recipient geography, dispute/publication metadata, manufacturer identity, product category/indication slots 1-5, travel details, flags.
- [x] T022 [P1] Update CMS Open Payments loader to read all ~91 columns from public CSV. Reference CMS Open Payments Data Dictionary (Program Year 2024).
- [x] T023 [P1] Extend `hcs_bronze.cms_open_payments` and `mol_bronze.cms_open_payments` SQLMesh model passthroughs to include every new column.
- [ ] T024 [P1] **SKIPPED -- backfill requires cluster access.** Re-run backfill for historical program years (partitioned by `_source_year`). Use chunked procedure pattern for WAL safety. Verify `physician_npi` populated for physician rows, `teaching_hospital_ccn` for teaching-hospital rows, total column count >= 85.

### Item 26: CMS NPPES expansion

- [x] T025 [P1] New migration `src/dk_data/sql/migrations/233_cms_nppes_loader_expansion.sql`: add ~280 missing columns to `hcs_raw.cms_nppes` DDL -- taxonomies 3-15 (52 columns), other_provider_identifier 1-50 (200 columns), practice location addresses, authorized official details, deactivation/reactivation fields, entity-type-specific fields, `last_update_date`, `certification_date`.
- [x] T026 [P1] Update NPPES loader to parse all ~330 columns from monthly dissemination file. Dynamic kwargs construction with dict-comprehension column mappings. CMSNPPESRecord uses extra='allow' for 252 slot columns.
- [x] T027 [P1] Extend `hcs_bronze.cms_nppes` SQLMesh model passthrough to include every new column (~284 columns total in SELECT).
- [x] T028 [P1] Add composite indexes on `(other_provider_identifier_type_code_N, other_provider_identifier_N)` for slots 1-5 (included in migration 233, CONCURRENTLY after COMMIT).
- [ ] T029 [P1] **SKIPPED -- backfill requires cluster access.** Execute full NPPES backfill via tray pattern (UNLOGGED staging -> chunked load -> SET LOGGED -> atomic swap) for ~7M rows. Verify taxonomy slot 5 populated for multi-certified physicians, DEA numbers visible, practice-location addresses non-null, total column count >= 300.

---

## Phase 4: Weeks 4-5 -- P2 Short New Sources

### Item 14: EMA PRAC safety signals

- [ ] T030 [P2] Create `mol_silver.ema_prac_signals` SQLMesh model parsing PRAC records from `mol_bronze.ema` based on `action_type` / `document_type` field. Columns: `signal_id`, `drug_name`, `active_substance`, `signal_type`, `signal_date`, `outcome`, `document_url`. Add molecule crosswalk. Verify >= 50 rows, a known EMA safety review appears.

### Item 15: FDA Drug Shortages

- [ ] T031 [P2] Create fetcher + loader for openFDA Drug Shortages endpoint (`https://api.fda.gov/drug/drugshortages.json`). Write to `mol_raw.fda_drug_shortages`.
- [ ] T032 [P2] Create bronze model `mol_bronze.fda_drug_shortages` with columns: `shortage_id`, `generic_name`, `brand_name`, `company`, `status`, `shortage_reason`, `shortage_start_date`, `shortage_end_date`, `affected_products` (JSONB), `notes`. Set cron to daily refresh.
- [ ] T033 [P2] Create `mol_silver.fda_drug_shortages` with molecule crosswalk via normalized generic_name. Expose via PostgREST. Verify a known active shortage appears with correct status and start date.

### Item 16: FDA Companion Diagnostics

- [ ] T034 [P2] Create scraper + loader for FDA CDx pairing list. Write to `mol_raw.fda_cdx_pairs`.
- [ ] T035 [P2] Create bronze model `mol_bronze.fda_cdx_pairs` with columns: `cdx_id`, `device_name`, `manufacturer`, `intended_use`, `drug_trade_name`, `drug_generic_name`, `approval_date`, `submission_type`, `source_url`. Silver crosswalk to molecules via drug_generic_name. Verify >= 50 rows.

### Item 27: Other CMS/HRSA loader expansions

**27a. CMS Part D Prescriber:**
- [ ] T036 [P2] New migration: expand `hcs_raw.cms_part_d_prescriber` DDL to ~25-30 columns -- add `opioid_prescriber_rate`, `opioid_day_supply`, `long_acting_opioid_*`, antibiotic breakouts, branded-vs-generic splits.
- [ ] T037 [P2] Update Part D Prescriber loader to read all new columns from CMS PUF.
- [ ] T038 [P2] Extend `hcs_bronze.cms_part_d_prescriber` SQLMesh model passthrough. Verify column count >= 25.

**27b. CMS Hospital General Info:**
- [ ] T039 [P2] New migration: expand `hcs_raw.cms_hospital_general_info` DDL to ~40+ columns -- add 26+ per-measure quality ratings (mortality, readmission, safety, patient experience, timeliness, imaging, HAI rates).
- [ ] T040 [P2] Update Hospital General Info loader to read all quality rating columns.
- [ ] T041 [P2] Extend `hcs_bronze.cms_hospital_general_info` SQLMesh model passthrough. Verify >= 20 quality rating columns present.

**27c. CMS Physician PUF:**
- [ ] T042 [P2] New migration: create child table `hcs_raw.cms_physician_puf_services` for per-HCPCS line items (`hcpcs_code`, `hcpcs_description`, `place_of_service`, `number_of_services`, `number_of_medicare_beneficiaries`, `average_medicare_allowed_amt`, `average_submitted_charge_amt`, `average_medicare_payment_amt`, `average_medicare_standardized_amt`, beneficiary breakouts).
- [ ] T043 [P2] Update Physician PUF loader to ingest per-HCPCS line items into child table.
- [ ] T044 [P2] Create `hcs_bronze.cms_physician_puf_services` SQLMesh model passthrough. Verify per-HCPCS line items populated.

**27d. HRSA:**
- [ ] T045 [P2] New migration: expand `hcs_raw.hrsa` DDL to ~20-25 columns -- add `hpsa_status_code`, `designation_history` (JSONB), `provider_count`, `primary_care_physician_count`, `dental_provider_count`, `mental_health_provider_count`, `mua_status`, `mua_score`, `withdrawn_date`.
- [ ] T046 [P2] Update HRSA loader to read all new fields.
- [ ] T047 [P2] Extend `hcs_bronze.hrsa` SQLMesh model passthrough. Verify `hpsa_status_code`, `provider_count`, `primary_care_physician_count` columns present.

---

## Phase 5: Weeks 6+ -- P1 Large New Source Ingestion

### Item 8: Treatment guidelines feed

- [ ] T048 [P0] Create fetcher/loader infrastructure for guidelines. Create bronze model `mol_bronze.guidelines` with columns: `id` (UUID), `body` (TEXT), `title` (TEXT), `publication_date` (DATE), `version` (TEXT), `indication_icd11` (TEXT), `indication_name` (TEXT), `source_url` (TEXT), `full_text` (TEXT), `sections` (JSONB), `recommendations` (JSONB).
- [ ] T049 [P0] Manual curation: ingest top 10-15 guidelines per therapeutic area. Target bodies: AAD, ACR, EADV, GINA, GOLD, NCCN, ESMO, ASCO. Verify >= 50 guidelines ingested.
- [ ] T050 [P0] Create silver model `mol_silver.guidelines` with molecule and condition crosswalks. Expose via PostgREST. Verify AAD, ACR, GINA, NCCN each represented; each guideline has parseable `sections` JSONB.
- [ ] T051 [P0] Establish quarterly maintenance cadence: document review schedule, add automated scraping for bodies with predictable formats, create monitoring for stale guidelines (> 6 months since last check).

### Item 10: EMA SmPC parser

- [ ] T052 [P0] Build PDF parser for EMA SmPC canonical section structure: map 4.1-5.3 sections to FDA-equivalent column names (4.1 -> `indications_and_usage`, 4.2 -> `dosage_and_administration`, 4.3 -> `contraindications`, 4.4 -> `warnings_and_cautions`, 4.5 -> `drug_interactions`, 4.6 -> `pregnancy` + `nursing_mothers`, 4.7 -> `use_in_specific_populations`, 4.8 -> `adverse_reactions`, 4.9 -> `overdosage`, 5.1 -> `pharmacodynamics`, 5.2 -> `pharmacokinetics`, 5.3 -> `nonclinical_toxicology`).
- [ ] T053 [P0] Create silver model `mol_silver.drug_labels_ema` with same column structure as `mol_silver.drug_labels`. Crosswalk to molecules via `mol_silver.ema_regulatory` linkage. Expose via PostgREST.
- [ ] T054 [P0] Validate parsing quality: run parser against 50-SmPC validation set, verify >= 90% section-header accuracy. Verify Dupixent EU SmPC sections 4.1-5.3 parsed and non-null. Verify >= 500 SmPCs total.

### Item 28: IP patent/trademark loader expansions

**28a. USPTO Patents:**
- [ ] T055 [P1] New migration: expand `ip_raw.uspto_patents` DDL from ~10 to ~50 columns -- add `cited_patents` (JSONB), `citing_patents` (JSONB), `npl_citations` (JSONB), `parent_application` (TEXT), `child_applications` (JSONB), `continuation_type` (TEXT), `claims_full_text` (TEXT), `assignment_events` (JSONB), `examiner_first_name`, `examiner_last_name`, `examiner_art_unit`, `family_id`, `equivalent_foreign_patents` (JSONB), `application_number`, `publication_number`, `priority_date`, IPC codes (TEXT[]).
- [ ] T056 [P1] Update USPTO patents loader to read all fields from PatentsView API. Preserve deeply nested fields (citations, family members, assignment events) as JSONB arrays.
- [ ] T057 [P1] Extend `ip_bronze.uspto_patents` SQLMesh model passthrough to include every new column.
- [ ] T058 [P1] Verify `cited_patents`, `citing_patents`, `parent_application`, `claims_full_text` populated.

**28b. EPO Patents:**
- [ ] T059 [P1] New migration: expand `ip_raw.epo_patents` DDL from ~9 to ~35 columns -- add `priority_claims` (JSONB), `family_members` (JSONB), `abstract_en`, `abstract_fr`, `abstract_de`, `legal_status_events` (JSONB), `designated_states` (JSONB), `grant_date`, `cited_patents` (JSONB).
- [ ] T060 [P1] Update EPO patents loader to read all fields from EPO OPS API.
- [ ] T061 [P1] Extend `ip_bronze.epo_patents` SQLMesh model passthrough.
- [ ] T062 [P1] Verify `family_members`, `priority_claims`, `legal_status_events` populated.

**28c. USPTO Trademarks:**
- [ ] T063 [P1] New migration: expand `ip_raw.uspto_trademarks` DDL from ~15 to ~40 columns -- add `case_file_statements` (JSONB), `owner_events` (JSONB), `assignments` (JSONB), `prosecution_history` (JSONB), `tta_proceedings` (JSONB), `renewal_events` (JSONB), Madrid Protocol linkage (TEXT), `mark_image_url` (TEXT).
- [ ] T064 [P1] Update USPTO trademarks loader to read all fields from TESS/TSDR.
- [ ] T065 [P1] Extend `ip_bronze.uspto_trademarks` SQLMesh model passthrough. Verify `case_file_statements`, `oppositions` (via `tta_proceedings`), `assignments` populated.

**28d. EUIPO Trademarks:**
- [ ] T066 [P1] New migration: expand `ip_raw.euipo_trademarks` DDL from ~15 to ~35 columns -- add `oppositions` (JSONB), `cancellations` (JSONB), `seniorities` (JSONB), `priority_claims` (JSONB), `vienna_codes` (JSONB), `publication_events` (JSONB), owner change history (JSONB), `acquired_distinctiveness_flag` (BOOLEAN).
- [ ] T067 [P1] Update EUIPO trademarks loader to read all fields from EUIPO/TMview JSON API.
- [ ] T068 [P1] Extend `ip_bronze.euipo_trademarks` SQLMesh model passthrough. Verify `oppositions`, `cancellations`, `seniorities` populated.

**New silver views (depend on bronze tasks above):**
- [ ] T069 [P1] Create `ip_silver.patent_families` -- one row per `family_id` with member patents from both USPTO and EPO. Verify dupilumab composition-of-matter family returns all members.
- [ ] T070 [P1] Create `ip_silver.patent_citations` -- edge list of patent-to-patent citations from both USPTO and EPO.
- [ ] T071 [P1] Create `ip_silver.trademark_oppositions` -- one row per opposition event from both USPTO (via `tta_proceedings`) and EUIPO (via `oppositions`).

### Item 9: FDA enforcement actions

- [ ] T072 [P1] Create fetcher + loader + bronze model `mol_bronze.fda_warning_letters` (scrape from FDA compliance actions page). Columns: `letter_id`, `letter_date`, `company_name`, `company_address`, `subject`, `issuing_office`, `response_letter_url`, `closeout_letter_url`, `full_text`, `drug_mentions` (JSONB). Silver crosswalk to molecules. Verify >= 100 rows.
- [ ] T073 [P1] Create fetcher + loader + bronze model `mol_bronze.fda_untitled_letters` (same structure as warning letters). Silver crosswalk. Verify >= 100 rows.
- [ ] T074 [P1] Create fetcher + loader + bronze model `mol_bronze.fda_483_observations`. Columns: `observation_id`, `inspection_date`, `company_name`, `facility`, `observations` (JSONB), `full_text`. Silver crosswalk. Verify >= 100 rows.
- [ ] T075 [P1] Create fetcher + loader + bronze model `mol_bronze.fda_dear_hcp_letters` (from FDA Drug Safety Communications). Silver crosswalk. Verify >= 100 rows.
- [ ] T076 [P1] Create fetcher + loader + bronze model `mol_bronze.fda_crls` (Complete Response Letters from public 8-K/FOIA sources). Silver crosswalk. Verify >= 100 rows. Verify molecule crosswalk covers >= 50% of rows with drug mentions across all 5 sources.

### Item 13: Conference abstracts feed

- [ ] T077 [P1] Create bronze model `mol_bronze.conference_abstracts` with columns: `abstract_id`, `conference_name`, `conference_body`, `conference_date`, `presentation_date`, `presentation_type`, `title`, `authors` (JSONB), `affiliations` (JSONB), `abstract_text`, `embargo_date`, `publication_date`, `session_title`, `track`, `source_url`. Track `embargo_date` and `publication_date` as distinct fields.
- [ ] T078 [P1] Build scrapers for top 10-15 conference programs: AAD, EADV (Dermatology); ACR, EULAR (Rheumatology); ATS, AAAAI, ERS (Respiratory); ASCO, ESMO, ASH (Oncology); AHA, ESC (Cardiology); ADA, EASD (Endocrinology); DDW, UEGW (Gastroenterology).
- [ ] T079 [P1] Create silver model `mol_silver.conference_abstracts` with molecule and condition crosswalks. Verify >= 500 abstracts across >= 5 conferences.
- [ ] T080 [P1] Implement embargo-aware publication filter in silver model: `WHERE publication_date <= CURRENT_DATE OR publication_date IS NULL`. Embargoed abstracts MUST NOT appear in the rules engine context bag until `publication_date`. Verify a known AAD late-breaking abstract has correct `embargo_date` and `publication_date` tracked distinctly.

---

## Phase 6: Polish

- [ ] T081 [P1] PostgREST grants: verify all new silver/gold models (`atc_classifications`, `ema_prac_signals`, `fda_drug_shortages`, `fda_cdx_pairs`, `guidelines`, `drug_labels_ema`, `drug_label_changes`, `conference_abstracts`, `patent_families`, `patent_citations`, `trademark_oppositions`) have `SELECT` grants for the PostgREST role and are in `PGRST_DB_SCHEMAS`. Test each new endpoint returns data.
- [ ] T082 [P1] Run post-audit queries: execute `SELECT jsonb_object_keys(raw_json) EXCEPT (projected_columns)` against `mol_bronze.openfda_labels` to verify zero documented openFDA keys remain unprojected. Run equivalent completeness checks on all expanded loader tables.
- [ ] T083 [P1] E2E validation: execute every acceptance scenario from spec.md against production data. Confirm: Purple Book >= 1,000 rows with Dupilumab BLA 761055; all 56 new label columns populated; ATC hierarchy walk for D11AH05; evidence tier distribution >= 95% populated; designation flags correct; shortage list current; CDx >= 50 pairs; guidelines >= 50; SmPC >= 500; conference abstracts >= 500; IP fields populated; enforcement >= 100 rows per source. Notify `behavior-labs-ai` team that `@repo/claims-response-dk-adapter` can remove `raw_json` JSONB-parse workarounds.
