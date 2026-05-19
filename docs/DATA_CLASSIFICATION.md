# Data Classification Policy

This document defines the data classification scheme, retention policies, and purge
strategies for the dk-data pharmaceutical analytics platform.

## Classification Tiers

The platform uses a four-tier classification scheme applied at the table level.
Classifications are stored in `meta.data_classification` and enforced by the
retention purge system.

| Tier           | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| **Public**     | Open-source or freely available datasets. No access restrictions.           |
| **Internal**   | Competitive intelligence and aggregated research data. Internal use only.   |
| **PII**        | Contains personally identifiable information (researcher profiles, names).  |
| **Confidential** | Proprietary scoring, financial, and hospital-level business data.         |

## Schema-Level Breakdown

### Public

| Schema       | Tables                | Notes                                     |
|--------------|-----------------------|-------------------------------------------|
| `mol_raw`    | bindingdb, chembl, clinicaltrials, cochrane_reviews, drugbank, ema, epo_patents, euipo_trademarks, hta_decisions, journal_rss, medical_news, openalex_ci, openfda_faers, openfda_labels, orange_book, pdb, pubchem, pubmed, sec_edgar, sider, uniprot, uspto_ci, uspto_patents, uspto_trademarks, who_icd | Open regulatory and molecular databases |
| `mol_raw`    | kegg_drug, pharmgkb, rxnorm, tdc_admet, who_inn, euipo_designs | Drug vocabulary and pharmacology |
| `mol_bronze` | * (all tables)        | Deduplicated, typed molecule data         |
| `mol_silver` | molecules, clinical_trials, adverse_events, publications, patents, trademarks, drug_labels, bioactivity, binding_affinities, side_effects, regulatory_decisions, molecule_aliases, identifier_mappings, hcpcs_molecule_bridge, ndc_molecule_bridge | Conformed molecule data |
| `mol_gold`   | * (all tables)        | Curated molecule analytics                |
| `hcs_raw`    | acc_tvc_certification, cms_cost_reports, cms_hospital_info, cms_medicare_inpatient, cms_geographic_variation, hrsa_shortage_areas | Open CMS / HRSA facility data |
| `hcs_bronze` | * (all tables)        | Deduplicated CMS facility data            |
| `hcs_silver` | drug_utilization, part_d_prescribing, open_payments_drug_linkage | Drug spend and prescribing (aggregated, no patient PII) |

### Internal

| Schema | Tables                | Notes                                     |
|--------|-----------------------|-------------------------------------------|
| `mol_raw` | nih_reporter, europepmc | CI pipeline sources — aggregated research |
| `hcs_raw` | cms_care_compare, cms_chow, cms_formulary, cms_hospital_quality, cms_magnet, cms_pecos | Provider intelligence — internal use only |

### PII

| Schema | Tables | Notes                                          |
|--------|--------|------------------------------------------------|
| `mol_raw` | orcid | Researcher profiles with names and affiliations |

### Confidential

| Schema    | Tables                | Notes                             |
|-----------|-----------------------|------------------------------------|
| `hcs_silver` | provider_profile   | Aggregated NPI-level provider data |
| `xenon`   | * (all tables)        | Proprietary scoring / enrichment   |

## PII Field Inventory

The following columns in `mol_raw.orcid` contain personally identifiable information:

| Table           | Column                | Data Type    | Example                    |
|-----------------|-----------------------|--------------|----------------------------|
| mol_raw.orcid   | given_names           | VARCHAR(255) | "Jane"                     |
| mol_raw.orcid   | family_name           | VARCHAR(255) | "Smith"                    |
| mol_raw.orcid   | credit_name           | VARCHAR(500) | "J. Smith, PhD"            |
| mol_raw.orcid   | biography             | TEXT         | "Professor of Chemistry..."  |
| mol_raw.orcid   | current_affiliations  | JSONB        | [{"name": "MIT", ...}]    |
| mol_raw.orcid   | external_ids          | JSONB        | [{"type": "Scopus", ...}] |

## Retention Periods

| Classification | Retention     | Rationale                                                   |
|----------------|---------------|-------------------------------------------------------------|
| Public         | Perpetual     | Open data with no expiration requirements                   |
| Internal       | 730 days      | CI data refreshed regularly; older records lose relevance   |
| PII            | 365 days      | Minimise PII exposure; profiles refresh from ORCID weekly   |
| Confidential   | 730 days      | Business data retained for 2-year rolling analysis window   |

## Purge Strategy

### Rolling Window (`rolling_window`)

Used by: Internal, PII, Confidential tables.

Records older than the configured `retention_days` are deleted in batches of 1,000.
The timestamp column used for age comparison varies by schema:

- `raw.*` tables: `fetched_at`
- `meta.*` tables: `_logged_at`
- All other schemas: `created_at`

The purge runs via the CLI:

```bash
# Dry run -- see what would be purged without deleting
python -m dk_data.scripts.purge_history --all-tables --dry-run

# Execute purge across all governed tables
python -m dk_data.scripts.purge_history --all-tables --force
```

Each purge operation is logged to `meta.refresh_log` for auditability.

The timestamp column used for age comparison:

- `mol_raw.*` / `hcs_raw.*` tables: `ingested_at`
- `meta.*` tables: `_logged_at`
- All other schemas: `created_at`

### Perpetual (`perpetual`)

Used by: Public tables, molecule medallion schemas.

No automated purge. Data is retained indefinitely. These are open-source datasets
that serve as the foundation of the molecule discovery pipeline.

### Archive Then Purge (`archive_then_purge`)

Reserved for future use. Intended for tables that should be archived to cold storage
(e.g., MinIO/S3) before deletion. Not currently implemented.

## Querying Classification Data

Classification data is available via the PostgREST API:

```bash
# List all classified tables
curl https://data.preview.behaviorlabs.ai/data_classification

# Filter by classification tier
curl "https://data.preview.behaviorlabs.ai/data_classification?classification=eq.pii"

# Find tables with retention policies
curl "https://data.preview.behaviorlabs.ai/data_classification?retention_days=not.is.null"
```

## Governance

- Classifications are seeded by migration `069_data_classification.sql`
- New tables should be classified when their migration is created
- PII tables must be reviewed quarterly for compliance
- The `classified_by` column tracks who last reviewed each classification
- The `api.data_classification` view exposes classification data to the API layer
