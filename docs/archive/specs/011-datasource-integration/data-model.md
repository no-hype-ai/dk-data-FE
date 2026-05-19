# Data Model: Data Source Integration

**Feature**: 011-datasource-integration
**Date**: 2026-02-14

## Entity Overview

```
meta.data_sources ←──── meta.batch_jobs (via source_ids array)
       │                       │
       │                       ├──── meta.batch_job_runs
       │                       │
       ▼                       ▼
meta.table_health        k8s CronJob manifests
       │
       ▼
meta.ci_search_terms (new) ←── query-scoped CI fetchers read from here

raw.* tables (CI sources, TAVR sources)
mol_raw.* tables (molecule sources — existing)
```

## Existing Entities (No Schema Changes)

### meta.data_sources
Already exists. New rows added via seed SQL for all 33 sources.

| Column | Type | Description |
|--------|------|-------------|
| source_id | SERIAL PK | Auto-generated ID |
| source_name | VARCHAR(100) UNIQUE | Snake_case identifier |
| source_type | VARCHAR(20) | `api`, `csv`, `scrape` |
| source_url | TEXT | Base API URL |
| description | TEXT | Human-readable description |
| refresh_frequency | VARCHAR(20) | `daily`, `weekly`, `monthly`, `quarterly`, `annual` |
| is_active | BOOLEAN | Whether source is enabled |
| topic_tags | TEXT[] | Semantic tags for discovery |
| column_descriptions | JSONB | Per-column metadata |
| staleness_threshold_hours | INTEGER | Hours before "stale" |
| ai_description | TEXT | AI-optimized description |
| target_tables | TEXT[] | Downstream tables |

### meta.batch_jobs
Already exists. New rows added for CI CronJobs.

### meta.batch_job_runs
Already exists. No changes needed — CI fetchers log runs here.

### meta.table_health
Already exists. Catalog refresh populates health records.

### mol_raw.* tables
Already exist for Tier 1 sources. Tier 2A/3 sources write to these tables via `RawIngestionService.fetch_and_store()`. Tables are created by migrations 028/029. No new DDL needed for molecule sources.

**Existing mol_raw tables** (used by Tier 2A/3):
- `mol_raw.clinicaltrials`, `mol_raw.openfda_labels`, `mol_raw.openfda_faers`
- `mol_raw.chembl`, `mol_raw.pubchem`, `mol_raw.uniprot`, `mol_raw.openalex`
- `mol_raw.drugbank`, `mol_raw.sider`

**Note**: Some Tier 2A/3 sources (BindingDB, Orange Book, TDC ADMET, KEGG, TTD, PharmGKB, IMGT, CDC Vaccines, RxNorm, DailyMed, FDA Drugs, EMA) may need `mol_raw.*` tables created if they don't already exist. Check migration 028 during implementation — if missing, add to a new migration.

## New Entity: meta.ci_search_terms

Stores configurable search terms for query-scoped CI fetchers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| term_id | SERIAL | PK | Auto-generated ID |
| term_type | VARCHAR(50) | NOT NULL | `drug_name`, `therapeutic_area`, `mesh_term`, `company`, `indication` |
| term_value | VARCHAR(255) | NOT NULL | The search term value |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE | Whether term is used in queries |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | When term was added |
| | | UNIQUE(term_type, term_value) | Deduplication |

**Used by**: HTA body fetcher, USPTO CI fetcher, Cochrane fetcher, Journal RSS fetcher (for filtering), EPO OPS fetcher, medical news fetcher, SEC EDGAR fetcher.

**Not used by**: PubMed (broad ingest), OpenAlex CI (broad ingest), EMA Regulatory (fetches all decisions).

## New Entities: CI Source Raw Tables

Each Tier 4 CI source gets a raw table in the `raw` schema following the standard audit column pattern.

### raw.pubmed

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| pmid | VARCHAR(20) | NOT NULL, UNIQUE | PubMed ID (natural key) |
| title | TEXT | | Article title |
| abstract | TEXT | | Article abstract |
| authors | JSONB | | Author list with affiliations |
| journal | VARCHAR(500) | | Journal name |
| publication_date | DATE | | Publication date |
| mesh_terms | TEXT[] | | MeSH descriptor terms |
| doi | VARCHAR(100) | | Digital Object Identifier |
| publication_types | TEXT[] | | Article types (review, clinical trial, etc.) |
| keywords | TEXT[] | | Author-provided keywords |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | Audit: load timestamp |
| _source_file | VARCHAR(500) | | Audit: source identifier |
| _source_hash | VARCHAR(64) | | Audit: content hash |

### raw.openalex_ci

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| work_id | VARCHAR(50) | NOT NULL, UNIQUE | OpenAlex work ID (natural key) |
| doi | VARCHAR(100) | | DOI |
| title | TEXT | | Work title |
| abstract | TEXT | | Abstract (inverted index decoded) |
| publication_date | DATE | | Publication date |
| cited_by_count | INTEGER | | Citation count |
| concepts | JSONB | | Concept tags with scores |
| authorships | JSONB | | Authors with institutions |
| primary_location | JSONB | | Journal/venue info |
| open_access | JSONB | | OA status and URL |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.ema_regulatory

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| document_id | VARCHAR(100) | NOT NULL, UNIQUE | EMA document ID (natural key) |
| document_type | VARCHAR(50) | | `chmp_opinion`, `epar`, `referral`, `safety_signal` |
| product_name | VARCHAR(500) | | Drug/product name |
| active_substance | VARCHAR(500) | | Active substance (INN) |
| therapeutic_area | VARCHAR(500) | | Therapeutic area classification |
| decision_date | DATE | | Date of regulatory decision |
| decision_type | VARCHAR(100) | | `positive`, `negative`, `withdrawal`, `variation` |
| document_url | TEXT | | Link to full document |
| summary | TEXT | | Decision summary |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.journal_rss

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| article_id | VARCHAR(255) | NOT NULL, UNIQUE | DOI or article URL (natural key) |
| feed_source | VARCHAR(100) | NOT NULL | Journal name (NEJM, Lancet, etc.) |
| title | TEXT | | Article title |
| authors | TEXT | | Author string |
| abstract | TEXT | | Abstract if available |
| publication_date | DATE | | Publication date |
| link | TEXT | | Article URL |
| doi | VARCHAR(100) | | DOI if available |
| categories | TEXT[] | | RSS categories/tags |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.uspto_ci

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| patent_id | VARCHAR(50) | NOT NULL, UNIQUE | Patent number (natural key) |
| title | TEXT | | Patent title |
| abstract | TEXT | | Patent abstract |
| inventors | JSONB | | Inventor names and locations |
| assignees | JSONB | | Assignee organizations |
| filing_date | DATE | | Filing date |
| grant_date | DATE | | Grant date |
| cpc_codes | TEXT[] | | CPC classification codes |
| claims_count | INTEGER | | Number of claims |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.hta_decisions

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| decision_id | VARCHAR(100) | NOT NULL, UNIQUE | Agency-specific ID (natural key) |
| agency | VARCHAR(50) | NOT NULL | `nice`, `gba`, `has`, `pbac` |
| drug_name | VARCHAR(500) | | Drug name |
| indication | TEXT | | Therapeutic indication |
| decision_type | VARCHAR(100) | | `recommended`, `not_recommended`, `restricted`, `optimised` |
| decision_date | DATE | | Decision date |
| document_url | TEXT | | Link to full appraisal |
| summary | TEXT | | Decision summary |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.epo_patents

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| publication_id | VARCHAR(50) | NOT NULL, UNIQUE | EPO publication number (natural key) |
| title | TEXT | | Patent title |
| abstract | TEXT | | Patent abstract |
| applicants | JSONB | | Applicant organizations |
| inventors | JSONB | | Inventor names |
| filing_date | DATE | | Filing date |
| publication_date | DATE | | Publication date |
| ipc_codes | TEXT[] | | IPC classification codes |
| family_id | VARCHAR(50) | | Patent family ID |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.cochrane_reviews

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| review_id | VARCHAR(100) | NOT NULL, UNIQUE | Cochrane review ID (natural key) |
| title | TEXT | | Review title |
| authors | TEXT | | Author string |
| abstract | TEXT | | Plain language summary |
| publication_date | DATE | | Publication/update date |
| review_type | VARCHAR(50) | | `systematic_review`, `nma`, `clinical_answer` |
| interventions | TEXT[] | | Interventions compared |
| conditions | TEXT[] | | Health conditions covered |
| conclusions | TEXT | | Authors' conclusions |
| doi | VARCHAR(100) | | DOI |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.medical_news

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| article_id | VARCHAR(255) | NOT NULL, UNIQUE | URL or source-specific ID (natural key) |
| source_name | VARCHAR(100) | NOT NULL | `medscape`, `healio`, `fiercepharma`, etc. |
| title | TEXT | | Headline |
| summary | TEXT | | Article summary/excerpt |
| publication_date | DATE | | Publication date |
| url | TEXT | | Article URL |
| drug_mentions | TEXT[] | | Extracted drug names |
| therapeutic_areas | TEXT[] | | Extracted therapeutic areas |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

### raw.sec_edgar

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| accession_number | VARCHAR(50) | NOT NULL, UNIQUE | SEC accession number (natural key) |
| company_name | VARCHAR(500) | | Company name |
| cik | VARCHAR(20) | | SEC CIK number |
| filing_type | VARCHAR(20) | NOT NULL | `10-K`, `10-Q`, `8-K` |
| filing_date | DATE | | Filing date |
| document_url | TEXT | | EDGAR document URL |
| description | TEXT | | Filing description |
| _loaded_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| _source_file | VARCHAR(500) | | |
| _source_hash | VARCHAR(64) | | |

## Validation Rules

### Common Rules (all CI sources)
- Natural key field is NOT NULL and UNIQUE (deduplication)
- `_loaded_at` defaults to NOW(), never NULL
- `_source_hash` is SHA-256 of response content
- Text fields trimmed of leading/trailing whitespace
- Date fields validated as proper dates (not future dates for historical data)

### Source-Specific Rules
- **PubMed**: PMID must be numeric string; MeSH terms validated against known descriptors
- **OpenAlex CI**: work_id must start with `W`; cited_by_count >= 0
- **EMA Regulatory**: decision_type must be one of known enum values
- **Journal RSS**: article_id is DOI (preferred) or URL; feed_source must match configured feeds
- **SEC EDGAR**: filing_type must be `10-K`, `10-Q`, or `8-K`; CIK is numeric
- **HTA Decisions**: agency must be one of `nice`, `gba`, `has`, `pbac`

## Relationships

- Each `raw.*` CI table → one `meta.data_sources` entry (via source_name)
- Each CI CronJob → one `meta.batch_jobs` entry (via job_name)
- Each `meta.batch_jobs` → one or more `meta.data_sources` (via source_ids array)
- Query-scoped CI fetchers → read from `meta.ci_search_terms` at fetch time
- Molecule sources → write to existing `mol_raw.*` tables (no new tables needed for most)
