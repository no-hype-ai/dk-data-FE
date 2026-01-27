# Data Model: DK Molecule Data Platform

**Feature**: 012-dk-data-platform
**Created**: 2026-01-24
**Status**: Complete
**Updated**: 2026-01-27 (Naming convention clarified)

---

## Schema Naming Convention

Tables are organized into PostgreSQL schemas by layer:

| Schema | Purpose | Example Tables |
|--------|---------|----------------|
| `raw` | Unprocessed API responses | `raw.chembl`, `raw.clinicaltrials` |
| `bronze` | Source-native typed data | `bronze.chembl`, `bronze.pubchem` |
| `silver` | Entity-resolved normalized data | `silver.molecules`, `silver.clinical_trials` |
| `gold` | Pre-aggregated analytics | `gold.molecule_profile`, `gold.competitive_landscape` |
| `application` | User-specific data | `application.user_tracked_molecules` |

**Note**: Tables use schema prefixes (e.g., `silver.molecules`) rather than underscore naming (e.g., `silver_molecules`).
The primary key for most tables is `id` (UUID), with `molecule_id` used as foreign keys referencing `silver.molecules(id)`.

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
│  SILVER LAYER (Entity-Resolved) - Schema: silver                          │              │
│  ───────────────────────────────────────────                              │              │
│                                                                           │              │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐   │              │
│  │silver.molecules │◄────▶│silver.id_maps   │◄────▶│silver.aliases   │   │              │
│  │─────────────────│      │─────────────────│      │─────────────────│   │              │
│  │ id (PK)         │      │ id (PK)         │      │ id (PK)         │   │              │
│  │ inchi_key (UK)  │      │ molecule_id (FK)│      │ molecule_id (FK)│   │              │
│  │ canonical_name  │      │ identifier_type │      │ alias_name      │   │              │
│  │ canonical_smiles│      │ identifier_value│      │ alias_type      │   │              │
│  │ molecule_type   │      │ source          │      │ region          │   │              │
│  │ development_    │      │ confidence      │      └─────────────────┘   │              │
│  │   status        │      └─────────────────┘                            │              │
│  │ needs_review    │                                                     │              │
│  └────────┬────────┘                                                     │              │
│           │                                                              │              │
│           │ 1:N                                                          │              │
│           ▼                                                              │              │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐   │              │
│  │silver.clinical_ │      │silver.drug_     │      │silver.adverse_  │◄──┘              │
│  │       trials    │      │       labels    │      │       events    │                  │
│  │─────────────────│      │─────────────────│      │─────────────────│                  │
│  │ id (PK)         │      │ id (PK)         │      │ id (PK)         │                  │
│  │ nct_id (UK)     │      │ set_id (UK)     │      │ source_report_id│                  │
│  │ molecule_id (FK)│      │ molecule_id (FK)│      │ molecule_id (FK)│                  │
│  │ phase           │      │ brand_name      │      │ meddra_pt       │                  │
│  │ status          │      │ indications_    │      │ outcome         │                  │
│  │                 │      │   and_usage     │      │                 │                  │
│  └─────────────────┘      └─────────────────┘      └─────────────────┘                  │
│                                                                                          │
│  GOLD LAYER (Aggregated) - Schema: gold                                                 │
│  ──────────────────────────────────────                                                 │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐                  │
│  │gold.molecule_   │      │gold.competitive_│      │gold.safety_     │                  │
│  │      profile    │      │      landscape  │      │      signals    │                  │
│  │─────────────────│      │─────────────────│      │─────────────────│                  │
│  │ profile_id (PK) │      │ landscape_id(PK)│      │ signal_id (PK)  │                  │
│  │ molecule_id (FK)│      │ indication      │      │ molecule_id (FK)│                  │
│  │ lifecycle_stage │      │ molecules[]     │      │ prr_score       │                  │
│  │ data_complete   │      │ market_share    │      │ ror_score       │                  │
│  └─────────────────┘      └─────────────────┘      └─────────────────┘                  │
│                                                                                          │
│  APPLICATION LAYER - Schema: application                                                │
│  ───────────────────────────────────────                                                │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐                  │
│  │application.user_│      │application.user_│      │application.     │                  │
│  │tracked_molecules│      │    annotations  │      │  alert_configs  │                  │
│  │─────────────────│      │─────────────────│      │─────────────────│                  │
│  │ id (PK)         │      │ id (PK)         │      │ id (PK)         │                  │
│  │ user_id         │      │ molecule_id (FK)│      │ user_id         │                  │
│  │ molecule_id (FK)│      │ user_id         │      │ molecule_id (FK)│                  │
│  │ indication      │      │ annotation_type │      │ alert_type      │                  │
│  │ lifecycle_stage │      │ content         │      │ threshold       │                  │
│  │                 │      │ is_private      │      │ is_active       │                  │
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

**Schema**: `silver`

#### silver.molecules
Master molecule identity table with entity resolution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Canonical molecule ID |
| `inchi_key` | VARCHAR(27) | UNIQUE | Master identifier (NULL for biologics) |
| `canonical_name` | VARCHAR(500) | | Preferred name |
| `name_source` | VARCHAR(50) | | Which source provided the canonical name |
| `canonical_smiles` | TEXT | | Canonical SMILES |
| `inchi` | TEXT | | InChI string |
| `molecular_formula` | VARCHAR(200) | | Molecular formula |
| `molecular_weight` | NUMERIC(12,4) | | Molecular weight |
| `molecule_type` | VARCHAR(50) | | small_molecule, protein, antibody, peptide, etc. |
| `therapeutic_areas` | JSONB | | Therapeutic classifications |
| `mechanism_of_action` | TEXT | | MOA description |
| `development_status` | VARCHAR(50) | | preclinical, phase_1, phase_2, phase_3, approved, withdrawn |
| `max_phase` | INTEGER | | Maximum clinical phase reached |
| `first_approval_year` | INTEGER | | Year of first approval |
| `approval_date` | DATE | | First approval date |
| `resolution_confidence` | NUMERIC(3,2) | DEFAULT 1.0 | Entity resolution confidence (0-1) |
| `needs_review` | BOOLEAN | DEFAULT FALSE | Quarantine flag for <0.8 confidence |
| `review_reason` | TEXT | | Why flagged for review |
| `data_sources` | JSONB | | Array of sources contributing to this record |
| `primary_source` | VARCHAR(50) | | Highest precedence source |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update time |

**Indexes**: inchi_key, canonical_name, development_status, needs_review (partial), canonical_name (GIN trigram)

**Note**: Cross-reference identifiers (chembl_id, drugbank_id, pubchem_cid, etc.) are stored in `silver.identifier_mappings` rather than denormalized in this table.

---

#### silver.identifier_mappings
Cross-reference mapping table for identifier resolution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Mapping record ID |
| `molecule_id` | UUID | FK → silver.molecules(id) ON DELETE CASCADE | Master molecule reference |
| `identifier_type` | VARCHAR(30) | NOT NULL | inchi_key, chembl_id, drugbank_id, pubchem_cid, rxnorm_cui, unii, cas_number, etc. |
| `identifier_value` | VARCHAR(500) | NOT NULL | The identifier value |
| `source` | VARCHAR(50) | NOT NULL | Which API provided this mapping |
| `confidence` | NUMERIC(3,2) | DEFAULT 1.0 | 0-1 confidence score |
| `is_primary` | BOOLEAN | DEFAULT FALSE | Primary ID for this type? |
| `is_validated` | BOOLEAN | DEFAULT FALSE | Has been validated? |
| `validated_at` | TIMESTAMPTZ | | Validation timestamp |
| `validated_by` | VARCHAR(100) | | Who validated |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Constraints**: UNIQUE(molecule_id, identifier_type, identifier_value)
**Indexes**: (identifier_type, identifier_value), molecule_id, source

---

#### silver.molecule_aliases
Name aliases for fuzzy resolution.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Alias record ID |
| `molecule_id` | UUID | FK → silver.molecules(id) ON DELETE CASCADE | Master molecule reference |
| `alias_name` | VARCHAR(500) | NOT NULL | The alias name |
| `alias_type` | VARCHAR(30) | NOT NULL | brand_name, generic_name, inn, synonym, trade_name, code_name |
| `alias_name_normalized` | VARCHAR(500) | | Lowercase, no special chars (for search) |
| `region` | VARCHAR(50) | | USA, EU, JP, etc. (for regional names) |
| `language` | VARCHAR(10) | DEFAULT 'en' | en, de, ja, etc. |
| `source` | VARCHAR(50) | NOT NULL | Source of this alias |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |

**Constraints**: UNIQUE(molecule_id, alias_name, alias_type)
**Indexes**: alias_name_normalized, molecule_id, alias_name_normalized (GIN with pg_trgm)

---

#### silver.clinical_trials
Normalized clinical trial data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Internal trial ID |
| `molecule_id` | UUID | FK → silver.molecules(id) | Linked molecule |
| `nct_id` | VARCHAR(15) | UNIQUE, NOT NULL | ClinicalTrials.gov ID |
| `org_study_id` | VARCHAR(100) | | Organization study ID |
| `title` | TEXT | | Trial title |
| `brief_summary` | TEXT | | Summary |
| `phase` | VARCHAR(20) | | Phase 1, 2, 3, 4, N/A |
| `study_type` | VARCHAR(50) | | Interventional, Observational |
| `status` | VARCHAR(50) | | Current status |
| `start_date` | DATE | | Trial start |
| `completion_date` | DATE | | Expected completion |
| `primary_completion_date` | DATE | | Primary completion date |
| `sponsor` | VARCHAR(500) | | Lead sponsor |
| `sponsor_type` | VARCHAR(50) | | Industry, NIH, Academic |
| `collaborators` | JSONB | | Array of collaborators |
| `allocation` | VARCHAR(50) | | Randomized, etc. |
| `intervention_model` | VARCHAR(100) | | Parallel, Crossover, etc. |
| `masking` | VARCHAR(100) | | Double-blind, Open-label, etc. |
| `enrollment` | INTEGER | | Target enrollment |
| `eligibility_criteria` | TEXT | | Eligibility criteria |
| `minimum_age` | VARCHAR(20) | | Minimum age |
| `maximum_age` | VARCHAR(20) | | Maximum age |
| `sex` | VARCHAR(20) | | All, Male, Female |
| `conditions` | JSONB | | Array of conditions studied |
| `interventions` | JSONB | | Array of interventions |
| `primary_outcomes` | JSONB | | Primary outcome measures |
| `secondary_outcomes` | JSONB | | Secondary outcome measures |
| `locations` | JSONB | | Trial locations |
| `countries` | JSONB | | Countries involved |
| `source` | VARCHAR(50) | DEFAULT 'clinicaltrials_gov' | Data source |
| `source_updated_at` | TIMESTAMPTZ | | When source last updated |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Indexes**: nct_id, molecule_id, phase, status, sponsor

---

#### silver.drug_labels
Normalized FDA drug label data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Internal label ID |
| `molecule_id` | UUID | FK → silver.molecules(id) | Linked molecule |
| `set_id` | VARCHAR(50) | NOT NULL | SPL set ID |
| `spl_id` | VARCHAR(50) | | SPL ID |
| `version` | INTEGER | | Label version |
| `brand_name` | TEXT | | Brand name |
| `generic_name` | TEXT | | Generic name |
| `manufacturer` | VARCHAR(500) | | Manufacturer |
| `application_number` | VARCHAR(20) | | NDA/BLA number |
| `product_type` | VARCHAR(100) | | Product type |
| `indications_and_usage` | TEXT | | Indications section |
| `dosage_and_administration` | TEXT | | Dosage section |
| `contraindications` | TEXT | | Contraindications |
| `warnings` | TEXT | | Warnings |
| `boxed_warning` | TEXT | | Boxed warning if any |
| `adverse_reactions` | TEXT | | Adverse reactions section |
| `drug_interactions` | TEXT | | Drug interactions |
| `mechanism_of_action` | TEXT | | MOA from label |
| `effective_date` | DATE | | Label effective date |
| `source` | VARCHAR(50) | DEFAULT 'openfda_labels' | Data source |
| `source_updated_at` | TIMESTAMPTZ | | When source last updated |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Constraints**: UNIQUE(set_id, version)
**Indexes**: molecule_id, set_id, brand_name

---

#### silver.adverse_events
Aggregated adverse event data from FAERS.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Internal event ID |
| `molecule_id` | UUID | FK → silver.molecules(id) | Linked molecule |
| `meddra_pt` | VARCHAR(200) | | MedDRA Preferred Term |
| `meddra_pt_code` | VARCHAR(20) | | MedDRA PT code |
| `meddra_soc` | VARCHAR(200) | | System Organ Class |
| `meddra_soc_code` | VARCHAR(20) | | MedDRA SOC code |
| `report_count` | INTEGER | DEFAULT 0 | Number of reports |
| `serious_count` | INTEGER | DEFAULT 0 | Number of serious reports |
| `death_count` | INTEGER | DEFAULT 0 | Number of death reports |
| `hospitalization_count` | INTEGER | DEFAULT 0 | Number of hospitalization reports |
| `reporting_rate` | NUMERIC(10,4) | | Rate per 1000 reports |
| `prr` | NUMERIC(10,4) | | Proportional Reporting Ratio |
| `ror` | NUMERIC(10,4) | | Reporting Odds Ratio |
| `first_report_date` | DATE | | First report date |
| `last_report_date` | DATE | | Most recent report |
| `source` | VARCHAR(50) | DEFAULT 'openfda_faers' | Data source |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update |

**Constraints**: UNIQUE(molecule_id, meddra_pt_code)
**Indexes**: molecule_id, meddra_pt, meddra_soc

---

### 4. Gold Layer Tables

**Schema**: `gold`

#### gold.molecule_profile
Pre-aggregated molecule profiles for decision support.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `profile_id` | UUID | PK, DEFAULT gen_random_uuid() | Profile record ID |
| `molecule_id` | UUID | FK → silver.molecules(id), UNIQUE | Master molecule |
| `preferred_name` | VARCHAR(500) | | Molecule name |
| `molecule_type` | VARCHAR(30) | | Type of molecule |
| `inchi_key` | VARCHAR(27) | | InChI key (denormalized) |
| `lifecycle_stage` | VARCHAR(50) | | Detected lifecycle stage |
| `lifecycle_stage_confidence` | DECIMAL | | Confidence in stage detection |
| `lifecycle_last_detected` | TIMESTAMPTZ | | When stage was last detected |
| `drugbank_id` | VARCHAR(20) | | DrugBank ID (denormalized) |
| `chembl_id` | VARCHAR(20) | | ChEMBL ID (denormalized) |
| `pubchem_cid` | VARCHAR(20) | | PubChem CID (denormalized) |
| `rxnorm_cui` | VARCHAR(20) | | RxNorm CUI (denormalized) |
| `unii` | VARCHAR(20) | | FDA UNII (denormalized) |
| `approved_indications` | JSONB | | Array of approved indications |
| `pipeline_indications` | JSONB | | Array of pipeline indications |
| `boxed_warning_count` | INTEGER | DEFAULT 0 | Number of boxed warnings |
| `serious_ae_count` | INTEGER | DEFAULT 0 | Serious adverse events |
| `ae_summary` | JSONB | | Top adverse events with counts |
| `therapeutic_area` | VARCHAR(100) | | Primary therapeutic area |
| `mechanism_of_action` | VARCHAR(500) | | MOA |
| `competitor_count` | INTEGER | DEFAULT 0 | Number of competitors |
| `earliest_patent_expiry` | DATE | | Earliest patent expiry |
| `patent_count` | INTEGER | DEFAULT 0 | Number of patents |
| `exclusivity_expiry` | DATE | | Exclusivity expiry date |
| `data_completeness_score` | DECIMAL | | Data completeness (0-1) |
| `data_sources` | JSONB | | Sources with record counts |
| `last_data_update` | TIMESTAMPTZ | | Last data update |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last aggregation time |
| `aggregation_run_id` | UUID | | Which aggregation run |

**Indexes**: preferred_name, lifecycle_stage, drugbank_id, therapeutic_area

**Note**: This view excludes molecules where needs_review=TRUE from silver.molecules

---

#### gold.competitive_landscape
Competitive analysis by indication.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `landscape_id` | UUID | PK, DEFAULT gen_random_uuid() | Landscape record ID |
| `indication` | VARCHAR(500) | NOT NULL | Therapeutic indication |
| `indication_mesh` | VARCHAR(50) | | MeSH term ID |
| `therapeutic_area` | VARCHAR(100) | | Therapeutic area |
| `total_molecules` | INTEGER | DEFAULT 0 | Total molecules in landscape |
| `approved_count` | INTEGER | DEFAULT 0 | Approved drugs |
| `phase_3_count` | INTEGER | DEFAULT 0 | Phase 3 candidates |
| `phase_2_count` | INTEGER | DEFAULT 0 | Phase 2 candidates |
| `phase_1_count` | INTEGER | DEFAULT 0 | Phase 1 candidates |
| `preclinical_count` | INTEGER | DEFAULT 0 | Preclinical candidates |
| `market_leaders` | JSONB | | Top molecules by market share |
| `recent_approvals` | JSONB | | Last 2 years approvals |
| `late_stage_pipeline` | JSONB | | Late-stage pipeline molecules |
| `moa_distribution` | JSONB | | MOA distribution |
| `upcoming_patent_expiries` | JSONB | | Upcoming patent expiries |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Creation time |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last aggregation time |
| `snapshot_date` | DATE | DEFAULT CURRENT_DATE | Snapshot date |

**Constraints**: UNIQUE(indication, snapshot_date)
**Indexes**: indication, therapeutic_area, snapshot_date

---

#### gold.safety_signals
Aggregated safety signal analysis.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `signal_id` | UUID | PK, DEFAULT gen_random_uuid() | Signal record ID |
| `molecule_id` | UUID | FK → silver.molecules(id) ON DELETE CASCADE | Master molecule |
| `reaction_name` | VARCHAR(500) | NOT NULL | Reaction name |
| `reaction_meddra_pt` | VARCHAR(100) | | MedDRA Preferred Term code |
| `case_count` | INTEGER | DEFAULT 0 | Number of cases |
| `serious_count` | INTEGER | DEFAULT 0 | Serious cases |
| `fatal_count` | INTEGER | DEFAULT 0 | Fatal cases |
| `pro_score` | DECIMAL | | Proportional Reporting Ratio |
| `ror_score` | DECIMAL | | Reporting Odds Ratio |
| `is_signal` | BOOLEAN | DEFAULT FALSE | Is this a signal? |
| `first_reported` | DATE | | First report date |
| `last_reported` | DATE | | Most recent report |
| `trend_direction` | VARCHAR(20) | | Increasing, Stable, Decreasing |
| `vs_class_average` | DECIMAL | | Comparison to therapeutic class |
| `calculated_at` | TIMESTAMPTZ | DEFAULT NOW() | Calculation time |
| `faers_quarter` | VARCHAR(10) | | FAERS quarter (e.g., '2026Q1') |

**Indexes**: molecule_id, is_signal (partial), reaction_meddra_pt

---

### 5. Application Layer Tables

**Schema**: `application`

#### application.user_tracked_molecules
User's tracked molecule portfolio.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Tracking record ID |
| `user_id` | UUID | NOT NULL | User who is tracking |
| `molecule_id` | UUID | FK → silver.molecules(id) | Tracked molecule |
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

#### application.user_annotations
User-added annotations and evidence.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Annotation record ID |
| `user_id` | UUID | NOT NULL | User who created |
| `molecule_id` | UUID | FK → silver.molecules(id) | Related molecule |
| `tracking_id` | UUID | FK → application.user_tracked_molecules(id) | Related tracking record |
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

#### application.alert_configs
User alert configuration.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Config record ID |
| `user_id` | UUID | NOT NULL | User who configured |
| `molecule_id` | UUID | FK → silver.molecules(id) | Molecule to monitor |
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
