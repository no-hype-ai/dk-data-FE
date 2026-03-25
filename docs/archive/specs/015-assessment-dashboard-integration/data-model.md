# Data Model: Assessment Dashboard Integration

**Branch**: `015-assessment-dashboard-integration` | **Date**: 2026-02-25
**Source**: [spec.md](spec.md) key entities + [research.md](research.md) findings

## New Tables (4)

### xenon.assessment_generated

Application-layer table for AI-generated assessment content. Outside medallion pipeline (Constraint 5).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, DEFAULT gen_random_uuid() | Record identifier |
| molecule_id | UUID | NOT NULL | Reference to molecule |
| section_type | VARCHAR(50) | NOT NULL | One of 10 types (see enum below) |
| content | JSONB | NOT NULL | Generated section content |
| version | INTEGER | NOT NULL, DEFAULT 1 | Content version number |
| generation_source | VARCHAR(100) | | Agent/model that generated content |
| generation_metadata | JSONB | | Model params, prompt hash, timing |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update timestamp |

**Unique constraint**: `(molecule_id, section_type, version)` — FR-005 deduplication
**Index**: `idx_assessment_molecule_section` on `(molecule_id, section_type)`

**Section types** (10): `executive_summary`, `key_metrics`, `financial_analysis`, `hcp_segmentation`, `patient_journey`, `market_opportunity`, `dosing_administration`, `risk_assessment`, `strategic_recommendations`, `investment_thesis`

---

### xenon.publication_evidence

LLM-extracted clinical endpoint data. Outside medallion pipeline (Constraint 5). Feeds `mol_gold.trial_outcomes` via UNION.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, DEFAULT gen_random_uuid() | Record identifier |
| molecule_id | UUID | NOT NULL | Reference to molecule |
| trial_nct_id | VARCHAR(20) | | Optional NCT ID linkage |
| endpoint_name | VARCHAR(200) | NOT NULL | Clinical endpoint measured |
| endpoint_type | VARCHAR(50) | | primary, secondary, exploratory |
| hazard_ratio | NUMERIC(8,4) | | HR if applicable |
| p_value | NUMERIC(10,8) | | Statistical significance |
| response_rate | NUMERIC(5,2) | | ORR/response rate % |
| median_survival_months | NUMERIC(6,1) | | OS/PFS in months |
| sample_size | INTEGER | | Number of patients |
| confidence_score | NUMERIC(3,2) | NOT NULL, CHECK (0.0-1.0) | Extraction confidence |
| evidence_source | VARCHAR(20) | NOT NULL, DEFAULT 'publication' | Source attribution |
| doi | VARCHAR(100) | | Digital object identifier |
| pmid | VARCHAR(20) | | PubMed ID |
| extraction_metadata | JSONB | | Model, prompt, extraction timestamp |
| content_hash | VARCHAR(64) | NOT NULL | SHA-256 of key fields for dedup |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Unique constraint**: `(content_hash)` — FR-009 deduplication
**Index**: `idx_pub_evidence_molecule` on `(molecule_id)`
**Index**: `idx_pub_evidence_confidence` on `(confidence_score)` WHERE `confidence_score >= 0.40`

---

### raw.pdb_structures

Raw PDB protein structure API responses. Standard raw schema (Constraint 1).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, DEFAULT uuid_generate_v4() | Record identifier |
| request_id | VARCHAR(100) | NOT NULL | Batch/request correlation |
| request_timestamp | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | When request was made |
| api_endpoint | VARCHAR(500) | NOT NULL | PDB API URL called |
| api_version | VARCHAR(20) | | API version |
| request_params | JSONB | | Query parameters |
| request_headers | JSONB | | Request headers (sanitized) |
| response_status | INTEGER | NOT NULL | HTTP status code |
| response_headers | JSONB | | Response headers |
| response_body | JSONB | NOT NULL | Unmodified API response |
| response_body_hash | VARCHAR(64) | | SHA-256 for idempotency |
| response_size_bytes | INTEGER | | Response payload size |
| response_time_ms | INTEGER | | API response latency |
| processed_to_bronze | BOOLEAN | DEFAULT FALSE | Incremental flag |
| processed_at | TIMESTAMPTZ | | When processed |
| processing_error | TEXT | | Error if processing failed |
| ingested_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Ingestion timestamp |
| source_id | VARCHAR(50) | NOT NULL, DEFAULT 'pdb_structures' | Source identifier |

**Indexes**: `request_id`, `request_timestamp`, `processed_to_bronze`, `response_body_hash`

---

### raw.who_icd

Raw WHO ICD-10 code API responses. Standard raw schema (same structure as `raw.pdb_structures` above with `source_id = 'who_icd'`).

---

## New SQLMesh Models — Bronze (15)

All follow the existing pattern: `INCREMENTAL_BY_TIME_RANGE`, filter on `processed_to_bronze = FALSE AND response_status = 200`, extract from `response_body` JSONB.

| Model Name | Source Raw Table | Key Extracted Fields | Output Schema |
|------------|-----------------|---------------------|---------------|
| bronze.pubmed | raw.pubmed | pmid, title, abstract, authors, journal, pub_date, mesh_terms, doi | mol_bronze or bronze |
| bronze.ema | raw.ema | product_name, active_substance, authorization_status, decision_date, therapeutic_area | bronze |
| bronze.hta_decisions | raw.hta_decisions | agency, drug_name, indication, decision, decision_date, recommendation | bronze |
| bronze.cochrane_reviews | raw.cochrane_reviews | review_id, title, authors, abstract, pub_date, doi, review_type | bronze |
| bronze.sec_edgar | raw.sec_edgar | cik, company_name, filing_type, filing_date, revenue, net_income, total_assets | bronze |
| bronze.orcid | raw.orcid | orcid_id, given_name, family_name, affiliations, works_count, h_index_proxy | bronze |
| bronze.journal_rss | raw.journal_rss | title, link, pub_date, journal_name, summary, authors, doi | bronze |
| bronze.medical_news | raw.medical_news | title, link, pub_date, source_name, summary, drug_mentions, sentiment | bronze |
| bronze.cms_inpatient | raw.cms_medicare_inpatient | provider_id, drg_code, total_discharges, avg_charges, avg_payments, fiscal_year | bronze |
| bronze.cms_hospital_info | raw.cms_hospital_info | provider_id, hospital_name, city, state, hospital_type, ownership, rating | bronze |
| bronze.cms_cost_reports | raw.cms_cost_reports | provider_id, fiscal_year, total_costs, net_revenue, operating_margin, bed_count | bronze |
| bronze.acc_tvc | raw.acc_tvc_certification | facility_id, facility_name, city, state, certification_type, cert_date, volumes | bronze |
| bronze.hrsa | raw.hrsa_shortage_areas | hpsa_id, designation_type, state, county, discipline, score, status | bronze |
| bronze.pdb_structures | raw.pdb_structures | pdb_id, title, resolution, method, organism, ligand_id, ligand_name, uniprot_id | bronze |
| bronze.who_icd | raw.who_icd | icd_code, title, chapter, block_id, category, includes, excludes | bronze |

---

## New SQLMesh Models — Silver (6 new + 3 extended)

### New Silver Tables

| Model Name | Unique Key | Source Bronze Models | Key Fields |
|------------|-----------|---------------------|------------|
| silver.regulatory_decisions | (agency, drug_name, indication, decision_date) | bronze.ema, bronze.hta_decisions | agency, drug_name, active_substance, indication, decision, decision_date, therapeutic_area, recommendation_details, source |
| silver.financial_data | (cik, filing_type, filing_date) | bronze.sec_edgar | cik, company_name, filing_type, filing_date, revenue, net_income, total_assets, market_cap, drug_revenue_pct, source_updated_at |
| silver.researchers | (orcid_id) | bronze.orcid | orcid_id, given_name, family_name, affiliation, country, works_count, h_index, research_areas, therapeutic_areas, source_updated_at |
| silver.news_signals | (source_url, pub_date) | bronze.medical_news | title, source_name, pub_date, source_url, drug_mentions, sentiment_polarity, sentiment_score, therapeutic_area, signal_type |
| silver.healthcare_facilities | (provider_id, source) | bronze.cms_inpatient, bronze.cms_hospital_info, bronze.cms_cost_reports, bronze.acc_tvc, bronze.hrsa | provider_id, facility_name, city, state, facility_type, bed_count, total_discharges, avg_charges, certifications, shortage_score, source |
| silver.icd_codes | (icd_code) | bronze.who_icd | icd_code, title, chapter, block_id, category, parent_code, is_leaf, includes_text, excludes_text |

### Extended Silver Tables

| Existing Model | New Sources Added | Key Changes |
|---------------|-------------------|-------------|
| silver.publications | bronze.pubmed, bronze.cochrane_reviews, bronze.journal_rss | Add UNION ALL blocks for PubMed, Cochrane, journal RSS alongside existing OpenAlex source |
| silver.patents | bronze.orange_book | Add UNION ALL block for Orange Book patents alongside existing USPTO/EPO/DrugBank sources |
| silver.targets | bronze.pdb_structures | Add UNION ALL block for PDB structural data alongside existing UniProt source |

---

## New SQLMesh Models — Gold (8 views)

### mol_gold.kol_profiles

Aggregated KOL researcher profiles with influence scoring.

| Field | Source | Description |
|-------|--------|-------------|
| researcher_id | silver.researchers.orcid_id | Unique researcher ID |
| name | silver.researchers | Full name |
| affiliation | silver.researchers | Primary affiliation |
| h_index | silver.researchers | H-index metric |
| publication_count | silver.publications (COUNT) | Total publications |
| citation_count | silver.publications (SUM) | Total citations |
| trial_count | mol_silver.clinical_trials (COUNT) | Clinical trial involvement |
| grant_count | silver.researchers | Grant count |
| influence_score | Computed | h_index*0.3 + pubs*0.2 + cites*0.25 + trials*0.15 + grants*0.1 |
| influence_tier | Computed | Global (95th), National (80th), Regional (50th), Rising (<50th) |
| therapeutic_areas | silver.researchers | Array of areas |
| expertise_areas | silver.researchers | Array of expertise |

### mol_gold.kol_network

Co-authorship network relationships.

| Field | Source | Description |
|-------|--------|-------------|
| source_researcher_id | silver.publications (co-author join) | Source node |
| target_researcher_id | silver.publications (co-author join) | Target node |
| shared_publications | COUNT | Number of co-authored papers |
| connection_type | Computed | 'co_author' |

### mol_gold.kol_drug_associations

Researcher-drug relationships.

| Field | Source | Description |
|-------|--------|-------------|
| researcher_id | silver.researchers | KOL identifier |
| molecule_id | mol_silver.molecules | Molecule reference |
| drug_name | mol_silver.molecules | Drug name |
| association_types | Array | trial_investigator, publication_author, grant_recipient |
| evidence_count | COUNT | Number of associations |

### mol_gold.advocacy_groups

Patient advocacy organizations by disease.

| Field | Source | Description |
|-------|--------|-------------|
| group_id | Generated | Unique group ID |
| organization_name | silver.news_signals + external | Organization name |
| disease_focus | silver.news_signals | Indication/disease |
| size_estimate | Derived | Small/Medium/Large |
| activities | JSONB array | Advocacy activities |
| indication | silver.news_signals | Medical indication |

### mol_gold.advocacy_sentiment

Sentiment signals per molecule from news/media.

| Field | Source | Description |
|-------|--------|-------------|
| molecule_id | mol_silver.molecules | Molecule reference |
| source | silver.news_signals.source_name | Media source |
| sentiment_polarity | silver.news_signals | Positive/Negative/Neutral |
| signal_count | COUNT | Number of signals |
| recent_signals | JSONB array (top 10) | Most recent signal details |
| time_period | Computed | Aggregation window |

### mol_gold.trial_outcomes (UNION view)

Combined trial outcomes from two evidence sources.

| Field | Source | Description |
|-------|--------|-------------|
| molecule_id | Both sources | Molecule reference |
| trial_nct_id | Both sources | NCT ID (nullable for pub evidence) |
| evidence_source | 'clinicaltrials_gov' or 'publication' | Source attribution |
| endpoint_name | Both sources | Clinical endpoint |
| hazard_ratio | Both sources | HR value |
| p_value | Both sources | Statistical significance |
| response_rate | Both sources | ORR % |
| sample_size | Both sources | Patient count |
| confidence_score | 1.0 for registry, 0.40-1.0 for publication | Confidence level |
| evidence_date | Both sources | Date of evidence |

**Source 1**: `mol_silver.clinical_trials` WHERE results_outcomes IS NOT NULL → confidence 1.0
**Source 2**: `xenon.publication_evidence` WHERE confidence_score >= 0.40

### mol_gold.regulatory_timeline

Cross-source regulatory decision history per molecule.

| Field | Source | Description |
|-------|--------|-------------|
| molecule_id | mol_silver.molecules (JOIN) | Molecule reference |
| drug_name | silver.regulatory_decisions | Drug name |
| agency | silver.regulatory_decisions | EMA, NICE, HAS, etc. |
| decision | silver.regulatory_decisions | Approved, Rejected, etc. |
| decision_date | silver.regulatory_decisions | Decision date |
| indication | silver.regulatory_decisions | Therapeutic indication |
| recommendation_details | silver.regulatory_decisions | Details JSONB |

### mol_gold.financial_summary

Cross-source financial data per molecule/company.

| Field | Source | Description |
|-------|--------|-------------|
| molecule_id | mol_silver.molecules (JOIN via company) | Molecule reference |
| company_name | silver.financial_data | Company name |
| cik | silver.financial_data | SEC CIK |
| latest_revenue | silver.financial_data | Most recent revenue |
| latest_net_income | silver.financial_data | Most recent net income |
| total_assets | silver.financial_data | Total assets |
| drug_revenue_pct | silver.financial_data | % revenue from drugs |
| filing_count | COUNT | Number of filings |
| latest_filing_date | MAX | Most recent filing |

---

## LAYER_MODELS Registry Expansion

After this feature, `LAYER_MODELS` in `transform_molecules.py` expands from 6 layers to:

```python
LAYER_MODELS = {
    'bronze': [
        # Existing (5)
        'mol_bronze.chembl_molecules',
        'mol_bronze.pubchem_compounds',
        'mol_bronze.clinical_trials',
        'mol_bronze.openfda_labels',
        'mol_bronze.openfda_faers',
    ],
    'silver': [
        # Existing (4)
        'mol_silver.molecules_from_bronze',
        'mol_silver.clinical_trials',
        'mol_silver.drug_labels',
        'mol_silver.adverse_events',
    ],
    'gold': [
        # Existing (3)
        'mol_gold.molecule_profiles_agg',
        'mol_gold.safety_signals_agg',
        'mol_gold.trial_analytics_agg',
        # New (6)
        'mol_gold.kol_profiles',
        'mol_gold.kol_network',
        'mol_gold.advocacy_sentiment',
        'mol_gold.trial_outcomes',
        'mol_gold.regulatory_timeline',
        'mol_gold.financial_summary',
    ],
    'ip_bronze': [
        # Existing (5)
        'bronze.uspto_patents',
        'bronze.uspto_ci',
        'bronze.epo_patents',
        'bronze.uspto_trademarks',
        'bronze.euipo_trademarks',
        # New (15)
        'bronze.pubmed',
        'bronze.ema',
        'bronze.hta_decisions',
        'bronze.cochrane_reviews',
        'bronze.sec_edgar',
        'bronze.orcid',
        'bronze.journal_rss',
        'bronze.medical_news',
        'bronze.cms_inpatient',
        'bronze.cms_hospital_info',
        'bronze.cms_cost_reports',
        'bronze.acc_tvc',
        'bronze.hrsa',
        'bronze.pdb_structures',
        'bronze.who_icd',
    ],
    'ip_silver': [
        # Existing (2)
        'silver.patents',
        'silver.trademarks',
        # New/Extended (8)
        'silver.publications',    # extended with pubmed, cochrane, journal_rss
        'silver.targets',         # extended with pdb_structures
        'silver.regulatory_decisions',
        'silver.financial_data',
        'silver.researchers',
        'silver.news_signals',
        'silver.healthcare_facilities',
        'silver.icd_codes',
    ],
    'ip_gold': [
        # Existing (1)
        'gold.molecule_profile',
        # New (2) - NOTE: kol_drug_associations and advocacy_groups may be mol_gold
        'mol_gold.kol_drug_associations',
        'mol_gold.advocacy_groups',
    ],
}
```

---

## Entity Relationships

```
mol_silver.molecules (molecule_id)
  ├── xenon.assessment_generated (molecule_id) — application writes
  ├── xenon.publication_evidence (molecule_id) — application writes
  ├── mol_gold.kol_drug_associations (molecule_id) — read-only view
  ├── mol_gold.advocacy_sentiment (molecule_id) — read-only view
  ├── mol_gold.trial_outcomes (molecule_id) — UNION view
  ├── mol_gold.regulatory_timeline (molecule_id) — cross-join view
  └── mol_gold.financial_summary (molecule_id) — cross-join view

silver.researchers (orcid_id)
  ├── mol_gold.kol_profiles (researcher_id)
  ├── mol_gold.kol_network (source/target_researcher_id)
  └── mol_gold.kol_drug_associations (researcher_id)

silver.news_signals
  ├── mol_gold.advocacy_groups (disease_focus)
  └── mol_gold.advocacy_sentiment (molecule linkage via drug_mentions)

silver.regulatory_decisions
  └── mol_gold.regulatory_timeline (drug_name → molecule JOIN)

silver.financial_data
  └── mol_gold.financial_summary (company_name → molecule JOIN)
```

---

## Configuration Entities

### Rate Limit Registry (`src/dk_data/config/rate_limits.yaml`)

```yaml
# Per-source rate limits and timeouts for MCP tools
defaults:
  timeout_seconds: 30
  base_delay_seconds: 1
  max_delay_seconds: 30
  max_retries: 3
  jitter: true

sources:
  clinicaltrials:
    requests_per_second: 3
    timeout_seconds: 30
    burst_limit: 10
  openfda:
    requests_per_second: 4    # 240/min
    timeout_seconds: 30
    burst_limit: 20
  chembl:
    requests_per_second: 10
    timeout_seconds: 30
    burst_limit: 30
  drugbank:
    requests_per_second: 5
    timeout_seconds: 60       # XML parsing is slow
    burst_limit: 10
    max_retries: 5            # override default — DrugBank XML responses are large
  pubmed:
    requests_per_second: 3    # NCBI rate limit
    timeout_seconds: 30
    burst_limit: 10
  epo:
    requests_per_second: 10
    timeout_seconds: 30
    burst_limit: 20
  # ... (all 28 sources)
```
