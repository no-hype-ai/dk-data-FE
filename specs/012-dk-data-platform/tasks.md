# Tasks: DK Molecule Data Platform (012)

**Input**: `/Users/pschloz/Desktop/DataKinetic/dk-data-FE/specs/012-dk-data-platform/spec.md`
**Generated**: 2026-01-23
**Updated**: 2026-01-24 (Post-Clarification)
**Total User Stories**: 15 (9 P1, 4 P2, 2 P3)

## Clarification Decisions Incorporated

| Decision | Implementation Impact |
|----------|----------------------|
| RTO 1hr / RPO 15min | pgBackRest with WAL archiving, warm standby |
| DrugBank > ChEMBL > PubChem | Source precedence in entity resolution |
| Tiered Freshness | Daily/Weekly/Monthly CronJobs per source |
| Quarantine Workflow | `needs_review` flag, resolution queue UI |
| E2E Testing | Golden datasets, pipeline integration tests |
| PostgREST for Gold | Auto-generated REST API, RLS policies |

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US0.1, US1.1)
- Include exact file paths in descriptions

---

## Phase 0: Raw Layer (API Response Archive)

**Purpose**: Store unmodified API responses for audit/compliance/reprocessing

- [ ] T001 [P] [US0.1] Create Raw layer database migrations in `migrations/020_raw_tables.sql`
- [ ] T002 [P] [US0.1] Create raw_clinicaltrials table with JSONB response_body
- [ ] T003 [P] [US0.1] Create raw_openfda_faers table
- [ ] T004 [P] [US0.1] Create raw_openfda_labels table
- [ ] T005 [P] [US0.1] Create raw_chembl table
- [ ] T006 [P] [US0.1] Create raw_drugbank table
- [ ] T007 [P] [US0.1] Create raw_pubchem table
- [ ] T008 [P] [US0.1] Create raw_uniprot table
- [ ] T009 [P] [US0.1] Create raw_pdb table
- [ ] T010 [P] [US0.1] Create raw_sider table
- [ ] T011 [P] [US0.1] Create raw_openalex table
- [ ] T012 [US0.1] Implement RawIngestionService with HTTP context preservation in `src/services/raw_ingestion.py`
- [ ] T013 [US0.1] Add response_body_hash for change detection

**Checkpoint**: All 10 Raw tables created, HTTP responses archived with full context

---

## Phase 1: Setup (Project Infrastructure)

**Purpose**: Initialize project structure and shared infrastructure

- [ ] T014 Create feature branch `012-dk-data-platform` from main
- [ ] T015 [P] Create Bronze layer database migrations in `migrations/030_bronze_tables.sql`
- [ ] T016 [P] Create Silver layer database migrations in `migrations/031_silver_tables.sql`
- [ ] T017 [P] Create Gold layer database migrations in `migrations/032_gold_tables.sql`
- [ ] T018 [P] Create Application layer database migrations in `migrations/033_application_tables.sql`
- [ ] T019 Enable pg_trgm extension for fuzzy matching in `migrations/034_enable_extensions.sql`
- [ ] T020 [P] Create SQLMesh project structure in `sqlmesh/`
- [ ] T021 [P] Configure Prometheus metrics endpoint in `src/api/routes/metrics.py`
- [ ] T022 [P] Configure pgBackRest for WAL archiving (RTO 1hr, RPO 15min) in `config/pgbackrest.conf`
- [ ] T023 [P] Create PostgREST configuration for Gold layer in `config/postgrest.conf`

**Checkpoint**: Database schema, backup, and project structure ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core services that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T024 Create IdentifierResolver service with source precedence (DrugBank > ChEMBL > PubChem) in `src/services/identifier_resolver.py`
- [ ] T025 [P] Create DataSourceConfig model in `src/models/data_source.py`
- [ ] T026 [P] Create MoleculeIdentifier model in `src/models/molecule.py`
- [ ] T027 Implement fuzzy name matching with pg_trgm (threshold 0.3) in `src/services/fuzzy_matcher.py`
- [ ] T028 [P] Create base Raw table model in `src/models/raw_base.py`
- [ ] T029 [P] Create base Bronze table model in `src/models/bronze_base.py`
- [ ] T030 [P] Create base Silver table model in `src/models/silver_base.py`
- [ ] T031 [P] Create base Gold table model in `src/models/gold_base.py`
- [ ] T032 Implement JWT authentication service in `src/services/auth/jwt_service.py`
- [ ] T033 Implement RBAC middleware (viewer, analyst, data_ops, admin) in `src/api/middleware/rbac.py`
- [ ] T034 Create API error handlers in `src/api/errors/data_platform_errors.py`
- [ ] T035 [P] Configure structured JSON logging in `src/core/logging.py`
- [ ] T036 [P] Create PostgreSQL Row-Level Security policies in `migrations/035_rls_policies.sql`

**Checkpoint**: Foundation ready - user story implementation can begin

---

## Phase 3: User Story 1.1 - Ingest to Raw and Bronze (Priority: P1) 🎯 MVP

**Goal**: Data engineer can add a new external data source storing raw responses in Raw layer, parsed to Bronze

**Independent Test**: Register ClinicalTrials.gov API, trigger ingestion, verify raw JSON in raw_clinicaltrials and typed columns in bronze_clinicaltrials

### Implementation for US 1.1

- [ ] T037 [P] [US1.1] Create DataSourceRegistry service in `src/services/data_source_registry.py`
- [ ] T038 [P] [US1.1] Create BronzeIngestionService (Raw → Bronze extraction) in `src/services/bronze_ingestion.py`
- [ ] T039 [US1.1] Implement retry logic with exponential backoff in `src/services/retry_handler.py`
- [ ] T040 [US1.1] Create bronze_clinicaltrials table model with typed columns in `src/models/bronze/clinicaltrials.py`
- [ ] T041 [P] [US1.1] Create bronze_openfda_labels table model in `src/models/bronze/openfda_labels.py`
- [ ] T042 [P] [US1.1] Create bronze_openfda_faers table model in `src/models/bronze/openfda_faers.py`
- [ ] T043 [P] [US1.1] Create bronze_chembl table model in `src/models/bronze/chembl.py`
- [ ] T044 [P] [US1.1] Create bronze_drugbank table model in `src/models/bronze/drugbank.py`
- [ ] T045 [P] [US1.1] Create bronze_pubchem table model in `src/models/bronze/pubchem.py`
- [ ] T046 [P] [US1.1] Create bronze_uniprot table model in `src/models/bronze/uniprot.py`
- [ ] T047 [P] [US1.1] Create bronze_pdb table model in `src/models/bronze/pdb.py`
- [ ] T048 [P] [US1.1] Create bronze_sider table model in `src/models/bronze/sider.py`
- [ ] T049 [P] [US1.1] Create bronze_openalex table model in `src/models/bronze/openalex.py`
- [ ] T050 [US1.1] Create Bronze API router in `src/api/routes/bronze.py`
- [ ] T051 [US1.1] Add ingestion metrics (records_total, duration_seconds) in bronze_ingestion.py

**Checkpoint**: Data sources can be registered, raw responses archived, and Bronze tables populated

---

## Phase 4: User Story 2.1 - Transform Bronze to Silver (Priority: P1)

**Goal**: Analyst sees normalized, deduplicated data from multiple sources in consistent schema

**Independent Test**: Run transformation on bronze_clinicaltrials, verify normalized records in silver_clinical_trials

### Implementation for US 2.1

- [ ] T052 [P] [US2.1] Create SilverTransformationService in `src/services/silver_transformation.py`
- [ ] T053 [P] [US2.1] Create silver_clinical_trials table model in `src/models/silver/clinical_trials.py`
- [ ] T054 [P] [US2.1] Create silver_drug_labels table model in `src/models/silver/drug_labels.py`
- [ ] T055 [P] [US2.1] Create silver_adverse_events table model in `src/models/silver/adverse_events.py`
- [ ] T056 [P] [US2.1] Create silver_molecules table model with `needs_review` flag in `src/models/silver/molecules.py`
- [ ] T057 [P] [US2.1] Create silver_bioactivity table model in `src/models/silver/bioactivity.py`
- [ ] T058 [P] [US2.1] Create silver_targets table model in `src/models/silver/targets.py`
- [ ] T059 [P] [US2.1] Create silver_publications table model in `src/models/silver/publications.py`
- [ ] T060 [P] [US2.1] Create silver_patents table model in `src/models/silver/patents.py`
- [ ] T061 [US2.1] Implement deduplication logic using record_hash in silver_transformation.py
- [ ] T062 [US2.1] Create SQLMesh model for clinicaltrials transformation in `sqlmesh/models/silver/clinical_trials.sql`
- [ ] T063 [US2.1] Create transformation error handling with Bronze preservation in silver_transformation.py
- [ ] T064 [US2.1] Add transformation logging (before/after counts, errors) in silver_transformation.py

**Checkpoint**: Bronze-to-Silver transformation pipeline operational

---

## Phase 5: User Story 2.2 - Entity Resolution with Quarantine (Priority: P1)

**Goal**: Data scientist can link molecule data across sources via InChI Key; low-confidence records are quarantined

**Independent Test**: Query "aspirin" → unified profile; query ambiguous name → record marked `needs_review=true`

### Implementation for US 2.2

- [ ] T065 [P] [US2.2] Create silver_identifier_mappings table model in `src/models/silver/identifier_mappings.py`
- [ ] T066 [P] [US2.2] Create silver_molecule_aliases table model in `src/models/silver/molecule_aliases.py`
- [ ] T067 [US2.2] Implement InChI Key resolution via RDKit in `src/services/inchi_resolver.py`
- [ ] T068 [US2.2] Implement external API cross-reference (PubChem, ChEMBL, UniChem) in `src/services/external_resolver.py`
- [ ] T069 [US2.2] Implement confidence scoring (threshold 0.8 for quarantine) in identifier_resolver.py
- [ ] T070 [US2.2] Implement source precedence merge (DrugBank > ChEMBL > PubChem) in identifier_resolver.py
- [ ] T071 [US2.2] Create identifier type auto-detection (regex patterns) in identifier_resolver.py
- [ ] T072 [US2.2] Handle biologics fallback (UniProt ID → DrugBank ID → UNII) in identifier_resolver.py
- [ ] T073 [US2.2] Create resolution API endpoint in `src/api/routes/resolution.py`
- [ ] T074 [US2.2] Implement quarantine queue for low-confidence records in `src/services/resolution_queue.py`
- [ ] T075 [US2.2] Create resolution queue API endpoint in `src/api/routes/resolution_queue.py`

**Checkpoint**: Cross-source entity resolution with quarantine workflow for <0.8 confidence

---

## Phase 6: User Story 3.1 - Query Gold via PostgREST (Priority: P1)

**Goal**: User queries Gold layer for pre-aggregated, decision-ready molecule profiles via auto-generated REST API

**Independent Test**: Query `/gold_molecule_profile?name=eq.imatinib` via PostgREST, receive complete profile in <200ms

### Implementation for US 3.1

- [ ] T076 [P] [US3.1] Create gold_molecule_profile view (excludes needs_review=true) in `migrations/040_gold_views.sql`
- [ ] T077 [P] [US3.1] Create gold_competitive_landscape view in `migrations/040_gold_views.sql`
- [ ] T078 [P] [US3.1] Create gold_safety_signals view in `migrations/040_gold_views.sql`
- [ ] T079 [P] [US3.1] Create gold_company_pipeline view in `migrations/040_gold_views.sql`
- [ ] T080 [US3.1] Create GoldAggregationService in `src/services/gold_aggregation.py`
- [ ] T081 [US3.1] Create SQLMesh model for molecule profile in `sqlmesh/models/gold/molecule_profile.sql`
- [ ] T082 [US3.1] Configure PostgREST with Gold schema in `config/postgrest.conf`
- [ ] T083 [US3.1] Create Row-Level Security policies for Gold views in `migrations/041_gold_rls.sql`
- [ ] T084 [US3.1] Implement fuzzy search RPC function in `migrations/042_search_functions.sql`
- [ ] T085 [US3.1] Implement data completeness scoring in gold_aggregation.py
- [ ] T086 [US3.1] Create custom search endpoint (fuzzy) in `src/api/routes/search.py`

**Checkpoint**: Gold layer queries return decision-ready data via PostgREST in <200ms

---

## Phase 7: User Story 3.2 - Lifecycle Stage Detection (Priority: P1)

**Goal**: System auto-detects molecule lifecycle stage based on evidence in Silver layer

**Independent Test**: Add Phase 3 trial to Silver, verify molecule lifecycle updates to "Phase 3" with confidence score

### Implementation for US 3.2

- [ ] T087 [P] [US3.2] Create gold_lifecycle_stages view in `migrations/040_gold_views.sql`
- [ ] T088 [P] [US3.2] Create gold_lifecycle_evidence view in `migrations/040_gold_views.sql`
- [ ] T089 [US3.2] Create LifecycleDetectionService in `src/services/lifecycle_detection.py`
- [ ] T090 [US3.2] Implement evidence-to-stage mapping rules in lifecycle_detection.py
- [ ] T091 [US3.2] Implement confidence scoring for lifecycle detection in lifecycle_detection.py
- [ ] T092 [US3.2] Create lifecycle API endpoints in `src/api/routes/lifecycle.py`

**Checkpoint**: Lifecycle stages auto-detected from Silver layer evidence

---

## Phase 8: User Story 4.1 - Onboard New Molecule (Priority: P1) 🎯 MVP

**Goal**: Analyst can add a new molecule by name/ID with auto-detected lifecycle stage and available data

**Independent Test**: Enter "Dupixent", system resolves to DB06674, shows lifecycle stage and data by source

### Implementation for US 4.1

- [ ] T061 [P] [US4.1] Create user_tracked_molecules table model in `app/backend/src/models/application/tracked_molecules.py`
- [ ] T062 [P] [US4.1] Create user_annotations table model in `app/backend/src/models/application/annotations.py`
- [ ] T063 [P] [US4.1] Create onboarding_audit_log table model in `app/backend/src/models/application/audit_log.py`
- [ ] T064 [US4.1] Create MoleculeOnboardingService in `app/backend/src/services/data_platform/molecule_onboarding.py`
- [ ] T065 [US4.1] Implement 10-step wizard state management in molecule_onboarding.py
- [ ] T066 [US4.1] Create onboarding API router in `app/backend/src/api/routes/onboarding.py`
- [ ] T067 [US4.1] Implement molecule name/ID resolution integration with IdentifierResolver
- [ ] T068 [US4.1] Add auto-save functionality for wizard steps in molecule_onboarding.py

**Checkpoint**: Users can onboard molecules with auto-detected lifecycle stages

---

## Phase 9: User Story 4.2 - View Lifecycle Stage Evidence (Priority: P1)

**Goal**: Regulatory analyst sees evidence supporting current lifecycle stage including gaps

**Independent Test**: View molecule at Phase 2, see required/present/missing evidence with source links

### Implementation for US 4.2

- [ ] T069 [US4.2] Create EvidenceRequirementService in `app/backend/src/services/data_platform/evidence_requirements.py`
- [ ] T070 [US4.2] Define evidence requirements per lifecycle stage in `app/backend/config/lifecycle_requirements.yaml`
- [ ] T071 [US4.2] Implement evidence gap detection in evidence_requirements.py
- [ ] T072 [US4.2] Create evidence API endpoints in `app/backend/src/api/routes/evidence.py`
- [ ] T073 [US4.2] Add source link generation for evidence citations in evidence_requirements.py

**Checkpoint**: Users can view evidence requirements and gaps for any molecule

---

## Phase 10: User Story 4.3 - Validate Stage and Progress (Priority: P1)

**Goal**: Data ops can validate molecule has sufficient evidence for claimed stage

**Independent Test**: Click "Validate Stage" on molecule with all requirements, see validation confirmed and logged

### Implementation for US 4.3

- [ ] T074 [US4.3] Create StageValidationService in `app/backend/src/services/data_platform/stage_validation.py`
- [ ] T075 [US4.3] Implement validation rules per lifecycle stage in stage_validation.py
- [ ] T076 [US4.3] Add audit logging for validation events in stage_validation.py
- [ ] T077 [US4.3] Create validation API endpoints in `app/backend/src/api/routes/validation.py`
- [ ] T078 [US4.3] Implement admin override capability for stage progression

**Checkpoint**: Stage validation with evidence verification operational

---

## Phase 11: User Story 7.1 - Scan for IVA-Relevant Publications (Priority: P1)

**Goal**: Scan and categorize publications by CEJ narrative pillar for evidence strengthening

**Independent Test**: Scan "Dupixent" publications, see results categorized by pillar with relevance scores

### Implementation for US 7.1

- [ ] T079 [US7.1] Verify iva_publications table exists (from previous implementation)
- [ ] T080 [US7.1] Verify IVA scan endpoint works in `app/backend/src/api/routes/iva_publications.py`
- [ ] T081 [US7.1] Integrate IVA publications with Gold layer molecule profiles
- [ ] T082 [US7.1] Add IVA evidence to lifecycle stage detection

**Checkpoint**: IVA publications integrated with data platform

---

## Phase 12: User Story 1.2 - Register Data Source with Auto-Schema Detection (Priority: P2)

**Goal**: Data ops can register new API with minimal config, system auto-detects schema

**Independent Test**: Provide new API URL and sample response, system creates Bronze table automatically

### Implementation for US 1.2

- [ ] T083 [US1.2] Implement JSON schema auto-detection in `app/backend/src/services/data_platform/schema_detector.py`
- [ ] T084 [US1.2] Create dynamic Bronze table generator in `app/backend/src/services/data_platform/table_generator.py`
- [ ] T085 [US1.2] Implement secure credential storage (AES-256) in `app/backend/src/services/data_platform/credential_store.py`
- [ ] T086 [US1.2] Create data source registration API in `app/backend/src/api/routes/data_sources.py`

**Checkpoint**: New data sources can be registered with auto-schema detection

---

## Phase 13: User Story 4.4 - Set Up Tracking Alerts (Priority: P2)

**Goal**: Portfolio manager can configure alerts for lifecycle events

**Independent Test**: Enable "Stage Transition" alert, trigger stage change, receive notification

### Implementation for US 4.4

- [ ] T087 [P] [US4.4] Create user_alert_configs table model in `app/backend/src/models/application/alert_configs.py`
- [ ] T088 [P] [US4.4] Create alert_history table model in `app/backend/src/models/application/alert_history.py`
- [ ] T089 [US4.4] Create AlertService in `app/backend/src/services/data_platform/alert_service.py`
- [ ] T090 [US4.4] Implement alert delivery (email, webhook, in-app) in alert_service.py
- [ ] T091 [US4.4] Create alert API endpoints in `app/backend/src/api/routes/alerts.py`
- [ ] T092 [US4.4] Implement digest delivery (daily, weekly) scheduling

**Checkpoint**: Users can configure and receive alerts for molecule events

---

## Phase 14: User Story 6.1 - Monitor Pipeline Health (Priority: P2)

**Goal**: Data ops can view dashboard showing pipeline health and transformation status

**Independent Test**: View monitoring dashboard, see all pipeline stages with success/error counts

### Implementation for US 6.1

- [ ] T093 [US6.1] Create PipelineMonitoringService in `app/backend/src/services/data_platform/pipeline_monitoring.py`
- [ ] T094 [US6.1] Create pipeline_runs table model in `app/backend/src/models/data_platform/pipeline_runs.py`
- [ ] T095 [US6.1] Implement pipeline health metrics (Prometheus) in pipeline_monitoring.py
- [ ] T096 [US6.1] Create monitoring API endpoints in `app/backend/src/api/routes/monitoring.py`
- [ ] T097 [US6.1] Create Grafana dashboard JSON in `app/backend/config/grafana/pipeline_health.json`

**Checkpoint**: Pipeline health monitoring dashboard operational

---

## Phase 15: User Story 6.2 - Tiered Automatic Sync (Priority: P2)

**Goal**: Data ops can configure tiered refresh schedules (daily/weekly/monthly) per source

**Independent Test**: Configure daily sync for ClinicalTrials.gov, verify automatic fetch at scheduled time

### Implementation for US 6.2

- [ ] T098 [US6.2] Implement incremental processing logic in silver_transformation.py
- [ ] T099 [US6.2] Add change detection using response_body_hash in raw_ingestion.py
- [ ] T100 [US6.2] Create SQLMesh incremental model support in sqlmesh/
- [ ] T101 [US6.2] Create Kubernetes CronJob for daily sync (ClinicalTrials, OpenFDA Labels) in `kubernetes/cronjobs/daily-sync.yaml`
- [ ] T102 [US6.2] Create Kubernetes CronJob for weekly sync (FAERS, OpenAlex) in `kubernetes/cronjobs/weekly-sync.yaml`
- [ ] T103 [US6.2] Create Kubernetes CronJob for monthly sync (ChEMBL, DrugBank, PubChem, UniProt, PDB, SIDER) in `kubernetes/cronjobs/monthly-sync.yaml`
- [ ] T104 [US6.2] Add incremental update API endpoints in monitoring.py
- [ ] T105 [US6.2] Implement full refresh mode for reconciliation

**Checkpoint**: Tiered automatic sync operational with incremental and full refresh modes

---

## Phase 16: User Story 7.2 - Monitor for New Publications (Priority: P2)

**Goal**: System continuously monitors for new IVA-relevant publications and alerts

**Independent Test**: Configure monitoring for drug, new publication appears, receive alert

### Implementation for US 7.2

- [ ] T103 [US7.2] Verify iva_monitoring_config table exists
- [ ] T104 [US7.2] Integrate publication monitoring with alert service
- [ ] T105 [US7.2] Add publication alerts to alert_history

**Checkpoint**: Publication monitoring integrated with platform alerts

---

## Phase 17: User Story 4.5 - Bulk Molecule Onboarding (Priority: P3)

**Goal**: Data team can onboard multiple molecules via spreadsheet upload

**Independent Test**: Upload CSV with 50 molecules, see processing status and success/failure report

### Implementation for US 4.5

- [ ] T106 [US4.5] Create BulkOnboardingService in `app/backend/src/services/data_platform/bulk_onboarding.py`
- [ ] T107 [US4.5] Implement CSV/Excel parsing in bulk_onboarding.py
- [ ] T108 [US4.5] Add async processing with progress tracking in bulk_onboarding.py
- [ ] T109 [US4.5] Create bulk upload API endpoints in onboarding.py
- [ ] T110 [US4.5] Implement error reporting for invalid entries

**Checkpoint**: Bulk onboarding via file upload operational

---

## Phase 18: E2E Testing & Golden Datasets

**Purpose**: End-to-end testing with real API samples per clarification decision

- [ ] T111 [P] Create golden dataset: Core 100 molecules with verified cross-references in `tests/fixtures/golden_core_100.json`
- [ ] T112 [P] Create golden dataset: Edge cases (stereoisomers, salts, prodrugs, biologics) in `tests/fixtures/golden_edge_cases.json`
- [ ] T113 [P] Create golden dataset: Conflict set (known data conflicts between sources) in `tests/fixtures/golden_conflicts.json`
- [ ] T114 [P] Create E2E test: Full pipeline Raw → Bronze → Silver → Gold in `tests/e2e/test_full_pipeline.py`
- [ ] T115 Create E2E test: Entity resolution accuracy on Core 100 (target: 95%+) in `tests/e2e/test_resolution_accuracy.py`
- [ ] T116 Create E2E test: Quarantine workflow for low-confidence records in `tests/e2e/test_quarantine.py`
- [ ] T117 [P] Create E2E test: PostgREST API response time (<200ms) in `tests/e2e/test_api_performance.py`
- [ ] T118 Create E2E test: Tiered sync scheduling validation in `tests/e2e/test_sync_schedule.py`

**Checkpoint**: E2E test suite with 95%+ resolution accuracy on golden datasets

---

## Phase 19: Polish & Cross-Cutting Concerns

**Purpose**: Improvements affecting multiple user stories

- [ ] T119 [P] PostgREST auto-generates OpenAPI from Gold schema
- [ ] T120 [P] Create custom search endpoint documentation in `docs/api/search.md`
- [ ] T121 Performance optimization for Gold layer queries (add indexes)
- [ ] T122 Security audit for credential storage and RBAC
- [ ] T123 [P] Validate quickstart.md guide works end-to-end
- [ ] T124 Run full pipeline validation with sample data
- [ ] T125 Create Grafana dashboards (pipeline health, data quality) in `config/grafana/`

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 0 (Raw) → Phase 1 (Setup) → Phase 2 (Foundation) → Phases 3-11 (P1 Stories) → Phases 12-16 (P2) → Phase 17 (P3) → Phase 18 (Polish)
```

### User Story Dependencies

| Story | Depends On | Can Parallel With |
|-------|------------|-------------------|
| US 0.1 (Raw Archive) | Setup | - |
| US 1.1 (Bronze Ingestion) | US 0.1, Foundation | - |
| US 2.1 (Bronze→Silver) | US 1.1 | - |
| US 2.2 (Entity Resolution + Quarantine) | US 2.1 | - |
| US 3.1 (Gold Query via PostgREST) | US 2.2 | US 3.2 |
| US 3.2 (Lifecycle Detection) | US 2.2 | US 3.1 |
| US 4.1 (Onboard Molecule) | US 3.1, US 3.2 | US 4.2, US 4.3 |
| US 4.2 (View Evidence) | US 3.2 | US 4.1, US 4.3 |
| US 4.3 (Validate Stage) | US 4.2 | - |
| US 7.1 (IVA Scan) | Foundation | Any |
| US 1.2 (Auto Schema) | US 1.1 | - |
| US 4.4 (Alerts) | US 4.1 | US 6.1, US 6.2 |
| US 6.1 (Monitor) | US 2.1 | US 6.2 |
| US 6.2 (Tiered Auto Sync) | US 0.1, US 2.1 | US 6.1 |
| US 7.2 (Pub Monitor) | US 7.1, US 4.4 | - |
| US 4.5 (Bulk Onboard) | US 4.1 | - |

### Critical Path (MVP)

```
Setup → US 0.1 (Raw) → Foundation → US 1.1 → US 2.1 → US 2.2 (+ Quarantine) → US 3.1 (PostgREST) + US 3.2 → US 4.1
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Tasks** | 130+ |
| **P1 User Stories** | 9 (including US 0.1 Raw Layer) |
| **P2 User Stories** | 4 |
| **P3 User Stories** | 2 |
| **Parallel Opportunities** | 45+ tasks marked [P] |
| **MVP Scope** | Phases 0-8 (US 0.1 through US 4.1) |

### Key Additions (Post-Clarification)

- **Phase 0**: Raw layer with complete HTTP response archiving
- **Quarantine Workflow**: Resolution queue for <0.8 confidence records
- **PostgREST**: Auto-generated REST API for Gold layer
- **Tiered Sync**: Daily/Weekly/Monthly CronJobs per source
- **RLS Policies**: Row-level security for viewer/analyst/data_ops/admin roles
- **pgBackRest**: WAL archiving for RTO 1hr / RPO 15min

### Suggested MVP Delivery

1. **Week 1-2**: Setup + Foundation + US 0.1 (Raw Layer) + US 1.1 (Bronze Ingestion)
2. **Week 3-4**: US 2.1 + US 2.2 (Silver Layer + Entity Resolution + Quarantine)
3. **Week 5-6**: US 3.1 + US 3.2 (Gold Layer via PostgREST + Lifecycle Detection)
4. **Week 7-8**: US 4.1 (Molecule Onboarding Application)

**MVP Checkpoint**: Users can onboard molecules with auto-detected lifecycle stages from unified data platform with full audit trail
