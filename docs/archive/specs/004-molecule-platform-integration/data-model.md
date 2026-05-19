# Data Model: Molecule Platform Integration

**Feature**: 004-molecule-platform-integration
**Date**: 2026-01-28

## Schema Organization

```
PostgreSQL: dk_data
├── raw          (existing — TAVR CMS raw data)
├── staging      (existing — TAVR processing)
├── mart         (existing — TAVR analytics)
├── scoring      (existing — TAVR scoring)
├── meta         (existing — pipeline metadata, shared)
├── api          (existing — PostgREST views for TAVR)
├── mol_raw      (NEW — unmodified API response archive)
├── mol_bronze   (NEW — typed source-native columns)
├── mol_silver   (NEW — entity-resolved normalized data)
├── mol_gold     (NEW — pre-computed analytics)
├── mol_app      (NEW — user-facing application features)
└── mol_api      (NEW — PostgREST views for molecule data)
```

## Entity Relationship Diagram

```
mol_raw.{source}                mol_bronze.{source}
┌──────────────────┐           ┌──────────────────────┐
│ id (UUID PK)     │──1:1───►  │ id (UUID PK)         │
│ request_id       │           │ raw_id (FK)          │
│ response_body    │           │ {source-native cols} │
│ response_hash    │           │ record_hash          │
│ processed_to_    │           │ processed_to_silver  │
│   bronze (bool)  │           │ ingested_at          │
│ ingested_at      │           └──────────┬───────────┘
└──────────────────┘                      │
                                          │ N:1
                                          ▼
                              ┌──────────────────────┐
                              │ mol_silver.molecules  │
                              │ (canonical entity)    │
                              ├──────────────────────┤
                              │ id (UUID PK)         │
                              │ inchi_key (UNIQUE)    │
                              │ canonical_name        │
                              │ canonical_smiles      │
                              │ molecular_formula     │
                              │ molecular_weight      │
                              │ molecule_type         │
                              │ development_status    │
                              │ max_phase             │
                              │ needs_review (bool)   │
                              │ created_at            │
                              │ updated_at            │
                              └────────┬─────────────┘
                                       │ 1:N
                    ┌──────────────────┼──────────────────┐
                    │                  │                   │
                    ▼                  ▼                   ▼
    ┌───────────────────┐ ┌────────────────────┐ ┌────────────────────┐
    │ mol_silver.        │ │ mol_silver.         │ │ mol_silver.         │
    │ identifier_        │ │ clinical_trials     │ │ adverse_events      │
    │ mappings           │ ├────────────────────┤ ├────────────────────┤
    ├───────────────────┤ │ id (UUID PK)        │ │ id (UUID PK)        │
    │ id (UUID PK)      │ │ molecule_id (FK)    │ │ molecule_id (FK)    │
    │ molecule_id (FK)  │ │ nct_id              │ │ report_id           │
    │ identifier_type   │ │ phase               │ │ event_type          │
    │ identifier_value  │ │ status              │ │ seriousness         │
    │ source            │ │ enrollment_count    │ │ outcome             │
    │ confidence (0-1)  │ │ ...                 │ │ ...                 │
    └───────────────────┘ └────────────────────┘ └────────────────────┘
                                       │
                                       │ aggregated into
                                       ▼
                    ┌──────────────────────────────────┐
                    │ mol_gold.molecule_profile         │
                    ├──────────────────────────────────┤
                    │ profile_id (UUID PK)              │
                    │ molecule_id (FK → silver.molecules)│
                    │ lifecycle_stage                    │
                    │ data_complete (bool)               │
                    │ clinical_trial_count               │
                    │ safety_events_count                │
                    │ fda_approval_date                  │
                    │ last_updated                       │
                    └──────────────────────────────────┘
```

## Raw Layer (mol_raw)

One table per data source. All share a common structure:

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Auto-generated |
| request_id | VARCHAR(100) | Unique request tracking |
| request_timestamp | TIMESTAMPTZ | When request was made |
| api_endpoint | VARCHAR(500) | Source URL |
| response_status | INTEGER | HTTP status code |
| response_body | JSONB | Complete unmodified response |
| response_body_hash | VARCHAR(64) | SHA-256 for dedup |
| processed_to_bronze | BOOLEAN | Processing flag |
| ingested_at | TIMESTAMPTZ | When stored |
| source_id | VARCHAR(50) | Source identifier |

**Tables** (core 5): `mol_raw.clinicaltrials`, `mol_raw.openfda_labels`, `mol_raw.openfda_faers`, `mol_raw.chembl`, `mol_raw.pubchem`

## Bronze Layer (mol_bronze)

Source-native typed columns. Schema varies per source. Example for ClinicalTrials.gov:

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Auto-generated |
| raw_id | UUID FK | Reference to mol_raw entry |
| nct_id | VARCHAR(15) UNIQUE | ClinicalTrials identifier |
| brief_title | TEXT | Study title |
| phase | VARCHAR(20) | Phase 1/2/3/4/N/A |
| overall_status | VARCHAR(50) | Recruiting, Completed, etc. |
| lead_sponsor_name | VARCHAR(500) | Sponsor organization |
| enrollment_count | INTEGER | Participant count |
| conditions | JSONB | Array of conditions studied |
| interventions | JSONB | Array of interventions |
| record_hash | VARCHAR(64) | Content hash for dedup |
| processed_to_silver | BOOLEAN | Processing flag |
| ingested_at | TIMESTAMPTZ | When stored |

## Silver Layer (mol_silver)

### molecules (master entity)

| Column | Type | Constraint | Description |
|--------|------|-----------|-------------|
| id | UUID | PK | Canonical molecule ID |
| inchi_key | VARCHAR(27) | UNIQUE | Structural identifier (master key) |
| canonical_name | VARCHAR(500) | NOT NULL | Preferred name |
| canonical_smiles | TEXT | | Structural representation |
| molecular_formula | VARCHAR(200) | | Chemical formula |
| molecular_weight | NUMERIC(12,4) | | Daltons |
| molecule_type | VARCHAR(50) | | small_molecule, protein, antibody, peptide |
| development_status | VARCHAR(50) | | preclinical, phase_1, phase_2, phase_3, approved |
| max_phase | INTEGER | | Highest clinical phase reached |
| needs_review | BOOLEAN | DEFAULT FALSE | Flagged if confidence < 0.80 |
| created_at | TIMESTAMPTZ | | |
| updated_at | TIMESTAMPTZ | | |

### identifier_mappings

| Column | Type | Constraint | Description |
|--------|------|-----------|-------------|
| id | UUID | PK | |
| molecule_id | UUID | FK → molecules | |
| identifier_type | VARCHAR(50) | NOT NULL | inchikey, smiles, cas, chembl_id, pubchem_cid, drugbank_id, drug_name, unii |
| identifier_value | VARCHAR(500) | NOT NULL | |
| source | VARCHAR(50) | NOT NULL | Origin source |
| confidence | DECIMAL(3,2) | | 0.00–1.00 |
| created_at | TIMESTAMPTZ | | |

**Index**: UNIQUE(molecule_id, identifier_type, identifier_value, source)

### Additional silver tables

- `clinical_trials` — normalized trial data linked to molecule_id
- `drug_labels` — FDA label information linked to molecule_id
- `adverse_events` — FAERS data linked to molecule_id
- `bioactivity` — ChEMBL assay data linked to molecule_id
- `targets` — protein targets linked to molecule_id
- `publications` — literature references linked to molecule_id
- `patents` — patent data linked to molecule_id

## Gold Layer (mol_gold)

Pre-computed aggregations as materialized views:

- `molecule_profile` — comprehensive molecule summary (properties, phase, approval status, counts)
- `competitive_landscape` — molecules grouped by indication with competitive analysis
- `safety_signals` — adverse event aggregation with proportional reporting ratios (PRR/ROR)
- `lifecycle_stages` — evidence roll-up for lifecycle stage validation

## Application Layer (mol_app)

User-facing features:

- `user_tracked_molecules` — portfolio tracking (user_id, molecule_id, indication, lifecycle_stage)
- `user_annotations` — notes and comments per molecule
- `alert_configs` — alert subscriptions (molecule, condition, channel)
- `audit_log` — compliance audit trail
- `onboarding_queue` — async molecule ingestion requests
- `resolution_queue` — low-confidence matches pending review

## Meta Layer (meta — shared)

Already exists, extended with:

- `data_sources` — registered source configurations (name, url, tier, enabled, credentials_ref)
- `sync_state` — last sync timestamps per source per layer
- `pipeline_runs` — pipeline execution history

## Validation Rules

- **Molecule.inchi_key**: 27-character string, format `XXXXXXXXXXXXXX-XXXXXXXXXX-X`
- **Identifier Mapping.confidence**: 0.00–1.00, records < 0.80 trigger `needs_review` on parent molecule
- **Raw Record.response_body_hash**: SHA-256 of response body; duplicate hashes are skipped during ingestion
- **Bronze Record.record_hash**: SHA-256 of typed columns; used for change detection
- **Development Status**: enum of `preclinical`, `phase_1`, `phase_2`, `phase_3`, `approved`, `withdrawn`

## State Transitions

### Molecule Processing State

```
Raw Record:    ingested → processed_to_bronze=TRUE
Bronze Record: ingested → processed_to_silver=TRUE
Silver Record: created → needs_review=TRUE (if confidence < 0.80)
                      → needs_review=FALSE (auto-linked or manually approved)
Gold Aggregate: computed → refreshed (on next aggregation run)
```

### Molecule Development Status

```
preclinical → phase_1 → phase_2 → phase_3 → approved
                                           → withdrawn (at any phase)
```

Status is derived from the highest phase observed across all linked clinical trial records.
