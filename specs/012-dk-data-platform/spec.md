# Feature Specification: DK Molecule Data Platform

**Feature Branch**: `012-dk-data-platform`
**Created**: January 2026
**Status**: Draft
**Priority**: P0 - Core Infrastructure
**Spec Number**: 012
**Supersedes**: 010-molecule-onboarding, 011-medallion-data-pipeline

---

## Clarifications

### Session 2026-01-21
- Q: What authentication/authorization model should the platform use? → A: JWT tokens with role-based access control (RBAC)
- Q: What availability target should the system meet? → A: 99.9% availability (~8.76 hours downtime/year)
- Q: How should the system scale as data volume grows? → A: Vertical scaling per instance + horizontal sharding with complete entities per database
- Q: What observability approach should the platform use? → A: Structured JSON logging + centralized aggregation (Loki/ELK) + Prometheus metrics + Grafana dashboards
- Q: What UX behavior should the onboarding wizard follow? → A: Free navigation - all steps accessible anytime; final validation only at completion

### Session 2026-01-21 (continued)
- Q: Which pipeline orchestration tool should be used for Bronze→Silver→Gold transformations? → A: **SQLMesh** - next-gen data transformation framework with plan/apply workflows, virtual data environments, incremental model support, and SQL/Python model definitions
- Q: How should fuzzy molecule name matching be implemented for identifier resolution? → A: **Levenshtein + trigram** using PostgreSQL pg_trgm extension - handles typos well, good balance of speed/accuracy
- Q: How should multi-indication tracking be modeled when a molecule has different lifecycle stages per indication? → A: **Separate tracking records** - one molecule_id, multiple user_tracked_molecules rows with indication field
- Q: Should the platform integrate with an existing identity provider for user authentication? → A: **Standalone JWT** - self-contained auth with username/password + optional MFA

### Session 2026-01-24
- Q: What storage backend and retention policy should the Raw layer use? → A: **PostgreSQL JSONB with indefinite retention** - all layers (Raw, Bronze, Silver, Gold) retain data indefinitely; no automatic deletion policies
- Q: How should data be exported from the platform for external consumption? → A: **PostgREST** - auto-generated REST API directly from PostgreSQL schema; provides filtering, pagination, and multiple output formats without custom API code
- Q: What deployment model should the platform use? → A: **Kubernetes** - full container orchestration with auto-scaling, rolling deployments, and self-healing capabilities
- Q: Which cloud provider should be the primary deployment target? → A: **Local/on-premises** - self-managed Kubernetes (k3s or bare metal) with self-hosted PostgreSQL; no cloud provider dependency
- Q: What backup strategy should be used for PostgreSQL? → A: **WAL archiving with pgBackRest** - continuous archiving with point-in-time recovery (PITR) to any moment; supports full, incremental, and differential backups

### Session 2026-01-24 (Data Loading Clarifications)
- Q: What are the disaster recovery objectives (RTO/RPO)? → A: **RTO: 1 hour, RPO: 15 minutes** - standard high-availability targets achievable with pgBackRest PITR and continuous WAL archiving
- Q: When sources have conflicting values for same property, which takes precedence? → A: **Curated first: DrugBank > ChEMBL > PubChem > Others** - trust curation quality; DrugBank is FDA-linked and manually curated, ChEMBL is EBI-curated with structure validation
- Q: How stale can data be before requiring refresh? → A: **Tiered freshness**: Clinical trials & FDA labels daily, safety data (FAERS) weekly, reference data (ChEMBL, DrugBank, PubChem) monthly
- Q: What happens to records with low-confidence entity resolution (<0.8)? → A: **Quarantine**: Record promoted to Silver with `needs_review=true` flag, but excluded from Gold layer until reviewed and approved
- Q: What testing strategy should be used for data pipelines? → A: **End-to-end testing**: Test complete pipeline with real API samples, verify final Gold output; focus on integration over unit tests

---

## Executive Summary

The DK Molecule Data Platform is the unified data foundation for pharmaceutical molecule intelligence. It implements an extended **Medallion Architecture** (Raw/Bronze/Silver/Gold) for progressive data refinement, combined with a user-facing **Molecule Onboarding Application** for lifecycle tracking and validation.

> **Architecture Update (2026-01-24)**: Added Raw layer below Bronze to store unmodified API responses. Bronze now maintains source column structure rather than storing raw JSONB blobs.

> **Business Context**: From meeting notes - "Nick King proposed aligning on the data being added and building transform and view tables on top of the consistently updating underlying substrate" and "Streamline molecule onboarding and lifecycle stage validation to ensure each stage is completed with validated content."

This unified spec replaces the previously separate molecule-onboarding (010) and medallion-data-pipeline (011) specs, which had overlapping concerns and duplicated entities.

---

## Platform Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DK MOLECULE DATA PLATFORM                                │
│                  (Extended Medallion Architecture: Raw→Bronze→Silver→Gold)       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ LAYER 5: APPLICATION (Molecule Onboarding Service)                         │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │ │
│  │ │  10-Step     │ │   Stage      │ │   Alert      │ │   Portfolio  │       │ │
│  │ │   Wizard     │ │  Validation  │ │  Management  │ │   Tracking   │       │ │
│  │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │ │
│  │ Tables: user_tracked_molecules, user_annotations, alert_configs            │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                        ▲                                         │
│                                        │ READS                                   │
│                                        │                                         │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ LAYER 4: BUSINESS INTELLIGENCE (Gold Layer)                                │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │ │
│  │ │  Molecule    │ │  Lifecycle   │ │ Competitive  │ │   Safety     │       │ │
│  │ │  Profile     │ │   Stage      │ │  Landscape   │ │  Signals     │       │ │
│  │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │ │
│  │ Pre-aggregated • Decision-ready • Enriched • Indefinite retention          │ │
│  │ Tables: gold_molecule_profile, gold_competitive_landscape, gold_safety...  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                        ▲                                         │
│                                        │ TRANSFORMS                              │
│                                        │                                         │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ LAYER 3: ENTITY RESOLUTION (Silver Layer)                                  │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │ │
│  │ │  Clinical    │ │    Drug      │ │   Adverse    │ │   Patents    │       │ │
│  │ │   Trials     │ │   Labels     │ │   Events     │ │              │       │ │
│  │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │ │
│  │ Normalized schema • Deduplicated • Entity-resolved • Indefinite retention  │ │
│  │ Tables: silver_clinical_trials, silver_drug_labels, silver_adverse_events..│ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                        ▲                                         │
│                                        │ PARSES & TYPES                          │
│                                        │                                         │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ LAYER 2: STRUCTURED INGESTION (Bronze Layer)                               │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │ │
│  │ │ ClinicalTri- │ │   OpenFDA    │ │   ChEMBL     │ │   UniProt    │       │ │
│  │ │   als.gov    │ │   FAERS      │ │   BindingDB  │ │   ...more    │       │ │
│  │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │ │
│  │ Source column structure • Typed columns • Append-only • Indefinite retention│ │
│  │ Tables: bronze_{source_name} with source-native columns (not JSONB blob)   │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                        ▲                                         │
│                                        │ EXTRACTS                                │
│                                        │                                         │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ LAYER 1: RAW API RESPONSES (Raw Layer)                                     │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │ │
│  │ │  HTTP Body   │ │   Headers    │ │   Status     │ │   Metadata   │       │ │
│  │ │   (JSONB)    │ │   (JSONB)    │ │    Code      │ │  (timestamp) │       │ │
│  │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │ │
│  │ Unmodified API responses • Complete HTTP context • Immutable • Indefinite  │ │
│  │ Tables: raw_{source_name} with response_body JSONB column                  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Industry Standard: Medallion Architecture

The Medallion pattern (pioneered by Databricks/Delta Lake) is the industry standard for pharmaceutical data platforms because:

| Requirement | How Medallion Solves It |
|-------------|------------------------|
| **Auditability** | Bronze layer preserves raw data for regulatory compliance |
| **Heterogeneous Sources** | Each source gets its own Bronze table, unified in Silver |
| **Entity Resolution** | Silver layer resolves molecule identity across sources |
| **Business Agility** | Gold layer can be rebuilt from Silver as requirements change |
| **Performance** | Gold pre-aggregations enable sub-second queries |

### Layer Definitions

| Layer | Purpose | Characteristics | Retention | Storage |
|-------|---------|-----------------|-----------|---------|
| **Raw** | API response archive | Unmodified HTTP responses (body, headers, status), immutable | Indefinite | JSONB blob |
| **Bronze** | Structured source data | Source-native column structure, typed, append-only | Indefinite | Relational (source schema) |
| **Silver** | Normalized entities | Standard schema, deduplicated, typed, entity-resolved | Indefinite | Relational |
| **Gold** | Decision data | Aggregated, enriched, pre-computed, indexed | Indefinite | Relational + Materialized Views |
| **Application** | User features | User annotations, tracking, alerts | Indefinite | Relational |

### Raw vs Bronze: Key Distinction

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        RAW vs BRONZE LAYER DISTINCTION                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  RAW LAYER (Layer 1):                                                            │
│  ────────────────────                                                            │
│  • Stores EXACT HTTP response from API call                                      │
│  • Single JSONB column with complete response body                               │
│  • Includes HTTP headers, status code, request metadata                          │
│  • For debugging, auditing, and reprocessing if Bronze logic changes             │
│  • Indefinite retention                                                          │
│                                                                                  │
│  BRONZE LAYER (Layer 2):                                                         │
│  ────────────────────────                                                        │
│  • Parses raw JSON/XML into TYPED COLUMNS                                        │
│  • Maintains source's original column structure (e.g., ClinicalTrials.gov cols) │
│  • One table per source with source-native schema                                │
│  • Enables efficient querying without JSON parsing at runtime                    │
│  • Indefinite retention                                                          │
│                                                                                  │
│  EXAMPLE - ClinicalTrials.gov:                                                   │
│  ─────────────────────────────                                                   │
│                                                                                  │
│  raw_clinicaltrials:                                                             │
│    response_body: {"studies":[{"protocolSection":{"identificationModule":{...}}} │
│                                                                                  │
│  bronze_clinicaltrials:                                                          │
│    nct_id VARCHAR(15)                    -- from protocolSection.identificationModule.nctId
│    brief_title TEXT                      -- from protocolSection.identificationModule.briefTitle
│    official_title TEXT                   -- from protocolSection.identificationModule.officialTitle
│    overall_status VARCHAR(50)            -- from protocolSection.statusModule.overallStatus
│    phase VARCHAR(20)                     -- from protocolSection.designModule.phases[0]
│    study_type VARCHAR(50)                -- from protocolSection.designModule.studyType
│    enrollment_count INTEGER              -- from protocolSection.designModule.enrollmentInfo.count
│    start_date DATE                       -- from protocolSection.statusModule.startDateStruct.date
│    ... (all source columns preserved)                                            │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 0: Raw API Response Layer (Raw)

### Purpose
Archive unmodified HTTP responses from all external API calls, preserving complete request/response context for debugging, auditing, compliance, and reprocessing if Bronze parsing logic changes.

### User Story 0.1 - Archive Raw API Response (Priority: P1)

A data engineer wants to preserve the exact API response received from an external source, including HTTP headers and status codes, for debugging and compliance purposes.

**Acceptance Scenarios**:

1. **Given** an API call to ClinicalTrials.gov, **When** the response is received, **Then** the complete HTTP response (body, headers, status) is stored in Raw layer before any parsing
2. **Given** a malformed API response, **When** Bronze parsing fails, **Then** the original Raw response is preserved for debugging and manual inspection
3. **Given** a compliance audit request, **When** auditors need to verify data provenance, **Then** the exact API response from that date/time can be retrieved from Raw layer

### Raw Table Schema

```sql
-- Generic Raw table pattern (one per source)
CREATE TABLE raw_{source_name} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Request context
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20),
    request_params JSONB,                  -- Query parameters sent
    request_headers JSONB,                 -- Headers sent (auth redacted)

    -- Response (UNMODIFIED)
    response_status INTEGER NOT NULL,      -- HTTP status code
    response_headers JSONB,                -- All response headers
    response_body JSONB NOT NULL,          -- Complete response body (unmodified)
    response_body_hash VARCHAR(64),        -- SHA-256 for dedup detection
    response_size_bytes INTEGER,
    response_time_ms INTEGER,              -- API latency

    -- Processing status
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,

    -- Metadata
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL,

    -- Indexes
    INDEX idx_raw_request_id (request_id),
    INDEX idx_raw_timestamp (request_timestamp),
    INDEX idx_raw_processed (processed_to_bronze),
    INDEX idx_raw_hash (response_body_hash)
);

-- Retention policy: Indefinite (no automatic deletion)
-- All Raw data preserved for complete audit trail and reprocessing capability
```

### Raw Tables by Source

| Table Name | Source | Update Frequency | Estimated Volume | Retention |
|------------|--------|------------------|------------------|-----------|
| `raw_clinicaltrials` | ClinicalTrials.gov API v2 | Daily | 500K responses | Indefinite |
| `raw_openfda_labels` | OpenFDA Drug Labels | Daily | 84K responses | Indefinite |
| `raw_openfda_faers` | OpenFDA FAERS | Weekly | 20M responses | Indefinite |
| `raw_chembl` | ChEMBL API | Monthly | 2.7M responses | Indefinite |
| `raw_drugbank` | DrugBank XML | Quarterly | 17K responses | Indefinite |
| `raw_pubchem` | PubChem PUG-REST | On-demand | 1M responses | Indefinite |
| `raw_uniprot` | UniProt REST | Monthly | 20K responses | Indefinite |
| `raw_openalex` | OpenAlex API | Weekly | Variable | Indefinite |

---

## Part 1: Structured Ingestion Layer (Bronze)

### Purpose
Parse Raw API responses into typed, queryable columns while preserving the source's original data structure. Each source gets its own table with columns matching the source API's field names.

### User Story 1.1 - Parse Raw Response to Bronze Columns (Priority: P1)

A data engineer wants raw API responses automatically parsed into typed, queryable columns that match the source's data structure.

**Acceptance Scenarios**:

1. **Given** a raw API response in the Raw layer, **When** Bronze extraction runs, **Then** JSON fields are extracted into typed columns matching the source's field names
2. **Given** a ClinicalTrials.gov response with nested `protocolSection.identificationModule.nctId`, **When** extracted, **Then** it appears as a `nct_id VARCHAR(15)` column in Bronze
3. **Given** an API response with arrays (e.g., `interventions[]`), **When** extracted, **Then** arrays are preserved as JSONB columns or normalized to child tables

### User Story 1.2 - Register Data Source with Schema Definition (Priority: P1)

A data operations team member wants to register a new external API with a schema mapping that defines how JSON paths map to Bronze columns.

**Acceptance Scenarios**:

1. **Given** an API endpoint and a schema mapping file, **When** the user registers the source, **Then** the system creates a Bronze table with typed columns
2. **Given** a source with authentication requirements, **When** registered with credentials, **Then** credentials are stored securely (encrypted) and API calls succeed
3. **Given** a previously registered source, **When** the schema mapping is updated, **Then** new columns are added without losing historical data

### User Story 1.3 - Auto-Detect Bronze Schema (Priority: P2)

A data engineer wants the system to auto-detect column structure from sample API responses for rapid source onboarding.

**Acceptance Scenarios**:

1. **Given** an API endpoint URL and sample response, **When** the user triggers auto-detection, **Then** the system generates a schema mapping with inferred column types
2. **Given** an auto-detected schema, **When** the user reviews it, **Then** they can modify column names, types, or JSON paths before finalizing
3. **Given** a complex nested JSON structure, **When** auto-detected, **Then** the system suggests flattening strategies (inline vs child tables)

### Bronze Table Schema (Source-Native Columns)

Bronze tables use **typed columns matching the source's data structure**, not a single JSONB blob. This enables efficient SQL queries without runtime JSON parsing.

```sql
-- Example: ClinicalTrials.gov Bronze table with source-native columns
CREATE TABLE bronze_clinicaltrials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Linkage to Raw layer
    raw_id UUID REFERENCES raw_clinicaltrials(id),

    -- Ingestion metadata
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'clinicaltrials_gov',
    api_version VARCHAR(20),

    -- === SOURCE-NATIVE COLUMNS (from ClinicalTrials.gov API v2 structure) ===

    -- Identification Module
    nct_id VARCHAR(15) NOT NULL,
    org_study_id VARCHAR(100),
    brief_title TEXT,
    official_title TEXT,
    acronym VARCHAR(50),

    -- Status Module
    overall_status VARCHAR(50),
    last_known_status VARCHAR(50),
    start_date DATE,
    start_date_type VARCHAR(20),
    completion_date DATE,
    completion_date_type VARCHAR(20),
    study_first_submit_date DATE,
    study_first_post_date DATE,
    last_update_post_date DATE,

    -- Sponsor/Collaborators Module
    lead_sponsor_name VARCHAR(500),
    lead_sponsor_class VARCHAR(50),  -- NIH, FED, INDUSTRY, OTHER
    collaborators JSONB,  -- Array of {name, class}

    -- Design Module
    study_type VARCHAR(50),          -- Interventional, Observational, etc.
    phases JSONB,                    -- Array: ["Phase 1", "Phase 2"]
    allocation VARCHAR(50),
    intervention_model VARCHAR(100),
    primary_purpose VARCHAR(100),
    masking VARCHAR(100),
    enrollment_count INTEGER,
    enrollment_type VARCHAR(20),

    -- Arms/Interventions Module
    arms_groups JSONB,               -- Array of arm definitions
    interventions JSONB,             -- Array of {type, name, description}

    -- Outcomes Module
    primary_outcomes JSONB,          -- Array of {measure, timeFrame, description}
    secondary_outcomes JSONB,

    -- Eligibility Module
    eligibility_criteria TEXT,
    sex VARCHAR(20),
    minimum_age VARCHAR(20),
    maximum_age VARCHAR(20),
    healthy_volunteers VARCHAR(10),

    -- Contacts/Locations Module
    locations JSONB,                 -- Array of {facility, city, state, country}
    central_contacts JSONB,

    -- References Module
    references JSONB,                -- Array of {pmid, citation}
    see_also_links JSONB,

    -- IPD Sharing Module
    ipd_sharing VARCHAR(20),
    ipd_sharing_description TEXT,

    -- Derived/Computed (still at Bronze level)
    conditions JSONB,                -- Array of condition strings
    keywords JSONB,                  -- Array of keyword strings
    mesh_terms JSONB,                -- Array of MeSH terms

    -- Processing status
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,

    -- Record hash for change detection
    record_hash VARCHAR(64),

    -- Indexes
    INDEX idx_bronze_ct_nct_id (nct_id),
    INDEX idx_bronze_ct_ingested_at (ingested_at),
    INDEX idx_bronze_ct_status (overall_status),
    INDEX idx_bronze_ct_phase (phases),
    INDEX idx_bronze_ct_sponsor (lead_sponsor_name),
    INDEX idx_bronze_ct_processed (processed_to_silver)
);

-- Retention policy: Indefinite (no automatic deletion)
-- All Bronze data preserved for complete audit trail
```

### Schema Mapping Configuration

Each source requires a schema mapping that defines how JSON paths map to Bronze columns:

```yaml
# Example: schema_mapping_clinicaltrials.yaml
source_id: clinicaltrials_gov
source_name: ClinicalTrials.gov
api_version: v2
bronze_table: bronze_clinicaltrials

# Root path for study records in API response
record_root: $.studies[*]

columns:
  - name: nct_id
    json_path: $.protocolSection.identificationModule.nctId
    type: VARCHAR(15)
    nullable: false

  - name: brief_title
    json_path: $.protocolSection.identificationModule.briefTitle
    type: TEXT
    nullable: true

  - name: overall_status
    json_path: $.protocolSection.statusModule.overallStatus
    type: VARCHAR(50)
    nullable: true

  - name: phases
    json_path: $.protocolSection.designModule.phases
    type: JSONB  # Preserve array as JSONB
    nullable: true

  - name: lead_sponsor_name
    json_path: $.protocolSection.sponsorCollaboratorsModule.leadSponsor.name
    type: VARCHAR(500)
    nullable: true

  - name: enrollment_count
    json_path: $.protocolSection.designModule.enrollmentInfo.count
    type: INTEGER
    nullable: true

  - name: start_date
    json_path: $.protocolSection.statusModule.startDateStruct.date
    type: DATE
    transform: parse_date  # Custom date parser

  - name: interventions
    json_path: $.protocolSection.armsInterventionsModule.interventions
    type: JSONB  # Complex array preserved as JSONB
    nullable: true

# Arrays that should become child tables (Silver layer handles this)
nested_arrays:
  - json_path: $.protocolSection.armsInterventionsModule.interventions
    target_table: silver_trial_interventions
```

### Bronze Tables by Source

Each Bronze table has typed columns matching the source's data structure:

| Table Name | Source | Key Columns | Update Frequency | Volume |
|------------|--------|-------------|------------------|--------|
| `bronze_clinicaltrials` | ClinicalTrials.gov API v2 | nct_id, brief_title, overall_status, phases, lead_sponsor_name, interventions | Daily | 500K |
| `bronze_openfda_labels` | OpenFDA Drug Labels | application_number, brand_name, generic_name, manufacturer, indications_and_usage, warnings | Daily | 84K |
| `bronze_openfda_faers` | OpenFDA FAERS | safety_report_id, patient_age, patient_sex, reactions, drugs, outcomes | Weekly | 20M |
| `bronze_chembl` | ChEMBL API | chembl_id, molecule_type, pref_name, max_phase, first_approval, inchi_key | Monthly | 2.7M |
| `bronze_drugbank` | DrugBank XML | drugbank_id, name, type, cas_number, unii, state, indication, pharmacodynamics | Quarterly | 17K |
| `bronze_bindingdb` | BindingDB TSV | monomerid, smiles, inchi_key, target_name, ki, ic50, kd | Monthly | 2.3M |
| `bronze_pubchem` | PubChem PUG-REST | cid, iupac_name, molecular_formula, molecular_weight, canonical_smiles, inchi_key | On-demand | 1M |
| `bronze_uniprot` | UniProt REST | accession, entry_name, protein_name, gene_names, organism, sequence | Monthly | 20K |
| `bronze_ema` | EMA Open Data | product_number, medicine_name, inn, therapeutic_area, authorisation_status | Weekly | 3K |
| `bronze_orange_book` | FDA Orange Book | appl_no, product_no, trade_name, applicant, ingredient, te_code, patent_no | Monthly | 4K |
| `bronze_patents` | USPTO Bulk Data | patent_number, title, abstract, assignee, filing_date, grant_date, claims | Weekly | 500K |
| `bronze_sider` | SIDER Download | stitch_id, drug_name, meddra_concept_type, meddra_concept_id, side_effect | Quarterly | 450K |
| `bronze_openalex` | OpenAlex API | work_id, doi, title, publication_year, cited_by_count, concepts, authorships | Weekly | Variable |

### Key Entity: DataSource Configuration

```python
@dataclass
class DataSourceConfig:
    source_id: str                    # e.g., "clinicaltrials_gov"
    source_name: str                  # e.g., "ClinicalTrials.gov"
    api_type: Literal["REST", "GraphQL", "Bulk", "XML"]
    base_url: str
    auth_type: Optional[Literal["none", "api_key", "oauth2", "basic"]]
    auth_config: Optional[Dict[str, Any]]  # Encrypted credentials

    # Scheduling
    schedule: str                     # Cron expression
    rate_limit_per_second: float
    retry_config: RetryConfig

    # Schema detection
    sample_response: Optional[Dict]
    detected_schema: Optional[Dict]

    # Status
    is_active: bool
    last_successful_sync: Optional[datetime]
    last_error: Optional[str]
```

---

## Part 2: Entity Resolution Layer (Silver)

### Purpose
Transform raw Bronze data into normalized, deduplicated entities with consistent schemas. Resolve molecule identity across sources using InChI Key as the master identifier.

### User Story 2.1 - Transform Bronze to Silver (Priority: P1)

A data analyst wants to see normalized, deduplicated data from multiple sources in a consistent schema, without dealing with raw API quirks.

**Acceptance Scenarios**:

1. **Given** raw clinical trial JSON from ClinicalTrials.gov in Bronze, **When** Silver transformation runs, **Then** data appears in normalized `silver_clinical_trials` table with standard columns
2. **Given** the same trial appears in both ClinicalTrials.gov and company press releases, **When** deduplicated, **Then** Silver contains one canonical record with sources merged
3. **Given** an API changes its response format, **When** transformation fails, **Then** Bronze data is preserved and Silver transformation is marked as failed with specific error

### User Story 2.2 - Entity Resolution Across Sources (Priority: P1)

A data scientist needs to link data for the same molecule across different sources (ChEMBL activity + DrugBank info + FDA label).

**Acceptance Scenarios**:

1. **Given** a molecule exists in ChEMBL, DrugBank, and PubChem with different identifiers, **When** entity resolution runs, **Then** all records link to a single canonical `molecule_id` via InChI Key
2. **Given** a molecule name has multiple spellings across sources, **When** resolved, **Then** the system maintains an alias table linking all variants
3. **Given** a new compound not in the master table, **When** first encountered, **Then** a new canonical molecule record is created with available identifiers

### Cross-Data Source Identifier Mapping

A critical function of the Silver Layer is resolving molecule identity across heterogeneous data sources. Each source uses different identifier systems, and the platform must map between them to create unified molecule profiles.

#### Identifier Type Inventory

| Identifier | Format | Example | Primary Sources | Coverage |
|------------|--------|---------|-----------------|----------|
| **InChI Key** (canonical) | 27-char hash | `BSYNRYMUTXBXSQ-UHFFFAOYSA-N` | ChEMBL, PubChem, BindingDB | ~95% small molecules |
| **InChI** | Variable string | `InChI=1S/C9H8O4/c1-6(10)...` | PubChem, ChEMBL | ~95% small molecules |
| **SMILES** | Variable string | `CC(=O)OC1=CC=CC=C1C(=O)O` | All chemistry sources | ~98% small molecules |
| **ChEMBL ID** | `CHEMBL{N}` | `CHEMBL25` | ChEMBL | 2.4M compounds |
| **PubChem CID** | Integer | `2244` | PubChem | 116M compounds |
| **DrugBank ID** | `DB{NNNNN}` | `DB00945` | DrugBank | 15K drugs |
| **UNII** | 10-char alphanumeric | `R16CO5Y76E` | FDA (OpenFDA, Orange Book) | ~100K substances |
| **CAS Number** | `NNNNN-NN-N` | `50-78-2` | Publications, patents | Universal |
| **RxNorm CUI** | Integer | `1191` | RxNorm, clinical systems | US marketed drugs |
| **NDC Code** | `NNNNN-NNNN-NN` | `00069-1520-01` | FDA, pharmacy systems | US products only |
| **INN Name** | Text | `aspirin` | WHO, regulatory | ~10K names |
| **ATC Code** | 7-char | `N02BA01` | WHO | Therapeutic classification |
| **UniProt ID** | `[A-Z][0-9]{5}` | `P23219` | UniProt (for biologics) | Proteins/biologics |
| **STITCH ID** | `CIDm{N}` or `CIDs{N}` | `CIDm2244` | SIDER | Maps to PubChem |

#### Resolution Hierarchy

InChI Key serves as the canonical identifier for small molecules. For biologics and complex drugs, DrugBank ID or UniProt ID is used as fallback.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     IDENTIFIER RESOLUTION HIERARCHY                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                           ┌─────────────────┐                                │
│                           │   InChI Key     │ ◄── Canonical Master           │
│                           │  (27-char hash) │     (structure-based)          │
│                           └────────┬────────┘                                │
│                                    │                                         │
│         ┌──────────────────────────┼──────────────────────────┐              │
│         │                          │                          │              │
│         ▼                          ▼                          ▼              │
│  ┌──────────────┐         ┌──────────────┐          ┌──────────────┐        │
│  │   ChEMBL ID  │         │  PubChem CID │          │ DrugBank ID  │        │
│  │  (2.4M)      │         │   (116M)     │          │   (15K)      │        │
│  └──────┬───────┘         └──────┬───────┘          └──────┬───────┘        │
│         │                        │                         │                 │
│         ▼                        ▼                         ▼                 │
│  ┌──────────────┐         ┌──────────────┐          ┌──────────────┐        │
│  │  BindingDB   │         │    SIDER     │          │    RxNorm    │        │
│  │   targets    │         │  (via STITCH)│          │     CUI      │        │
│  └──────────────┘         └──────────────┘          └──────┬───────┘        │
│                                                            │                 │
│                                                            ▼                 │
│                                                    ┌──────────────┐          │
│                                                    │  NDC Codes   │          │
│                                                    │  (products)  │          │
│                                                    └──────────────┘          │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ FALLBACK FOR BIOLOGICS (no InChI Key):                               │   │
│  │   UniProt ID → DrugBank ID → UNII → Generic Name                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Identifier Mapping Table

```sql
-- Cross-reference mapping table for identifier resolution
CREATE TABLE silver_identifier_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The canonical molecule reference
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Identifier being mapped
    identifier_type VARCHAR(30) NOT NULL, -- inchi_key, chembl_id, pubchem_cid, etc.
    identifier_value VARCHAR(500) NOT NULL,

    -- Provenance
    source VARCHAR(50) NOT NULL, -- Which API/database provided this mapping
    confidence DECIMAL DEFAULT 1.0, -- 0-1, lower for fuzzy matches

    -- Validation
    is_primary BOOLEAN DEFAULT FALSE, -- Is this the primary ID for this type?
    is_validated BOOLEAN DEFAULT FALSE,
    validated_at TIMESTAMPTZ,
    validated_by VARCHAR(100), -- API or user

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(molecule_id, identifier_type, identifier_value),
    INDEX idx_mapping_type_value (identifier_type, identifier_value),
    INDEX idx_mapping_molecule (molecule_id)
);

-- Name aliases (for fuzzy name resolution)
CREATE TABLE silver_molecule_aliases (
    alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Alias information
    alias_name VARCHAR(500) NOT NULL,
    alias_type VARCHAR(30) NOT NULL, -- brand_name, generic_name, inn, synonym, trade_name

    -- Context
    region VARCHAR(50), -- USA, EU, etc. (for regional brand names)
    language VARCHAR(10), -- en, de, ja, etc.

    -- Source
    source VARCHAR(50) NOT NULL,

    -- Search optimization
    alias_name_normalized VARCHAR(500), -- Lowercase, no special chars

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes
    INDEX idx_alias_name (alias_name_normalized),
    INDEX idx_alias_molecule (molecule_id)
);
```

#### Resolution Strategy

The system resolves identifiers in the following order:

1. **Direct Lookup**: Query `silver_identifier_mappings` for exact match
2. **Structure-based Resolution**: Convert SMILES → InChI Key using RDKit
3. **API Cross-reference**: Query external APIs (PubChem, ChEMBL, UniChem) for mappings
4. **Name-based Resolution**: Fuzzy match against `silver_molecule_aliases` using **Levenshtein + trigram** (pg_trgm)
5. **Manual Curation**: Flag for human review if confidence < 0.8

#### Source Precedence for Conflicting Data

When multiple sources provide different values for the same property, use this precedence order (trust curation quality):

| Precedence | Source | Rationale |
|------------|--------|-----------|
| 1 (Highest) | **DrugBank** | FDA-linked, manually curated by pharmacists |
| 2 | **ChEMBL** | EBI-curated, structure-validated, peer-reviewed |
| 3 | **PubChem** | Broad coverage, automated aggregation |
| 4 | **BindingDB** | Experimental data, less curation |
| 5 | **SIDER** | Derived from drug labels, older data |
| 6 (Lowest) | **Other sources** | Case-by-case evaluation |

**Implementation**: When merging molecule records in Silver layer:
```python
SOURCE_PRECEDENCE = ['drugbank', 'chembl', 'pubchem', 'bindingdb', 'sider']

def merge_property(property_name: str, values_by_source: Dict[str, Any]) -> Any:
    """Return highest-precedence non-null value."""
    for source in SOURCE_PRECEDENCE:
        if source in values_by_source and values_by_source[source] is not None:
            return values_by_source[source]
    return None
```

#### Low-Confidence Resolution Quarantine Workflow

When entity resolution confidence is < 0.8, records are quarantined for manual review:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUARANTINE WORKFLOW FOR LOW-CONFIDENCE MATCHES            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Bronze Record                                                               │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────┐                                                         │
│  │ Entity          │                                                         │
│  │ Resolution      │                                                         │
│  └────────┬────────┘                                                         │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────┐      ┌─────────────────────────┐               │
│  │ Confidence >= 0.8?      │──NO─▶│ QUARANTINE              │               │
│  └────────┬────────────────┘      │ - Silver: needs_review  │               │
│           │                       │ - Excluded from Gold    │               │
│          YES                      │ - Added to review queue │               │
│           │                       └───────────┬─────────────┘               │
│           ▼                                   │                              │
│  ┌─────────────────┐                          ▼                              │
│  │ Silver Layer    │               ┌─────────────────────────┐              │
│  │ (full access)   │               │ Manual Review UI        │              │
│  └────────┬────────┘               │ - Show candidate matches│              │
│           │                        │ - Allow merge/reject    │              │
│           ▼                        │ - Record decision       │              │
│  ┌─────────────────┐               └───────────┬─────────────┘              │
│  │ Gold Layer      │                           │                             │
│  │ (aggregations)  │◀──────────────────────────┘                             │
│  └─────────────────┘         (after review approval)                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Silver Table Schema Addition**:
```sql
-- Add quarantine columns to silver_molecules
ALTER TABLE silver_molecules ADD COLUMN IF NOT EXISTS
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason TEXT,
    resolution_confidence DECIMAL(3,2),
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(100);

-- Index for review queue
CREATE INDEX idx_molecules_needs_review ON silver_molecules(needs_review)
WHERE needs_review = TRUE;

-- Gold layer views MUST exclude quarantined records
CREATE VIEW gold_molecule_profile AS
SELECT * FROM silver_molecules WHERE needs_review = FALSE;
```

**Fuzzy Name Matching Implementation** (PostgreSQL pg_trgm):

```sql
-- Enable pg_trgm extension
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create GIN index for fast trigram searches
CREATE INDEX idx_alias_trigram ON silver_molecule_aliases
USING GIN (alias_name_normalized gin_trgm_ops);

-- Fuzzy search function with similarity threshold
CREATE OR REPLACE FUNCTION fuzzy_molecule_search(
    search_term TEXT,
    similarity_threshold FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    molecule_id UUID,
    matched_name VARCHAR,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.molecule_id,
        a.alias_name,
        similarity(a.alias_name_normalized, LOWER(search_term)) as sim
    FROM silver_molecule_aliases a
    WHERE a.alias_name_normalized % LOWER(search_term)  -- trigram similarity operator
      AND similarity(a.alias_name_normalized, LOWER(search_term)) >= similarity_threshold
    ORDER BY sim DESC
    LIMIT 10;
END;
$$ LANGUAGE plpgsql;

-- Example: Search for "asprin" (misspelled)
SELECT * FROM fuzzy_molecule_search('asprin', 0.4);
-- Returns: aspirin with similarity ~0.6
```

```python
class IdentifierResolver:
    """Resolves any identifier to canonical molecule_id."""

    RESOLUTION_ORDER = [
        ("inchi_key", 1.0),    # Canonical - always highest priority
        ("chembl_id", 0.95),   # Structure-validated
        ("pubchem_cid", 0.95), # Structure-validated
        ("drugbank_id", 0.90), # Curated database
        ("unii", 0.85),        # FDA standard
        ("cas_number", 0.80),  # Universal but sometimes ambiguous
        ("rxnorm_cui", 0.80),  # Clinical standard
        ("generic_name", 0.70), # Can be ambiguous
        ("brand_name", 0.60),  # Region-specific, can conflict
    ]

    async def resolve(
        self,
        identifier: str,
        identifier_type: Optional[str] = None
    ) -> Optional[Tuple[UUID, float]]:
        """
        Resolve identifier to molecule_id with confidence score.

        Returns (molecule_id, confidence) or None if not found.
        """
        # 1. If type is known, direct lookup
        if identifier_type:
            result = await self._direct_lookup(identifier, identifier_type)
            if result:
                return result

        # 2. Auto-detect identifier type
        detected_type = self._detect_identifier_type(identifier)
        if detected_type:
            result = await self._direct_lookup(identifier, detected_type)
            if result:
                return result

        # 3. Try structure conversion (SMILES → InChI Key)
        if self._looks_like_smiles(identifier):
            inchi_key = self._smiles_to_inchi_key(identifier)
            if inchi_key:
                result = await self._direct_lookup(inchi_key, "inchi_key")
                if result:
                    return result

        # 4. Cross-reference via external APIs
        result = await self._external_api_resolution(identifier)
        if result:
            return result

        # 5. Fuzzy name matching
        result = await self._fuzzy_name_match(identifier)
        if result and result[1] >= 0.7:  # Only return if confidence >= 70%
            return result

        return None

    def _detect_identifier_type(self, identifier: str) -> Optional[str]:
        """Auto-detect identifier type from format."""
        import re

        patterns = {
            "inchi_key": r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$",
            "chembl_id": r"^CHEMBL\d+$",
            "drugbank_id": r"^DB\d{5}$",
            "pubchem_cid": r"^\d{1,9}$",  # Up to 9 digits
            "unii": r"^[A-Z0-9]{10}$",
            "cas_number": r"^\d{2,7}-\d{2}-\d$",
            "rxnorm_cui": r"^\d{4,7}$",
            "ndc_code": r"^\d{5}-\d{4}-\d{2}$",
            "atc_code": r"^[A-Z]\d{2}[A-Z]{2}\d{2}$",
        }

        for id_type, pattern in patterns.items():
            if re.match(pattern, identifier):
                return id_type

        return None  # Assume name if no pattern matches
```

#### Source-Specific Identifier Mappings

| Data Source | Primary ID | Secondary IDs Available | Resolution Method |
|-------------|-----------|------------------------|-------------------|
| **ChEMBL** | ChEMBL ID | InChI Key, SMILES, UniProt, PubChem | API cross-ref |
| **PubChem** | PubChem CID | InChI Key, SMILES, CAS, UNII | PUG-REST API |
| **DrugBank** | DrugBank ID | CAS, UNII, RxNorm, ChEMBL | XML mapping file |
| **BindingDB** | BindingDB ID | InChI Key, ChEMBL ID, PubChem | TSV download |
| **OpenFDA Labels** | Set ID | UNII, RxNorm, NDC, application_number | API response |
| **SIDER** | STITCH ID | PubChem CID (extracted), drug name | CID extraction |
| **UniProt** | UniProt ID | Gene symbol, ChEMBL target ID | API cross-ref |
| **Orange Book** | Application Number | NDC, patent numbers, UNII | Download file |
| **ClinicalTrials.gov** | NCT ID | Intervention names (fuzzy) | Name matching |

#### Special Cases

1. **SIDER STITCH ID Resolution**: SIDER uses STITCH IDs (`CIDm2244` or `CIDs2244`). Extract PubChem CID: `CIDm2244` → PubChem CID `2244` (merged) or `CIDs2244` → `2244` (stereo-specific).

2. **Biologics Without InChI Key**: For antibodies, proteins, and cell therapies that lack InChI Keys:
   - Use UniProt ID as primary for protein sequences
   - Use DrugBank ID as fallback master
   - UNII is available for most FDA-approved biologics

3. **Salt Forms and Stereoisomers**: Same active ingredient may have different InChI Keys for different salt forms:
   - Group under single `molecule_id` with `inchi_key_parent` (connectivity layer only)
   - Track specific forms in `silver_identifier_mappings` with `is_salt_form = TRUE`

4. **Multi-Component Drugs**: Fixed-dose combinations have unique identifiers:
   - Create separate `molecule_id` for the combination
   - Link to component `molecule_ids` via `silver_molecule_components` table

### Master Entity Tables

```sql
-- Canonical molecule identity table
CREATE TABLE silver_molecules (
    molecule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Primary identifier (27-character hash)
    inchi_key VARCHAR(27) UNIQUE NOT NULL,

    -- Cross-reference identifiers
    drugbank_id VARCHAR(20),
    chembl_id VARCHAR(30),
    pubchem_cid BIGINT,
    rxnorm_cui VARCHAR(20),
    unii VARCHAR(20),
    cas_number VARCHAR(20),
    ndc_codes TEXT[],

    -- Names (canonical + aliases)
    canonical_name VARCHAR(500),
    brand_names TEXT[],
    generic_names TEXT[],
    synonyms TEXT[],

    -- Structure
    smiles TEXT,
    inchi TEXT,
    molecular_formula VARCHAR(200),

    -- Classification
    molecule_type VARCHAR(50), -- small_molecule, biologic, gene_therapy, etc.
    therapeutic_areas TEXT[],
    atc_codes TEXT[],

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    source_count INTEGER DEFAULT 1,

    -- Indexes
    INDEX idx_molecules_drugbank (drugbank_id),
    INDEX idx_molecules_chembl (chembl_id),
    INDEX idx_molecules_pubchem (pubchem_cid),
    INDEX idx_molecules_name (canonical_name)
);

-- Canonical target identity table
CREATE TABLE silver_targets (
    target_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Primary identifier
    uniprot_id VARCHAR(20) UNIQUE NOT NULL,

    -- Cross-references
    gene_symbol VARCHAR(50),
    ensembl_id VARCHAR(30),
    hgnc_id VARCHAR(20),

    -- Information
    protein_name VARCHAR(500),
    organism VARCHAR(100),
    target_class VARCHAR(100), -- GPCR, kinase, ion_channel, etc.

    -- Function
    function_description TEXT,
    subcellular_location TEXT,
    pathway_involvement TEXT[],

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Standard Silver Schemas

```sql
-- Clinical trials (normalized from ClinicalTrials.gov)
CREATE TABLE silver_clinical_trials (
    trial_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nct_id VARCHAR(20) UNIQUE NOT NULL,

    -- Basic info
    title TEXT,
    brief_summary TEXT,
    phase VARCHAR(20), -- Phase 1, Phase 2, Phase 3, Phase 4, N/A
    status VARCHAR(50), -- Recruiting, Completed, Terminated, etc.
    study_type VARCHAR(50), -- Interventional, Observational

    -- Molecule link
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    intervention_names TEXT[],

    -- Conditions
    conditions TEXT[],
    condition_mesh_terms TEXT[],

    -- Design
    enrollment_target INTEGER,
    enrollment_actual INTEGER,
    primary_outcomes TEXT[],
    secondary_outcomes TEXT[],

    -- Dates
    start_date DATE,
    completion_date DATE,
    primary_completion_date DATE,
    first_posted DATE,
    last_updated DATE,

    -- Sponsor
    sponsor VARCHAR(500),
    sponsor_type VARCHAR(50), -- Industry, NIH, Academic, etc.
    collaborators TEXT[],

    -- Results (if available)
    has_results BOOLEAN DEFAULT FALSE,
    outcome_type VARCHAR(50), -- Success, Failure, Inconclusive

    -- Metadata
    bronze_source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Drug labels (normalized from OpenFDA/DailyMed)
CREATE TABLE silver_drug_labels (
    label_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id VARCHAR(50) UNIQUE NOT NULL,
    spl_id VARCHAR(50),

    -- Molecule link
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Product info
    brand_name VARCHAR(500),
    generic_name VARCHAR(500),
    manufacturer VARCHAR(500),
    application_number VARCHAR(20), -- NDA/BLA number

    -- Regulatory
    approval_date DATE,
    marketing_status VARCHAR(50),
    route_of_administration TEXT[],
    dosage_forms TEXT[],

    -- Label content
    indications TEXT,
    contraindications TEXT,
    warnings TEXT,
    boxed_warning TEXT,
    adverse_reactions TEXT,
    drug_interactions TEXT,

    -- Metadata
    effective_date DATE,
    version_number INTEGER,
    bronze_source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Adverse events (normalized from FAERS + SIDER)
CREATE TABLE silver_adverse_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    source VARCHAR(20) NOT NULL, -- faers, sider, eudravigilance
    source_report_id VARCHAR(100),

    -- Molecule link
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    drug_name_reported VARCHAR(500),

    -- Event details
    reaction_meddra_pt VARCHAR(500), -- MedDRA Preferred Term
    reaction_meddra_code VARCHAR(20),
    organ_system_class VARCHAR(200), -- MedDRA SOC

    -- Severity
    is_serious BOOLEAN,
    seriousness_death BOOLEAN,
    seriousness_hospitalization BOOLEAN,
    seriousness_disability BOOLEAN,
    seriousness_lifethreatening BOOLEAN,

    -- Frequency (from SIDER)
    frequency_category VARCHAR(50), -- rare, infrequent, frequent
    frequency_lower DECIMAL,
    frequency_upper DECIMAL,

    -- Patient demographics (from FAERS)
    patient_age INTEGER,
    patient_sex VARCHAR(10),
    patient_weight DECIMAL,

    -- Outcome
    outcome VARCHAR(50), -- recovered, not_recovered, fatal, unknown

    -- Metadata
    report_date DATE,
    bronze_source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Patents (normalized from Orange Book + USPTO)
CREATE TABLE silver_patents (
    patent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patent_number VARCHAR(30) UNIQUE NOT NULL,

    -- Molecule link
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    application_number VARCHAR(20), -- NDA/BLA if from Orange Book

    -- Patent info
    title TEXT,
    abstract TEXT,
    claims TEXT,

    -- Dates
    filing_date DATE,
    issue_date DATE,
    expiry_date DATE,

    -- Parties
    assignee VARCHAR(500),
    inventors TEXT[],

    -- Classification
    patent_type VARCHAR(50), -- drug_substance, formulation, method_of_use
    exclusivity_codes TEXT[],

    -- Metadata
    source VARCHAR(20), -- orange_book, uspto, epo
    bronze_source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bioactivity data (normalized from ChEMBL + BindingDB)
CREATE TABLE silver_bioactivity (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Links
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    target_id UUID REFERENCES silver_targets(target_id),

    -- Source
    source VARCHAR(20) NOT NULL, -- chembl, bindingdb
    source_assay_id VARCHAR(50),

    -- Activity measurement
    activity_type VARCHAR(20), -- IC50, Ki, Kd, EC50
    activity_value DECIMAL,
    activity_units VARCHAR(20), -- nM, uM
    activity_relation VARCHAR(5), -- =, <, >, ~
    pchembl_value DECIMAL, -- Standardized -log10(activity)

    -- Assay info
    assay_type VARCHAR(50), -- binding, functional
    assay_description TEXT,

    -- Metadata
    bronze_source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Publications (normalized from OpenAlex/PubMed)
CREATE TABLE silver_publications (
    publication_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identifiers
    doi VARCHAR(200) UNIQUE,
    pmid VARCHAR(20),
    pmcid VARCHAR(20),

    -- Content
    title TEXT,
    abstract TEXT,
    authors TEXT[],
    journal VARCHAR(500),
    publication_date DATE,

    -- Classification
    mesh_terms TEXT[],
    keywords TEXT[],
    publication_type VARCHAR(50), -- research, review, clinical_trial, etc.

    -- Links (many-to-many, separate table)
    -- molecule_publications links to silver_molecules

    -- Metrics
    citation_count INTEGER,

    -- Metadata
    bronze_source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Regulatory actions (approvals, warnings, withdrawals)
CREATE TABLE silver_regulatory_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Molecule link
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Action details
    action_type VARCHAR(50), -- approval, withdrawal, safety_update, boxed_warning
    agency VARCHAR(50), -- FDA, EMA, PMDA, Health_Canada
    region VARCHAR(50),

    -- Product
    product_name VARCHAR(500),
    application_number VARCHAR(50),

    -- Action specifics
    action_date DATE,
    indication TEXT,
    description TEXT,

    -- For approvals
    approval_type VARCHAR(50), -- standard, accelerated, priority, breakthrough

    -- Metadata
    source_url TEXT,
    bronze_source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Transformation Pipeline

```python
@dataclass
class TransformationJob:
    job_id: UUID
    source_table: str              # bronze_clinicaltrials
    target_table: str              # silver_clinical_trials
    status: Literal["pending", "running", "success", "failed"]

    # Execution
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Metrics
    records_read: int
    records_written: int
    records_skipped: int
    records_failed: int

    # Error handling
    error_message: Optional[str]
    failed_record_ids: List[UUID]

    # Incremental processing
    last_processed_timestamp: datetime
    is_full_refresh: bool
```

---

## Part 3: Business Intelligence Layer (Gold)

### Purpose
Pre-compute aggregated, decision-ready data for end users. Gold tables are rebuilt from Silver as requirements change, enabling business agility without data loss.

### User Story 3.1 - Query Gold for Decision Support (Priority: P1)

A business user wants to query pre-aggregated, decision-ready data for portfolio analysis or competitive intelligence without understanding data complexity.

**Acceptance Scenarios**:

1. **Given** Silver data for a molecule across trials, labels, and patents, **When** Gold aggregation runs, **Then** `gold_molecule_profile` contains unified view with current stage, trial count, approval status, patent expiry
2. **Given** a user queries competitive landscape, **When** Gold is queried, **Then** response includes pre-computed competitive position, market share indicators, and differentiation scores
3. **Given** new Silver data arrives, **When** Gold refresh runs, **Then** aggregations update incrementally without full recomputation

### User Story 3.2 - Lifecycle Stage Detection (Priority: P1)

A portfolio manager needs the system to automatically detect the current development stage of a molecule based on available evidence.

**Acceptance Scenarios**:

1. **Given** a molecule with Phase 3 trials in Silver, **When** lifecycle detection runs, **Then** Gold shows current_stage="Phase 3" with evidence links
2. **Given** conflicting evidence (FDA approval + ongoing Phase 4), **When** detected, **Then** the most advanced confirmed stage is used with conflicts flagged
3. **Given** evidence of trial failure or discontinuation, **When** detected, **Then** system flags potential stage regression for user confirmation

### Gold Table Schemas

```sql
-- Unified molecule profile (THE key Gold table)
CREATE TABLE gold_molecule_profile (
    molecule_id UUID PRIMARY KEY REFERENCES silver_molecules(molecule_id),

    -- Identity (denormalized for query performance)
    inchi_key VARCHAR(27) NOT NULL,
    canonical_name VARCHAR(500),
    brand_names TEXT[],
    molecule_type VARCHAR(50),

    -- LIFECYCLE STATE (computed from evidence)
    current_stage VARCHAR(50), -- Discovery, Preclinical, Phase1, Phase2, Phase3, NDA_Filed, Approved, Marketed
    stage_confidence DECIMAL, -- 0-1 confidence in stage detection
    stage_evidence_count INTEGER,
    stage_last_updated TIMESTAMPTZ,

    -- Lifecycle dates (extracted from evidence)
    discovery_date DATE,
    ind_filed_date DATE,
    phase1_start_date DATE,
    phase2_start_date DATE,
    phase3_start_date DATE,
    nda_filed_date DATE,
    approval_date DATE,
    first_marketed_date DATE,

    -- Clinical summary
    total_trials INTEGER,
    active_trials INTEGER,
    trials_by_phase JSONB, -- {"Phase 1": 5, "Phase 2": 3, ...}
    total_enrollment INTEGER,
    primary_indications TEXT[],

    -- Regulatory summary
    approvals_by_region JSONB, -- {"USA": {date, status}, "EU": {...}}
    current_label_date DATE,
    has_boxed_warning BOOLEAN,
    orphan_designations TEXT[],
    breakthrough_designations TEXT[],

    -- Safety summary
    total_adverse_events INTEGER,
    serious_adverse_events INTEGER,
    top_adverse_events JSONB, -- [{event, frequency, severity}, ...]
    safety_signal_count INTEGER,

    -- Patent/exclusivity summary
    earliest_patent_expiry DATE,
    latest_exclusivity_expiry DATE,
    active_patents INTEGER,

    -- Commercial (for marketed drugs)
    latest_annual_revenue_usd DECIMAL,
    revenue_trend VARCHAR(20), -- growing, stable, declining

    -- Competitive
    competitor_count INTEGER,
    competitor_molecule_ids UUID[],

    -- Metadata
    data_completeness_score DECIMAL, -- 0-1 based on available data
    last_refreshed TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes
    INDEX idx_gold_stage (current_stage),
    INDEX idx_gold_name (canonical_name),
    INDEX idx_gold_approval (approval_date)
);

-- Competitive landscape aggregation
CREATE TABLE gold_competitive_landscape (
    landscape_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Grouping
    therapeutic_area VARCHAR(200),
    indication VARCHAR(500),
    mechanism_of_action VARCHAR(500),

    -- Molecules in this landscape
    molecule_ids UUID[],
    molecule_count INTEGER,

    -- Stage distribution
    discovery_count INTEGER,
    preclinical_count INTEGER,
    phase1_count INTEGER,
    phase2_count INTEGER,
    phase3_count INTEGER,
    approved_count INTEGER,

    -- Leaders
    first_to_market_molecule_id UUID,
    highest_revenue_molecule_id UUID,
    most_advanced_pipeline_molecule_id UUID,

    -- Market metrics (for approved)
    total_market_size_usd DECIMAL,
    market_growth_rate DECIMAL,

    -- Competitive dynamics
    avg_time_to_approval_months INTEGER,
    success_rate_phase1_to_approval DECIMAL,

    -- Metadata
    last_refreshed TIMESTAMPTZ DEFAULT NOW()
);

-- Safety signal aggregation
CREATE TABLE gold_safety_signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Molecule
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Signal identification
    reaction_meddra_pt VARCHAR(500),
    organ_system_class VARCHAR(200),

    -- Metrics
    total_reports INTEGER,
    serious_reports INTEGER,
    fatal_reports INTEGER,

    -- Disproportionality analysis
    pro_score DECIMAL, -- Proportional Reporting Ratio
    ror_score DECIMAL, -- Reporting Odds Ratio
    ic_score DECIMAL, -- Information Component

    -- Trend
    reports_last_quarter INTEGER,
    reports_previous_quarter INTEGER,
    trend VARCHAR(20), -- increasing, stable, decreasing

    -- Signal status
    is_known_reaction BOOLEAN, -- In label
    is_emerging_signal BOOLEAN,

    -- Metadata
    last_refreshed TIMESTAMPTZ DEFAULT NOW()
);

-- Pipeline summary by company
CREATE TABLE gold_company_pipeline (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name VARCHAR(500) UNIQUE NOT NULL,

    -- Pipeline counts
    total_molecules INTEGER,
    discovery_count INTEGER,
    preclinical_count INTEGER,
    phase1_count INTEGER,
    phase2_count INTEGER,
    phase3_count INTEGER,
    approved_count INTEGER,

    -- Molecule lists
    molecule_ids UUID[],

    -- Revenue
    total_pharma_revenue_usd DECIMAL,
    top_5_products JSONB, -- [{molecule_id, name, revenue}, ...]

    -- Risk metrics
    revenue_at_risk_5y DECIMAL, -- From patent cliffs
    pipeline_balance_score DECIMAL, -- 0-1

    -- Metadata
    last_refreshed TIMESTAMPTZ DEFAULT NOW()
);
```

### Lifecycle Stage Detection Algorithm

```python
class LifecycleStage(Enum):
    DISCOVERY = "Discovery"
    PRECLINICAL = "Preclinical"
    IND_FILED = "IND Filed"
    PHASE_1 = "Phase 1"
    PHASE_2 = "Phase 2"
    PHASE_3 = "Phase 3"
    NDA_FILED = "NDA/BLA Filed"
    FDA_REVIEW = "FDA Review"
    APPROVED = "Approved"
    MARKETED = "Marketed"
    WITHDRAWN = "Withdrawn"

# Evidence requirements per stage
STAGE_EVIDENCE_REQUIREMENTS = {
    LifecycleStage.DISCOVERY: [
        "target_identification",  # ChEMBL/UniProt target link
        "mechanism_hypothesis",   # Publication or patent
    ],
    LifecycleStage.PRECLINICAL: [
        "animal_study_data",     # Publication
        "safety_pharmacology",   # Patent or publication
    ],
    LifecycleStage.IND_FILED: [
        "ind_number",            # FDA database
        "sec_filing_mention",    # SEC EDGAR
    ],
    LifecycleStage.PHASE_1: [
        "nct_id_phase1",         # ClinicalTrials.gov
        "trial_status_active",
    ],
    LifecycleStage.PHASE_2: [
        "nct_id_phase2",
        "efficacy_signal",       # Publication or trial results
    ],
    LifecycleStage.PHASE_3: [
        "nct_id_phase3_pivotal",
        "enrollment_significant", # >100 patients
    ],
    LifecycleStage.NDA_FILED: [
        "nda_bla_number",        # FDA
        "pdufa_date",
    ],
    LifecycleStage.APPROVED: [
        "approval_letter",       # FDA Drugs@FDA
        "label_set_id",          # DailyMed
    ],
    LifecycleStage.MARKETED: [
        "revenue_data",          # SEC EDGAR
        "label_updates",         # DailyMed history
    ],
}

def detect_lifecycle_stage(molecule_id: UUID) -> Tuple[LifecycleStage, float]:
    """
    Detect lifecycle stage by checking evidence requirements
    from most advanced stage backward.

    Returns (stage, confidence_score)
    """
    # Check from most advanced to least
    for stage in reversed(list(LifecycleStage)):
        requirements = STAGE_EVIDENCE_REQUIREMENTS.get(stage, [])
        evidence_found = check_evidence_for_stage(molecule_id, requirements)

        if evidence_found:
            confidence = calculate_confidence(molecule_id, stage, evidence_found)
            return stage, confidence

    return LifecycleStage.DISCOVERY, 0.5  # Default
```

---

## Part 4: Molecule Onboarding Application

### Purpose
User-facing application for tracking molecules through their lifecycle with a streamlined 10-step onboarding workflow.

### User Story 4.1 - Onboard New Molecule (Priority: P1)

A data analyst wants to add a new molecule to track by entering its name or identifier, and have the system automatically detect its lifecycle stage and populate available data.

**Acceptance Scenarios**:

1. **Given** a drug name (e.g., "Dupixent"), **When** the user initiates onboarding, **Then** the system resolves identifiers (DrugBank, RxNorm, NDC), queries Gold layer for profile, and shows available data by source
2. **Given** a DrugBank ID (e.g., "DB06674"), **When** the user initiates onboarding, **Then** the system uses the ID to fetch existing Gold profile or trigger Bronze-Silver-Gold pipeline
3. **Given** an unknown or misspelled drug name, **When** the user initiates onboarding, **Then** the system suggests similar molecules and allows selection or manual entry
4. **Given** a novel compound not in any database, **When** the user initiates onboarding, **Then** the system allows manual entry starting at Discovery stage

### User Story 4.2 - View Lifecycle Stage Evidence (Priority: P1)

A regulatory analyst wants to see what evidence supports the current lifecycle stage, including gaps.

**Acceptance Scenarios**:

1. **Given** a molecule at Phase 2 stage, **When** the user views requirements, **Then** the system shows: required evidence, present evidence with source links, missing evidence with guidance
2. **Given** a molecule with all requirements met, **When** the user views requirements, **Then** all items show as "validated" with green checkmarks and clickable evidence links
3. **Given** a molecule missing critical evidence, **When** the user views requirements, **Then** missing items are highlighted with specific guidance on data sources

### User Story 4.3 - Validate Stage and Progress (Priority: P1)

A data operations team member wants to validate that a molecule has sufficient evidence for its claimed stage.

**Acceptance Scenarios**:

1. **Given** a molecule with all Phase 2 evidence present, **When** the user clicks "Validate Stage", **Then** the system confirms validation, logs the audit event, and enables tracking
2. **Given** a molecule claiming Phase 3 but missing required trial data, **When** the user clicks "Validate Stage", **Then** the system rejects with specific missing items
3. **Given** new evidence arriving (e.g., FDA approval), **When** evidence is detected, **Then** the system automatically suggests stage progression

### 10-Step Onboarding Flow

| Step | Name | Description | Data Layer |
|------|------|-------------|------------|
| 1 | **Identify** | Enter molecule name or ID, resolve to canonical identifiers | Query Silver molecules |
| 2 | **Classify** | Confirm molecule type (small molecule, biologic, gene therapy) | Read/update Silver |
| 3 | **Stage Detect** | Auto-detect lifecycle stage from evidence | Read Gold profile |
| 4 | **Evidence Review** | Review detected evidence, confirm accuracy | Read Silver evidence |
| 5 | **Fill Gaps** | Add missing required evidence (optional) | Write to Silver |
| 6 | **Validate Stage** | Confirm stage with evidence validation | Update Gold |
| 7 | **Competitors** | Identify and link competitor molecules | Read Gold landscape |
| 8 | **Indications** | Specify tracked indications | Write user annotations |
| 9 | **Alerts** | Configure tracking alerts | Write alert configs |
| 10 | **Complete** | Finalize and add to portfolio | Write tracked molecules |

### Wizard UX Behavior

- **Navigation**: Free navigation - all 10 steps accessible at any time via step indicator/sidebar
- **Saving**: Auto-save on each field change; no explicit "Save" button required per step
- **Validation**: Final validation only when user clicks "Complete" (Step 10); individual steps show warnings but don't block navigation
- **Progress Indicator**: Visual indicator shows which steps have data entered vs. empty; completion percentage displayed
- **Loading States**: Skeleton loaders for async data fetches (e.g., molecule resolution, evidence lookup); step content remains interactive during background loads
- **Error Handling**: API errors displayed as dismissible toast notifications; failed saves retry automatically with exponential backoff; offline changes queued for sync
- **Resumability**: Incomplete onboarding sessions persist indefinitely; user can return and continue from any step

### Application Tables

```sql
-- User-tracked molecules
-- NOTE: For multi-indication tracking, create SEPARATE rows per indication
-- This allows tracking different lifecycle stages per indication (e.g.,
-- drug X: Phase 3 for oncology, Phase 2 for autoimmune)
CREATE TABLE user_tracked_molecules (
    tracking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Indication-specific tracking (one row per indication)
    indication VARCHAR(500),          -- e.g., "Non-small cell lung cancer"
    indication_mesh_term VARCHAR(50), -- MeSH term for standardization

    -- Tracking config
    tracking_name VARCHAR(500), -- User's custom name
    notes TEXT,

    -- Indication-specific lifecycle stage (may differ from Gold profile)
    tracked_stage VARCHAR(50),        -- User's assessment of stage for THIS indication
    tracked_stage_confidence DECIMAL, -- User confidence in this stage

    -- Onboarding status
    onboarding_completed BOOLEAN DEFAULT FALSE,
    onboarding_step INTEGER DEFAULT 1,
    onboarding_started_at TIMESTAMPTZ,
    onboarding_completed_at TIMESTAMPTZ,

    -- Validation
    stage_validated BOOLEAN DEFAULT FALSE,
    stage_validated_at TIMESTAMPTZ,
    stage_validated_by UUID,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Allow same user to track same molecule for different indications
    UNIQUE(user_id, molecule_id, indication)
);

-- User annotations (manual evidence additions)
CREATE TABLE user_annotations (
    annotation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Annotation
    annotation_type VARCHAR(50), -- evidence, note, correction, flag
    title VARCHAR(500),
    content TEXT,
    source_url TEXT,
    source_date DATE,

    -- For evidence annotations
    evidence_type VARCHAR(100), -- Maps to stage evidence requirements
    supports_stage VARCHAR(50),

    -- Visibility
    is_private BOOLEAN DEFAULT TRUE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alert configurations
CREATE TABLE user_alert_configs (
    alert_config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Alert types
    alert_on_stage_change BOOLEAN DEFAULT TRUE,
    alert_on_trial_update BOOLEAN DEFAULT TRUE,
    alert_on_safety_signal BOOLEAN DEFAULT TRUE,
    alert_on_regulatory_action BOOLEAN DEFAULT TRUE,
    alert_on_patent_event BOOLEAN DEFAULT FALSE,
    alert_on_publication BOOLEAN DEFAULT FALSE,

    -- Delivery
    delivery_method VARCHAR(20), -- email, webhook, in_app
    delivery_frequency VARCHAR(20), -- immediate, daily_digest, weekly_digest
    webhook_url TEXT,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alert history
CREATE TABLE alert_history (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES silver_molecules(molecule_id),
    alert_config_id UUID REFERENCES user_alert_configs(alert_config_id),

    -- Alert details
    alert_type VARCHAR(50),
    title VARCHAR(500),
    description TEXT,
    data JSONB, -- Alert-specific payload

    -- Delivery
    delivered_at TIMESTAMPTZ,
    delivery_method VARCHAR(20),
    delivery_status VARCHAR(20), -- pending, delivered, failed

    -- User interaction
    read_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log for compliance
CREATE TABLE onboarding_audit_log (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Context
    user_id UUID NOT NULL,
    molecule_id UUID,
    tracking_id UUID,

    -- Action
    action_type VARCHAR(50), -- onboard_start, stage_validate, evidence_add, etc.
    action_details JSONB,

    -- Before/after state
    previous_state JSONB,
    new_state JSONB,

    -- Metadata
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### User Story 4.4 - Set Up Tracking Alerts (Priority: P2)

A portfolio manager wants to configure alerts for lifecycle events.

**Acceptance Scenarios**:

1. **Given** a molecule at Phase 3, **When** the user enables "Stage Transition" alerts, **Then** they receive notification when FDA acceptance or approval is detected
2. **Given** multiple molecules tracked, **When** the user configures "weekly digest", **Then** they receive one summary email per week
3. **Given** a safety signal detected in FAERS, **When** user has "Safety Alert" enabled, **Then** they receive immediate notification with details

### User Story 4.5 - Bulk Molecule Onboarding (Priority: P3)

A data team wants to onboard multiple molecules at once via spreadsheet upload.

**Acceptance Scenarios**:

1. **Given** a CSV with 50 molecule names, **When** uploaded for bulk onboarding, **Then** the system processes each, reports success/failure, and allows review
2. **Given** a CSV with some invalid entries, **When** processed, **Then** valid molecules are onboarded and invalid ones listed with specific errors
3. **Given** bulk onboarding in progress, **When** the user views status, **Then** they see real-time progress with count completed

---

## Part 5: Data Sources Inventory

### Currently Implemented (6 sources, ~9.1M records)

| Source | Table | Records | Key Data | Update Frequency |
|--------|-------|---------|----------|------------------|
| **BindingDB** | bronze_bindingdb | 2.28M | Drug-target binding affinities (Ki, Kd, IC50) | Monthly |
| **ChEMBL** | bronze_chembl | 2.73M | Bioactivity data, SAR analysis | Quarterly |
| **PubChem** | bronze_pubchem | 965K | Molecular properties, ADMET descriptors | On-demand |
| **DrugBank** | bronze_drugbank | 17.4K drugs + 2.8M DDIs | Drug info, interactions, targets | Quarterly |
| **ClinicalTrials.gov** | bronze_clinicaltrials | 95.5K | Trial metadata, outcomes | Daily |
| **FDA Labels** | bronze_openfda_labels | 83.8K | Approved drug labels, warnings | Daily |

### Priority 1 - Critical Missing Sources (~55M additional records)

| Source | Priority | Records | Key Data | Bronze Table |
|--------|----------|---------|----------|--------------|
| **UniProt** | P0 | 20K | Protein sequences, function, targets | bronze_uniprot |
| **Open Targets** | P0 | 7.5M | Target-disease associations | bronze_opentargets |
| **OpenFDA FAERS** | P0 | 20M | Adverse event reports | bronze_openfda_faers |
| **SIDER** | P0 | 449K | Drug side effects (structured) | bronze_sider |
| **EMA EPAR** | P0 | 2.6K | EU regulatory decisions | bronze_ema |
| **Orange Book** | P1 | 4K | US patents, exclusivity | bronze_orange_book |
| **Purple Book** | P1 | 500 | Biosimilar reference products | bronze_purple_book |
| **TDC Benchmarks** | P1 | 4M | ML training data (ADMET) | bronze_tdc |
| **PubChem BioAssay** | P1 | 1.5M | Assay protocols, results | bronze_pubchem_bioassay |
| **ICH Guidelines** | P1 | 58 docs | Regulatory compliance rules | bronze_ich |
| **USPTO Patents** | P1 | 500K | Pharma patent filings | bronze_patents_uspto |
| **ChEMBL MMP** | P2 | 2M | Matched molecular pairs | bronze_chembl_mmp |
| **KEGG** | P2 | 12K | Drug metabolism, pathways | bronze_kegg |
| **AlphaFold** | P2 | 5K | Protein structures | bronze_alphafold |
| **DisGeNET** | P2 | 1.1M | Gene-disease associations | bronze_disgenet |
| **AACT** | P2 | 500K | Analysis-ready trials | bronze_aact |
| **OMIM** | P2 | 16K | Genetic disorders | bronze_omim |
| **Health Canada** | P2 | 20K | Canadian regulatory | bronze_health_canada |

### Data Linkage Strategy

All entities linked via canonical identifiers:

```
                    ENTITY LINKAGE MAP
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  MOLECULES (InChI Key as master)                                │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐               │
│  │ BindingDB │────│  ChEMBL   │────│  PubChem  │               │
│  │ (inchi_key│    │(chembl_id)│    │(pubchem_  │               │
│  │  970K)    │    │  (808K)   │    │  cid 965K)│               │
│  └─────┬─────┘    └─────┬─────┘    └─────┬─────┘               │
│        │                │                │                      │
│        └────────────────┼────────────────┘                      │
│                         │                                       │
│                         ▼                                       │
│              ┌─────────────────────┐                            │
│              │  silver_molecules   │                            │
│              │  (canonical master) │                            │
│              │  Links: DrugBank,   │                            │
│              │  RxNorm, UNII, CAS  │                            │
│              └─────────────────────┘                            │
│                                                                  │
│  TARGETS (UniProt ID as master)                                 │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐               │
│  │  UniProt  │────│  ChEMBL   │────│ BindingDB │               │
│  │ (uniprot_ │    │ (target_  │    │ (target_  │               │
│  │  id 20K)  │    │ chembl_id)│    │ uniprot_id│               │
│  └───────────┘    └───────────┘    └───────────┘               │
│                                                                  │
│  TRIALS (NCT ID as master)                                      │
│  ClinicalTrials.gov ←→ AACT ←→ EMA Clinical Trials              │
│                                                                  │
│  REGULATORY (Application Number as link)                        │
│  FDA Labels ←→ Orange Book ←→ EMA EPAR                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 6: Pipeline Operations

### User Story 6.1 - Monitor Pipeline Health (Priority: P2)

A data engineer wants to monitor pipeline health and be alerted when issues occur.

**Acceptance Scenarios**:

1. **Given** active pipelines, **When** the engineer views the dashboard, **Then** they see status of Bronze ingestion, Silver transformation, and Gold aggregation with timestamps
2. **Given** a transformation fails, **When** failure occurs, **Then** the engineer receives alert with specific error, affected records, and suggested remediation
3. **Given** data quality drops below threshold, **When** detected, **Then** alert is raised before data propagates to Gold

### User Story 6.2 - Run Incremental Updates (Priority: P2)

A system administrator wants the pipeline to support incremental updates.

**Acceptance Scenarios**:

1. **Given** 1 million records in Silver and 100 new Bronze records, **When** Silver transformation runs, **Then** only new/changed records are processed
2. **Given** a record in Bronze is corrected, **When** transformation runs, **Then** corresponding Silver record is updated and propagates to Gold
3. **Given** incremental mode is enabled, **When** admin triggers full refresh, **Then** system performs full recomputation for reconciliation

### Pipeline Orchestration (SQLMesh)

SQLMesh is used for all Bronze→Silver→Gold transformations, providing:
- **Plan/Apply Workflow**: Preview changes before deploying, similar to Terraform
- **Virtual Data Environments**: Isolated development without warehouse costs
- **Incremental Models**: Automatic tracking of modified data, running only necessary transformations
- **SQL + Python Models**: Support for both SQL queries and Python transformations

```python
# Example SQLMesh model: bronze_clinicaltrials.sql (Raw → Bronze extraction)
MODEL (
    name bronze_clinicaltrials,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 1  # Process 1 day at a time
    ),
    cron '@hourly',
    depends_on [raw_clinicaltrials]
);

SELECT
    r.id as raw_id,
    NOW() as ingested_at,
    'clinicaltrials_gov' as source_id,
    'v2' as api_version,

    -- Extract typed columns from JSON response
    study->>'protocolSection'->>'identificationModule'->>'nctId' as nct_id,
    study->>'protocolSection'->>'identificationModule'->>'briefTitle' as brief_title,
    study->>'protocolSection'->>'identificationModule'->>'officialTitle' as official_title,
    study->>'protocolSection'->>'statusModule'->>'overallStatus' as overall_status,
    (study->>'protocolSection'->>'designModule'->>'phases')::JSONB as phases,
    study->>'protocolSection'->>'designModule'->>'studyType' as study_type,
    (study->>'protocolSection'->>'designModule'->>'enrollmentInfo'->>'count')::INTEGER as enrollment_count,
    study->>'protocolSection'->>'sponsorCollaboratorsModule'->>'leadSponsor'->>'name' as lead_sponsor_name,
    study->>'protocolSection'->>'sponsorCollaboratorsModule'->>'leadSponsor'->>'class' as lead_sponsor_class,
    (study->>'protocolSection'->>'armsInterventionsModule'->>'interventions')::JSONB as interventions,
    (study->>'protocolSection'->>'outcomesModule'->>'primaryOutcomes')::JSONB as primary_outcomes,
    study->>'protocolSection'->>'eligibilityModule'->>'eligibilityCriteria' as eligibility_criteria,
    (study->>'protocolSection'->>'contactsLocationsModule'->>'locations')::JSONB as locations,
    (study->>'derivedSection'->>'conditionBrowseModule'->>'meshes')::JSONB as mesh_terms,

    FALSE as processed_to_silver,
    NULL as processed_at,
    NULL as processing_error,
    md5(study::TEXT) as record_hash

FROM raw_clinicaltrials r,
     jsonb_array_elements(r.response_body->'studies') as study
WHERE r.processed_to_bronze = FALSE
  AND r.response_status = 200
  AND @start_ds <= r.request_timestamp::date
  AND r.request_timestamp::date < @end_ds;
```

```python
# Example SQLMesh model: silver_clinical_trials.sql (Bronze → Silver normalization)
MODEL (
    name silver_clinical_trials,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 7  # Process 7 days at a time
    ),
    cron '@daily',
    grain nct_id
);

SELECT
    gen_random_uuid() as trial_id,

    -- Direct column references (Bronze already has typed columns)
    b.nct_id,
    b.brief_title as title,
    b.official_title,
    b.phases[0] as phase,                    -- Extract first phase from array
    b.overall_status as status,
    b.study_type,
    b.enrollment_count,
    b.lead_sponsor_name,
    b.lead_sponsor_class,
    b.start_date,
    b.completion_date,
    b.eligibility_criteria,

    -- Link to molecule via intervention name resolution
    resolve_molecule_id(
        jsonb_array_elements_text(b.interventions)->>'name'
    ) as molecule_id,

    -- Normalize locations to structured format
    normalize_locations(b.locations) as trial_locations,

    -- Extract primary endpoints
    normalize_outcomes(b.primary_outcomes) as primary_endpoints,

    b.ingested_at as last_updated,
    b.id as bronze_source_id

FROM bronze_clinicaltrials b
WHERE NOT b.processed_to_silver
  AND @start_ds <= b.ingested_at::date
  AND b.ingested_at::date < @end_ds;
```

```python
# Example SQLMesh model: gold_molecule_profile.sql
MODEL (
    name gold_molecule_profile,
    kind FULL,  # Full refresh for aggregated Gold tables
    cron '@daily',
    grain molecule_id
);

SELECT
    m.molecule_id,
    m.inchi_key,
    m.canonical_name,
    m.brand_names,
    m.molecule_type,
    -- Lifecycle stage detection
    detect_lifecycle_stage(m.molecule_id) as current_stage,
    calculate_stage_confidence(m.molecule_id) as stage_confidence,
    -- Clinical summary
    COUNT(DISTINCT t.nct_id) as total_trials,
    COUNT(DISTINCT t.nct_id) FILTER (WHERE t.status IN ('Recruiting', 'Active')) as active_trials,
    -- Additional aggregations...
FROM silver_molecules m
LEFT JOIN silver_clinical_trials t ON m.molecule_id = t.molecule_id
GROUP BY m.molecule_id, m.inchi_key, m.canonical_name, m.brand_names, m.molecule_type;
```

**SQLMesh Project Structure**:
```
dk-data-platform/
├── models/
│   ├── raw/              # Raw layer tables (API response archive)
│   │   ├── raw_clinicaltrials.sql
│   │   ├── raw_openfda_labels.sql
│   │   └── raw_openfda_faers.sql
│   ├── bronze/           # Bronze layer (Raw → typed columns)
│   │   ├── bronze_clinicaltrials.sql
│   │   ├── bronze_openfda_labels.sql
│   │   └── bronze_openfda_faers.sql
│   ├── silver/           # Normalized, entity-resolved
│   │   ├── silver_molecules.sql
│   │   ├── silver_clinical_trials.sql
│   │   └── silver_adverse_events.sql
│   └── gold/             # Aggregated, decision-ready
│       ├── gold_molecule_profile.sql
│       └── gold_safety_signals.sql
├── macros/
│   ├── resolve_molecule_id.sql
│   └── detect_lifecycle_stage.sql
├── audits/               # Data quality checks
│   └── silver_molecules_audit.sql
├── tests/                # Unit tests
│   └── test_molecule_resolution.yaml
└── config.yaml           # SQLMesh configuration
```

**Scheduling**:
- Bronze ingestion: Custom Python scripts triggered via cron or SQLMesh seeds
- Silver transformation: `@daily` cron in SQLMesh models
- Gold aggregation: `@daily` cron, runs after Silver models complete (automatic DAG)

### Data Quality Metrics

```sql
-- Data quality tracking table
CREATE TABLE data_quality_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Target
    table_name VARCHAR(100),
    layer VARCHAR(10), -- bronze, silver, gold

    -- Metric
    metric_name VARCHAR(100), -- completeness, uniqueness, timeliness, etc.
    metric_value DECIMAL,
    threshold_value DECIMAL,
    is_passing BOOLEAN,

    -- Details
    sample_failures JSONB, -- Example records that failed

    -- Timing
    measured_at TIMESTAMPTZ DEFAULT NOW(),
    measurement_duration_ms INTEGER
);

-- Example quality checks
INSERT INTO data_quality_metrics (table_name, layer, metric_name, metric_value, threshold_value, is_passing)
VALUES
    ('silver_molecules', 'silver', 'inchi_key_completeness', 0.99, 0.95, TRUE),
    ('silver_molecules', 'silver', 'inchi_key_uniqueness', 1.00, 1.00, TRUE),
    ('silver_clinical_trials', 'silver', 'molecule_linkage_rate', 0.87, 0.80, TRUE),
    ('gold_molecule_profile', 'gold', 'stage_detection_confidence_avg', 0.82, 0.70, TRUE);
```

---

## Functional Requirements

### Raw Layer (API Response Archive)

- **FR-R01**: System MUST store complete, unmodified HTTP responses from all external API calls
- **FR-R02**: System MUST capture full request context (endpoint, params, headers) with each Raw record
- **FR-R03**: System MUST capture full response context (status code, headers, body, latency) with each Raw record
- **FR-R04**: System MUST compute SHA-256 hash of response body for deduplication detection
- **FR-R05**: System MUST retain Raw data indefinitely (no automatic deletion policy)
- **FR-R06**: System MUST preserve Raw data when Bronze extraction fails for debugging
- **FR-R07**: System MUST support reprocessing from Raw to Bronze if extraction logic changes

### Bronze Layer (Structured Ingestion)

- **FR-B01**: System MUST parse Raw JSON/XML responses into typed, queryable columns
- **FR-B02**: System MUST maintain source-native column structure (columns match source API field names)
- **FR-B03**: System MUST capture metadata with each Bronze record (timestamp, source_id, api_version, raw_id linkage)
- **FR-B04**: System MUST support schema mapping configuration (JSON path → column) for each source
- **FR-B05**: System SHOULD auto-detect JSON schema from sample responses for new source registration
- **FR-B06**: System MUST implement retry logic with exponential backoff for failed API calls
- **FR-B07**: System MUST retain Bronze data indefinitely (no automatic deletion policy)
- **FR-B07**: System MUST compute hash of raw_data for deduplication detection

### Silver Layer (Entity Resolution)

- **FR-S01**: System MUST support Silver layer with normalized, standardized schemas per data type
- **FR-S02**: System MUST resolve molecule identity across sources using InChI Key as master identifier
- **FR-S03**: System MUST deduplicate records during Bronze-to-Silver transformation
- **FR-S04**: System MUST maintain alias tables for molecule names and identifiers
- **FR-S05**: System MUST support incremental updates (process only new/changed records)
- **FR-S06**: System MUST support full refresh mode for reconciliation
- **FR-S07**: System MUST preserve Bronze data when Silver transformation fails
- **FR-S08**: System MUST log all transformations with before/after record counts and errors

### Identifier Resolution

- **FR-ID01**: System MUST accept any of the following identifier types for molecule lookup: InChI Key, ChEMBL ID, PubChem CID, DrugBank ID, UNII, CAS Number, RxNorm CUI, NDC Code, SMILES, generic name, brand name
- **FR-ID02**: System MUST auto-detect identifier type from input format using regex patterns
- **FR-ID03**: System MUST convert SMILES to InChI Key using RDKit for structure-based resolution
- **FR-ID04**: System MUST query external APIs (PubChem, ChEMBL, UniChem) for cross-reference resolution when local mapping not found
- **FR-ID05**: System MUST cache all resolved identifier mappings in `silver_identifier_mappings` table
- **FR-ID06**: System MUST support fuzzy name matching using Levenshtein distance + trigram similarity (pg_trgm) with configurable similarity threshold (default 0.3 for trigram, maps to ~0.7 confidence)
- **FR-ID07**: System MUST return confidence score (0-1) with each resolution result
- **FR-ID08**: System MUST flag mappings with confidence < 0.8 for manual review
- **FR-ID09**: System MUST handle biologics without InChI Key using DrugBank ID or UniProt ID as fallback master
- **FR-ID10**: System MUST group salt forms and stereoisomers under parent molecule while tracking specific forms
- **FR-ID11**: System MUST extract PubChem CID from SIDER STITCH IDs (CIDm/CIDs prefix removal)
- **FR-ID12**: System MUST support multi-component drugs by linking to component molecule_ids

### Gold Layer (Business Intelligence)

- **FR-G01**: System MUST support Gold layer with pre-computed aggregations for decision support
- **FR-G02**: System MUST auto-detect molecule lifecycle stage based on evidence in Silver layer
- **FR-G03**: System MUST compute confidence scores for lifecycle stage detection
- **FR-G04**: System MUST link evidence to lifecycle stages with source citations
- **FR-G05**: System MUST support incremental Gold refresh as Silver data arrives
- **FR-G06**: System MUST provide competitive landscape aggregations by indication/mechanism
- **FR-G07**: System MUST aggregate safety signals with disproportionality scores
- **FR-G08**: System MUST compute data completeness scores for each molecule profile

### Application Layer (Onboarding)

- **FR-A01**: System MUST accept molecule identifiers (name, DrugBank ID, RxNorm, NDC, UNII, CAS) for onboarding
- **FR-A02**: System MUST provide 10-step guided onboarding wizard
- **FR-A03**: System MUST show evidence requirements for each lifecycle stage
- **FR-A04**: System MUST allow users to add manual evidence annotations
- **FR-A05**: System MUST support stage validation with evidence verification
- **FR-A06**: System MUST prevent stage progression without required evidence (with admin override)
- **FR-A07**: System MUST support alerting for stage changes, safety signals, and regulatory events
- **FR-A08**: System MUST support bulk onboarding via CSV/Excel upload
- **FR-A09**: System MUST maintain audit log of all onboarding and validation events
- **FR-A10**: System MUST handle multiple indications/formulations as separate lifecycle tracks

### Data Export API (PostgREST)

- **FR-API01**: System MUST expose Gold layer tables via PostgREST auto-generated REST API
- **FR-API02**: System MUST support filtering, sorting, and pagination via PostgREST query syntax
- **FR-API03**: System MUST support JSON and CSV output formats via Accept header
- **FR-API04**: System MUST enforce row-level security (RLS) through PostgREST JWT integration
- **FR-API05**: System MUST expose read-only views for Silver layer data (analyst+ roles only)
- **FR-API06**: System MUST support bulk export via range requests for large datasets
- **FR-API07**: System SHOULD provide OpenAPI/Swagger documentation auto-generated by PostgREST

### Pipeline Operations

- **FR-P01**: System MUST validate data quality at each layer transition
- **FR-P02**: System MUST provide monitoring dashboard showing pipeline health
- **FR-P03**: System MUST alert on transformation failures or data quality issues
- **FR-P04**: System MUST support rollback to previous layer state on critical failures
- **FR-P05**: System MUST support configurable transformation rules without code changes

### Security & Access Control

- **FR-SEC01**: System MUST authenticate users via JWT tokens with configurable expiration
- **FR-SEC02**: System MUST implement role-based access control (RBAC) with the following roles:
  - `viewer`: Read-only access to Gold layer and own tracked molecules
  - `analyst`: Can onboard molecules, add annotations, configure alerts
  - `data_ops`: Can trigger pipelines, manage data sources, view Bronze/Silver
  - `admin`: Full access including user management and system configuration
- **FR-SEC03**: System MUST encrypt API credentials for external data sources at rest using AES-256
- **FR-SEC04**: System MUST log all authentication events and sensitive operations to audit log
- **FR-SEC05**: System MUST enforce row-level security on user_tracked_molecules and user_annotations tables

### Reliability & Availability

- **FR-REL01**: System MUST achieve 99.9% availability (maximum 8.76 hours unplanned downtime per year)
- **FR-REL02**: System MUST support scheduled maintenance windows (max 4 hours monthly) outside of business hours (weekends or 2-6 AM)
- **FR-REL03**: Bronze layer MUST be append-only with all historical data recoverable (indefinite retention)
- **FR-REL04**: System MUST implement database connection pooling with automatic reconnection on transient failures
- **FR-REL05**: Pipeline failures MUST NOT corrupt existing Silver/Gold data; failed jobs must be idempotent and retryable
- **FR-REL06**: System MUST implement continuous WAL archiving via pgBackRest with point-in-time recovery (PITR) capability; full backups weekly, incremental daily
- **FR-REL07**: System MUST meet Recovery Time Objective (RTO) of 1 hour - time to restore service after disaster
- **FR-REL08**: System MUST meet Recovery Point Objective (RPO) of 15 minutes - maximum acceptable data loss window

### Scalability

- **FR-SCALE01**: System MUST support vertical scaling by increasing database instance resources (CPU, RAM, storage)
- **FR-SCALE02**: System MUST support horizontal scaling by adding database instances, with each instance containing complete entities (no entity splitting across shards)
- **FR-SCALE03**: Sharding strategy: Bronze tables MAY be sharded by data source; Silver/Gold tables sharded by molecule_id range or therapeutic area
- **FR-SCALE04**: Application layer MUST use connection routing to direct queries to appropriate database shard
- **FR-SCALE05**: System MUST support 100M+ records in Bronze layer and 10M+ records in Silver layer without degradation
- **FR-SCALE06**: Cross-shard queries (e.g., competitive landscape spanning multiple shards) MUST be handled by application-level aggregation

### Observability

- **FR-OBS01**: All application logs MUST be structured JSON format with consistent fields: timestamp, level, service, correlation_id, message, context
- **FR-OBS02**: Logs MUST be aggregated to centralized logging system (Loki or ELK stack) with 30-day retention
- **FR-OBS03**: System MUST expose Prometheus-compatible metrics endpoint with the following metric types:
  - Pipeline metrics: ingestion_records_total, transformation_duration_seconds, transformation_errors_total
  - API metrics: request_duration_seconds, request_total (by endpoint, status)
  - Data quality metrics: quality_check_score, records_by_layer
- **FR-OBS04**: Grafana dashboards MUST be provided for: pipeline health, API performance, data quality trends, alert history
- **FR-OBS05**: All pipeline jobs MUST include correlation_id for end-to-end traceability from Bronze ingestion through Gold aggregation
- **FR-OBS06**: System MUST alert on: pipeline failures, API error rate >1%, data quality below threshold, database connection issues

### Deployment (Kubernetes)

- **FR-K8S01**: System MUST be deployable via Helm charts with configurable values
- **FR-K8S02**: System MUST support horizontal pod autoscaling (HPA) based on CPU/memory metrics
- **FR-K8S03**: System MUST implement rolling deployments with zero-downtime updates
- **FR-K8S04**: System MUST use Kubernetes secrets for credential management (database passwords, API keys)
- **FR-K8S05**: System MUST include liveness and readiness probes for all services
- **FR-K8S06**: System MUST support namespace isolation for dev/staging/prod environments
- **FR-K8S07**: Database MUST use PostgreSQL StatefulSet with persistent volumes (local/on-premises deployment)

---

## Success Criteria

### Data Platform Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **SC-001** | New data sources can be registered and ingesting to Raw within 30 minutes | Time from config to first record |
| **SC-002** | Raw-to-Bronze extraction processes 1 million records within 5 minutes | Batch processing time |
| **SC-003** | Bronze-to-Silver transformation processes 1 million records within 10 minutes | Batch processing time |
| **SC-004** | Incremental updates process 10x faster than full refresh | Processing time ratio |
| **SC-005** | Data quality issues detected and alerted within 5 minutes | Alert latency |
| **SC-006** | Gold aggregations available within 15 minutes of Silver data landing | End-to-end latency |
| **SC-007** | 99.9% of Raw records successfully extract to Bronze | Raw→Bronze error rate |
| **SC-008** | 99.9% of Bronze records successfully transform to Silver | Bronze→Silver error rate |
| **SC-009** | Schema changes in source APIs detected without breaking pipelines | Graceful degradation |
| **SC-010** | Gold table queries return in sub-second for typical queries | Query performance |
| **SC-011** | Raw layer can be reprocessed to Bronze within 4 hours | Reprocessing capability |

### Identifier Resolution Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **SC-ID01** | Identifier resolution returns result within 500ms (cached) or 3s (API lookup) | Response latency |
| **SC-ID02** | 95% of small molecules resolved to InChI Key across all sources | Linkage rate |
| **SC-ID03** | 90% of identifier resolutions have confidence ≥ 0.8 | Resolution quality |
| **SC-ID04** | 99% of ChEMBL ↔ PubChem ↔ DrugBank cross-references correctly mapped | Mapping accuracy |
| **SC-ID05** | Name-based resolution achieves 85% accuracy against gold standard | Fuzzy match quality |
| **SC-ID06** | SIDER adverse events linkage to InChI Key increases from 0% to 80%+ | SIDER data recovery |

### Onboarding Application Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **SC-009** | Users can onboard a known drug with stage auto-detected in under 2 minutes | Task completion time |
| **SC-010** | 90% of lifecycle stages are correctly auto-detected | Accuracy vs manual verification |
| **SC-011** | 10-step wizard can be completed in under 10 minutes for typical molecule | Wizard completion time |
| **SC-012** | Bulk onboarding of 50 molecules completes within 15 minutes | Batch processing time |
| **SC-013** | Stage transition alerts delivered within 24 hours of data change | Alert latency |
| **SC-014** | 95% of validated stages have complete evidence trails with source links | Evidence completeness |
| **SC-015** | Molecule onboarding time reduced from 2 hours (manual) to 10 minutes | Efficiency improvement |

---

## Edge Cases

### Data Ingestion (Raw Layer)
- What happens when an API is down for extended period? System queues requests and alerts after threshold; Raw continues from last successful sync
- How does system handle rate limiting? Exponential backoff with jitter; respects Retry-After headers
- What happens when API returns malformed JSON? Raw layer stores as-is with error flag; Bronze extraction skips with logging

### Data Extraction (Bronze Layer)
- What happens when API response format changes? Raw layer preserves new format; Bronze extraction fails gracefully with alert; schema mapping can be updated
- What happens when Bronze extraction logic has a bug? Raw data preserved for reprocessing; fix extraction logic and rerun
- How are new columns in API responses handled? Schema mapping can be updated to add columns; existing Bronze records not backfilled unless reprocessed

### Entity Resolution
- What happens when two sources have conflicting data for same molecule? Silver keeps both with source attribution; Gold uses precedence rules
- How does system handle molecules with no InChI Key (biologics)? Uses DrugBank ID or UNII as secondary master key
- What happens when molecule names are ambiguous? Presents disambiguation to user; creates alias mapping

### Lifecycle Detection
- What happens when a molecule regresses in lifecycle (trial failure)? System flags potential regression; requires user confirmation
- How does system handle molecules with multiple indications at different stages? Tracks each indication separately with distinct lifecycle
- What happens when evidence is retracted? System removes evidence; recalculates stage with audit log

### Application
- What happens during concurrent edits by multiple users? Optimistic locking with conflict resolution UI
- How does system handle confidential/unpublished data? Supports private annotations that don't affect public stage detection
- What happens when onboarding is interrupted? Session state saved; user can resume from last step

---

## Dependencies

### Technical Dependencies
- **Database**: PostgreSQL 14+ with JSONB support for Bronze layer and pg_trgm extension for fuzzy matching
- **pgBackRest**: WAL archiving and backup solution with point-in-time recovery (PITR) capability
- **PostgREST**: Auto-generated REST API from PostgreSQL schema for data export and querying (https://docs.postgrest.org/en/v14/)
- **Kubernetes**: Self-managed container orchestration (k3s or bare metal K8s) with Helm charts for local/on-premises deployment
- **008-ground-truth-service**: External API clients for data ingestion
- **SQLMesh**: For pipeline orchestration, transformation scheduling, and incremental model processing
- **RDKit**: Python library for SMILES → InChI Key conversion in identifier resolution
- **Monitoring**: Grafana for dashboards and alerting, Prometheus for metrics collection
- **Message Queue**: Redis for async processing and caching

### Data Dependencies
- **ClinicalTrials.gov API v2**: Trial registration and status
- **OpenFDA API**: Labels, FAERS adverse events
- **ChEMBL API**: Bioactivity data
- **UniProt REST API**: Protein information
- **SEC EDGAR**: Company filings for commercial data

---

## Testing Strategy

### Approach: End-to-End Pipeline Testing

The data platform uses **end-to-end testing** with real API samples to verify complete pipeline correctness. This approach prioritizes integration testing over unit tests because data pipelines are inherently integration-heavy.

### Test Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    END-TO-END PIPELINE TESTING                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TEST DATA                                                                   │
│  ─────────                                                                   │
│  Real API samples captured from each source:                                 │
│  - tests/fixtures/raw/chembl_sample.json (100 molecules)                    │
│  - tests/fixtures/raw/drugbank_sample.xml (50 drugs)                        │
│  - tests/fixtures/raw/clinicaltrials_sample.json (200 trials)               │
│  - tests/fixtures/raw/openfda_labels_sample.json (100 labels)               │
│                                                                              │
│  TEST EXECUTION                                                              │
│  ──────────────                                                              │
│  1. Load test fixtures into Raw layer                                        │
│  2. Run Bronze extraction pipelines                                          │
│  3. Run Silver entity resolution                                             │
│  4. Run Gold aggregation                                                     │
│  5. Verify final Gold output against expected results                        │
│                                                                              │
│  ASSERTIONS                                                                  │
│  ──────────                                                                  │
│  - Record counts at each layer transition                                    │
│  - Schema compliance (all required columns present, correct types)           │
│  - Entity resolution: known molecules correctly linked                       │
│  - No data loss: all valid records reach Gold                               │
│  - Quarantine: low-confidence records flagged correctly                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Test Categories

| Category | Scope | Frequency | Purpose |
|----------|-------|-----------|---------|
| **Pipeline E2E** | Raw → Bronze → Silver → Gold | PR merge | Verify complete data flow |
| **Source Regression** | Per-source Bronze extraction | PR merge | Catch API format changes |
| **Entity Resolution** | Known molecule test set | PR merge | Verify cross-source linking |
| **Performance** | 100K record batch | Weekly | Ensure throughput targets met |
| **Recovery** | Failure injection | Monthly | Verify RTO/RPO achievable |

### Test Fixtures

```python
# tests/conftest.py

@pytest.fixture
def sample_chembl_molecules():
    """Load 100 real ChEMBL molecule responses."""
    return load_fixture('raw/chembl_sample.json')

@pytest.fixture
def expected_silver_molecules():
    """Expected Silver output for test molecules."""
    return load_fixture('expected/silver_molecules.json')

# tests/test_pipeline_e2e.py

async def test_full_pipeline_chembl(sample_chembl_molecules, expected_silver_molecules):
    """Test complete pipeline for ChEMBL data."""
    # 1. Load to Raw
    raw_ids = await load_to_raw('chembl', sample_chembl_molecules)
    assert len(raw_ids) == 100

    # 2. Extract to Bronze
    bronze_ids = await run_bronze_extraction('chembl', raw_ids)
    assert len(bronze_ids) == 100

    # 3. Entity resolution to Silver
    await run_entity_resolution(bronze_ids)

    # 4. Verify Silver output
    silver_records = await get_silver_molecules(bronze_ids)
    assert_molecules_match(silver_records, expected_silver_molecules)

    # 5. Verify Gold aggregations updated
    gold_profiles = await get_gold_profiles(silver_records)
    assert all(p['data_completeness'] > 0 for p in gold_profiles)
```

### Continuous Integration

```yaml
# .github/workflows/pipeline-tests.yml

name: Pipeline E2E Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_DB: test_pharma
        options: --health-cmd pg_isready

    steps:
      - uses: actions/checkout@v3
      - name: Load test fixtures to Raw
        run: python -m tests.load_fixtures
      - name: Run pipeline tests
        run: pytest tests/test_pipeline_e2e.py -v
      - name: Verify Gold output
        run: python -m tests.verify_gold_output
```

---

## Out of Scope

- Real-time streaming ingestion (batch-oriented design)
- Cross-database federation (single database target)
- Machine learning model training pipelines (see Pharma-Bench)
- Data anonymization/masking (handled separately)
- Multi-tenant data isolation (single tenant initially)
- International regulatory tracking beyond FDA/EMA in initial release
- Integration with internal company data systems

---

## Part 7: IVA Publication Tracking

### Purpose

Enable Ground Truth to capture, store, and monitor IVA-relevant (Integrated Value Assessment) real-world evidence publications for priority molecules. This addresses a critical gap where publications are fetched live but not stored for historical tracking or IVA-relevance classification.

### User Story 7.1 - Scan for IVA-Relevant Publications (Priority: P1)

A medical affairs lead wants to discover and track publications that support IVA narrative pillars (durability, safety, QoL, efficacy, comparative) for their molecule.

**Acceptance Scenarios**:

1. **Given** a configured drug (e.g., Dupixent), **When** publication scan runs, **Then** new publications from OpenAlex are classified by indication, narrative pillar, and evidence type
2. **Given** a publication about 5-year registry data, **When** classified, **Then** it is tagged as evidence_type="registry", pillar="durability", with high relevance score
3. **Given** publications are discovered, **When** stored, **Then** they include extracted endpoints (EASI-75, IGA 0/1), study population size, and duration

### User Story 7.2 - Monitor for New Publications (Priority: P2)

An IVA team wants automated alerts when high-relevance publications are published about their drug.

**Acceptance Scenarios**:

1. **Given** monitoring is configured for Dupixent, **When** daily scan runs, **Then** new publications are discovered, classified, and stored
2. **Given** a high-relevance publication (score >= 0.8), **When** detected, **Then** an alert is generated with the publication details
3. **Given** a registry study publication, **When** detected, **Then** an alert is generated regardless of citation count

### IVA Classification Enums

```python
class IVAEvidenceType(str, Enum):
    """Types of IVA evidence."""
    RCT = "rct"  # Randomized controlled trial
    RWE = "rwe"  # Real-world evidence
    REGISTRY = "registry"  # Registry study
    META_ANALYSIS = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    CASE_SERIES = "case_series"
    EXPERT_OPINION = "expert_opinion"


class IVANarrativePillar(str, Enum):
    """IVA narrative pillars aligned with CEJ (Customer Engagement Journey)."""
    DURABILITY = "durability"  # Long-term efficacy, persistence
    SAFETY = "safety"  # Safety profile, tolerability
    QOL = "qol"  # Quality of life improvements
    EFFICACY = "efficacy"  # Clinical efficacy outcomes
    MECHANISM = "mechanism"  # MOA-related data
    COMPARATIVE = "comparative"  # Head-to-head comparisons
```

### IVA Publication Tables

```sql
-- IVA-Relevant Publications Table
CREATE TABLE IF NOT EXISTS iva_publications (
    id SERIAL PRIMARY KEY,

    -- OpenAlex identifiers
    openalex_id VARCHAR(50) UNIQUE NOT NULL,
    doi VARCHAR(255),
    pmid VARCHAR(20),

    -- Basic metadata
    title TEXT NOT NULL,
    abstract TEXT,
    publication_date DATE,
    publication_year INTEGER,
    journal VARCHAR(500),
    publication_type VARCHAR(50), -- article, review, clinical-trial, registry

    -- Authors (JSONB for flexibility)
    authors JSONB, -- [{name, orcid, affiliations}]
    first_author VARCHAR(255),
    last_author VARCHAR(255),

    -- Metrics
    cited_by_count INTEGER DEFAULT 0,
    is_open_access BOOLEAN DEFAULT FALSE,

    -- Drug associations
    drug_names TEXT[], -- ['dupilumab', 'dupixent']
    drug_ids TEXT[], -- ChEMBL IDs, DrugBank IDs
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- IVA Classification
    iva_relevance_score FLOAT DEFAULT 0, -- 0-1 computed score
    iva_indication VARCHAR(50), -- AD, PN, CSU, Asthma, etc.
    iva_narrative_pillar VARCHAR(100), -- 'durability', 'safety', 'qol', etc.
    iva_evidence_type VARCHAR(50), -- 'RCT', 'RWE', 'registry', 'meta-analysis'

    -- Study characteristics (for RWE)
    study_type VARCHAR(50), -- retrospective, prospective, registry, claims
    study_population_size INTEGER,
    study_duration_weeks INTEGER,
    data_source VARCHAR(100), -- BioDay, PROSE, Medicare, etc.

    -- Key findings (structured)
    key_endpoints JSONB, -- [{endpoint, value, comparator, timepoint}]

    -- IVA workflow
    iva_status VARCHAR(20) DEFAULT 'new', -- new, reviewed, approved, rejected
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP,
    reviewer_notes TEXT,

    -- Validation (via Devil's Advocate)
    validation_status VARCHAR(20), -- pending, validated, flagged
    validation_result JSONB, -- Validation details from DevilsAdvocateValidator
    validated_at TIMESTAMP,

    -- Tracking
    first_seen_at TIMESTAMP DEFAULT NOW(),
    last_updated_at TIMESTAMP DEFAULT NOW(),
    citation_trend JSONB, -- [{date, count}] for tracking citation growth

    -- Indexing
    mesh_terms TEXT[],
    concepts JSONB, -- OpenAlex concepts with scores

    -- Indexes
    INDEX idx_iva_pub_drug_names (drug_names) USING GIN,
    INDEX idx_iva_pub_indication (iva_indication),
    INDEX idx_iva_pub_pillar (iva_narrative_pillar),
    INDEX idx_iva_pub_status (iva_status),
    INDEX idx_iva_pub_relevance (iva_relevance_score DESC),
    INDEX idx_iva_pub_date (publication_date DESC)
);

-- IVA Monitoring Configuration Table
CREATE TABLE IF NOT EXISTS iva_monitoring_config (
    id SERIAL PRIMARY KEY,
    drug_name VARCHAR(255) NOT NULL,
    drug_id VARCHAR(50),
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Indications to monitor
    indications TEXT[], -- ['atopic dermatitis', 'prurigo nodularis', 'CSU']

    -- Search terms
    search_terms TEXT[], -- Additional terms beyond drug name

    -- IVA narrative pillars to track
    narrative_pillars JSONB, -- {pillar: [keywords]}

    -- Alert thresholds
    min_citations_for_alert INTEGER DEFAULT 10,
    min_relevance_score FLOAT DEFAULT 0.7,

    -- Monitoring settings
    is_active BOOLEAN DEFAULT TRUE,
    check_frequency_hours INTEGER DEFAULT 24,
    last_checked_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- IVA Publication Alerts Table
CREATE TABLE IF NOT EXISTS iva_publication_alerts (
    id SERIAL PRIMARY KEY,
    publication_id INTEGER REFERENCES iva_publications(id),
    config_id INTEGER REFERENCES iva_monitoring_config(id),

    alert_type VARCHAR(50), -- 'new_publication', 'high_citations', 'trending'
    alert_reason TEXT,
    priority VARCHAR(20), -- 'high', 'medium', 'low'

    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW()
);
```

### IVA API Endpoints

- `GET /api/v1/iva/publications/{drug_name}` - Get IVA publications for a drug
- `POST /api/v1/iva/scan/{drug_name}` - Scan for new publications
- `POST /api/v1/iva/monitor/run` - Trigger monitoring cycle
- `GET /api/v1/iva/alerts` - Get pending alerts
- `POST /api/v1/iva/alerts/{id}/acknowledge` - Acknowledge an alert
- `GET /api/v1/iva/monitoring-config` - Get monitoring configurations
- `POST /api/v1/iva/monitoring-config` - Create monitoring configuration

### IVA Functional Requirements

- **FR-IVA01**: System MUST classify publications by IVA evidence type (RCT, RWE, Registry, Meta-analysis)
- **FR-IVA02**: System MUST classify publications by IVA narrative pillar (Durability, Safety, QoL, Efficacy, Comparative)
- **FR-IVA03**: System MUST calculate IVA relevance scores (0-1) based on indication match, pillar match, evidence type, and endpoint extraction
- **FR-IVA04**: System MUST extract key endpoints from publication text (EASI-75, IGA 0/1, UAS7, DLQI)
- **FR-IVA05**: System MUST detect known registry sources (BioDay, PROSE, RELIEVE-AD, TREATgermany)
- **FR-IVA06**: System MUST generate alerts for high-relevance publications (score >= 0.8)
- **FR-IVA07**: System MUST support daily automated monitoring for configured drugs
- **FR-IVA08**: System MUST store publication citation trends for tracking impact over time
- **FR-IVA09**: System MUST integrate with Devil's Advocate validator for publication verification

---

## Part 8: Clinical Endpoints Ontology Integration

### Purpose

Integrate a comprehensive clinical endpoints ontology to provide standardized endpoint definitions, ICD-10 mappings, MCID values, and regulatory compliance requirements for each indication.

### Ontology Structure

```yaml
# Clinical Endpoints Ontology (clinical_endpoints_ontology.yaml)
version: "2.0"
last_updated: "2026-01-22"

indications:
  atopic_dermatitis:
    name: "Atopic Dermatitis"
    icd10_codes:
      - code: "L20"
        description: "Atopic dermatitis"
      - code: "L20.0"
        description: "Besnier's prurigo"
      - code: "L20.81"
        description: "Atopic neurodermatitis"

    primary_endpoints:
      - name: "EASI-75"
        description: "≥75% reduction from baseline in EASI score"
        unit: "percentage"
        direction: "higher_is_better"
        mcid: 6.6
        fda_accepted: true

      - name: "IGA 0/1"
        description: "Clear or almost clear skin"
        unit: "categorical"
        direction: "higher_is_better"
        fda_accepted: true

    secondary_endpoints:
      - name: "DLQI"
        description: "Dermatology Life Quality Index"
        unit: "score"
        range: [0, 30]
        direction: "lower_is_better"
        mcid: 4.0

      - name: "Pruritus NRS"
        description: "Peak Pruritus Numerical Rating Scale"
        unit: "score"
        range: [0, 10]
        direction: "lower_is_better"
        mcid: 4.0
```

### Ontology Service Integration

```python
from services.ground_truth import get_clinical_endpoints_ontology

# Get singleton ontology instance
ontology = get_clinical_endpoints_ontology()

# Validate endpoint for indication
is_valid = ontology.is_valid_endpoint("atopic_dermatitis", "EASI-75")

# Get ICD-10 codes
codes = ontology.get_icd10_codes("atopic_dermatitis")

# Check if value is clinically meaningful
is_meaningful = ontology.is_clinically_meaningful("EASI-75", 80.0)  # True if > MCID
```

### Ontology Functional Requirements

- **FR-ONT01**: System MUST provide centralized clinical endpoints ontology accessible via singleton pattern
- **FR-ONT02**: System MUST map indications to ICD-10 codes with descriptions
- **FR-ONT03**: System MUST define primary and secondary endpoints per indication with FDA acceptance status
- **FR-ONT04**: System MUST provide MCID (Minimal Clinically Important Difference) values for endpoints
- **FR-ONT05**: System MUST validate extracted endpoint values against expected ranges
- **FR-ONT06**: System MUST support endpoint pattern matching for publication text extraction

---

## Migration Path

For existing data in the trials-predictor system:

1. **Phase 1 (Week 1-2)**: Create Bronze tables, begin dual-write from existing ingestion
2. **Phase 2 (Week 3-4)**: Create Silver schemas, backfill from existing tables + Bronze
3. **Phase 3 (Week 5-6)**: Create Gold aggregations, validate lifecycle detection
4. **Phase 4 (Week 7-8)**: Deploy onboarding application, migrate existing tracked molecules
5. **Phase 5 (Week 9-10)**: Deprecate legacy tables after validation period

### Backward Compatibility

During migration:
- Existing API endpoints continue to work, reading from legacy tables
- New endpoints read from Gold layer
- Feature flags control which data source is used
- Legacy tables kept read-only for 90 days post-migration

---

## Appendix A: Lifecycle Stage Evidence Matrix

| Stage | Required Evidence | Data Sources | Confidence Weight |
|-------|-------------------|--------------|-------------------|
| **Discovery** | Target identification, mechanism hypothesis | ChEMBL, UniProt, publications | 0.5 |
| **Preclinical** | Animal study data, safety pharmacology | Publications, patents | 0.6 |
| **IND Filed** | IND number or announcement | FDA database, SEC filings, press releases | 0.8 |
| **Phase 1** | Trial registration (NCT ID), safety cohort | ClinicalTrials.gov | 0.9 |
| **Phase 2** | Trial registration, efficacy signals | ClinicalTrials.gov, publications | 0.9 |
| **Phase 3** | Pivotal trial registration, significant enrollment | ClinicalTrials.gov, publications | 0.95 |
| **NDA/BLA Filed** | Application number, PDUFA date | FDA, SEC filings | 0.95 |
| **FDA Review** | PDUFA date, review status | FDA, Drugs@FDA | 0.95 |
| **Approved** | Approval letter, label (SetID) | OpenFDA, DailyMed | 1.0 |
| **Marketed** | Revenue data, label updates | SEC EDGAR, DailyMed | 1.0 |

---

## Appendix B: Data Quality Rules

### Raw Layer
- `response_body` must be valid JSON/XML (or binary for file downloads)
- `response_status` must be a valid HTTP status code (100-599)
- `request_timestamp` must be within 1 hour of current time
- `response_body_hash` must be computed for all responses
- `source_id` must match registered source

### Bronze Layer
- All required columns (per schema mapping) must be non-null
- `source_id` must match registered source
- `ingested_at` must be within 1 hour of current time
- `raw_id` must reference a valid Raw layer record
- `record_hash` must be unique per source (no exact duplicates)

### Silver Layer
- `inchi_key` must match format `^[A-Z]{14}-[A-Z]{10}-[A-Z]$`
- `molecule_id` must exist in `silver_molecules`
- Foreign key references must be valid
- Date fields must be reasonable (not future, not before 1900)

### Gold Layer
- `current_stage` must be valid LifecycleStage enum value
- `stage_confidence` must be between 0 and 1
- `stage_evidence_count` must be > 0
- `data_completeness_score` must be between 0 and 1

---

## Appendix C: API Endpoints (Summary)

### Bronze/Silver/Gold Management (Internal)
- `POST /api/v1/pipeline/sources` - Register new data source
- `POST /api/v1/pipeline/ingest/{source_id}` - Trigger ingestion
- `POST /api/v1/pipeline/transform/{source_id}` - Trigger transformation
- `GET /api/v1/pipeline/status` - Pipeline health status

### Molecule Onboarding (User-facing)
- `POST /api/v1/onboarding/start` - Start onboarding wizard
- `GET /api/v1/onboarding/{tracking_id}/step/{step}` - Get step data
- `POST /api/v1/onboarding/{tracking_id}/step/{step}` - Submit step
- `POST /api/v1/onboarding/{tracking_id}/validate` - Validate stage
- `POST /api/v1/onboarding/bulk` - Bulk upload

### Molecule Data (Query)
- `GET /api/v1/molecules/{molecule_id}/profile` - Full Gold profile
- `GET /api/v1/molecules/{molecule_id}/evidence` - Evidence list
- `GET /api/v1/molecules/{molecule_id}/timeline` - Lifecycle timeline
- `GET /api/v1/molecules/search` - Search molecules
- `GET /api/v1/landscape/{indication}` - Competitive landscape

### Alerts
- `GET /api/v1/alerts/configs` - User's alert configurations
- `POST /api/v1/alerts/configs` - Create alert config
- `GET /api/v1/alerts/history` - Alert history

---

## Part 9: Database Migration from trials-predictor

### Purpose

Migrate the existing local PostgreSQL database from `/Users/pschloz/Desktop/DataKinetic/trials-predictor` to the dk-data-FE external server deployment. This includes all data, schemas, SQLMesh models, and ingestion pipelines.

### Migration Scope

#### Source System
- **Location**: `/Users/pschloz/Desktop/DataKinetic/trials-predictor`
- **Database**: `pharma_predictor` on localhost:5432
- **Data Volume**: ~9.1M records across 6 primary sources
- **SQLMesh Models**: Bronze/Silver/Gold layer transformations

#### Target System
- **Location**: dk-data-FE external server (Kubernetes deployment)
- **Database**: PostgreSQL StatefulSet with persistent volumes
- **Access**: PostgREST API + direct PostgreSQL connection

### Migration Strategy

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     DATABASE MIGRATION STRATEGY                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  PHASE 1: SCHEMA MIGRATION                                                        │
│  ─────────────────────────                                                        │
│  1. Export schema definitions (pg_dump --schema-only)                            │
│  2. Create Raw layer tables (new in dk-data-FE)                                  │
│  3. Create Bronze layer tables with source-native columns                        │
│  4. Create Silver layer normalized tables                                        │
│  5. Create Gold layer aggregation tables                                         │
│  6. Create Application layer tables (user tracking, alerts)                      │
│  7. Create indexes, constraints, triggers                                        │
│                                                                                   │
│  PHASE 2: DATA MIGRATION                                                          │
│  ─────────────────────────                                                        │
│  1. Export Bronze data (pg_dump --data-only --table=bronze_*)                    │
│  2. Transfer via pgBackRest or pg_dump/pg_restore                                │
│  3. Run SQLMesh models to regenerate Silver/Gold from Bronze                     │
│  4. Validate record counts and data integrity                                    │
│                                                                                   │
│  PHASE 3: SERVICE MIGRATION                                                       │
│  ─────────────────────────                                                        │
│  1. Deploy external API clients to Kubernetes                                    │
│  2. Configure data loaders with new database connection                          │
│  3. Set up SQLMesh scheduler (cron jobs)                                         │
│  4. Configure pgBackRest for continuous archiving                                │
│  5. Enable PostgREST for API access                                              │
│                                                                                   │
│  PHASE 4: VALIDATION & CUTOVER                                                    │
│  ─────────────────────────────                                                    │
│  1. Run parallel ingestion on both systems                                       │
│  2. Compare data consistency between local and external                          │
│  3. Switch API endpoints to external server                                      │
│  4. Decommission local database (archive first)                                  │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Current Database Tables (trials-predictor)

#### Bronze Layer (Raw Ingestion)
| Table | Records | Source | Description |
|-------|---------|--------|-------------|
| `bronze_clinicaltrials` | 95.5K | ClinicalTrials.gov API v2 | Raw trial JSONB data |
| `bronze_chembl` | 2.73M | ChEMBL API | Bioactivity data |
| `bronze_pubchem` | 965K | PubChem PUG-REST | Molecular properties |
| `bronze_drugbank` | 17.4K drugs + 2.8M DDIs | DrugBank XML | Drug info, interactions |
| `bronze_bindingdb` | 2.28M | BindingDB TSV | Binding affinities |
| `bronze_openfda_labels` | 83.8K | OpenFDA Labels | Approved drug labels |
| `bronze_openfda_faers` | 20M (partial) | OpenFDA FAERS | Adverse events |
| `bronze_sider` | 449K | SIDER | Side effects |

#### Silver Layer (Normalized)
| Table | Description |
|-------|-------------|
| `silver_molecules` | Canonical molecule identities (InChI Key master) |
| `silver_clinical_trials` | Normalized trial data |
| `silver_drug_labels` | Normalized FDA labels |
| `silver_adverse_events` | Normalized adverse events |
| `silver_patents` | Patent and exclusivity data |
| `silver_bioactivity` | Normalized binding/activity data |
| `silver_identifier_mappings` | Cross-reference ID mappings |
| `silver_molecule_aliases` | Name aliases for fuzzy matching |
| `silver_targets` | Protein/gene targets |
| `silver_publications` | Publications linked to molecules |
| `silver_regulatory_actions` | Approvals, withdrawals, warnings |

#### Gold Layer (Aggregated)
| Table | Description |
|-------|-------------|
| `gold_molecule_profile` | Unified molecule profiles with lifecycle stage |
| `gold_competitive_landscape` | Pre-computed competitive analysis |
| `gold_safety_signals` | Aggregated safety signals with disproportionality |
| `gold_company_pipeline` | Pipeline summaries by company |

#### Application Layer
| Table | Description |
|-------|-------------|
| `user_tracked_molecules` | User molecule tracking |
| `user_annotations` | Manual evidence annotations |
| `user_alert_configs` | Alert configurations |
| `alert_history` | Delivered alerts |
| `onboarding_audit_log` | Compliance audit trail |
| `iva_publications` | IVA-relevant publications |
| `iva_monitoring_config` | Publication monitoring settings |
| `iva_publication_alerts` | Publication alerts |

### Migration Functional Requirements

- **FR-MIG01**: System MUST export all Bronze layer data using pg_dump with --data-only flag
- **FR-MIG02**: System MUST transfer database via secure connection (SSH tunnel or VPN)
- **FR-MIG03**: System MUST regenerate Silver/Gold layers from Bronze using SQLMesh on target
- **FR-MIG04**: System MUST validate record counts match between source and target (±1%)
- **FR-MIG05**: System MUST verify data integrity via checksums on critical tables
- **FR-MIG06**: System MUST support rollback to source database within 24 hours of cutover
- **FR-MIG07**: System MUST archive source database before decommissioning

---

## Part 10: External API Clients (Complete Inventory)

### Purpose

Document all external API clients that must be migrated from trials-predictor to dk-data-FE. These clients fetch data from external sources and populate the Bronze layer.

### API Client Location
Source: `/Users/pschloz/Desktop/DataKinetic/trials-predictor/app/backend/src/services/external_apis/`

### Clinical Trials & Development Data

| Client | Endpoint | Rate Limit | Methods | Data |
|--------|----------|------------|---------|------|
| **ClinicalTrialsGovClient** | `https://clinicaltrials.gov/api/v2` | 100/min | `search_studies`, `get_trial`, `get_trial_with_results`, `search_by_drug`, `search_by_condition`, `search_by_sponsor`, `get_competitors_for_indication`, `get_pipeline_for_sponsor` | Trial phases, sponsors, interventions, conditions, outcomes |
| **ChEMBLClient** | `https://www.ebi.ac.uk/chembl/api/data` | 10/sec | `get_molecule`, `search_molecules`, `get_activities`, `get_mechanisms`, `get_target`, `search_by_inchi_key`, `get_drug_data` | Molecular structures, bioactivity, drug targets, MOA |

### Regulatory & Safety Data

| Client | Endpoint | Rate Limit | Methods | Data |
|--------|----------|------------|---------|------|
| **OpenFDAClient** | `api.fda.gov/drug/*` | 240/min (w/key) | `search_drug_labels`, `comprehensive_drug_search`, `get_adverse_events`, `count_adverse_events`, `get_orange_book`, `get_drug_applications`, `get_mechanism_of_action`, `get_indications` | Labels, FAERS, NDC, Orange Book |
| **EMAClient** | EMA Open Data | - | Regulatory decisions | EU approvals |
| **HealthCanadaClient** | Health Canada API | - | TPD approvals | Canadian regulatory |
| **SECEdgarClient** | SEC EDGAR | - | Company filings | Financial/regulatory |

### Patent & Intellectual Property

| Client | Endpoint | Methods | Data |
|--------|----------|---------|------|
| **PatentClient** | USPTO/EPO | Patent search | Pharma patents, claims, expiry |

### Biomedical & Scientific Data

| Client | Endpoint | Methods | Data |
|--------|----------|---------|------|
| **PubMedClient** | NCBI E-utilities | `search`, `fetch` | MEDLINE literature |
| **UniProtClient** | UniProt REST | `get_protein`, `search` | Protein sequences, function |
| **RCSBPDBClient** | RCSB PDB API | `get_structure` | 3D protein structures |

### Nomenclature & Identifiers

| Client | Endpoint | Methods | Data |
|--------|----------|---------|------|
| **RxNormClient** | RxNorm API | `get_rxcui`, `resolve_name` | Standard drug naming |
| **MeSHClient** | MeSH RDF | `lookup_term` | Medical subject headings |
| **UMLSClient** | UMLS REST | `resolve_cui` | Unified medical concepts |
| **WHOICDClient** | WHO ICD API | `get_icd10`, `get_icd11` | Disease classifications |

### Literature & Knowledge

| Client | Endpoint | Methods | Data |
|--------|----------|---------|------|
| **OpenAlexClient** | `api.openalex.org` | `search_works`, `get_citations` | Academic publications |
| **SemanticScholarClient** | Semantic Scholar API | `search_papers` | Paper search, citations |
| **ORCIDClient** | ORCID API | `get_researcher` | Researcher identifiers |
| **RSSClient** | Various RSS feeds | `fetch_feeds` | News aggregation |
| **PreprintClient** | bioRxiv/medRxiv API | `search_preprints` | Preprint articles |

### Public Health & Real-World Evidence

| Client | Endpoint | Methods | Data |
|--------|----------|---------|------|
| **CDCWonderClient** | CDC WONDER | `get_cause_of_death_stats`, `get_icd10_mortality_codes` | Mortality, disease surveillance |
| **AHRQHCUPClient** | AHRQ HCUP | `get_hcup_stats`, `get_hospital_stays`, `get_emergency_visits` | Hospital utilization |
| **CMSMedicareClient** | CMS Open Data | `get_drug_utilization`, `get_prescriber_data`, `get_part_d_spending` | Medicare drug spending |
| **NIHReporterClient** | NIH Reporter API | `search_grants` | Research funding |
| **NORDClient** | NORD API | `get_rare_disease` | Rare disease info |

### API Client Requirements

- **FR-API-EXT01**: All API clients MUST implement retry logic with exponential backoff
- **FR-API-EXT02**: All API clients MUST respect rate limits (configurable per client)
- **FR-API-EXT03**: All API clients MUST cache responses (configurable TTL per source)
- **FR-API-EXT04**: All API clients MUST log all requests with correlation IDs
- **FR-API-EXT05**: All API clients MUST store raw responses in Raw layer before parsing
- **FR-API-EXT06**: API credentials MUST be stored in Kubernetes secrets

---

## Part 11: Data Loaders (Complete Inventory)

### Purpose

Document all data loaders that transform raw external data into Bronze layer tables.

### Loader Location
Source: `/Users/pschloz/Desktop/DataKinetic/trials-predictor/app/backend/src/data/`

### Primary Loaders

| Loader | Source | Target Table | Frequency | Description |
|--------|--------|--------------|-----------|-------------|
| **ClinicalTrialsGovLoader** | ClinicalTrials.gov API | `bronze_clinicaltrials` | Daily | Bulk trial ingestion |
| **ComprehensiveLoader** | Multiple | Multiple Bronze | Orchestrated | Multi-source orchestration |
| **ChEMBLLoader** | ChEMBL API | `bronze_chembl` | Monthly | Bioactivity data |
| **PubChemBulkLoader** | PubChem FTP | `bronze_pubchem` | Monthly | Molecular properties |
| **DrugBankXMLLoader** | DrugBank XML | `bronze_drugbank` | Quarterly | Drug info, interactions |
| **BindingDBLoader** | BindingDB TSV | `bronze_bindingdb` | Monthly | Binding affinities |
| **SIDERLoader** | SIDER Download | `bronze_sider` | Quarterly | Side effects |
| **FAERSLoader** | OpenFDA FAERS | `bronze_openfda_faers` | Weekly | Adverse events |
| **OpenFDALabelsLoader** | OpenFDA Labels | `bronze_openfda_labels` | Daily | Drug labels |

### Specialized Loaders

| Loader | Source | Purpose |
|--------|--------|---------|
| **DTIDataLoader** | TDC, BindingDB, PDBbind | Drug-target interaction datasets |
| **DDInterLoader** | DDInter | Drug-drug interactions |
| **PDBbindPLIPLoader** | PDBbind | Protein-ligand complexes |
| **PDSPLoader** | PDSP Ki Database | Receptor binding data |
| **INNLoader** | WHO INN | International nonproprietary names |
| **IndicationDataLoader** | Multiple | Indication/disease mappings |
| **AdverseEffectDataLoader** | FAERS, SIDER | Aggregated AE signals |
| **TDCTrialOutcomeLoader** | TDC | ML trial outcome data |

### Loader Requirements

- **FR-LOAD01**: All loaders MUST write to Raw layer first, then trigger Bronze extraction
- **FR-LOAD02**: All loaders MUST implement idempotent ingestion (safe to re-run)
- **FR-LOAD03**: All loaders MUST track last successful sync timestamp
- **FR-LOAD04**: All loaders MUST report record counts (read/written/failed)
- **FR-LOAD05**: All loaders MUST handle partial failures gracefully (continue with valid records)
- **FR-LOAD06**: Bulk loaders MUST support resumable downloads for large files

---

## Part 12: REST API Endpoints (Complete Inventory)

### Purpose

Document all REST API endpoints from trials-predictor that must be implemented in dk-data-FE.

### API Location
Source: `/Users/pschloz/Desktop/DataKinetic/trials-predictor/app/backend/src/api/`

### Prediction APIs

#### Indications Router (`/api/v1/indications`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/indications` | Predict indications for a drug |
| POST | `/indications/batch` | Batch indication predictions |
| GET | `/indications/lookup/{inchi_key}` | Lookup by InChI key |
| GET | `/indications/model-info` | Model information |
| GET | `/indications/therapeutic-areas` | Available therapeutic areas |
| GET | `/indications/search` | Search indications |
| GET | `/indications/by-meddra/{meddra_id}` | Filter by MedDRA ID |
| POST | `/indications/match` | Match indications |
| GET | `/indications/areas-with-counts` | Therapeutic area counts |
| GET | `/indications/by-area/{therapeutic_area}` | Filter by area |

#### Adverse Effects Router (`/api/v1/adverse-effects`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/adverse-effects` | Predict adverse effects |
| POST | `/adverse-effects/batch` | Batch AE predictions |
| GET | `/adverse-effects/lookup/{inchi_key}` | Lookup by structure |
| GET | `/adverse-effects/model-info` | Model metadata |

#### Repositioning Router (`/api/v1/repositioning`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/repositioning` | Drug repositioning predictions |
| POST | `/repositioning/batch` | Batch repositioning |
| GET | `/repositioning/evidence/{inchi_key}` | Supporting evidence |

#### DTI Router (`/api/v1/dti`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/dti` | Predict drug-target interactions |

#### Similarity Router (`/api/v1/similarity`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/search` | Find similar compounds |
| GET | `/by-inchi/{inchi_key}` | Similar by structure |
| GET | `/stats` | Cache statistics |
| POST | `/compute` | Compute fingerprint |

#### Structure Router (`/api/v1/structure`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/3d` | Generate 3D structure |
| GET | `/3d/molblock` | Get MOL file |
| POST | `/properties` | Calculate properties |

### Intelligence APIs

#### Ground Truth Router (`/api/v1/ground-truth`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/landscape` | Competitive landscape analysis |
| POST | `/resolve-indication` | Resolve indication terms |
| POST | `/drug-data` | Comprehensive drug lookup |
| POST | `/competitors` | Find competitors |
| GET | `/health` | Service health |
| GET | `/recent-analyses` | Recent analysis history |
| POST | `/export/json` | Export JSON |
| POST | `/export/csv` | Export CSV |
| POST | `/export/excel` | Export Excel |
| POST | `/export/pdf` | Export PDF |
| GET | `/visualization/{molecule_id}` | Visualize data |

#### Competitive Intelligence Router (`/api/v1/competitive`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/landscape/{indication}` | Competitive landscape |
| GET | `/pipeline/{company}` | Company pipeline |
| GET | `/market-share/{indication}` | Market share data |

#### Market Intelligence Router (`/api/v1/market`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/pricing/{drug}` | Drug pricing data |
| GET | `/sizing/{indication}` | Market sizing |

#### Regulatory Router (`/api/v1/regulatory`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status/{molecule_id}` | Regulatory status |
| GET | `/approvals` | Recent approvals |
| GET | `/warnings` | Safety warnings |

#### Lifecycle Router (`/api/v1/lifecycle`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stage/{molecule_id}` | Current lifecycle stage |
| GET | `/evidence/{molecule_id}` | Stage evidence |
| GET | `/timeline/{molecule_id}` | Lifecycle timeline |

### Search & Discovery APIs

#### Search Router (`/api/v1/search`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/molecules` | Search molecules |
| GET | `/trials` | Search trials |
| GET | `/publications` | Search publications |
| POST | `/comprehensive` | Multi-source search |

#### DrugBank Router (`/api/v1/drugbank`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/{drugbank_id}` | Get drug data |
| GET | `/interactions/{drugbank_id}` | Drug interactions |
| GET | `/targets/{drugbank_id}` | Drug targets |

### Monitoring & Analytics APIs

#### Metrics Router (`/api/v1/metrics`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/summary` | Performance summary |
| GET | `/all` | All model metrics |
| GET | `/by-task/{task_type}` | Metrics by task |
| GET | `/roc-curves` | ROC curves |
| GET | `/confusion-matrices` | Confusion matrices |
| GET | `/feature-importance/{task_type}/{endpoint}` | Feature importance |

#### Dashboard Router (`/api/v1/dashboard`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/overview` | Dashboard overview |
| GET | `/pipeline-status` | Pipeline health |
| GET | `/data-quality` | Data quality metrics |

### IVA & Publications APIs

#### IVA Publications Router (`/api/v1/iva`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/publications/{drug_name}` | IVA publications |
| POST | `/scan/{drug_name}` | Scan for new publications |
| POST | `/monitor/run` | Trigger monitoring |
| GET | `/alerts` | Pending alerts |
| POST | `/alerts/{id}/acknowledge` | Acknowledge alert |
| GET | `/monitoring-config` | Monitoring configs |
| POST | `/monitoring-config` | Create config |

### Reports Router (`/api/v1/reports`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/trial/pdf` | Generate trial PDF |
| POST | `/batch/pdf` | Generate batch PDF |
| GET | `/templates` | List templates |

### WebSocket API

| Endpoint | Description |
|----------|-------------|
| `ws://host/ws/metrics` | Real-time metrics stream |
| `ws://host/ws/alerts` | Real-time alert notifications |

---

## Part 13: Ground Truth Services (Complete Inventory)

### Purpose

Document all Ground Truth services that provide intelligence and analysis capabilities.

### Service Location
Source: `/Users/pschloz/Desktop/DataKinetic/trials-predictor/app/backend/src/services/ground_truth/`

### Core Services

| Service | Purpose | Key Methods |
|---------|---------|-------------|
| **GroundTruthService** | Main orchestration | `analyze_molecule`, `get_competitive_landscape` |
| **DataAggregator** | Multi-source consolidation | `aggregate`, `merge_sources` |
| **SearchService** | Comprehensive search | `search`, `fuzzy_match` |
| **IdentifierResolver** | ID resolution | `resolve`, `cross_reference` |

### Intelligence Services

| Service | Purpose | Key Methods |
|---------|---------|-------------|
| **CompetitiveIntelligenceService** | Competitor analysis | `get_competitors`, `analyze_landscape` |
| **CompetitiveGraphService** | Graph-based analysis | `build_graph`, `find_paths` |
| **LifecycleService** | Stage detection | `detect_stage`, `get_evidence` |
| **GlobalRegulatoryService** | Multi-region regulatory | `get_status`, `track_approvals` |
| **PricingService** | Drug pricing | `get_pricing`, `compare_prices` |

### Data Services

| Service | Purpose | Key Methods |
|---------|---------|-------------|
| **DrugBankService** | DrugBank data access | `get_drug`, `get_interactions` |
| **IndicationResolverService** | Indication normalization | `resolve`, `map_to_mesh` |
| **IndicationOntologyService** | Indication hierarchy | `get_children`, `get_parents` |
| **CoverageService** | Data completeness | `calculate_coverage`, `identify_gaps` |

### Monitoring Services

| Service | Purpose | Key Methods |
|---------|---------|-------------|
| **NewsService** | News monitoring | `fetch_news`, `filter_relevant` |
| **ConferenceMonitoringService** | Conference tracking | `get_upcoming`, `get_presentations` |
| **KOLIntelligenceService** | KOL tracking | `identify_kols`, `get_publications` |
| **PatientAdvocacyService** | Patient groups | `get_groups`, `track_activity` |
| **IVAPublicationService** | IVA publications | `scan`, `classify`, `alert` |
| **MonitoringScheduler** | Scheduled tasks | `schedule`, `run_all` |

### Export & Visualization Services

| Service | Purpose | Key Methods |
|---------|---------|-------------|
| **ExportService** | Multi-format export | `to_json`, `to_csv`, `to_excel`, `to_pdf` |
| **VisualizationService** | Data visualization | `generate_chart`, `render_graph` |

### User Services

| Service | Purpose | Key Methods |
|---------|---------|-------------|
| **UserOnboardingService** | Molecule onboarding | `start`, `get_step`, `validate`, `complete` |
| **UserFeedbackService** | Feedback collection | `submit`, `get_history` |
| **DataQualityMonitoringService** | Quality tracking | `check_quality`, `report_issues` |

---

## Migration Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| **SC-MIG01** | All Bronze tables migrated with 100% record count match | `COUNT(*)` comparison |
| **SC-MIG02** | Silver/Gold regeneration completes within 4 hours | SQLMesh run time |
| **SC-MIG03** | All 25+ API clients functional on external server | Health check endpoints |
| **SC-MIG04** | All data loaders execute successfully on first run | Loader status logs |
| **SC-MIG05** | All 100+ API endpoints return 200 OK | Endpoint smoke tests |
| **SC-MIG06** | PostgREST serves Gold layer queries in <100ms (p95) | Response time metrics |
| **SC-MIG07** | pgBackRest continuous archiving active | WAL archive lag <1 minute |
| **SC-MIG08** | Zero data loss during cutover | Audit trail verification |

---

## Part 14: Complete Database Table-to-Layer Mapping

### Purpose

Map all 122 tables from the `pharma_predictor` database to the appropriate medallion architecture layer for migration to dk-data-FE.

### Database Summary

- **Total Tables**: 122
- **Total Records**: ~14.5M (across tables with data)
- **Total Storage**: ~12.8 GB
- **Database**: `pharma_predictor` on localhost:5433

### Layer Classification Criteria

| Layer | Criteria | Characteristics |
|-------|----------|-----------------|
| **Raw** | Unmodified API responses | JSONB blob, HTTP metadata, immutable |
| **Bronze** | Source-native structured data | **ONLY source-native identifiers** (e.g., only `chembl_id` from ChEMBL) |
| **Silver** | Normalized, entity-resolved | **Multiple source identifiers linked** (e.g., `chembl_id` + `drugbank_id` + `pubchem_cid`) |
| **Gold** | Aggregated, decision-ready | Pre-computed analytics, disproportionality scores, rankings |
| **Application** | User features | Tracking, alerts, configurations, audit logs |
| **ML/Prediction** | Model outputs | Predictions, explanations, model registry |
| **Feature Store** | Pre-computed features | Fingerprints, descriptors, embeddings |
| **System/Cache** | Infrastructure | API cache, computation cache, metrics |

### Entity Resolution: The Bronze → Silver Transformation

**Key Insight**: Data sources are NOT interconnected. Each source uses its own identifiers:
- ChEMBL → `molecule_chembl_id`
- DrugBank → `drugbank_id`
- PubChem → `cid` (pubchem_cid)
- SIDER → `stitch_id`
- BindingDB → `monomerid`

**Entity resolution** links these identifiers using **InChI Key** as the master molecular identifier:

```
BRONZE (Source-Native)                    SILVER (Entity-Resolved)
┌─────────────────────┐                   ┌─────────────────────────────────────┐
│ chembl_molecules    │                   │ compounds                           │
│ - chembl_id ────────┼───┐               │ - inchi_key (master identifier)     │
│ - inchi_key         │   │               │ - chembl_id ◄────────────────────┐  │
└─────────────────────┘   │               │ - drugbank_id ◄───────────────┐  │  │
                          │ Entity        │ - pubchem_cid ◄────────────┐  │  │  │
┌─────────────────────┐   │ Resolution    │                            │  │  │  │
│ drugbank_targets    │   │ via           └─────────────────────────────┼──┼──┼──┘
│ - drugbank_id ──────┼───┤ InChI Key                                   │  │  │
└─────────────────────┘   │                                             │  │  │
                          │               ┌─────────────────────────────────┼──┼──┼──┐
┌─────────────────────┐   │               │ bindingdb_affinities (SILVER)   │  │  │  │
│ pubchem_compounds   │   │               │ - inchi_key (joined)            │  │  │  │
│ - cid ──────────────┼───┘               │ - chembl_id ◄───────────────────┘  │  │  │
│ - inchi_key         │                   │ - drugbank_id ◄────────────────────┘  │  │
└─────────────────────┘                   │ - pubchem_cid ◄───────────────────────┘  │
                                          └──────────────────────────────────────────┘
```

**Classification Rule**:
- **Bronze**: Table has **ONE** source's native identifier (even if it has InChI Key from that source)
- **Silver**: Table has **MULTIPLE** source identifiers linked together (entity resolution done)

---

### RAW LAYER (1 table, 1.8K records, 3.1 GB)

Tables storing unmodified API responses for audit, debugging, and reprocessing.

| Table | Records | Size | Source | Description |
|-------|---------|------|--------|-------------|
| `fda_raw_labels` | 1,823 | 3.1 GB | OpenFDA | Raw JSON responses from OpenFDA drug label API |

**Migration Notes:**
- Store complete HTTP response including headers, status, body
- Add `request_id`, `request_timestamp`, `response_body_hash` columns
- This table already follows Raw layer pattern with `raw_response JSONB`

---

### BRONZE LAYER (40 tables, ~7.6M records, 5.3 GB)

Tables storing source-native structured data with **only source-native identifiers** (no cross-source linking).

#### Clinical Trials & Development (2 tables)

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `clinical_trials` | 95,479 | 81 MB | ClinicalTrials.gov | `nct_id` only |
| `experimental_data` | 83,755 | 11 MB | Various | experiment_id only |

#### ChEMBL Data (4 tables)

ChEMBL natively provides InChI Key, but these tables have **only ChEMBL identifiers** for cross-referencing.

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `chembl_activities` | 2,731,454 | 460 MB | ChEMBL API | `molecule_chembl_id` only |
| `chembl_molecules` | 6 | 96 KB | ChEMBL API | `molecule_chembl_id` only |
| `chembl_mechanisms` | 0 | 8 KB | ChEMBL API | `molecule_chembl_id` only |
| `assay_information` | 0 | 8 KB | ChEMBL API | `assay_chembl_id` only |

#### DrugBank Data (12 tables) - Source-Native Only

These tables contain **only `drugbank_id`** as identifier - no cross-source linking.

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `drugbank_interactions` | 2,547,451 | 1.6 GB | DrugBank XML | `drugbank_id` (drug_1, drug_2) |
| `drugbank_targets` | 22,697 | 37 MB | DrugBank XML | `drugbank_id` only |
| `drugbank_enzymes` | 5,898 | 7.9 MB | DrugBank XML | `drugbank_id` only |
| `drugbank_transporters` | 3,516 | 4.4 MB | DrugBank XML | `drugbank_id` only |
| `drugbank_carriers` | 964 | 880 KB | DrugBank XML | `drugbank_id` only |
| `drugbank_pathways` | 3,780 | 1.4 MB | DrugBank XML | `drugbank_id` only |
| `drugbank_products` | 462,851 | 74 MB | DrugBank XML | `drugbank_id` only |
| `drugbank_categories` | 101,512 | 8.2 MB | DrugBank XML | `drugbank_id` only |
| `drugbank_atc_codes` | 5,656 | 512 KB | DrugBank XML | `drugbank_id` only |
| `drugbank_patents` | 12,214 | 1 MB | DrugBank XML | `drugbank_id` only |
| `drugbank_snp_effects` | 310 | 120 KB | DrugBank XML | `drugbank_id` only |
| `drugbank_extended_status` | 0 | 0 | DrugBank XML | `drugbank_id` only |

#### PubChem Data (1 table)

PubChem natively provides InChI Key, but this table has **only PubChem CID** as source identifier.

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `pubchem_compounds` | 965,439 | 216 MB | PubChem API | `cid` only |

#### FDA/OpenFDA Data (2 tables)

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `fda_labels` | 83,805 | 662 MB | OpenFDA Labels | `set_id`, `application_number` only |
| `faers_events` | 675,335 | 163 MB | OpenFDA FAERS | `safetyreportid` only |

#### SIDER Data (1 table) - Source-Native Only

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `sider_atc_codes` | 1,560 | 264 KB | SIDER | `stitch_id` only |

**Note**: `sider_adverse_reactions` and `sider_indications` moved to Silver (they have `drugbank_id` cross-reference).

#### TDC (Therapeutic Data Commons) (6 tables)

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `tdc_compounds` | 82,624 | 8.8 MB | TDC | `drug_id` only |
| `tdc_admet_data` | 82,009 | 18 MB | TDC | `compound_id` only |
| `tdc_admet_values` | 65,198 | 10 MB | TDC | `compound_id` only |
| `tdc_datasets` | 24 | 16 KB | TDC | `dataset_id` only |
| `tdc_admet_datasets` | 20 | 16 KB | TDC | `dataset_id` only |
| `tdc_trial_outcomes` | 8,026 | 2.6 MB | TDC TOP | `nct_id` only |

#### UniProt/Protein Data (3 tables) - Source-Native Only

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `target_information` | 12,253 | 2.4 MB | UniProt | `uniprot_id` only |
| `uniprot_proteins` | 0 | 8 KB | UniProt API | `accession` only |
| `uniprot_features` | 0 | 8 KB | UniProt API | `accession` only |

**Note**: `uniprot_drug_targets` moved to Silver (has both `uniprot_id` and `drugbank_id`).

#### PDB/Structure Data (3 tables) - Source-Native Only

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `pdb_structures` | 0 | 8 KB | RCSB PDB | `pdb_id` only |
| `pdb_entities` | 0 | 8 KB | RCSB PDB | `pdb_id` only |
| `pdbbind_complexes` | 0 | 8 KB | PDBbind | `pdb_id` only |

**Note**: `drug_pdb_mappings` moved to Silver (has `chembl_id`, `drugbank_id`, `pubchem_cid`).

#### PLIP Interactions (2 tables)

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `plip_interactions` | 0 | 8 KB | PLIP | `pdb_id` only |
| `plip_interaction_residues` | 0 | 8 KB | PLIP | `pdb_id` only |

#### Other External Sources (4 tables) - Source-Native Only

| Table | Records | Size | Source | Source Identifier |
|-------|---------|------|--------|-------------------|
| `pdsp_ki_data` | 0 | 8 KB | PDSP | `ligand_id` only |
| `ddinter_raw` | 0 | 8 KB | DDInter | `ddinter_id` only |
| `meddra_terms` | 0 | 8 KB | MedDRA | `meddra_code` only |
| `rxnorm_ndc_codes` | 0 | 0 | RxNorm | `ndc_code` only |

**Note**: `who_inn_data` and `rxnorm_drugs` moved to Silver (have multiple source identifiers).

---

### SILVER LAYER (17 tables, ~6.6M records, 2.8 GB)

Tables with **multiple source identifiers linked together** - entity resolution has been performed.

#### Master Entity Tables (3 tables)

| Table | Records | Size | Cross-Linked Identifiers | Description |
|-------|---------|------|--------------------------|-------------|
| `compounds` | 46,813 | 434 MB | `chembl_id` + `drugbank_id` + `pubchem_cid` + `inchi_key` | **Master molecule table** with all source identifiers linked |
| `compound_cross_reference` | 1,005,135 | 907 MB | `chembl_id` + `drugbank_id` + `pubchem_cid` + `inchi_key` | Explicit cross-source ID mappings |
| `identifier_mappings` | 0 | 8 KB | `chembl_id` + `drugbank_id` + `pubchem_cid` | Cached ID resolutions from resolution service |

#### Entity-Resolved Drug Data (3 tables)

| Table | Records | Size | Cross-Linked Identifiers | Description |
|-------|---------|------|--------------------------|-------------|
| `drugbank_data` | 17,430 | 23 MB | `chembl_id` + `drugbank_id` + `pubchem_cid` + `inchi_key` | DrugBank enriched with cross-references |
| `drug_name_resolver` | 28,195 | 6.7 MB | `chembl_id` + `drugbank_id` + `pubchem_cid` + `inchi_key` | Name-to-identifier aliases across sources |
| `who_inn_data` | 55 | 16 KB | `chembl_id` + `drugbank_id` + `pubchem_cid` + `inchi_key` | WHO INN data with cross-references |

#### Entity-Resolved Interaction Data (2 tables)

| Table | Records | Size | Cross-Linked Identifiers | Description |
|-------|---------|------|--------------------------|-------------|
| `drug_interactions` | 2,842,746 | 1.6 GB | `inchi_key_1` + `inchi_key_2` (unified) | **Unified DDI** from DrugBank + DDInter |
| `bindingdb_affinities` | 2,278,614 | 827 MB | `chembl_id` + `drugbank_id` + `pubchem_cid` + `inchi_key` | Binding affinities with cross-linked identifiers |

#### Entity-Resolved Safety Data (2 tables)

| Table | Records | Size | Cross-Linked Identifiers | Description |
|-------|---------|------|--------------------------|-------------|
| `sider_adverse_reactions` | 309,849 | 60 MB | `stitch_id` + `drugbank_id` + `inchi_key` | SIDER AEs with DrugBank cross-reference |
| `sider_indications` | 30,835 | 11 MB | `stitch_id` + `drugbank_id` + `inchi_key` | SIDER indications with DrugBank cross-reference |

#### Entity-Resolved Structure/Target Mappings (3 tables)

| Table | Records | Size | Cross-Linked Identifiers | Description |
|-------|---------|------|--------------------------|-------------|
| `drug_pdb_mappings` | 0 | 8 KB | `chembl_id` + `drugbank_id` + `pubchem_cid` | Drug-to-PDB structure mappings |
| `uniprot_drug_targets` | 0 | 8 KB | `chembl_id` + `drugbank_id` | UniProt proteins linked to drugs |
| `rxnorm_drugs` | 3 | 16 KB | `rxcui` + `drugbank_id` + `inchi_key` | RxNorm with DrugBank cross-reference |

#### Supporting Silver Tables (4 tables)

| Table | Records | Size | Cross-Linked Identifiers | Description |
|-------|---------|------|--------------------------|-------------|
| `biologic_mappings` | 74 | 48 KB | `drugbank_id` + `uniprot_id` | Biologics without InChI Key (special case) |
| `compound_provenance` | 0 | 8 KB | `inchi_key` + sources | Data source attribution per molecule |
| `trial_drugs` | 0 | 8 KB | `nct_id` + `inchi_key` | Trial-to-compound linkage |
| `rxnorm_drug_classes` | 2 | 16 KB | `rxcui` + external mappings | RxNorm drug class hierarchies |

---

### GOLD LAYER (22 tables, ~550 records, 200 KB)

Pre-computed aggregations, analytics, and competitive intelligence.

#### Safety Signal Aggregations (2 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `faers_aggregated_events` | 500 | 96 KB | Pre-computed AE disproportionality (PRR, ROR, IC) |
| `faers_effect_counts` | 0 | 8 KB | Aggregated counts per drug-effect pair |

#### Ground Truth / Competitive Intelligence (15 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `gt_h2h_trials` | 9 | 16 KB | Head-to-head trial results with statistical winner |
| `gt_registry_studies` | 7 | 16 KB | Registry study summaries (BioDay, PROSE, etc.) |
| `gt_competitive_relationships` | 0 | 8 KB | Direct competitor mappings by dimension |
| `gt_threat_assessments` | 0 | 8 KB | Aggregated competitive threat scores |
| `gt_landscape_snapshots` | 0 | 8 KB | Historical competitive landscape snapshots |
| `gt_data_coverage` | 0 | 8 KB | Data completeness tracking per drug |
| `gt_data_sufficiency` | 0 | 8 KB | Evidence sufficiency for lifecycle stages |
| `gt_drug_indications` | 0 | 8 KB | Validated drug-indication mappings |
| `gt_indications` | 0 | 8 KB | Canonical indication list |
| `gt_icd10_codes` | 0 | 8 KB | ICD-10 code mappings |
| `gt_regulatory_milestones` | 0 | 8 KB | Key regulatory events timeline |
| `gt_patents` | 0 | 0 | Patent/exclusivity expiry dates |
| `gt_exclusivities` | 0 | 8 KB | FDA exclusivity periods |
| `gt_designations` | 0 | 8 KB | Orphan, breakthrough, fast track designations |
| `gt_ai_insights` | 0 | 8 KB | AI-generated analysis insights |

#### Other Gold Tables (5 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `gt_conference_abstracts` | 6 | 16 KB | Conference presentation summaries |
| `repositioning_candidates` | 0 | 8 KB | Computed drug repositioning opportunities |
| `disease_target_mapping` | 0 | 8 KB | Disease-to-target associations |
| `compound_clinical_trials` | 0 | 8 KB | Compound-to-trial linkage summary |
| `dashboard_stats` | 0 | 8 KB | Pre-computed dashboard metrics |

---

### APPLICATION LAYER (21 tables, ~150 records, 300 KB)

User-facing features, tracking, alerts, and configurations.

#### Molecule Tracking (1 table)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `tracked_molecules` | 0 | 16 KB | User molecule tracking with lifecycle stage |

#### IVA Publications (4 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `iva_publications` | 35 | 64 KB | IVA-relevant publications |
| `iva_curated_publications` | 15 | 16 KB | Manually curated IVA publications |
| `iva_monitoring_config` | 10 | 16 KB | Publication monitoring settings |
| `iva_publication_alerts` | 0 | 8 KB | Publication alerts |

#### News & Monitoring (1 table)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `news_alerts` | 0 | 8 KB | News alerts for tracked molecules |

#### Compound Libraries (3 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `compound_libraries` | 0 | 8 KB | User-created compound collections |
| `library_compounds` | 0 | 8 KB | Compounds in libraries |
| `library_predictions` | 0 | 8 KB | Batch predictions on libraries |

#### Comparisons & History (2 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `compound_comparisons` | 0 | 8 KB | Saved compound comparisons |
| `prediction_history` | 0 | 8 KB | Historical prediction results |

#### Data Management (5 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `data_load_history` | 7 | 16 KB | Data ingestion audit log |
| `data_source_stats` | 40 | 8 KB | Per-source statistics |
| `data_quality_issues` | 0 | 8 KB | Data quality problem tracking |
| `publication_discovery_runs` | 3 | 16 KB | Publication scan history |
| `publication_source_config` | 5 | 16 KB | Publication source settings |

#### API & Auth (2 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `api_keys` | 0 | 8 KB | API key management |
| `enrichment_request_log` | 0 | 8 KB | API request audit log |

#### Batch Processing (3 tables)

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `batch_jobs` | 0 | 8 KB | Batch job tracking |
| `batch_results` | 0 | 8 KB | Individual batch results |
| `enrichment_jobs` | 0 | 8 KB | Async enrichment jobs |

---

### ML/PREDICTION LAYER (8 tables, 0 records, 64 KB)

Model predictions, explanations, and registry.

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `indication_predictions` | 0 | 8 KB | Cached indication predictions |
| `adverse_effect_predictions` | 0 | 8 KB | Cached AE predictions |
| `dti_predictions` | 0 | 8 KB | Cached DTI predictions |
| `model_predictions` | 0 | 8 KB | Generic model prediction cache |
| `predictions` | 0 | 0 | Legacy predictions table |
| `prediction_explanations` | 0 | 8 KB | SHAP/feature importance |
| `model_registry` | 0 | 8 KB | Trained model metadata |
| `model_performance_logs` | 0 | 0 | Model performance tracking |

---

### FEATURE STORE LAYER (8 tables, ~94K records, 430 MB)

Pre-computed molecular features for ML and similarity search.

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `rdkit_fingerprints` | 46,813 | 421 MB | Morgan, MACCS, RDKit, AtomPair, Torsion fingerprints |
| `rdkit_descriptors` | 46,813 | 7.2 MB | Molecular descriptors (200+ properties) |
| `compound_features` | 0 | 8 KB | Aggregated feature vectors |
| `feature_vectors` | 0 | 8 KB | Generic feature storage |
| `molecular_embeddings` | 0 | 8 KB | GNN/Chemprop learned embeddings |
| `protein_embeddings` | 0 | 8 KB | ESM-2 protein embeddings |
| `text_embeddings` | 0 | 8 KB | PubMedBERT text embeddings |
| `binding_site_features` | 0 | 8 KB | Binding site descriptors |

---

### SYSTEM/CACHE LAYER (6 tables, 0 records, 48 KB)

Infrastructure tables for caching and metrics.

| Table | Records | Size | Description |
|-------|---------|------|-------------|
| `api_cache` | 0 | 8 KB | API response cache |
| `computation_cache` | 0 | 8 KB | Expensive computation cache |
| `enrichment_cache` | 0 | 8 KB | Drug enrichment cache |
| `enrichment_metrics_hourly` | 0 | 8 KB | Hourly aggregated metrics |

---

### MIGRATION LAYER SUMMARY

| Layer | Tables | Records | Size | Priority | Entity Resolution |
|-------|--------|---------|------|----------|-------------------|
| **Raw** | 1 | 1,823 | 3.1 GB | P0 | N/A |
| **Bronze** | 40 | 7.6M | 5.3 GB | P0 | **Source-native only** |
| **Silver** | 17 | 6.6M | 2.8 GB | P0 | **Cross-source linked** |
| **Gold** | 22 | 550 | 200 KB | P1 | Aggregated |
| **Application** | 21 | 150 | 300 KB | P1 | User features |
| **ML/Prediction** | 8 | 0 | 64 KB | P2 | Model outputs |
| **Feature Store** | 8 | 94K | 430 MB | P1 | Computed |
| **System/Cache** | 6 | 0 | 48 KB | P3 | Infrastructure |
| **TOTAL** | **123** | **~14.5M** | **~12.8 GB** | - | - |

**Key Insight**: The Bronze → Silver transformation is where **entity resolution** occurs:
- Bronze tables have ONLY their source's native identifier (e.g., `chembl_id` OR `drugbank_id`)
- Silver tables have MULTIPLE source identifiers linked via **InChI Key** as master identifier

---

### MIGRATION EXECUTION ORDER

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     MIGRATION EXECUTION ORDER                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  PHASE 1: SCHEMA CREATION (Day 1)                                               │
│  ─────────────────────────────────                                              │
│  1. Create Raw layer tables (1 table)                                           │
│  2. Create Bronze layer tables (40 tables) - Source-native only                 │
│  3. Create Silver layer tables (17 tables) - Entity-resolved                    │
│  4. Create Gold layer tables (22 tables)                                        │
│  5. Create Application layer tables (21 tables)                                 │
│  6. Create Feature Store tables (8 tables)                                      │
│  7. Create ML/Prediction tables (8 tables)                                      │
│  8. Create System/Cache tables (6 tables)                                       │
│  9. Create indexes and constraints                                              │
│                                                                                  │
│  PHASE 2: DATA MIGRATION - BRONZE FIRST (Day 2-3)                               │
│  ──────────────────────────────────────────────────                             │
│  **IMPORTANT: Bronze must be loaded BEFORE Silver (entity resolution depends    │
│  on source-native data being present)**                                         │
│                                                                                  │
│  1. Export Raw layer: fda_raw_labels (3.1 GB)                                   │
│  2. Export Bronze layer: 40 tables (5.3 GB) - SOURCE-NATIVE DATA                │
│     - chembl_molecules, chembl_activities (ChEMBL identifiers)                  │
│     - drugbank_targets, drugbank_enzymes, etc. (DrugBank identifiers)           │
│     - pubchem_compounds (PubChem CID identifiers)                               │
│     - fda_labels, faers_events (FDA identifiers)                                │
│     - sider_atc_codes (STITCH identifiers)                                      │
│  3. Export Silver layer: 17 tables (2.8 GB) - ENTITY-RESOLVED DATA              │
│     - compounds (master molecule table with linked identifiers)                 │
│     - compound_cross_reference (explicit ID mappings)                           │
│     - drugbank_data, bindingdb_affinities (enriched with cross-refs)            │
│     - sider_adverse_reactions, sider_indications (linked to DrugBank)           │
│     - drug_interactions (unified from multiple sources)                         │
│  4. Export Feature Store: rdkit_fingerprints, rdkit_descriptors (430 MB)        │
│  5. Export Gold layer: gt_* tables, faers_aggregated_events                     │
│  6. Export Application layer: iva_*, tracked_molecules, data_*                  │
│                                                                                  │
│  PHASE 3: VALIDATION - ENTITY RESOLUTION CHECK (Day 4)                          │
│  ─────────────────────────────────────────────────────                          │
│  1. Compare row counts: source vs target                                        │
│  2. **Verify InChI Key linkage in Silver tables**                               │
│     - Every Silver record should have valid InChI Key                           │
│     - Cross-check: chembl_id in Silver → exists in Bronze chembl_*              │
│     - Cross-check: drugbank_id in Silver → exists in Bronze drugbank_*          │
│  3. Validate foreign key integrity                                              │
│  4. Spot-check entity resolution (random molecules)                             │
│  5. Test PostgREST queries on Gold layer                                        │
│                                                                                  │
│  PHASE 4: SERVICE CUTOVER (Day 5)                                               │
│  ─────────────────────────────────                                              │
│  1. Deploy API clients to Kubernetes                                            │
│  2. Configure data loaders with new connection string                           │
│  3. Enable SQLMesh scheduler for Bronze → Silver → Gold pipelines               │
│  4. Start pgBackRest continuous archiving                                       │
│  5. Switch application to external database                                     │
│  6. Monitor for 24 hours before decommissioning local                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### BRONZE → SILVER TRANSFORMATION PIPELINES

SQLMesh models that perform entity resolution:

| Pipeline | Source Tables (Bronze) | Target Table (Silver) | Resolution Method |
|----------|------------------------|----------------------|-------------------|
| `silver__compounds` | `chembl_molecules`, `pubchem_compounds`, `drugbank_targets` | `compounds` | InChI Key matching |
| `silver__cross_reference` | All Bronze tables with `inchi_key` | `compound_cross_reference` | InChI Key linkage |
| `silver__drug_interactions` | `drugbank_interactions`, `ddinter_raw` | `drug_interactions` | Drug name → InChI Key |
| `silver__bindingdb` | `bindingdb_affinities` (raw) | `bindingdb_affinities` (enriched) | InChI Key → source IDs |
| `silver__sider` | `sider_*` Bronze + DrugBank | `sider_adverse_reactions`, `sider_indications` | STITCH → DrugBank → InChI |

---

### TABLES REQUIRING SCHEMA CHANGES

Some tables need schema modifications to align with the medallion architecture:

| Table | Current Issue | Required Change |
|-------|---------------|-----------------|
| `fda_raw_labels` | Missing HTTP headers | Add `request_headers`, `response_headers` columns |
| `clinical_trials` | Mixed Bronze/Silver | Split into `bronze_clinicaltrials` + `silver_clinical_trials` |
| `compounds` | Missing molecule_id UUID | Add `molecule_id UUID PRIMARY KEY` |
| `drug_interactions` | Missing source linkage | Add `bronze_source_id` reference |
| All Bronze tables | Missing `raw_id` | Add `raw_id UUID REFERENCES raw_{source}(id)` |
| All Bronze tables | Missing `record_hash` | Add `record_hash VARCHAR(64)` for dedup |

---

### EMPTY TABLES TO SKIP/DEFER

Tables with 0 records that can be created empty and populated later:

- **ML/Prediction**: All 8 tables (create schema only)
- **System/Cache**: All 6 tables (create schema only)
- **Many Gold tables**: gt_patents, gt_exclusivities, gt_designations, etc.
- **UniProt/PDB**: uniprot_proteins, pdb_structures, etc. (await loader implementation)

---

## Part 15: External Data Source Comparison & Data Loading Plan

### Purpose

Compare external API source totals with local database counts to identify data gaps and plan incremental loading.

### Data Source Comparison (as of 2026-01-24)

| Source | External Total | Local Count | Table | Coverage | Gap |
|--------|----------------|-------------|-------|----------|-----|
| **OpenFDA Labels** | 253,605 | 83,805 | `fda_labels` | 33.0% | **169,800** |
| **OpenFDA FAERS** | 19,684,585 | 675,335 | `faers_events` | 3.4% | **19,009,250** |
| **ChEMBL Molecules** | 2,878,135 | 6 | `chembl_molecules` | 0.0002% | **2,878,129** |
| **ChEMBL Activities** | 24,267,312 | 2,731,670 | `chembl_activities` | 11.3% | **21,535,642** |
| **ClinicalTrials.gov** | 567,814 | 95,479 | `clinical_trials` | 16.8% | **472,335** |
| **PubChem Compounds** | ~116,000,000 | 965,578 | `pubchem_compounds` | 0.8% | **~115M** |
| **DrugBank Drugs** | ~16,000 | 17,430 | `drugbank_data` | 100%+ | ✓ Complete |
| **BindingDB** | ~2,800,000 | 2,278,525 | `bindingdb_affinities` | 81.4% | **521,475** |
| **RCSB PDB** | 248,329 | 0 | `pdb_structures` | 0% | **248,329** |
| **UniProt (Swiss-Prot)** | ~572,000 | 0 | `uniprot_proteins` | 0% | **572,000** |
| **SIDER** | ~140,000 | 340,684 | `sider_*` tables | 100%+ | ✓ Complete |
| **TDC ADMET** | ~82,000 | 82,624 | `tdc_compounds` | 100% | ✓ Complete |

### Coverage Summary

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     DATA COVERAGE BY SOURCE                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ✓ COMPLETE (100%+ coverage)                                                    │
│  ─────────────────────────────                                                  │
│  • DrugBank         17,430 drugs (full XML export)                              │
│  • SIDER            340K+ side effects & indications                            │
│  • TDC ADMET        82K compounds with ADMET properties                         │
│                                                                                  │
│  ⚠ PARTIAL (10-90% coverage)                                                    │
│  ───────────────────────────                                                    │
│  • BindingDB        81% - missing ~521K binding measurements                    │
│  • OpenFDA Labels   33% - missing ~170K drug labels                             │
│  • ClinicalTrials   17% - missing ~472K trials                                  │
│  • ChEMBL Activities 11% - missing ~21.5M activity records                      │
│                                                                                  │
│  ✗ MINIMAL (<10% coverage)                                                      │
│  ─────────────────────────                                                      │
│  • FAERS            3.4% - missing ~19M adverse event reports                   │
│  • PubChem          0.8% - missing ~115M compounds                              │
│  • ChEMBL Molecules 0.0002% - missing ~2.9M molecules                           │
│  • UniProt          0% - no proteins loaded                                     │
│  • PDB              0% - no structures loaded                                   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Data Loading Plan

#### Priority 1: Critical Gaps (Empty Tables with Data Available)

| Table | Target Records | Loader | API/Source | Priority |
|-------|----------------|--------|------------|----------|
| `chembl_molecules` | 2,878,135 | `ChEMBLLoader` | ChEMBL API | P1-Critical |
| `uniprot_proteins` | ~572,000 | `UniProtLoader` | UniProt REST | P1-Critical |
| `pdb_structures` | 248,329 | `PDBLoader` | RCSB REST | P1-Critical |
| `pdb_entities` | ~1,000,000 | `PDBLoader` | RCSB REST | P1-Critical |
| `meddra_terms` | ~80,000 | `MedDRALoader` | MedDRA files | P1-Critical |

**Estimated Load Time**: 2-3 days with rate limiting

#### Priority 2: Significant Gaps (>50% missing)

| Table | Current | Target | Gap | Loader | Strategy |
|-------|---------|--------|-----|--------|----------|
| `fda_labels` | 83,805 | 253,605 | 169,800 | `OpenFDALabelsLoader` | Incremental by date |
| `clinical_trials` | 95,479 | 567,814 | 472,335 | `ClinicalTrialsLoader` | Incremental by NCT ID |
| `chembl_activities` | 2.73M | 24.27M | 21.54M | `ChEMBLActivitiesLoader` | Batch by assay |
| `faers_events` | 675K | 19.68M | 19.01M | `FAERSLoader` | Quarterly bulk files |

**Estimated Load Time**: 1-2 weeks with batch processing

#### Priority 3: Enhancement Gaps (<50% missing)

| Table | Current | Target | Gap | Strategy |
|-------|---------|--------|-----|----------|
| `bindingdb_affinities` | 2.28M | 2.8M | 521K | Incremental TSV update |
| `pubchem_compounds` | 965K | Selected subset | N/A | Load only drug-like compounds |

**Note**: Full PubChem (116M) is not practical. Focus on:
- Compounds with bioactivity data
- Compounds in clinical trials
- Compounds with DrugBank/ChEMBL cross-references

### Incremental Loading Strategy

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     INCREMENTAL LOADING WORKFLOW                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  1. CHECKPOINT TRACKING                                                         │
│     ─────────────────────                                                       │
│     Each loader maintains checkpoint in `data_load_history`:                    │
│     - last_loaded_id: Latest record ID processed                                │
│     - last_loaded_date: Timestamp of last successful load                       │
│     - records_loaded: Count of records in last batch                            │
│                                                                                  │
│  2. DELTA DETECTION                                                             │
│     ─────────────────                                                           │
│     Query external API for records newer than checkpoint:                       │
│     - OpenFDA: ?search=effective_time:[checkpoint TO *]                         │
│     - ChEMBL: ?limit=1000&offset=checkpoint                                     │
│     - ClinicalTrials: ?query.term=AREA[LastUpdatePostDate]RANGE[date,MAX]       │
│                                                                                  │
│  3. BATCH PROCESSING                                                            │
│     ─────────────────                                                           │
│     Process in batches of 1,000-10,000 records:                                 │
│     - Transform to Bronze schema                                                │
│     - Upsert (INSERT ON CONFLICT UPDATE)                                        │
│     - Update checkpoint on success                                              │
│                                                                                  │
│  4. ENTITY RESOLUTION TRIGGER                                                   │
│     ─────────────────────────                                                   │
│     After Bronze load, trigger SQLMesh pipeline:                                │
│     - silver__compounds (update master molecule table)                          │
│     - silver__cross_reference (update ID mappings)                              │
│     - Dependent Silver tables                                                   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Specific Loader Implementations

#### 1. ChEMBL Molecules Full Load

```python
# Loader: src/services/external/chembl_loader.py
# Target: 2,878,135 molecules

async def load_chembl_molecules_full():
    """
    Full load of ChEMBL molecules with pagination.
    API: https://www.ebi.ac.uk/chembl/api/data/molecule.json
    Rate limit: 10 req/sec
    """
    batch_size = 1000
    total = 2878135

    for offset in range(0, total, batch_size):
        response = await chembl_api.get_molecules(limit=batch_size, offset=offset)
        records = transform_to_bronze(response['molecules'])
        await upsert_batch('chembl_molecules', records)
        await update_checkpoint('chembl_molecules', offset + batch_size)
```

#### 2. UniProt Proteins Load

```python
# Loader: src/services/external/uniprot_loader.py
# Target: ~572,000 reviewed proteins (Swiss-Prot)

async def load_uniprot_proteins():
    """
    Load UniProt Swiss-Prot proteins.
    API: https://rest.uniprot.org/uniprotkb/stream?query=reviewed:true
    Format: JSON streaming
    """
    async for batch in uniprot_api.stream_proteins(reviewed=True, batch_size=500):
        records = transform_to_bronze(batch)
        await upsert_batch('uniprot_proteins', records)
```

#### 3. PDB Structures Load

```python
# Loader: src/services/external/pdb_loader.py
# Target: 248,329 structures

async def load_pdb_structures():
    """
    Load RCSB PDB structures.
    API: https://data.rcsb.org/rest/v1/core/entry/{pdb_id}
    Bulk: https://data.rcsb.org/rest/v1/holdings/current/entry_ids
    """
    pdb_ids = await pdb_api.get_all_entry_ids()  # 248,329 IDs

    for batch in chunks(pdb_ids, 100):
        structures = await pdb_api.get_entries_batch(batch)
        records = transform_to_bronze(structures)
        await upsert_batch('pdb_structures', records)
```

#### 4. FDA Labels Incremental Load

```python
# Loader: src/services/external/openfda_labels_loader.py
# Gap: 169,800 labels

async def load_fda_labels_incremental():
    """
    Incremental load of OpenFDA drug labels.
    API: https://api.fda.gov/drug/label.json
    Strategy: Load by effective_time date range
    """
    checkpoint = await get_checkpoint('fda_labels')
    last_date = checkpoint.get('last_effective_date', '2000-01-01')

    query = f"effective_time:[{last_date} TO *]"
    async for batch in openfda_api.paginate_labels(query, limit=100):
        records = transform_to_bronze(batch)
        await upsert_batch('fda_labels', records)
```

### Data Loading Schedule

| Week | Focus | Tables | Expected Records |
|------|-------|--------|------------------|
| **Week 1** | Critical empty tables | `chembl_molecules`, `uniprot_proteins` | 3.4M |
| **Week 2** | Structure data | `pdb_structures`, `pdb_entities` | 1.2M |
| **Week 3** | FDA data gaps | `fda_labels`, `faers_events` (batch 1) | 5M |
| **Week 4** | Clinical trials | `clinical_trials` | 472K |
| **Week 5-6** | ChEMBL activities | `chembl_activities` (batched) | 21.5M |
| **Week 7-8** | FAERS completion | `faers_events` (remaining) | 14M |
| **Ongoing** | Incremental updates | All sources | Daily delta |

### Success Criteria for Data Loading

| Metric | Target | Measurement |
|--------|--------|-------------|
| **SC-LOAD01** | ChEMBL molecules >95% coverage | 2.73M+ records |
| **SC-LOAD02** | UniProt proteins >90% coverage | 515K+ records |
| **SC-LOAD03** | PDB structures >95% coverage | 236K+ records |
| **SC-LOAD04** | FDA labels >90% coverage | 228K+ records |
| **SC-LOAD05** | Clinical trials >80% coverage | 454K+ records |
| **SC-LOAD06** | FAERS events >50% coverage | 9.8M+ records |
| **SC-LOAD07** | ChEMBL activities >50% coverage | 12M+ records |
| **SC-LOAD08** | All entity resolution completes | Silver tables updated |

---

## Part 16: Table Inventory Verification

### Database Table Count: 122 Base Tables + 28 Views

All 122 base tables from `pharma_predictor_db` are documented in this spec:

#### Tables by Layer (122 total)

| Layer | Count | Tables Documented |
|-------|-------|-------------------|
| Raw | 1 | `fda_raw_labels` |
| Bronze | 40 | All ChEMBL, DrugBank, PubChem, FDA, SIDER, TDC, UniProt, PDB tables |
| Silver | 17 | `compounds`, `compound_cross_reference`, `drug_interactions`, etc. |
| Gold | 22 | All `gt_*` tables, `faers_aggregated_events`, etc. |
| Application | 21 | `tracked_molecules`, `iva_*`, `data_*`, etc. |
| ML/Prediction | 8 | `*_predictions`, `model_*`, `predictions` |
| Feature Store | 8 | `rdkit_*`, `*_embeddings`, `compound_features`, etc. |
| System/Cache | 6 | `api_cache`, `computation_cache`, `enrichment_*` |
| **TOTAL** | **123** | (includes 1 legacy table: `trial_outcome_training`) |

#### Views (28 total - Gold Layer Analytics)

| View | Purpose |
|------|---------|
| `v_adverse_effects_by_soc` | AE aggregation by System Organ Class |
| `v_all_trial_training_data` | ML training data view |
| `v_clinical_trials_training` | Clinical trial training features |
| `v_competitive_landscape` | Competitive intelligence summary |
| `v_complex_interactions` | Multi-drug interaction view |
| `v_compound_data` | Unified compound data |
| `v_compound_experimental_data` | Experimental results summary |
| `v_compound_features_stats` | Feature statistics |
| `v_compound_indication_profile` | Indication mapping summary |
| `v_compound_overview` | Compound dashboard data |
| `v_compound_safety_profile` | Safety data aggregation |
| `v_compound_target_profile` | Target engagement summary |
| `v_compounds_with_features` | Compounds + computed features |
| `v_ddi_statistics` | Drug interaction statistics |
| `v_drug_interactions_resolved` | Resolved DDI with names |
| `v_drug_metabolism_profile` | Metabolism pathway summary |
| `v_drug_patent_status` | Patent expiry tracking |
| `v_drug_transport_profile` | Transporter interactions |
| `v_fda_labels_by_type` | FDA labels categorized |
| `v_registry_evidence` | Registry study evidence |
| `v_repositioning_summary` | Drug repositioning candidates |
| `v_sider_effects_enriched` | SIDER data with drug names |
| `v_target_interaction_stats` | Target binding statistics |
| `v_therapeutic_area_stats` | Therapeutic area analysis |
| `v_trial_statistics` | Clinical trial statistics |

### Verification Queries

```sql
-- Verify all 122 base tables exist
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
-- Expected: 122

-- Verify all 28 views exist
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'VIEW';
-- Expected: 28

-- Total objects
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'public';
-- Expected: 150
```

---

## Part 17: Automatic Data Loading & Entity Resolution System

### Purpose

Implement an automated system that:
1. **Discovers** new records from external data sources
2. **Deduplicates** against existing local data
3. **Processes** through Raw → Bronze → Silver → Gold pipeline
4. **Maintains** column structure integrity per source
5. **Resolves** molecule identities across data sources using InChI Key

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    AUTOMATIC DATA LOADING PIPELINE                                       │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   EXTERNAL SOURCES              DISCOVERY              DEDUPLICATION                     │
│   ─────────────────             ─────────              ─────────────                     │
│                                                                                          │
│   ┌──────────┐                  ┌─────────────────┐    ┌─────────────────┐              │
│   │ ChEMBL   │──update_date────▶│                 │    │ Check exists:   │              │
│   │ API      │                  │   Change        │    │ - source_id     │              │
│   └──────────┘                  │   Detection     │───▶│ - record_hash   │              │
│                                 │   Service       │    │                 │              │
│   ┌──────────┐                  │                 │    │ Filter:         │              │
│   │ DrugBank │──version_diff───▶│ Checks each    │    │ - new records   │              │
│   │ Releases │                  │ source's       │    │ - updated recs  │              │
│   └──────────┘                  │ change API     │    └────────┬────────┘              │
│                                 │                 │             │                        │
│   ┌──────────┐                  └─────────────────┘             │                        │
│   │ OpenFDA  │──effective_time─────────────────────────────────▶│                        │
│   │ API      │                                                   │                        │
│   └──────────┘                                                   ▼                        │
│                                                                                          │
│   ┌──────────┐                  ┌─────────────────────────────────────────────────────┐ │
│   │ PubChem  │──last_modified──▶│                                                     │ │
│   │ API      │                  │                RAW LAYER                            │ │
│   └──────────┘                  │  Store original API response with metadata          │ │
│                                 │  - request_timestamp                                │ │
│   ┌──────────┐                  │  - response_body (JSONB)                            │ │
│   │ Clinical │──LastUpdateDate─▶│  - source_api, endpoint, version                    │ │
│   │ Trials   │                  │  - record_hash (SHA256)                             │ │
│   └──────────┘                  └────────────────────┬────────────────────────────────┘ │
│                                                      │                                   │
│   ┌──────────┐                                       ▼                                   │
│   │ UniProt  │──entry_modified─▶┌─────────────────────────────────────────────────────┐ │
│   │ API      │                  │                                                     │ │
│   └──────────┘                  │               BRONZE LAYER                          │ │
│                                 │  Parse to typed columns (source-specific schema)    │ │
│   ┌──────────┐                  │  - Preserve ALL source columns                      │ │
│   │ RCSB PDB │──deposition_date▶│  - Add: raw_id, record_hash, loaded_at             │ │
│   │ API      │                  │  - Source-native identifier as PRIMARY KEY          │ │
│   └──────────┘                  └────────────────────┬────────────────────────────────┘ │
│                                                      │                                   │
│                                                      ▼                                   │
│                                 ┌─────────────────────────────────────────────────────┐ │
│                                 │                                                     │ │
│                                 │              SILVER LAYER                           │ │
│                                 │  ENTITY RESOLUTION via InChI Key                    │ │
│                                 │  - Link source IDs to master molecule_id            │ │
│                                 │  - Update compound_cross_reference                  │ │
│                                 │  - Normalize to canonical schema                    │ │
│                                 └────────────────────┬────────────────────────────────┘ │
│                                                      │                                   │
│                                                      ▼                                   │
│                                 ┌─────────────────────────────────────────────────────┐ │
│                                 │                                                     │ │
│                                 │               GOLD LAYER                            │ │
│                                 │  Update aggregations & analytics                    │ │
│                                 │  - Competitive landscape                            │ │
│                                 │  - Safety signal aggregations                       │ │
│                                 │  - Molecule profiles                                │ │
│                                 └─────────────────────────────────────────────────────┘ │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Per-Source Change Detection Configuration

Each external source has a specific API mechanism for detecting new/updated records:

| Source | Change Detection Method | API Parameter | Checkpoint Field |
|--------|------------------------|---------------|------------------|
| **ChEMBL** | `molecule_properties__updated_on` filter | `?molecule_properties__updated_on__gte=YYYY-MM-DD` | `last_update_date` |
| **DrugBank** | Version comparison + release notes | Version number (e.g., 5.1.11) | `last_version` |
| **OpenFDA Labels** | `effective_time` date filter | `?search=effective_time:[YYYYMMDD+TO+*]` | `last_effective_time` |
| **OpenFDA FAERS** | `receivedate` filter | `?search=receivedate:[YYYYMMDD+TO+*]` | `last_receive_date` |
| **ClinicalTrials.gov** | `LastUpdatePostDate` filter | `?query.term=AREA[LastUpdatePostDate]RANGE[date,MAX]` | `last_update_post_date` |
| **PubChem** | `ModifyDate` property | PUG REST with date filter | `last_modify_date` |
| **UniProt** | `modified` date in entry | `?query=modified:[date TO *]` | `last_modified_date` |
| **RCSB PDB** | `rcsb_accession_info.deposit_date` | Search API with date filter | `last_deposit_date` |
| **BindingDB** | Monthly TSV releases | Release date comparison | `last_release_date` |
| **SIDER** | Version releases (infrequent) | Version number | `last_version` |

### Source-Specific Schema Preservation

#### Bronze Layer Column Mapping

Each source maintains its native column structure in Bronze:

##### ChEMBL Molecules (`chembl_molecules`)

```sql
CREATE TABLE bronze.chembl_molecules (
    -- Source-native identifier (PRIMARY KEY)
    molecule_chembl_id VARCHAR(20) PRIMARY KEY,

    -- Source-native columns (PRESERVE ALL)
    pref_name TEXT,
    molecule_type VARCHAR(50),
    structure_type VARCHAR(50),
    max_phase VARCHAR(10),
    first_approval INTEGER,
    withdrawn_flag BOOLEAN,
    oral BOOLEAN,
    parenteral BOOLEAN,
    topical BOOLEAN,
    black_box_warning BOOLEAN,
    first_in_class BOOLEAN,
    prodrug BOOLEAN,
    natural_product BOOLEAN,
    therapeutic_flag BOOLEAN,

    -- Chemical identifiers (FROM SOURCE)
    canonical_smiles TEXT,
    standard_inchi TEXT,
    inchi_key VARCHAR(27),  -- Source provides this

    -- Molecular properties (FROM SOURCE)
    molecular_weight REAL,
    alogp REAL,
    psa REAL,
    hba INTEGER,
    hbd INTEGER,
    heavy_atom_count INTEGER,
    rtb INTEGER,
    num_ro5_violations INTEGER,
    aromatic_rings INTEGER,
    qed_weighted REAL,

    -- Cross-references (FROM SOURCE - not entity-resolved yet)
    atc_classifications JSONB,
    molecule_synonyms JSONB,
    cross_references JSONB,

    -- Pipeline metadata (ADDED BY SYSTEM)
    raw_id UUID REFERENCES raw.chembl_molecules(id),
    record_hash VARCHAR(64),
    loaded_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

##### DrugBank Data (`drugbank_data`)

```sql
CREATE TABLE bronze.drugbank_data (
    -- Source-native identifier (PRIMARY KEY)
    drugbank_id VARCHAR(10) PRIMARY KEY,

    -- Source-native columns (PRESERVE ALL)
    name TEXT NOT NULL,
    type VARCHAR(20),  -- 'small molecule', 'biotech'
    description TEXT,
    cas_number VARCHAR(20),
    unii VARCHAR(20),
    state VARCHAR(20),
    indication TEXT,
    pharmacodynamics TEXT,
    mechanism_of_action TEXT,
    toxicity TEXT,
    metabolism TEXT,
    absorption TEXT,
    half_life TEXT,
    protein_binding TEXT,
    route_of_elimination TEXT,
    volume_of_distribution TEXT,
    clearance TEXT,

    -- Chemical identifiers (FROM SOURCE)
    smiles TEXT,
    inchi TEXT,
    inchi_key VARCHAR(27),  -- Source provides this
    molecular_formula TEXT,
    molecular_weight REAL,

    -- Status fields (FROM SOURCE)
    groups JSONB,  -- ['approved', 'investigational', etc.]
    categories JSONB,
    affected_organisms JSONB,

    -- Pipeline metadata (ADDED BY SYSTEM)
    raw_id UUID REFERENCES raw.drugbank(id),
    record_hash VARCHAR(64),
    loaded_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

##### PubChem Compounds (`pubchem_compounds`)

```sql
CREATE TABLE bronze.pubchem_compounds (
    -- Source-native identifier (PRIMARY KEY)
    cid INTEGER PRIMARY KEY,

    -- Source-native columns (PRESERVE ALL)
    iupac_name TEXT,
    molecular_formula TEXT,
    molecular_weight REAL,
    exact_mass REAL,
    monoisotopic_mass REAL,
    canonical_smiles TEXT,
    isomeric_smiles TEXT,

    -- Chemical identifiers (FROM SOURCE)
    inchi TEXT,
    inchi_key VARCHAR(27),  -- Source provides this

    -- Computed properties (FROM SOURCE)
    xlogp REAL,
    tpsa REAL,
    complexity REAL,
    hbond_donor INTEGER,
    hbond_acceptor INTEGER,
    rotatable_bonds INTEGER,
    heavy_atoms INTEGER,
    charge INTEGER,

    -- 3D properties (FROM SOURCE)
    volume_3d REAL,
    conformer_count_3d INTEGER,

    -- Synonyms (FROM SOURCE)
    synonyms TEXT[],

    -- Pipeline metadata (ADDED BY SYSTEM)
    raw_id UUID REFERENCES raw.pubchem(id),
    record_hash VARCHAR(64),
    loaded_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

##### ClinicalTrials.gov (`clinical_trials`)

```sql
CREATE TABLE bronze.clinical_trials (
    -- Source-native identifier (PRIMARY KEY)
    nct_id VARCHAR(15) PRIMARY KEY,

    -- Source-native columns (PRESERVE ALL)
    org_study_id VARCHAR(100),
    brief_title TEXT,
    official_title TEXT,
    brief_summary TEXT,
    detailed_description TEXT,
    overall_status VARCHAR(50),
    last_known_status VARCHAR(50),
    why_stopped TEXT,
    start_date DATE,
    completion_date DATE,
    primary_completion_date DATE,
    phase VARCHAR(20),
    study_type VARCHAR(50),

    -- Design (FROM SOURCE)
    allocation VARCHAR(50),
    intervention_model VARCHAR(50),
    primary_purpose VARCHAR(50),
    masking VARCHAR(50),
    enrollment INTEGER,

    -- Structured data (FROM SOURCE - JSONB)
    conditions JSONB,
    interventions JSONB,
    arms_groups JSONB,
    outcomes JSONB,
    eligibility JSONB,
    contacts JSONB,
    locations JSONB,
    sponsors JSONB,
    collaborators JSONB,

    -- Dates (FROM SOURCE)
    study_first_submitted DATE,
    study_first_posted DATE,
    last_update_submitted DATE,
    last_update_posted DATE,

    -- Pipeline metadata (ADDED BY SYSTEM)
    raw_id UUID REFERENCES raw.clinicaltrials(id),
    record_hash VARCHAR(64),
    loaded_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Entity Resolution: Cross-Source Identifier Linking

#### The Entity Resolution Problem

Each data source uses its own identifier system:

```
ChEMBL:  CHEMBL25 ─────────────┐
DrugBank: DB00945 ─────────────┼───▶ Same molecule: Aspirin
PubChem:  CID 2244 ────────────┤
SIDER:    CID100002244 ────────┘
```

#### Solution: InChI Key as Master Identifier

**InChI Key** (International Chemical Identifier Key) is a 27-character hash derived from molecular structure that serves as a universal identifier:

```
Aspirin InChI Key: BSYNRYMUTXBXSQ-UHFFFAOYSA-N
                   └─────────┬────┘└───────┬──┘└┬┘
                   Connectivity  Stereochemistry Protonation
```

#### Entity Resolution Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                    ENTITY RESOLUTION PROCESS                                             │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  STEP 1: EXTRACT InChI Key FROM BRONZE                                                  │
│  ─────────────────────────────────────────                                              │
│                                                                                          │
│  For each new Bronze record:                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐               │
│  │ Source Table          │ InChI Key Source                            │               │
│  ├───────────────────────┼─────────────────────────────────────────────┤               │
│  │ chembl_molecules      │ inchi_key column (native)                   │               │
│  │ drugbank_data         │ inchi_key column (native)                   │               │
│  │ pubchem_compounds     │ inchi_key column (native)                   │               │
│  │ bindingdb_affinities  │ Ligand InChI column or SMILES → compute     │               │
│  │ sider_*               │ STITCH ID → PubChem CID → InChI Key lookup  │               │
│  │ tdc_compounds         │ SMILES → compute InChI Key via RDKit        │               │
│  └─────────────────────────────────────────────────────────────────────┘               │
│                                                                                          │
│  STEP 2: LOOKUP OR CREATE MASTER MOLECULE                                               │
│  ────────────────────────────────────────────                                           │
│                                                                                          │
│  ```python                                                                               │
│  async def resolve_molecule(inchi_key: str, source_id: str, source: str):              │
│      # Check if molecule already exists                                                 │
│      existing = await db.fetchrow("""                                                   │
│          SELECT id, molecule_id FROM compounds WHERE inchi_key = $1                     │
│      """, inchi_key)                                                                    │
│                                                                                          │
│      if existing:                                                                        │
│          molecule_id = existing['molecule_id']                                          │
│      else:                                                                               │
│          # Create new master molecule                                                   │
│          molecule_id = uuid.uuid4()                                                     │
│          await db.execute("""                                                           │
│              INSERT INTO compounds (molecule_id, inchi_key, created_at)                 │
│              VALUES ($1, $2, NOW())                                                     │
│          """, molecule_id, inchi_key)                                                   │
│                                                                                          │
│      # Add cross-reference                                                              │
│      await db.execute("""                                                               │
│          INSERT INTO compound_cross_reference                                           │
│              (molecule_id, inchi_key, source, source_id, linked_at)                     │
│          VALUES ($1, $2, $3, $4, NOW())                                                 │
│          ON CONFLICT (source, source_id) DO UPDATE SET linked_at = NOW()               │
│      """, molecule_id, inchi_key, source, source_id)                                   │
│                                                                                          │
│      return molecule_id                                                                 │
│  ```                                                                                     │
│                                                                                          │
│  STEP 3: UPDATE SILVER TABLES WITH LINKED IDENTIFIERS                                   │
│  ───────────────────────────────────────────────────────                                │
│                                                                                          │
│  After entity resolution, Silver tables have ALL source identifiers:                    │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐               │
│  │ compounds (Silver - Master Entity Table)                            │               │
│  ├─────────────────────────────────────────────────────────────────────┤               │
│  │ molecule_id     │ UUID (Primary Key - system generated)             │               │
│  │ inchi_key       │ Master identifier                                 │               │
│  │ canonical_smiles│ Canonical SMILES (from ChEMBL/RDKit)              │               │
│  │ chembl_id       │ CHEMBL25 (from entity resolution)                 │               │
│  │ drugbank_id     │ DB00945 (from entity resolution)                  │               │
│  │ pubchem_cid     │ 2244 (from entity resolution)                     │               │
│  │ name            │ Best name (priority: DrugBank > ChEMBL > PubChem) │               │
│  │ molecular_weight│ Computed (unified)                                │               │
│  └─────────────────────────────────────────────────────────────────────┘               │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Cross-Reference Table Schema

The `compound_cross_reference` table maintains all source-to-molecule linkages:

```sql
CREATE TABLE silver.compound_cross_reference (
    -- Composite primary key
    id SERIAL PRIMARY KEY,

    -- Master molecule reference
    molecule_id UUID NOT NULL REFERENCES compounds(molecule_id),
    inchi_key VARCHAR(27) NOT NULL,

    -- Source identification
    source VARCHAR(50) NOT NULL,  -- 'chembl', 'drugbank', 'pubchem', 'sider', etc.
    source_id VARCHAR(50) NOT NULL,  -- The source-native ID
    source_id_type VARCHAR(50),  -- 'chembl_id', 'drugbank_id', 'cid', 'stitch_id'

    -- Resolution metadata
    resolution_method VARCHAR(50),  -- 'inchi_exact', 'inchi_connectivity', 'name_match', 'manual'
    confidence_score REAL,  -- 0.0 to 1.0
    linked_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    UNIQUE (source, source_id),
    INDEX idx_molecule_id (molecule_id),
    INDEX idx_inchi_key (inchi_key),
    INDEX idx_source_lookup (source, source_id)
);
```

### Automatic Data Loading Service

#### Service Architecture

```python
# src/services/data_loading/auto_loader_service.py

class AutomaticDataLoaderService:
    """
    Orchestrates automatic discovery and loading of new data from external sources.
    Runs on configurable schedule (default: daily at 02:00 UTC).
    """

    def __init__(self):
        self.sources = {
            'chembl': ChEMBLChangeDetector(),
            'drugbank': DrugBankChangeDetector(),
            'openfda_labels': OpenFDALabelsChangeDetector(),
            'openfda_faers': OpenFDAFAERSChangeDetector(),
            'clinicaltrials': ClinicalTrialsChangeDetector(),
            'pubchem': PubChemChangeDetector(),
            'uniprot': UniProtChangeDetector(),
            'pdb': PDBChangeDetector(),
        }
        self.entity_resolver = EntityResolutionService()
        self.pipeline_runner = SQLMeshPipelineRunner()

    async def run_full_sync(self):
        """Execute full sync cycle for all sources."""

        for source_name, detector in self.sources.items():
            try:
                # 1. Detect changes
                changes = await detector.detect_changes()
                logger.info(f"{source_name}: Found {len(changes.new)} new, {len(changes.updated)} updated")

                if not changes.has_changes:
                    continue

                # 2. Load to Raw layer
                raw_ids = await self.load_to_raw(source_name, changes)

                # 3. Transform to Bronze layer
                bronze_ids = await self.transform_to_bronze(source_name, raw_ids)

                # 4. Entity resolution (Bronze → Silver)
                await self.entity_resolver.resolve_batch(source_name, bronze_ids)

                # 5. Update checkpoint
                await detector.update_checkpoint(changes.latest_timestamp)

            except Exception as e:
                logger.error(f"Error syncing {source_name}: {e}")
                await self.alert_on_failure(source_name, e)

        # 6. Run SQLMesh Silver → Gold pipelines
        await self.pipeline_runner.run_incremental()
```

#### Change Detection Implementation

```python
# src/services/data_loading/change_detectors/chembl_detector.py

class ChEMBLChangeDetector:
    """Detects new/updated molecules in ChEMBL since last sync."""

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    async def detect_changes(self) -> ChangeSet:
        checkpoint = await self.get_checkpoint()
        last_date = checkpoint.get('last_update_date', '2020-01-01')

        # Query ChEMBL for molecules updated since checkpoint
        url = f"{self.BASE_URL}/molecule.json"
        params = {
            'molecule_properties__updated_on__gte': last_date,
            'limit': 1000,
            'offset': 0
        }

        new_records = []
        updated_records = []

        async for batch in self.paginate(url, params):
            for mol in batch['molecules']:
                chembl_id = mol['molecule_chembl_id']

                # Check if exists locally
                exists = await self.check_exists(chembl_id)
                record_hash = self.compute_hash(mol)

                if not exists:
                    new_records.append(mol)
                elif await self.hash_changed(chembl_id, record_hash):
                    updated_records.append(mol)

        return ChangeSet(
            new=new_records,
            updated=updated_records,
            latest_timestamp=datetime.utcnow().isoformat()
        )

    def compute_hash(self, record: dict) -> str:
        """Compute SHA256 hash of record for change detection."""
        # Exclude volatile fields
        stable_fields = {k: v for k, v in record.items()
                        if k not in ['_links', 'updated_on']}
        return hashlib.sha256(
            json.dumps(stable_fields, sort_keys=True).encode()
        ).hexdigest()
```

### Scheduling & Orchestration

#### Cron Schedule

```yaml
# kubernetes/cronjobs/auto-data-loader.yaml

apiVersion: batch/v1
kind: CronJob
metadata:
  name: auto-data-loader
spec:
  schedule: "0 2 * * *"  # Daily at 02:00 UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: loader
            image: dk-data-platform:latest
            command: ["python", "-m", "services.data_loading.auto_loader"]
            env:
            - name: SOURCES_TO_SYNC
              value: "chembl,drugbank,openfda_labels,openfda_faers,clinicaltrials,pubchem,uniprot,pdb"
            - name: BATCH_SIZE
              value: "1000"
            - name: MAX_RECORDS_PER_RUN
              value: "100000"
```

#### Source-Specific Schedules (Tiered Freshness Policy)

Data freshness is tiered based on update frequency and business criticality:

**Tier 1 - Daily Refresh** (Clinical & Regulatory - changes frequently, high business impact)

| Source | Schedule | Max Staleness | Typical Volume |
|--------|----------|---------------|----------------|
| **ClinicalTrials.gov** | Daily 02:00 UTC | 24 hours | ~500/day |
| **OpenFDA Labels** | Daily 03:00 UTC | 24 hours | ~100/day |

**Tier 2 - Weekly Refresh** (Safety Data - moderate update frequency)

| Source | Schedule | Max Staleness | Typical Volume |
|--------|----------|---------------|----------------|
| **OpenFDA FAERS** | Weekly (Sunday 02:00 UTC) | 7 days | ~50K/quarter |
| **PDB** | Weekly (Saturday 02:00 UTC) | 7 days | ~200/week |
| **PubChem** | Weekly (Saturday 04:00 UTC) | 7 days | Variable |

**Tier 3 - Monthly Refresh** (Reference Data - stable, curated sources)

| Source | Schedule | Max Staleness | Typical Volume |
|--------|----------|---------------|----------------|
| **ChEMBL** | Monthly (1st Sunday 02:00 UTC) | 30 days | ~10K/month |
| **DrugBank** | Monthly (1st Sunday 04:00 UTC) | 30 days | ~100/release |
| **UniProt** | Monthly (1st Sunday 06:00 UTC) | 30 days | ~5K/month |
| **BindingDB** | Monthly (1st Sunday 08:00 UTC) | 30 days | ~20K/month |

### Data Quality Checks Post-Load

```python
# src/services/data_loading/quality_checks.py

async def run_post_load_checks(source: str, loaded_ids: List[str]):
    """Run quality checks after data load."""

    checks = [
        # 1. InChI Key validity
        ("inchi_key_valid", """
            SELECT COUNT(*) FROM bronze.{source}
            WHERE id = ANY($1) AND inchi_key !~ '^[A-Z]{14}-[A-Z]{10}-[A-Z]$'
        """),

        # 2. Required fields populated
        ("required_fields", """
            SELECT COUNT(*) FROM bronze.{source}
            WHERE id = ANY($1) AND (
                {primary_id} IS NULL OR
                inchi_key IS NULL
            )
        """),

        # 3. Entity resolution success
        ("entity_resolved", """
            SELECT COUNT(*) FROM bronze.{source} b
            LEFT JOIN silver.compound_cross_reference cr
                ON cr.source = '{source}' AND cr.source_id = b.{primary_id}
            WHERE b.id = ANY($1) AND cr.molecule_id IS NULL
        """),

        # 4. No duplicate source IDs
        ("no_duplicates", """
            SELECT {primary_id}, COUNT(*)
            FROM bronze.{source}
            WHERE id = ANY($1)
            GROUP BY {primary_id}
            HAVING COUNT(*) > 1
        """),
    ]

    issues = []
    for check_name, query in checks:
        result = await db.fetchval(query.format(source=source), loaded_ids)
        if result > 0:
            issues.append(DataQualityIssue(
                source=source,
                check=check_name,
                count=result,
                loaded_ids=loaded_ids
            ))

    if issues:
        await log_quality_issues(issues)
        await alert_data_quality_team(issues)

    return len(issues) == 0
```

### Monitoring & Alerting

#### Metrics to Track

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `data_loader_records_loaded` | Records loaded per source per run | N/A (info) |
| `data_loader_new_records` | New records discovered | N/A (info) |
| `data_loader_updated_records` | Updated records detected | N/A (info) |
| `data_loader_duration_seconds` | Time taken per source | > 3600s (1 hour) |
| `data_loader_errors` | Errors during loading | > 0 |
| `entity_resolution_unlinked` | Records that couldn't be linked | > 5% of batch |
| `data_quality_issues` | Quality check failures | > 0 |

#### Alert Configuration

```yaml
# alertmanager/rules/data-loader.yaml

groups:
- name: data-loader-alerts
  rules:
  - alert: DataLoaderFailed
    expr: data_loader_errors > 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Data loader failed for {{ $labels.source }}"

  - alert: EntityResolutionLowRate
    expr: entity_resolution_unlinked / data_loader_records_loaded > 0.05
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "Entity resolution success rate below 95% for {{ $labels.source }}"

  - alert: DataLoaderSlow
    expr: data_loader_duration_seconds > 3600
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Data loader taking >1 hour for {{ $labels.source }}"
```

### Success Criteria for Automatic Loading

| Metric | Target | Measurement |
|--------|--------|-------------|
| **SC-AUTO01** | New records loaded within 24h of availability | Timestamp comparison |
| **SC-AUTO02** | Entity resolution success rate >95% | Unlinked / Total |
| **SC-AUTO03** | Zero data quality issues per run | Quality check results |
| **SC-AUTO04** | All source IDs unique per source | Duplicate check |
| **SC-AUTO05** | InChI Key present for all small molecules | NULL count |
| **SC-AUTO06** | Cross-reference table updated for all new records | Join verification |
| **SC-AUTO07** | Silver/Gold pipelines complete within 4h of Bronze load | Pipeline timing |
| **SC-AUTO08** | No loader failures for 7 consecutive days | Error count = 0 |
