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
| `raw`        | bindingdb, orange_book, sider, tdc_admet, ema, rxnorm, dailymed, fda_drugs, kegg_drug, ttd, pharmgkb, imgt, cdc_vaccines, drugbank, chembl, pubchem, uniprot, pdb, uspto_patents, epo_patents, uspto_ci | Open regulatory and molecular databases |
| `mol_raw`    | * (all tables)        | Raw molecule compound data                |
| `mol_bronze` | * (all tables)        | Deduplicated molecule data                |
| `mol_silver` | * (all tables)        | Conformed molecule data                   |
| `mol_gold`   | * (all tables)        | Curated molecule analytics                |

### Internal

| Schema | Tables                | Notes                                     |
|--------|-----------------------|-------------------------------------------|
| `raw`  | pubmed, openalex_ci, journal_rss, cochrane_reviews, medical_news, sec_edgar, hta_decisions, ema_regulatory | CI pipeline sources -- aggregated research |

### PII

| Schema | Tables | Notes                                          |
|--------|--------|------------------------------------------------|
| `raw`  | orcid  | Researcher profiles with names and affiliations |

### Confidential

| Schema    | Tables                                  | Notes                             |
|-----------|-----------------------------------------|-----------------------------------|
| `scoring` | score_history, score_latest             | Proprietary hospital scoring      |
| `mart`    | dim_hospital, fact_tavr_program, fact_financial_metrics | Analytical dimensions and facts |
| `staging` | hospitals, certifications, tavr_volumes, geographic_designations | Pre-aggregation staging data |

## PII Field Inventory

The following columns in `raw.orcid` contain personally identifiable information:

| Table      | Column                | Data Type    | Example                    |
|------------|-----------------------|--------------|----------------------------|
| raw.orcid  | given_names           | VARCHAR(255) | "Jane"                     |
| raw.orcid  | family_name           | VARCHAR(255) | "Smith"                    |
| raw.orcid  | credit_name           | VARCHAR(500) | "J. Smith, PhD"            |
| raw.orcid  | biography             | TEXT         | "Professor of Chemistry..."  |
| raw.orcid  | current_affiliations  | JSONB        | [{"name": "MIT", ...}]    |
| raw.orcid  | external_ids          | JSONB        | [{"type": "Scopus", ...}] |

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
