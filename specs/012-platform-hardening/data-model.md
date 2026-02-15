# Data Model: Platform Hardening

## New Tables

### mol_gold.company_pipeline

Tracks pharmaceutical company drug development pipelines for competitive landscape analysis.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default gen | Row identifier |
| company_name | VARCHAR(255) | NOT NULL | Pharmaceutical company name |
| molecule_name | VARCHAR(255) | NOT NULL | Drug/molecule name |
| molecule_id | UUID | FK → mol_gold.molecule_profiles | Link to molecule if known |
| indication | VARCHAR(500) | | Therapeutic indication |
| phase | VARCHAR(50) | NOT NULL | Development phase (Preclinical, Phase I, II, III, Approved, Withdrawn) |
| status | VARCHAR(50) | DEFAULT 'Active' | Pipeline status (Active, Suspended, Terminated) |
| mechanism_of_action | VARCHAR(500) | | MOA description |
| source | VARCHAR(100) | | Data source identifier |
| last_updated | TIMESTAMPTZ | DEFAULT NOW() | Last data refresh |
| ingested_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Unique constraint**: (company_name, molecule_name, indication)
**Index**: company_name, phase

### mol_gold.trial_publication_features

Links clinical trials to their related publications for cross-referencing.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default gen | Row identifier |
| nct_id | VARCHAR(20) | NOT NULL | ClinicalTrials.gov NCT identifier |
| publication_doi | VARCHAR(255) | | DOI of linked publication |
| publication_pmid | VARCHAR(20) | | PubMed ID of linked publication |
| overlap_score | NUMERIC(5,4) | CHECK 0-1 | Similarity score between trial and publication |
| feature_type | VARCHAR(50) | NOT NULL | Type of linkage (author_overlap, title_similarity, endpoint_match) |
| trial_title | TEXT | | Trial title for display |
| publication_title | TEXT | | Publication title for display |
| source | VARCHAR(100) | | Data source identifier |
| ingested_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Unique constraint**: (nct_id, publication_doi, feature_type)
**Index**: nct_id, publication_doi

### mol_silver.targets

Drug target information linking molecules to their biological targets.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default gen | Row identifier |
| target_name | VARCHAR(255) | NOT NULL | Target protein/gene name |
| target_type | VARCHAR(50) | NOT NULL | Type (protein, gene, enzyme, receptor, ion_channel) |
| uniprot_accession | VARCHAR(20) | | UniProt accession for protein targets |
| gene_symbol | VARCHAR(50) | | HGNC gene symbol |
| organism | VARCHAR(100) | DEFAULT 'Homo sapiens' | Target organism |
| molecule_id | UUID | FK → mol_gold.molecule_profiles | Linked molecule |
| molecule_name | VARCHAR(255) | | Molecule name for display |
| action_type | VARCHAR(50) | | Pharmacological action (inhibitor, agonist, antagonist, etc.) |
| binding_affinity | NUMERIC(12,4) | | Binding affinity (nM) |
| source | VARCHAR(100) | | Data source (ChEMBL, BindingDB, UniProt) |
| ingested_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Unique constraint**: (target_name, molecule_name, source)
**Index**: uniprot_accession, gene_symbol, molecule_id

### raw.orcid (new for ORCID data source)

Raw ORCID researcher data from the public API.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default gen | Row identifier |
| orcid_id | VARCHAR(30) | NOT NULL, UNIQUE | ORCID iD (format: 0000-0000-0000-000X) |
| given_names | VARCHAR(255) | | First/given names |
| family_name | VARCHAR(255) | | Last/family name |
| credit_name | VARCHAR(500) | | Preferred display name |
| biography | TEXT | | Researcher biography |
| keywords | JSONB | | Research keywords array |
| current_affiliations | JSONB | | Current employment/affiliations |
| works_count | INTEGER | | Total publication count |
| external_ids | JSONB | | Scopus, ResearcherID, etc. |
| raw_response | JSONB | | Full API response for reprocessing |
| fetched_at | TIMESTAMPTZ | DEFAULT NOW() | When data was fetched |
| ingested_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Index**: orcid_id, family_name

## Existing Tables (referenced by new API views)

### bronze.sider (exists in migration 030)
Side effect data — already has columns for drug, side_effect, meddra_id, frequency, source.

### silver.bioactivity (exists in migration 031)
Bioactivity assay data — has molecule_id, target, activity_type, activity_value, source.

### silver.patents (exists in migration 031)
Patent data — has patent_number, title, assignee, filing_date, expiration_date, molecule_id.

### mol_gold.competitive_landscape (exists in migration 020)
Already complete with API view.

### mol_gold.molecule_profiles (exists in migration 020)
Already complete with API view.

## New API Views

| View Name | Source Table(s) | Schema |
|-----------|----------------|--------|
| api.company_pipeline | mol_gold.company_pipeline | New table + new view |
| api.trial_publication_features | mol_gold.trial_publication_features | New table + new view |
| api.molecule_targets | mol_silver.targets | New table + new view |
| api.sider_side_effects | bronze.sider | Existing table + new view |
| api.bioactivity | silver.bioactivity | Existing table + new view |
| api.patents | silver.patents | Existing table → update placeholder view |

## Entity Relationships

```
mol_gold.molecule_profiles
  ├── mol_gold.company_pipeline (molecule_id FK)
  ├── mol_silver.targets (molecule_id FK)
  ├── silver.patents (molecule_id FK)
  └── silver.bioactivity (molecule_id FK)

mol_gold.trial_publication_features
  └── standalone (links nct_id ↔ publication DOI/PMID)

bronze.sider
  └── standalone (drug name → side effects)

raw.orcid
  └── standalone (researcher profiles)
```
