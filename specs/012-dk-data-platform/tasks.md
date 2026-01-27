# Tasks: DK Molecule Data Platform (012)

**Input**: `/Users/pschloz/Desktop/DataKinetic/trials-predictor/.specify/specs/012-dk-data-platform/spec.md`
**Generated**: 2026-01-23
**Total User Stories**: 14 (8 P1, 4 P2, 2 P3)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1.1, US2.1)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Project Infrastructure)

**Purpose**: Initialize project structure and shared infrastructure

- [ ] T001 Create feature branch `012-dk-data-platform` from main
- [ ] T002 [P] Create Bronze layer database migrations in `app/backend/src/data/migrations/030_bronze_tables.sql`
- [ ] T003 [P] Create Silver layer database migrations in `app/backend/src/data/migrations/031_silver_tables.sql`
- [ ] T004 [P] Create Gold layer database migrations in `app/backend/src/data/migrations/032_gold_tables.sql`
- [ ] T005 [P] Create Application layer database migrations in `app/backend/src/data/migrations/033_onboarding_tables.sql`
- [ ] T006 Enable pg_trgm extension for fuzzy matching in `app/backend/src/data/migrations/034_enable_extensions.sql`
- [ ] T007 [P] Create SQLMesh project structure in `app/backend/sqlmesh/`
- [ ] T008 [P] Configure Prometheus metrics endpoint in `app/backend/src/api/routes/metrics.py`

**Checkpoint**: Database schema and project structure ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core services that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T009 Create IdentifierResolver service in `app/backend/src/services/data_platform/identifier_resolver.py`
- [ ] T010 [P] Create DataSourceConfig model in `app/backend/src/models/data_platform/data_source.py`
- [ ] T011 [P] Create MoleculeIdentifier model in `app/backend/src/models/data_platform/molecule.py`
- [ ] T012 Implement fuzzy name matching with pg_trgm in `app/backend/src/services/data_platform/fuzzy_matcher.py`
- [ ] T013 [P] Create base Bronze table model in `app/backend/src/models/data_platform/bronze_base.py`
- [ ] T014 [P] Create base Silver table model in `app/backend/src/models/data_platform/silver_base.py`
- [ ] T015 [P] Create base Gold table model in `app/backend/src/models/data_platform/gold_base.py`
- [ ] T016 Implement JWT authentication service in `app/backend/src/services/auth/jwt_service.py`
- [ ] T017 Implement RBAC middleware in `app/backend/src/api/middleware/rbac.py`
- [ ] T018 Create API error handlers in `app/backend/src/api/errors/data_platform_errors.py`
- [ ] T019 [P] Configure structured JSON logging in `app/backend/src/core/logging.py`

**Checkpoint**: Foundation ready - user story implementation can begin

---

## Phase 3: User Story 1.1 - Ingest New Data Source (Priority: P1) 🎯 MVP

**Goal**: Data engineer can add a new external data source storing raw responses in Bronze

**Independent Test**: Register ClinicalTrials.gov API, trigger ingestion, verify raw JSON in bronze_clinicaltrials

### Implementation for US 1.1

- [ ] T020 [P] [US1.1] Create DataSourceRegistry service in `app/backend/src/services/data_platform/data_source_registry.py`
- [ ] T021 [P] [US1.1] Create BronzeIngestionService in `app/backend/src/services/data_platform/bronze_ingestion.py`
- [ ] T022 [US1.1] Implement retry logic with exponential backoff in `app/backend/src/services/data_platform/retry_handler.py`
- [ ] T023 [US1.1] Create bronze_clinicaltrials table model in `app/backend/src/models/bronze/clinicaltrials.py`
- [ ] T024 [P] [US1.1] Create bronze_openfda_labels table model in `app/backend/src/models/bronze/openfda_labels.py`
- [ ] T025 [P] [US1.1] Create bronze_openfda_faers table model in `app/backend/src/models/bronze/openfda_faers.py`
- [ ] T026 [P] [US1.1] Create bronze_chembl table model in `app/backend/src/models/bronze/chembl.py`
- [ ] T027 [P] [US1.1] Create bronze_drugbank table model in `app/backend/src/models/bronze/drugbank.py`
- [ ] T028 [US1.1] Create Bronze API router in `app/backend/src/api/routes/bronze.py`
- [ ] T029 [US1.1] Implement 90-day retention cleanup job in `app/backend/src/services/data_platform/retention_manager.py`
- [ ] T030 [US1.1] Add ingestion metrics (records_total, duration_seconds) in bronze_ingestion.py

**Checkpoint**: Data sources can be registered and raw data ingested to Bronze

---

## Phase 4: User Story 2.1 - Transform Bronze to Silver (Priority: P1)

**Goal**: Analyst sees normalized, deduplicated data from multiple sources in consistent schema

**Independent Test**: Run transformation on bronze_clinicaltrials, verify normalized records in silver_clinical_trials

### Implementation for US 2.1

- [ ] T031 [P] [US2.1] Create SilverTransformationService in `app/backend/src/services/data_platform/silver_transformation.py`
- [ ] T032 [P] [US2.1] Create silver_clinical_trials table model in `app/backend/src/models/silver/clinical_trials.py`
- [ ] T033 [P] [US2.1] Create silver_drug_labels table model in `app/backend/src/models/silver/drug_labels.py`
- [ ] T034 [P] [US2.1] Create silver_adverse_events table model in `app/backend/src/models/silver/adverse_events.py`
- [ ] T035 [P] [US2.1] Create silver_molecules table model in `app/backend/src/models/silver/molecules.py`
- [ ] T036 [US2.1] Implement deduplication logic using raw_data_hash in silver_transformation.py
- [ ] T037 [US2.1] Create SQLMesh model for clinicaltrials transformation in `app/backend/sqlmesh/models/silver/clinical_trials.sql`
- [ ] T038 [US2.1] Create transformation error handling with Bronze preservation in silver_transformation.py
- [ ] T039 [US2.1] Add transformation logging (before/after counts, errors) in silver_transformation.py

**Checkpoint**: Bronze-to-Silver transformation pipeline operational

---

## Phase 5: User Story 2.2 - Entity Resolution Across Sources (Priority: P1)

**Goal**: Data scientist can link molecule data across ChEMBL, DrugBank, and PubChem via single molecule_id

**Independent Test**: Query "aspirin" and receive unified profile with data from all sources linked by InChI Key

### Implementation for US 2.2

- [ ] T040 [P] [US2.2] Create silver_identifier_mappings table model in `app/backend/src/models/silver/identifier_mappings.py`
- [ ] T041 [P] [US2.2] Create silver_molecule_aliases table model in `app/backend/src/models/silver/molecule_aliases.py`
- [ ] T042 [US2.2] Implement InChI Key resolution via RDKit in `app/backend/src/services/data_platform/inchi_resolver.py`
- [ ] T043 [US2.2] Implement external API cross-reference (PubChem, ChEMBL, UniChem) in `app/backend/src/services/data_platform/external_resolver.py`
- [ ] T044 [US2.2] Implement confidence scoring for resolution results in identifier_resolver.py
- [ ] T045 [US2.2] Create identifier type auto-detection (regex patterns) in identifier_resolver.py
- [ ] T046 [US2.2] Handle biologics fallback (UniProt ID → DrugBank ID → UNII) in identifier_resolver.py
- [ ] T047 [US2.2] Create resolution API endpoint in `app/backend/src/api/routes/resolution.py`

**Checkpoint**: Cross-source entity resolution working with confidence scores

---

## Phase 6: User Story 3.1 - Query Gold for Decision Support (Priority: P1)

**Goal**: User queries Gold layer for pre-aggregated, decision-ready molecule profiles

**Independent Test**: Query gold_molecule_profile for "imatinib" and receive complete profile in <1 second

### Implementation for US 3.1

- [ ] T048 [P] [US3.1] Create gold_molecule_profile table model in `app/backend/src/models/gold/molecule_profile.py`
- [ ] T049 [P] [US3.1] Create gold_competitive_landscape table model in `app/backend/src/models/gold/competitive_landscape.py`
- [ ] T050 [P] [US3.1] Create gold_safety_signals table model in `app/backend/src/models/gold/safety_signals.py`
- [ ] T051 [US3.1] Create GoldAggregationService in `app/backend/src/services/data_platform/gold_aggregation.py`
- [ ] T052 [US3.1] Create SQLMesh model for molecule profile in `app/backend/sqlmesh/models/gold/molecule_profile.sql`
- [ ] T053 [US3.1] Create Gold API router in `app/backend/src/api/routes/gold.py`
- [ ] T054 [US3.1] Implement data completeness scoring in gold_aggregation.py

**Checkpoint**: Gold layer queries return decision-ready data in sub-second

---

## Phase 7: User Story 3.2 - Lifecycle Stage Detection (Priority: P1)

**Goal**: System auto-detects molecule lifecycle stage based on evidence in Silver layer

**Independent Test**: Add Phase 3 trial to Silver, verify molecule lifecycle updates to "Phase 3" with confidence score

### Implementation for US 3.2

- [ ] T055 [P] [US3.2] Create gold_lifecycle_stages table model in `app/backend/src/models/gold/lifecycle_stages.py`
- [ ] T056 [P] [US3.2] Create gold_lifecycle_evidence table model in `app/backend/src/models/gold/lifecycle_evidence.py`
- [ ] T057 [US3.2] Create LifecycleDetectionService in `app/backend/src/services/data_platform/lifecycle_detection.py`
- [ ] T058 [US3.2] Implement evidence-to-stage mapping rules in lifecycle_detection.py
- [ ] T059 [US3.2] Implement confidence scoring for lifecycle detection in lifecycle_detection.py
- [ ] T060 [US3.2] Create lifecycle API endpoints in `app/backend/src/api/routes/lifecycle.py`

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

## Phase 15: User Story 6.2 - Run Incremental Updates (Priority: P2)

**Goal**: Data ops can trigger incremental pipeline updates processing only new/changed records

**Independent Test**: Run incremental update, verify only new Bronze records transformed to Silver

### Implementation for US 6.2

- [ ] T098 [US6.2] Implement incremental processing logic in silver_transformation.py
- [ ] T099 [US6.2] Add change detection using raw_data_hash in bronze_ingestion.py
- [ ] T100 [US6.2] Create SQLMesh incremental model support in sqlmesh/
- [ ] T101 [US6.2] Add incremental update API endpoints in monitoring.py
- [ ] T102 [US6.2] Implement full refresh mode for reconciliation

**Checkpoint**: Incremental and full refresh pipeline modes operational

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

## Phase 18: Polish & Cross-Cutting Concerns

**Purpose**: Improvements affecting multiple user stories

- [ ] T111 [P] Add OpenAPI documentation for all endpoints in `app/backend/src/api/openapi.py`
- [ ] T112 [P] Create end-to-end integration tests in `app/backend/tests/integration/test_data_platform.py`
- [ ] T113 Performance optimization for Gold layer queries
- [ ] T114 Security audit for credential storage and RBAC
- [ ] T115 [P] Create quickstart guide in `app/backend/docs/data_platform_quickstart.md`
- [ ] T116 Run full pipeline validation with sample data

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) → Phase 2 (Foundation) → Phases 3-11 (P1 Stories) → Phases 12-16 (P2) → Phase 17 (P3) → Phase 18 (Polish)
```

### User Story Dependencies

| Story | Depends On | Can Parallel With |
|-------|------------|-------------------|
| US 1.1 (Bronze Ingestion) | Foundation | - |
| US 2.1 (Bronze→Silver) | US 1.1 | - |
| US 2.2 (Entity Resolution) | US 2.1 | - |
| US 3.1 (Gold Query) | US 2.2 | US 3.2 |
| US 3.2 (Lifecycle Detection) | US 2.2 | US 3.1 |
| US 4.1 (Onboard Molecule) | US 3.1, US 3.2 | US 4.2, US 4.3 |
| US 4.2 (View Evidence) | US 3.2 | US 4.1, US 4.3 |
| US 4.3 (Validate Stage) | US 4.2 | - |
| US 7.1 (IVA Scan) | Foundation | Any |
| US 1.2 (Auto Schema) | US 1.1 | - |
| US 4.4 (Alerts) | US 4.1 | US 6.1, US 6.2 |
| US 6.1 (Monitor) | US 2.1 | US 6.2 |
| US 6.2 (Incremental) | US 2.1 | US 6.1 |
| US 7.2 (Pub Monitor) | US 7.1, US 4.4 | - |
| US 4.5 (Bulk Onboard) | US 4.1 | - |

### Critical Path (MVP)

```
Setup → Foundation → US 1.1 → US 2.1 → US 2.2 → US 3.1 + US 3.2 → US 4.1
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Tasks** | 116 |
| **P1 User Stories** | 8 |
| **P2 User Stories** | 4 |
| **P3 User Stories** | 2 |
| **Parallel Opportunities** | 35 tasks marked [P] |
| **MVP Scope** | Phases 1-8 (US 1.1 through US 4.1) |

### Suggested MVP Delivery

1. **Week 1-2**: Setup + Foundation + US 1.1 (Bronze Ingestion)
2. **Week 3-4**: US 2.1 + US 2.2 (Silver Layer + Entity Resolution)
3. **Week 5-6**: US 3.1 + US 3.2 (Gold Layer + Lifecycle Detection)
4. **Week 7-8**: US 4.1 (Molecule Onboarding Application)

**MVP Checkpoint**: Users can onboard molecules with auto-detected lifecycle stages from unified data platform
