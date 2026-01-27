# Data Model: DK Molecule Data Platform

**Feature**: 012-dk-data-platform
**Created**: 2026-01-24
**Status**: Complete

---

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              ENTITY RELATIONSHIP DIAGRAM                                 │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  RAW LAYER                                                                               │
│  ─────────                                                                               │
│  ┌─────────────────┐                                                                     │
│  │ raw_{source}    │  One table per external source                                      │
│  │─────────────────│                                                                     │
│  │ id (PK)         │                                                                     │
│  │ response_body   │───────────────────────────────────────────────────────────────┐    │
│  │ request_*       │                                                                │    │
│  │ response_*      │                                                                │    │
│  └─────────────────┘                                                                │    │
│                                                                                     │    │
│  BRONZE LAYER                                                                       │    │
│  ────────────                                                                       │    │
│  ┌─────────────────┐                                                                │    │
│  │ bronze_{source} │◄────────────────────────────────────────────────────────────────    │
│  │─────────────────│  One table per external source                                      │
│  │ id (PK)         │  Source-native columns                                              │
│  │ raw_id (FK)     │──────────────────────────────────────────────────────┐              │
│  │ {source_cols}   │                                                      │              │
│  │ record_hash     │                                                      │              │
│  └─────────────────┘                                                      │              │
│                                                                           │              │
│  SILVER LAYER (Entity-Resolved)                                           │              │
│  ──────────────────────────────                                           │              │
│                                                                           │              │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐   │              │
│  │ silver_molecules│◄────▶│ silver_id_maps  │◄────▶│ silver_aliases  │   │              │
│  │─────────────────│      │─────────────────│      │─────────────────│   │              │
│  │ molecule_id (PK)│      │ mapping_id (PK) │      │ alias_id (PK)   │   │              │
│  │ inchi_key (UK)  │      │ molecule_id (FK)│      │ molecule_id (FK)│   │              │
│  │ chembl_id       │      │ identifier_type │      │ alias_name      │   │              │
│  │ drugbank_id     │      │ identifier_value│      │ alias_type      │   │              │
│  │ pubchem_cid     │      │ source          │      │ region          │   │              │
│  │ canonical_name  │      │ confidence      │      └─────────────────┘   │              │
│  │ needs_review    │      └─────────────────┘                            │              │
│  └────────┬────────┘                                                     │              │
│           │                                                              │              │
│           │ 1:N                                                          │              │
│           ▼                                                              │              │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐   │              │
│  │ silver_trials   │      │ silver_labels   │      │ silver_events   │◄──┘              │
│  │─────────────────│      │─────────────────│      │─────────────────│                  │
│  │ trial_id (PK)   │      │ label_id (PK)   │      │ event_id (PK)   │                  │
│  │ nct_id (UK)     │      │ set_id (UK)     │      │ source_report_id│                  │
│  │ molecule_id (FK)│      │ molecule_id (FK)│      │ molecule_id (FK)│                  │
│  │ phase           │      │ brand_name      │      │ reaction_meddra │                  │
│  │ status          │      │ indications     │      │ outcome         │                  │
│  └─────────────────┘      └─────────────────┘      └─────────────────┘                  │
│                                                                                          │
│  GOLD LAYER (Aggregated)                                                                │
│  ───────────────────────                                                                │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐                  │
│  │ gold_molecule   │      │ gold_competitive│      │ gold_safety     │                  │
│  │ _profile        │      │ _landscape      │      │ _signals        │                  │
│  │─────────────────│      │─────────────────│      │─────────────────│                  │
│  │ molecule_id (FK)│      │ indication      │      │ molecule_id (FK)│                  │
│  │ lifecycle_stage │      │ molecules[]     │      │ signal_type     │                  │
│  │ data_complete   │      │ market_share    │      │ prr_score       │                  │
│  │ confidence      │      │ pipeline_count  │      │ ror_score       │                  │
│  └─────────────────┘      └─────────────────┘      └─────────────────┘                  │
│                                                                                          │
│  APPLICATION LAYER                                                                       │
│  ─────────────────                                                                       │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐                  │
│  │ user_tracked    │      │ user_annotations│      │ alert_configs   │                  │
│  │ _molecules      │      │─────────────────│      │─────────────────│                  │
│  │─────────────────│      │ annotation_id   │      │ config_id (PK)  │                  │
│  │ tracking_id (PK)│      │ molecule_id (FK)│      │ user_id         │                  │
│  │ user_id         │      │ user_id         │      │ molecule_id (FK)│                  │
│  │ molecule_id (FK)│      │ annotation_type │      │ alert_type      │                  │
│  │ indication      │      │ content         │      │ threshold       │                  │
│  │ lifecycle_stage │      │ is_private      │      │ is_active       │                  │
│  └─────────────────┘      └─────────────────┘      └─────────────────┘                  │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Entities

### 1. Raw Layer Tables

#### raw_{source_name}
Stores unmodified API responses from external sources.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Unique record identifier |
| `request_id` | VARCHAR(100) | NOT NULL | Correlation ID for the request |
| `request_timestamp` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | When request was made |
| `api_endpoint` | VARCHAR(500) | NOT NULL | Full API endpoint URL |
| `api_version` | VARCHAR(20) | | API version if available |
| `request_params` | JSONB | | Query parameters sent |
| `request_headers` | JSONB | | Request headers (auth redacted) |
| `response_status` | INTEGER | NOT NULL | HTTP status code |
| `response_headers` | JSONB | | Response headers |
| `response_body` | JSONB | NOT NULL | Complete response body |
| `response_body_hash` | VARCHAR(64) | | SHA-256 for dedup |
| `response_size_bytes` | INTEGER | | Response size |
| `response_time_ms` | INTEGER | | API latency |
| `processed_to_bronze` | BOOLEAN | DEFAULT FALSE | Processing status |
| `processed_at` | TIMESTAMPTZ | | When processed |
| `processing_error` | TEXT | | Error message if failed |
| `ingested_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Ingestion timestamp |
| `source_id` | VARCHAR(50) | NOT NULL | Source identifier |

**Indexes**: request_id, request_timestamp, processed_to_bronze, response_body_hash

---

### 2. Bronze Layer Tables

#### bronze_{source_name}
Source-native typed columns. Example for ClinicalTrials.gov:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK | Unique record identifier |
| `raw_id` | UUID | FK → raw_clinicaltrials | Link to raw response |
| `nct_id` | VARCHAR(15) | NOT NULL, UNIQUE | ClinicalTrials.gov ID |
| `brief_title` | TEXT | | Trial title |
| `official_title` | TEXT | | Full official title |
| `overall_status` | VARCHAR(50) | | Recruiting, Completed, etc. |
| `phase` | VARCHAR(20) | | Phase 1, 2, 3, 4, N/A |
| `study_type` | VARCHAR(50) | | Interventional, Observational |
| `lead_sponsor_name` | VARCHAR(500) | | Sponsor organization |
| `enrollment_count` | INTEGER | | Target enrollment |
| `start_date` | DATE | | Trial start date |
| `completion_date` | DATE | | Expected completion |
| `interventions` | JSONB | | Array of interventions |
| `conditions` | JSONB | | Array of conditions |
| `record_hash` | VARCHAR(64) | | For change detection |
| `ingested_at` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Ingestion time |
| `processed_to_silver` | BOOLEAN | DEFAULT FALSE | Processing status |

**Indexes**: nct_id, ingested_at, overall_status, lead_sponsor_name

---

### 3. Silver Layer Tables

#### silver_molecules
Master molecule identity table with entity resolution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `molecule_id` | UUID | PK, DEFAULT gen_random_uuid() | Canonical molecule ID |
| `inchi_key` | VARCHAR(27) | UNIQUE, NOT NULL | Master identifier |
| `chembl_id` | VARCHAR(30) | | ChEMBL identifier |
| `drugbank_id` | VARCHAR(20) | | DrugBank identifier |
| `pubchem_cid` | BIGINT | | PubChem compound ID |
| `rxnorm_cui` | VARCHAR(20) | | RxNorm concept ID |
| `unii` | VARCHAR(20) | | FDA UNII |
| `cas_number` | VARCHAR(20) | | CAS registry number |
| `canonical_name` | VARCHAR(500) | | Preferred name |
| `brand_names` | TEXT[] | | Array of brand names |
| `generic_names` | TEXT[] | | Array of generic names |
| `smiles` | TEXT | | Canonical SMILES |
| `molecular_formula` | VARCHAR(200) | | Molecular formula |
| `molecule_type` | VARCHAR(50) | | small_molecule, biologic, etc. |
| `therapeutic_areas` | TEXT[] | | Therapeutic classifications |
| `atc_codes` | TEXT[] | | ATC codes |
| `needs_review` | BOOLEAN | DEFAULT FALSE | Quarantine flag |
| `review_reason` | TEXT | | Why flagged for review |
| `resolution_confidence` | DECIMAL(3,2) | | Entity resolution confidence |
| `reviewed_at` | TIMESTAMPTZ | | When reviewed |
| `reviewed_by` | VARCHAR(100) | | Who reviewed |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update time |
| `source_count` | INTEGER | DEFAULT 1 | Number of sources |

**Indexes**: inchi_key, chembl_id, drugbank_id, pubchem_cid, canonical_name, needs_review

---

#### silver_identifier_mappings
Cross-reference mapping table for identifier resolution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `mapping_id` | UUID | PK | Mapping record ID |
| `molecule_id` | UUID | FK → silver_molecules | Master molecule reference |
| `identifier_type` | VARCHAR(30) | NOT NULL | inchi_key, chembl_id, etc. |
| `identifier_value` | VARCHAR(500) | NOT NULL | The identifier value |
| `source` | VARCHAR(50) | NOT NULL | Which API provided this |
| `confidence` | DECIMAL(3,2) | DEFAULT 1.0 | 0-1 confidence score |
| `is_primary` | BOOLEAN | DEFAULT FALSE | Primary ID for this type? |
| `is_validated` | BOOLEAN | DEFAULT FALSE | Has been validated? |
| `validated_at` | TIMESTAMPTZ | | Validation timestamp |
| `validated_by` | VARCHAR(100) | | Who validated |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Constraints**: UNIQUE(molecule_id, identifier_type, identifier_value)
**Indexes**: (identifier_type, identifier_value), molecule_id

---

#### silver_molecule_aliases
Name aliases for fuzzy resolution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `alias_id` | UUID | PK | Alias record ID |
| `molecule_id` | UUID | FK → silver_molecules | Master molecule reference |
| `alias_name` | VARCHAR(500) | NOT NULL | The alias name |
| `alias_type` | VARCHAR(30) | NOT NULL | brand_name, generic_name, inn, synonym |
| `region` | VARCHAR(50) | | USA, EU, etc. (for regional names) |
| `language` | VARCHAR(10) | | en, de, ja, etc. |
| `source` | VARCHAR(50) | NOT NULL | Source of this alias |
| `alias_name_normalized` | VARCHAR(500) | | Lowercase, no special chars |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |

**Indexes**: alias_name_normalized (GIN with pg_trgm), molecule_id

---

#### silver_clinical_trials
Normalized clinical trial data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `trial_id` | UUID | PK | Internal trial ID |
| `nct_id` | VARCHAR(20) | UNIQUE, NOT NULL | ClinicalTrials.gov ID |
| `molecule_id` | UUID | FK → silver_molecules | Linked molecule |
| `title` | TEXT | | Trial title |
| `brief_summary` | TEXT | | Summary |
| `phase` | VARCHAR(20) | | Phase 1, 2, 3, 4, N/A |
| `status` | VARCHAR(50) | | Current status |
| `study_type` | VARCHAR(50) | | Interventional, Observational |
| `conditions` | TEXT[] | | Conditions studied |
| `intervention_names` | TEXT[] | | Drug names in trial |
| `enrollment_target` | INTEGER | | Target enrollment |
| `enrollment_actual` | INTEGER | | Actual enrollment |
| `start_date` | DATE | | Trial start |
| `completion_date` | DATE | | Expected completion |
| `sponsor` | VARCHAR(500) | | Lead sponsor |
| `sponsor_type` | VARCHAR(50) | | Industry, NIH, Academic |
| `has_results` | BOOLEAN | DEFAULT FALSE | Results available? |
| `outcome_type` | VARCHAR(50) | | Success, Failure, Inconclusive |
| `bronze_source_id` | UUID | | Source Bronze record |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Indexes**: nct_id, molecule_id, phase, status, sponsor

---

#### silver_drug_labels
Normalized FDA drug label data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `label_id` | UUID | PK | Internal label ID |
| `set_id` | VARCHAR(50) | UNIQUE, NOT NULL | SPL set ID |
| `spl_id` | VARCHAR(50) | | SPL ID |
| `molecule_id` | UUID | FK → silver_molecules | Linked molecule |
| `brand_name` | VARCHAR(500) | | Brand name |
| `generic_name` | VARCHAR(500) | | Generic name |
| `manufacturer` | VARCHAR(500) | | Manufacturer |
| `application_number` | VARCHAR(20) | | NDA/BLA number |
| `approval_date` | DATE | | Approval date |
| `marketing_status` | VARCHAR(50) | | Marketing status |
| `route_of_administration` | TEXT[] | | Routes |
| `dosage_forms` | TEXT[] | | Dosage forms |
| `indications` | TEXT | | Indications text |
| `contraindications` | TEXT | | Contraindications |
| `warnings` | TEXT | | Warnings |
| `boxed_warning` | TEXT | | Boxed warning if any |
| `adverse_reactions` | TEXT | | Adverse reactions |
| `drug_interactions` | TEXT | | Drug interactions |
| `effective_date` | DATE | | Label effective date |
| `bronze_source_id` | UUID | | Source Bronze record |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Indexes**: set_id, molecule_id, brand_name, generic_name, application_number

---

#### silver_adverse_events
Normalized adverse event data from FAERS and SIDER.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `event_id` | UUID | PK | Internal event ID |
| `source` | VARCHAR(20) | NOT NULL | faers, sider, eudravigilance |
| `source_report_id` | VARCHAR(100) | | Original report ID |
| `molecule_id` | UUID | FK → silver_molecules | Linked molecule |
| `drug_name_reported` | VARCHAR(500) | | Drug name as reported |
| `reaction_meddra_pt` | VARCHAR(500) | | MedDRA Preferred Term |
| `reaction_meddra_code` | VARCHAR(20) | | MedDRA code |
| `seriousness` | VARCHAR(50) | | Serious, Non-serious |
| `outcome` | VARCHAR(50) | | Death, Hospitalization, etc. |
| `patient_age` | INTEGER | | Patient age |
| `patient_sex` | VARCHAR(10) | | M, F, Unknown |
| `report_date` | DATE | | Report date |
| `country` | VARCHAR(50) | | Country of report |
| `bronze_source_id` | UUID | | Source Bronze record |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |

**Indexes**: molecule_id, reaction_meddra_pt, source, report_date

---

### 4. Gold Layer Tables

#### gold_molecule_profile
Pre-aggregated molecule profiles for decision support.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `profile_id` | UUID | PK | Profile record ID |
| `molecule_id` | UUID | FK → silver_molecules, UNIQUE | Master molecule |
| `lifecycle_stage` | VARCHAR(50) | | Detected lifecycle stage |
| `stage_confidence` | DECIMAL(3,2) | | Confidence in stage detection |
| `data_completeness` | DECIMAL(3,2) | | % of data fields populated |
| `trial_count` | INTEGER | | Number of clinical trials |
| `active_trial_count` | INTEGER | | Actively recruiting trials |
| `label_count` | INTEGER | | Number of FDA labels |
| `indication_count` | INTEGER | | Number of indications |
| `adverse_event_count` | INTEGER | | Total adverse events |
| `serious_ae_count` | INTEGER | | Serious adverse events |
| `publication_count` | INTEGER | | Related publications |
| `patent_expiry_date` | DATE | | Earliest patent expiry |
| `first_approval_date` | DATE | | First FDA approval |
| `last_updated` | TIMESTAMPTZ | DEFAULT NOW() | Last aggregation time |

**Note**: View definition excludes needs_review=TRUE from silver_molecules

---

#### gold_competitive_landscape
Competitive analysis by indication.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `landscape_id` | UUID | PK | Landscape record ID |
| `indication` | VARCHAR(500) | NOT NULL | Therapeutic indication |
| `indication_mesh_id` | VARCHAR(20) | | MeSH term ID |
| `molecule_ids` | UUID[] | | Molecules in this landscape |
| `approved_count` | INTEGER | | Approved drugs |
| `phase3_count` | INTEGER | | Phase 3 candidates |
| `phase2_count` | INTEGER | | Phase 2 candidates |
| `phase1_count` | INTEGER | | Phase 1 candidates |
| `market_leaders` | JSONB | | Top molecules by market share |
| `recent_approvals` | JSONB | | Last 2 years approvals |
| `pipeline_trends` | JSONB | | Pipeline activity trends |
| `last_updated` | TIMESTAMPTZ | DEFAULT NOW() | Last aggregation time |

---

#### gold_safety_signals
Aggregated safety signal analysis.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `signal_id` | UUID | PK | Signal record ID |
| `molecule_id` | UUID | FK → silver_molecules | Master molecule |
| `reaction_meddra_pt` | VARCHAR(500) | | MedDRA Preferred Term |
| `reaction_soc` | VARCHAR(200) | | System Organ Class |
| `case_count` | INTEGER | | Number of cases |
| `prr_score` | DECIMAL(8,4) | | Proportional Reporting Ratio |
| `ror_score` | DECIMAL(8,4) | | Reporting Odds Ratio |
| `ic_score` | DECIMAL(8,4) | | Information Component |
| `signal_strength` | VARCHAR(20) | | Strong, Moderate, Weak |
| `first_reported` | DATE | | First report date |
| `last_reported` | DATE | | Most recent report |
| `trend_direction` | VARCHAR(20) | | Increasing, Stable, Decreasing |
| `last_updated` | TIMESTAMPTZ | DEFAULT NOW() | Last calculation time |

**Constraints**: UNIQUE(molecule_id, reaction_meddra_pt)

---

### 5. Application Layer Tables

#### user_tracked_molecules
User's tracked molecule portfolio.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `tracking_id` | UUID | PK | Tracking record ID |
| `user_id` | UUID | NOT NULL | User who is tracking |
| `molecule_id` | UUID | FK → silver_molecules | Tracked molecule |
| `indication` | VARCHAR(500) | | Specific indication tracked |
| `lifecycle_stage` | VARCHAR(50) | | User's assessed stage |
| `stage_validated` | BOOLEAN | DEFAULT FALSE | Has stage been validated? |
| `validation_date` | TIMESTAMPTZ | | When validated |
| `notes` | TEXT | | User notes |
| `priority` | VARCHAR(20) | | High, Medium, Low |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | When started tracking |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Constraints**: UNIQUE(user_id, molecule_id, indication)
**RLS**: Users can only see their own tracked molecules

---

#### user_annotations
User-added annotations and evidence.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `annotation_id` | UUID | PK | Annotation record ID |
| `user_id` | UUID | NOT NULL | User who created |
| `molecule_id` | UUID | FK → silver_molecules | Related molecule |
| `tracking_id` | UUID | FK → user_tracked_molecules | Related tracking record |
| `annotation_type` | VARCHAR(50) | | evidence, note, document, link |
| `title` | VARCHAR(500) | | Annotation title |
| `content` | TEXT | | Annotation content |
| `source_url` | VARCHAR(1000) | | Source URL if applicable |
| `is_private` | BOOLEAN | DEFAULT FALSE | Private to user? |
| `lifecycle_stage` | VARCHAR(50) | | Stage this evidence supports |
| `evidence_strength` | VARCHAR(20) | | Strong, Moderate, Weak |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**RLS**: Private annotations only visible to creator

---

#### alert_configs
User alert configuration.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `config_id` | UUID | PK | Config record ID |
| `user_id` | UUID | NOT NULL | User who configured |
| `molecule_id` | UUID | FK → silver_molecules | Molecule to monitor |
| `alert_type` | VARCHAR(50) | NOT NULL | stage_change, safety_signal, trial_update, etc. |
| `threshold` | JSONB | | Alert-specific thresholds |
| `channels` | TEXT[] | | email, in_app, webhook |
| `is_active` | BOOLEAN | DEFAULT TRUE | Is alert active? |
| `last_triggered` | TIMESTAMPTZ | | Last time alert fired |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Constraints**: UNIQUE(user_id, molecule_id, alert_type)

---

## State Transitions

### Molecule Lifecycle Stages

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Discovery  │────▶│  Preclinical │────▶│   Phase 1    │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Marketed   │◀────│   Approved   │◀────│   Phase 3    │◀──┐
└──────────────┘     └──────────────┘     └──────────────┘   │
       │                                         ▲           │
       ▼                                         │           │
┌──────────────┐                          ┌──────────────┐   │
│  Withdrawn   │                          │   Phase 2    │───┘
└──────────────┘                          └──────────────┘

Valid Transitions:
- Discovery → Preclinical
- Preclinical → Phase 1
- Phase 1 → Phase 2
- Phase 2 → Phase 3
- Phase 3 → Approved
- Approved → Marketed
- Any stage → Withdrawn (with reason)
- Regression possible with user confirmation
```

### Entity Resolution States

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Bronze     │────▶│   Resolving  │────▶│   Silver     │
│  (source)    │     │  (matching)  │     │ (confirmed)  │
└──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                            ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │  Quarantine  │────▶│    Gold      │
                     │ (needs_review)│     │ (aggregated) │
                     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Rejected   │
                     │  (invalid)   │
                     └──────────────┘
```

---

## Validation Rules

### InChI Key Format
- Pattern: `^[A-Z]{14}-[A-Z]{10}-[A-Z]$`
- Example: `BSYNRYMUTXBXSQ-UHFFFAOYSA-N`

### ChEMBL ID Format
- Pattern: `^CHEMBL\d+$`
- Example: `CHEMBL25`

### DrugBank ID Format
- Pattern: `^DB\d{5}$`
- Example: `DB00945`

### NCT ID Format
- Pattern: `^NCT\d{8}$`
- Example: `NCT01234567`

### Confidence Score
- Range: 0.00 to 1.00
- Quarantine threshold: < 0.80
- Auto-accept threshold: >= 0.80

---

## Data Volume Estimates

| Table | Initial Load | Monthly Growth | 5-Year Estimate |
|-------|--------------|----------------|-----------------|
| raw_* (all sources) | 30M records | 500K/month | 60M records |
| bronze_* (all sources) | 30M records | 500K/month | 60M records |
| silver_molecules | 3M records | 50K/month | 6M records |
| silver_clinical_trials | 600K records | 5K/month | 900K records |
| silver_drug_labels | 250K records | 500/month | 280K records |
| silver_adverse_events | 20M records | 200K/month | 32M records |
| gold_molecule_profile | 3M records | 50K/month | 6M records |
| user_tracked_molecules | 0 | 10K/month | 600K records |
