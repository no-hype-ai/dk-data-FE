# Tasks: Silver Column Retention

**Input**: Design documents from `/specs/028-silver-column-retention/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Tests**: Not requested — no test tasks generated.

**Organization**: Tasks grouped by user story. US1 covers single-source mol_silver models, US2 covers multi-source/HCS models, US3 covers adverse_events and remaining models.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1, US2, US3)
- Exact file paths included

## Path Conventions

All silver models: `src/dk_data/sqlmesh/models/*/silver/*.sql`
All bronze models: `src/dk_data/sqlmesh/models/*/bronze/*.sql` (read-only reference)

---

## Phase 1: Setup

**Purpose**: Establish the column-diff audit tooling and excluded column list

- [ ] T001 Create column-diff audit script at `scripts/audit_silver_columns.py` that: (1) parses each silver SQL model to extract upstream bronze source(s) from FROM clause, (2) parses bronze SQL model to extract SELECT columns, (3) diffs against silver SELECT columns, (4) outputs missing columns per model. Exclude list: `raw_json`, `raw_source_id`, `processed_to_bronze`, `processed_to_silver`, `_bronze_loaded_at`, bronze `id`, bronze `created_at`.
- [ ] T002 Run audit script and save output to `specs/028-silver-column-retention/column-audit-results.txt` to establish baseline gap count

**Checkpoint**: Audit tooling ready, baseline gaps documented

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Identify column collision patterns across multi-source models before modifying any SQL

- [ ] T003 Review all multi-source silver models to catalog column name collisions. Document in `specs/028-silver-column-retention/collision-map.md` which models need source-prefixed columns (per FR-004)

**Checkpoint**: Collision map ready — all silver model modifications can now proceed in parallel

---

## Phase 3: User Story 1 — Molecular Silver Single-Source Models (Priority: P1) 🎯 MVP

**Goal**: All single-source mol_silver models carry forward every bronze domain column

**Independent Test**: Run `scripts/audit_silver_columns.py` — zero gaps for all models in this phase

### Implementation for User Story 1

**Batch 1a: Drug & Chemical Data (14 models)**

- [ ] T004 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/drugbank.sql`
- [ ] T005 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/chembl.sql`
- [ ] T006 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/pubchem.sql`
- [ ] T007 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/fda_drugs.sql`
- [ ] T008 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/orange_book.sql`
- [ ] T009 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/dailymed_labels.sql`
- [ ] T010 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/rems_programs.sql`
- [ ] T011 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/ema.sql`
- [ ] T012 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/ema_regulatory.sql`
- [ ] T013 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/ema_regulatory_docs.sql`
- [ ] T014 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/nice_hta.sql`
- [ ] T015 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/ttd.sql`
- [ ] T016 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/rxnorm_concepts.sql`
- [ ] T017 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/pharmacogenomics.sql`

**Batch 1b: Bioactivity & Targets (10 models)**

- [ ] T018 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/bioactivity.sql`
- [ ] T019 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/binding_affinities.sql`
- [ ] T020 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/admet_properties.sql`
- [ ] T021 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/side_effects.sql`
- [ ] T022 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/drug_pharmacology.sql`
- [ ] T023 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/targets.sql`
- [ ] T024 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/protein_targets.sql`
- [ ] T025 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/proteins.sql`
- [ ] T026 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/protein_structures.sql`
- [ ] T027 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/pathways.sql`

**Batch 1c: Clinical & Research (10 models)**

- [ ] T028 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/clinical_trials.sql`
- [ ] T029 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/ct_gov_indication_stats.sql`
- [ ] T030 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/cochrane_reviews.sql`
- [ ] T031 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/pubmed_articles.sql`
- [ ] T032 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/publications.sql`
- [ ] T033 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/publication_evidence.sql`
- [ ] T034 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/research_grants.sql`
- [ ] T035 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/researchers.sql`
- [ ] T036 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/journal_rss.sql`
- [ ] T037 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/news_signals.sql`

**Batch 1d: Entity Resolution & Bridges (8 models)**

- [ ] T038 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/molecules.sql`
- [ ] T039 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/molecule_aliases.sql`
- [ ] T040 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/molecule_targets.sql`
- [ ] T041 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/molecule_publications.sql`
- [ ] T042 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/identifier_mappings.sql`
- [ ] T043 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/drug_synonyms.sql`
- [ ] T044 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/ndc_molecule_bridge.sql`
- [ ] T045 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/hcpcs_molecule_bridge.sql`

**Batch 1e: IP, Finance & Misc (14 models)**

- [ ] T046 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/patents.sql`
- [ ] T047 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/patent_exclusivities.sql`
- [ ] T048 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/trademarks.sql`
- [ ] T049 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/trademark_status_changes.sql`
- [ ] T050 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/euipo_designs.sql`
- [ ] T051 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/company_financials.sql`
- [ ] T052 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/financial_data.sql`
- [ ] T053 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/regulatory_decisions.sql`
- [ ] T054 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/regulatory_milestones.sql`
- [ ] T055 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/drug_spending.sql`
- [ ] T056 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/physician_payments.sql`
- [ ] T057 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/physician_profiles.sql`
- [ ] T058 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/web_content.sql`
- [ ] T059 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql`

**Batch 1f: Vocabulary & Reference (10 models)**

- [ ] T060 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/cdc_vaccines.sql`
- [ ] T061 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/imgt.sql`
- [ ] T062 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/who_inn_names.sql`
- [ ] T063 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/icd_codes.sql`
- [ ] T064 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/icd10_indicator_mapping.sql`
- [ ] T065 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/indication_ontology.sql`
- [ ] T066 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/indication_revenue.sql`
- [ ] T067 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/cms_coverage.sql`
- [ ] T068 [P] [US1] Add missing bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/cms_medicare.sql`
- [ ] T069 [US1] Run audit script to verify zero gaps for all 66 mol_silver models

**Checkpoint**: All mol_silver single-source models carry forward all bronze columns

---

## Phase 4: User Story 2 — Healthcare Silver Models (Priority: P1)

**Goal**: All hcs_silver models (including multi-source aggregation models) carry forward all bronze domain columns

**Independent Test**: Run `scripts/audit_silver_columns.py` — zero gaps for all hcs_silver models

### Implementation for User Story 2

**Batch 2a: Single-source CMS pass-throughs (17 models)**

- [ ] T070 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_care_compare.sql`
- [ ] T071 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_chow.sql`
- [ ] T072 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_cost_reports_puf_lines.sql`
- [ ] T073 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_dmepos.sql`
- [ ] T074 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_formulary.sql`
- [ ] T075 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_hospital_affiliation.sql`
- [ ] T076 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_hospital_info.sql`
- [ ] T077 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_hospital_quality.sql`
- [ ] T078 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_magnet.sql`
- [ ] T079 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_ndc.sql`
- [ ] T080 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_pecos.sql`
- [ ] T081 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_physician_puf_services.sql`
- [ ] T082 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_pos.sql`
- [ ] T083 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_post_acute.sql`
- [ ] T084 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_rbcs.sql`
- [ ] T085 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_stabilis.sql`
- [ ] T086 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_usp.sql`

**Batch 2b: Multi-source & cross-domain models (10 models)**

- [ ] T087 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_facility_profile.sql` — multi-source aggregation, add all upstream columns with source prefix per collision-map
- [ ] T088 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/cms_drug_market.sql`
- [ ] T089 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/drug_utilization.sql`
- [ ] T090 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/part_d_prescribing.sql`
- [ ] T091 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/open_payments_drug_linkage.sql`
- [ ] T092 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/facility_profile.sql`
- [ ] T093 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/geographic_health.sql`
- [ ] T094 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/healthcare_facilities.sql`
- [ ] T095 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/provider_profile.sql`
- [ ] T096 [P] [US2] Add missing bronze columns to `src/dk_data/sqlmesh/models/hcs/silver/ref_nucc_taxonomy.sql`
- [ ] T097 [US2] Run audit script to verify zero gaps for all 27 hcs_silver models

**Checkpoint**: All hcs_silver models carry forward all bronze columns

---

## Phase 5: User Story 3 — Adverse Events & Indication Models (Priority: P2)

**Goal**: adverse_events model includes all individual-level FAERS/SIDER columns; ind_silver models complete

**Independent Test**: Run audit script — zero gaps for adverse_events, epidemiology, icd11_ontology

### Implementation for User Story 3

- [ ] T098 [P] [US3] Add missing FAERS and SIDER bronze columns to `src/dk_data/sqlmesh/models/molecules/silver/adverse_events.sql` — include individual report fields (patient demographics, drug characterization, reporter details) alongside existing aggregation
- [ ] T099 [P] [US3] Add missing bronze columns to `src/dk_data/sqlmesh/models/ind/silver/epidemiology.sql`
- [ ] T100 [P] [US3] Add missing bronze columns to `src/dk_data/sqlmesh/models/ind/silver/icd11_ontology.sql`
- [ ] T101 [US3] Run audit script to verify zero gaps for adverse_events and ind_silver models

**Checkpoint**: All 95 silver models carry forward all bronze domain columns

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and cleanup

- [ ] T102 Run full audit script across all 95 silver models — verify zero total gaps
- [ ] T103 Update `transform_molecules.py` LAYER_MODELS dict if any new silver models were added to accommodate column additions
- [ ] T104 Commit all changes and push to `028-silver-column-retention` branch
- [ ] T105 Create PR to main with summary of models modified and columns added

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on T001 (audit script)
- **US1 (Phase 3)**: Depends on T003 (collision map) for multi-source models only; single-source models can start after T001
- **US2 (Phase 4)**: Depends on T003 (collision map); can run in parallel with US1
- **US3 (Phase 5)**: Depends on T003 (collision map); can run in parallel with US1/US2
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (mol_silver)**: Independent — can start after Phase 2
- **US2 (hcs_silver)**: Independent — can start after Phase 2
- **US3 (adverse_events + ind_silver)**: Independent — can start after Phase 2

### Parallel Opportunities

All tasks within each user story marked [P] modify different SQL files and can run in parallel. The 3 user stories are fully independent and can be worked on simultaneously.

Maximum parallelism: up to 66 tasks at once (all single-file modifications in US1 batch 1a-1f)

---

## Parallel Example: User Story 1 Batch 1a

```bash
# All 14 drug/chemical silver models can be modified simultaneously:
Task: "Add missing bronze columns to drugbank.sql"
Task: "Add missing bronze columns to chembl.sql"
Task: "Add missing bronze columns to pubchem.sql"
Task: "Add missing bronze columns to fda_drugs.sql"
# ... all 14 in parallel
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Audit script
2. Complete Phase 2: Collision map
3. Complete Phase 3: All 66 mol_silver models
4. **STOP and VALIDATE**: Run audit — zero gaps for mol_silver
5. Commit and push

### Incremental Delivery

1. Setup + Foundational → Tooling ready
2. Add US1 (mol_silver) → Validate → Commit (MVP)
3. Add US2 (hcs_silver) → Validate → Commit
4. Add US3 (adverse_events + ind) → Validate → Commit
5. Polish → PR

---

## Notes

- Each task reads the bronze model SQL file to identify columns, then adds missing ones to the silver SELECT
- JSONB columns (arrays, objects) are carried as-is — no flattening
- Excluded columns: `raw_json`, `raw_source_id`, `processed_to_bronze`, `processed_to_silver`, `_bronze_loaded_at`, bronze `id`, bronze `created_at`
- Source tracking columns (`source`, `_source_year`, `_source_hash`) ARE carried to silver
- For multi-source models, prefix colliding column names with source name
- Commit after each batch to keep diffs manageable
