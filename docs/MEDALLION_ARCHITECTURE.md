# Medallion Architecture — DK Data Platform

## Overview

The DK Data Platform implements a four-layer medallion architecture for pharmaceutical and healthcare data. All data flows through: **raw → bronze → silver → gold**. SQLMesh manages every transform declaratively; no hand-written migration scripts touch data.

```
External APIs / Files
        │
        ▼
┌──────────────┐    mol_raw.*     ┌──────────────┐    mol_bronze.*    ┌──────────────┐    mol_silver.*    ┌──────────────┐
│  Fetchers    │ ──────────────▶  │  SQLMesh     │ ──────────────────▶│  SQLMesh     │ ──────────────────▶│  SQLMesh     │
│ (FastAPI /   │  JSONB rows,     │  Bronze      │  Typed columns,    │  Silver      │  Entity-linked,    │  Gold        │
│  cron jobs)  │  one per API call│  models      │  source-native     │  models      │  FK to molecules   │  models      │
└──────────────┘                  └──────────────┘                    └──────────────┘                    └──────────────┘
                                                                               │                                  │
                                                                               └──────────────────────────────────┘
                                                                                          PostgREST (port 3030)
                                                                                          Xenon reads mol_silver.*
                                                                                          and mol_gold.* from here
```

## Schema Naming Convention

The schema name IS the domain prefix. Tables carry no additional prefix.

| Schema group | Domain | Example tables |
|---|---|---|
| `mol_raw.*` | Molecule — raw API responses | `mol_raw.clinicaltrials`, `mol_raw.openfda_faers`, `mol_raw.chembl` |
| `mol_bronze.*` | Molecule — typed, source-native | `mol_bronze.clinicaltrials`, `mol_bronze.openfda_faers`, `mol_bronze.drugbank` |
| `mol_silver.*` | Molecule — entity-linked, normalized | `mol_silver.molecules`, `mol_silver.clinical_trials`, `mol_silver.adverse_events` |
| `mol_gold.*` | Molecule — aggregated, report-ready | `mol_gold.safety_signals`, `mol_gold.market_summary`, `mol_gold.competitive_landscape` |
| `hcs_raw.*` | Healthcare system — CMS raw | `hcs_raw.cms_nppes`, `hcs_raw.cms_open_payments`, `hcs_raw.cms_usp` |
| `hcs_silver.*` | Healthcare system — enriched | `hcs_silver.cms_provider_360`, `hcs_silver.cms_drug_market` |
| `hcs_gold.*` | Healthcare system — gold views | `hcs_gold.cms_provider_360`, `hcs_gold.cms_drug_market_profile` |
| `ind_silver.*` | Indication / disease | `ind_silver.epidemiology`, `ind_silver.indication_ontology` |
| `hcp_silver.*` | HCP / researcher | `hcp_silver.researchers`, `hcp_silver.facilities` |
| `hcp_gold.*` | HCP — aggregated | `hcp_gold.kol_profiles`, `hcp_gold.kol_network` |

## Layer Details

### Raw Layer (`mol_raw.*`, `hcs_raw.*`)

**Purpose**: Immutable store of every API response, exactly as received.

**Uniform schema** across all sources:
```sql
id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
api_endpoint      TEXT,
response_status   INTEGER,
response_body     JSONB NOT NULL,
processed_to_bronze BOOLEAN DEFAULT FALSE
```

One row = one API call. Raw rows are never modified. The `processed_to_bronze` flag lets SQLMesh incremental models filter only new rows.

**Molecule sources** (`mol_raw.*`): clinicaltrials, openfda_faers, openfda_labels, chembl, pubchem, drugbank, uniprot, europepmc, openalex, sec_edgar, epo_patents, uspto_patents, uspto_ci, euipo_trademarks, nice_hta, hta_decisions, dailymed, nih_reporter, fda_drugsfda, orange_book, purple_book, reactome, kegg_drug, who_gho, who_inn, who_icd, npi_registry, cochrane_reviews, ct_gov_indication_stats, imgt, sider, bindingdb, tdc_admet, pharmgkb, ttd, journal_rss, medical_news, websearch_results, pdb_structures, rxnorm_concepts

**File-based sources** loaded at container startup (not via API call):
- DrugBank XML (`data/drugbank/drugbank_all_full_database.xml.zip`) — loaded if `mol_raw.drugbank` is empty
- CMS USP (`data/usp/usp_mmg_v9_alignment.xlsx`) — loaded if `hcs_raw.cms_usp` is empty

**CMS/healthcare sources** (`hcs_raw.*`): cms_nppes, cms_pecos, cms_physician_puf, cms_inpatient_puf, cms_outpatient_puf, cms_part_d_prescriber, cms_open_payments, cms_hcris, cms_care_compare, cms_ndc, cms_part_b_spending, cms_part_d_spending, cms_formulary, cms_hospital_general_info, cms_chow, cms_geographic_variation, cms_chronic_conditions, cms_dmepos, cms_post_acute, cms_rbcs, cms_ddinter, cms_pos, cms_nucc, cms_magnet, cms_usp, cms_stabilis

### Bronze Layer (`mol_bronze.*`)

**Purpose**: Source-native typed data, parsed from raw JSONB.

**SQLMesh kind**: `INCREMENTAL_BY_TIME_RANGE` — filters `mol_raw.<source>` by `request_timestamp` for newly arrived rows only.

One table per source. Typed columns extracted from `response_body` JSONB. Bronze IDs are `gen_random_uuid()` — they are not stable and not used for entity linking.

**All bronze models** (`mol_bronze.*`): acc_tvc, bindingdb, cdc_vaccines, chembl_molecules, clinicaltrials, cms_cost_reports, cms_hospital_info, cms_inpatient, cms_medicare, cms_open_payments, cochrane_reviews, ct_gov_indication_stats, dailymed, drugbank, ema, epo_patents, euipo_trademarks, europepmc, faers_events (model name: `mol_bronze.openfda_faers`), fda_drugs, fda_drugsfda, hrsa, hta_decisions, journal_rss, kegg_drug, medical_news, nice_hta, nih_reporter, npi_registry, openalex, openfda_labels, orange_book, pdb_structures, pharmgkb, pubchem, pubmed, purple_book, reactome, rxnorm_concepts, sec_edgar, sider, tdc_admet, ttd, uniprot, uspto_ci, uspto_patents, uspto_trademarks, websearch_results, who_gho, who_icd, who_inn, imgt

### Silver Layer (`mol_silver.*`, `ind_silver.*`, `hcp_silver.*`)

**Purpose**: Entity-resolved, molecule-linked data. The `molecule_id` UUID in every silver table is a deterministic `md5(chembl_id)::uuid` sourced from `mol_silver.molecules`.

**SQLMesh kinds used**:
- `FULL` — rebuilds entirely each run, ensuring all rows get `molecule_id` set as new molecules enter the registry
- `INCREMENTAL_BY_UNIQUE_KEY` — upserts on natural key (e.g. `nct_id` for clinical_trials), also scans all of bronze so new molecules get linked retroactively

**Entity linking strategy**:
- Small molecules: join on `inchi_key` (structural fingerprint, unique)
- Biologics (NULL `inchi_key`): join on `LOWER(chembl_id)` or `LOWER(canonical_name)`
- The master molecule registry is `mol_silver.molecules`, built from ChEMBL

**Molecule silver tables** (`mol_silver.*`):

| Table | Source | Kind | Description |
|---|---|---|---|
| `molecules` | ChEMBL | FULL | Master entity registry; deterministic UUIDs |
| `clinical_trials` | ClinicalTrials.gov | INCREMENTAL_BY_UNIQUE_KEY (nct_id) | Phase, status, endpoints, outcomes |
| `drug_labels` | openFDA | INCREMENTAL_BY_UNIQUE_KEY | FDA-approved labeling, boxed warnings |
| `adverse_events` | openFDA FAERS | INCREMENTAL_BY_TIME_RANGE | Report-level adverse events with MedDRA PTs |
| `targets` | DrugBank / ChEMBL | FULL | Drug target proteins |
| `bioactivity` | ChEMBL + BindingDB | FULL | IC50, Ki, EC50 assay results |
| `publications` | OpenAlex / EuropePMC | FULL | Scientific publications |
| `molecule_publications` | derived | FULL | Molecule ↔ publication links |
| `molecule_targets` | derived | FULL | Molecule ↔ target links |
| `molecule_aliases` | ChEMBL / DrugBank | FULL | Synonyms, brand names |
| `identifier_mappings` | cross-source | FULL | ChEMBL ↔ PubChem ↔ UniProt ↔ DrugBank IDs |
| `patents` | EPO | FULL | European patent grants |
| `patent_exclusivities` | Orange Book / Purple Book | FULL | FDA NDA/BLA exclusivity dates |
| `trademarks` | USPTO / EUIPO | FULL | Registered trademarks |
| `financial_data` | SEC EDGAR | FULL | 10-K/20-F filings; MD&A excerpts |
| `indication_revenue` | SEC EDGAR (MD&A parsed) | FULL | Per-indication revenue mentions |
| `hta_decisions` | NICE / G-BA / PBAC | FULL | HTA reimbursement decisions |
| `regulatory_milestones` | FDA Drugs@FDA / EMA | FULL | Approval dates, indications, priority reviews |
| `ema_regulatory` | EMA medicines list | FULL | EMA authorized medicines + EPARs |
| `patent_exclusivities` | Orange Book + Purple Book | FULL | NDA/BLA exclusivity cliffs |
| `rems_programs` | FDA REMS | FULL | Risk mitigation requirements |
| `drug_spending` | CMS Part B/D | FULL | Annual Medicare spending per molecule |
| `physician_payments` | CMS Open Payments | FULL | Payments to physicians by drug |
| `physician_profiles` | NPI Registry | FULL | Prescriber profiles with specialties |
| `research_grants` | NIH Reporter | FULL | NIH/BARDA grants mentioning the drug |
| `protein_targets` | UniProt / PDB | FULL | Protein structure and function |
| `pathways` | Reactome / KEGG | FULL | Pathway annotations |
| `cochrane_reviews` | Cochrane | FULL | Systematic reviews / meta-analyses |
| `pubchem` | PubChem | FULL | Molecular weight, CID, structure data |
| `drugbank` | DrugBank XML | FULL | Pharmacology, interactions, half-life |
| `chembl` | ChEMBL API | FULL | Compound + bioactivity summary |
| `dailymed_labels` | DailyMed | FULL | SPL label metadata |
| `news_signals` | Medical news feeds | FULL | Recent news signals |
| `side_effects` | SIDER | FULL | Known side effects (PubChem CID join) |
| `admet_properties` | TDC | FULL | ADMET predictions |
| `pharmacogenomics` | PharmGKB | FULL | PGx drug-gene interactions |

**Indication / disease tables** (`ind_silver.*`):

| Table | Description |
|---|---|
| `epidemiology` | WHO GHO ~300 disease burden indicators, ICD-10 linked |
| `indication_ontology` | Full ICD-10 ontology: therapeutic area, hierarchy, pharma-relevance |
| `icd10_indicator_mapping` | ICD-10 code ↔ WHO GHO indicator mapping |
| `ct_gov_indication_stats` | ClinicalTrials.gov trial counts per indication |

**HCP tables** (`hcp_silver.*`):

| Table | Description |
|---|---|
| `researchers` | Researcher profiles (ORCID, h-index) |
| `facilities` | Healthcare facility registry |

### Gold Layer (`mol_gold.*`, `hcs_gold.*`, `hcp_gold.*`)

**Purpose**: Aggregated, denormalized, report-ready data. Xenon consumes only silver and gold — never raw or bronze.

**SQLMesh kind**: `FULL` — always rebuilds entirely for consistency.

**Note on `molecule_id`**: Gold tables store `molecule_id` as TEXT (not UUID FK) to remain decoupled from the silver FK constraint.

**Molecule gold tables** (`mol_gold.*`):

| Table | Description |
|---|---|
| `safety_signals` | FAERS aggregate per molecule: total reports, serious/death counts, top 20 MedDRA PTs, risk level |
| `market_summary` | Revenue, Medicare spending, competitor count, HTA decisions, growth rate |
| `molecule_profile` | Wide denormalized view: classification, targets, mechanism, approvals |
| `competitive_landscape` | Competing drugs in same therapeutic area, per-competitor trial and exclusivity data |
| `company_pipeline` | Sponsor pipeline programs across indications and phases |
| `lifecycle_stages` | Development stage, approval dates, trial counts, evidence summary |
| `lifecycle_evidence` | Supporting evidence for stage classification |
| `regulatory_timeline` | All FDA/EMA approvals chronologically |
| `financial_summary` | Revenue trajectory from SEC EDGAR |
| `advocacy_groups` | Patient advocacy organizations (no molecule_id — fetch all) |
| `advocacy_sentiment` | Sentiment signals per molecule |
| `kol_drug_associations` | KOL ↔ drug associations |

**Healthcare system gold tables** (`hcs_gold.*`): cms_provider_360, cms_facility_360, cms_drug_market_profile, cms_market_analytics, cms_provider_network

**HCP gold tables** (`hcp_gold.*`): kol_profiles, kol_network, kol_drug_associations

## Pipeline Execution

### On-Demand Ingestion (xenon-triggered)

1. Xenon detects empty/stale data for a molecule + indication
2. Calls `POST /api/v1/data-platform/ingest` on the dk-data-FE job-trigger (port 8000) with source name + query params
3. Fetcher writes one or more rows to `mol_raw.<source>` and returns a `job_id`
4. SQLMesh transform chain runs: raw → bronze → silver → gold (via `transform_molecules.py`)
5. Xenon polls PostgREST until data appears (up to 120s timeout)

### Scheduled Ingestion (cron)

Sources run on cron schedules (daily / weekly / monthly) defined in `ops.sync_schedules`. The sync_runner CLI (`sync_runner.py`) is invoked by Kubernetes CronJobs:

```bash
python -m sync_runner --sources clinicaltrials,openfda_labels --tier daily
```

### SQLMesh Transforms

The transform chain runs via `transform_molecules.py`. For each source:

1. **Bronze transform**: SQLMesh INCREMENTAL_BY_TIME_RANGE — processes only new raw rows since last run
2. **Silver transform**: FULL or INCREMENTAL_BY_UNIQUE_KEY — entity-links bronze rows to `mol_silver.molecules`
3. **Gold transform**: FULL — aggregates silver into wide views

SQLMesh runs: `uv run sqlmesh -p src/dk_data/sqlmesh plan --auto-apply`

PostgREST must be restarted after any SQLMesh plan that adds or renames views.

## PostgREST Access

PostgREST (port 3030) exposes these schemas as REST endpoints:

```
mol_silver, mol_gold, ind_silver, ind_gold, hcp_silver, hcp_gold, hcs_silver, hcs_gold
```

Xenon uses the `Accept-Profile` header to specify the schema:

```bash
# Query mol_silver.molecules
curl http://localhost:3030/molecules \
  -H "Accept-Profile: mol_silver"

# Query mol_gold.safety_signals
curl "http://localhost:3030/safety_signals?molecule_id=eq.<uuid>" \
  -H "Accept-Profile: mol_gold"
```

All table paths and schema assignments are registered in `apps/api/src/assessment/agents/data-registry.ts` (Xenon) and `src/dk_data/data_registry.py` (dk-data-FE). Never hardcode table names or schemas outside those files.

## Data Quality

SQLMesh audits run after each transform:

- `not_null(columns := (molecule_id, canonical_name))` — required fields present
- `unique` — primary key uniqueness where declared
- `grain molecule_id` — one row per molecule in gold tables

Molecules with data quality issues are flagged `needs_review = TRUE` in `mol_silver.molecules` and excluded from gold aggregations until manually cleared.

## Entity Linking

The join key for all silver models is `molecule_id = md5(chembl_id)::uuid`. This UUID is deterministic and stable — the same ChEMBL ID always produces the same UUID.

For sources without a direct ChEMBL ID:
- PubChem: join via `mol_silver.identifier_mappings` (pubchem_cid ↔ chembl_id)
- DrugBank: join on `inchi_key` (small molecules) or `LOWER(canonical_name)` (biologics with NULL inchi_key)
- openFDA FAERS: join on `openfda.generic_name` (FDA-normalized, case-insensitive; NOT `medicinalproduct` which is verbatim)
- SEC EDGAR: join on molecule canonical name in filing text

## File Structure

```
src/dk_data/
├── ingestion/
│   ├── batch/api.py              # FastAPI job-trigger entry point (port 8000)
│   └── fetchers/                 # Per-source fetcher modules
│       ├── drugbank.py           # DrugBank XML parser
│       └── ...
├── services/
│   └── data_platform/
│       ├── raw_ingestion.py      # Core fetcher service (fetch_faers_events etc.)
│       ├── sync_runner.py        # CLI + SOURCE_TO_SQLMESH_MODELS registry
│       └── metrics.py            # Prometheus metrics, layer row counts
├── sqlmesh/
│   ├── config.yaml
│   └── models/
│       └── molecules/
│           ├── bronze/           # ~50 bronze SQLMesh models
│           ├── silver/           # ~50 silver SQLMesh models
│           └── gold/             # ~14 gold SQLMesh models
└── data_registry.py              # Canonical source registry (dk-data-FE side)
```
