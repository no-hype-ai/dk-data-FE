# Data Ingestion Reference

## Architecture

Data enters the platform through the **job-trigger** FastAPI service (port 8000). There are no standalone loader scripts — all ingestion runs through this service, either on-demand (triggered by Xenon or HTTP) or on a cron schedule (Kubernetes CronJobs).

```
Xenon (or HTTP caller)
        │
        ▼
FastAPI job-trigger (port 8000)
src/dk_data/ingestion/batch/api.py
        │
        ├── POST /api/v1/data-platform/ingest     — trigger fetch for one source/molecule
        ├── GET  /api/v1/data-platform/jobs/{id}  — poll job completion
        └── GET  /api/v1/data-platform/sources    — list available sources
        │
        ▼
raw_ingestion.py
services/data_platform/raw_ingestion.py
        │  Fetches external API, writes one row to mol_raw.<source>
        ▼
mol_raw.*
        │  SQLMesh (sync_runner.py invokes sqlmesh plan --auto-apply)
        ▼
mol_bronze.* → mol_silver.* → mol_gold.*
```

## Source Registry

Sources are registered in `services/data_platform/sync_runner.py` as `SOURCE_TO_SQLMESH_MODELS`:

```python
SOURCE_TO_SQLMESH_MODELS = {
    'clinicaltrials_gov':  { 'bronze': 'mol_bronze.clinicaltrials',   'silver': 'mol_silver.clinical_trials' },
    'openfda_faers':       { 'bronze': 'mol_bronze.openfda_faers',    'silver': 'mol_silver.adverse_events'  },
    'openfda_labels':      { 'bronze': 'mol_bronze.openfda_labels',   'silver': 'mol_silver.drug_labels'     },
    'chembl':              { 'bronze': 'mol_bronze.chembl_molecules',  'silver': 'mol_silver.molecules'       },
    'drugbank':            { 'bronze': 'mol_bronze.drugbank',          'silver': 'mol_silver.drugbank'        },
    'europepmc':           { 'bronze': 'mol_bronze.europepmc',         'silver': 'mol_silver.publications'    },
    'openalex':            { 'bronze': 'mol_bronze.openalex',          'silver': 'mol_silver.publications'    },
    'sec_edgar':           { 'bronze': 'mol_bronze.sec_edgar',         'silver': 'mol_silver.financial_data'  },
    'epo_patents':         { 'bronze': 'mol_bronze.epo_patents',       'silver': 'mol_silver.patents'         },
    'nih_reporter':        { 'bronze': 'mol_bronze.nih_reporter',      'silver': 'mol_silver.research_grants' },
    'nice_hta':            { 'bronze': 'mol_bronze.nice_hta',          'silver': 'mol_silver.hta_decisions'   },
    'fda_drugsfda':        { 'bronze': 'mol_bronze.fda_drugsfda',      'silver': 'mol_silver.regulatory_milestones' },
    'cms_open_payments':   { 'bronze': 'mol_bronze.cms_open_payments', 'silver': 'mol_silver.physician_payments' },
    'cms_medicare':        { 'bronze': 'mol_bronze.cms_medicare',      'silver': 'mol_silver.drug_spending'   },
    'who_gho':             { 'bronze': 'mol_bronze.who_gho',           'silver': 'ind_silver.epidemiology'    },
    'pubchem':             { 'bronze': 'mol_bronze.pubchem',           'silver': 'mol_silver.pubchem'         },
    'cochrane_reviews':    { 'bronze': 'mol_bronze.cochrane_reviews',  'silver': 'mol_silver.cochrane_reviews'},
    'ema_regulatory':      { 'bronze': 'mol_bronze.ema',               'silver': 'mol_silver.ema_regulatory'  },
    # ... and more
}
```

## Source Reference

### Molecule Sources

#### ClinicalTrials.gov
- **Source key**: `clinicaltrials_gov`
- **Raw**: `mol_raw.clinicaltrials`
- **Bronze**: `mol_bronze.clinicaltrials`
- **Silver**: `mol_silver.clinical_trials` (INCREMENTAL_BY_UNIQUE_KEY on nct_id)
- **Schedule**: daily
- **Query params**: `drug_name`, `nct_id`

#### openFDA FAERS (Adverse Events)
- **Source key**: `openfda_faers`
- **Raw**: `mol_raw.openfda_faers`
- **Bronze**: `mol_bronze.openfda_faers`
- **Silver**: `mol_silver.adverse_events`
- **Schedule**: daily
- **Query params**: drug name — searches `patient.drug.openfda.generic_name` (FDA-normalized, case-insensitive). Biologics with NULL `inchi_key` use canonical_name lookup. Requires `OPENFDA_API_KEY` for limit=1000; unauthenticated capped at ~100.
- **Note**: Do NOT use `patient.drug.medicinalproduct` — that field is verbatim/case-sensitive and misses most biologic reports.

#### openFDA Drug Labels
- **Source key**: `openfda_labels`
- **Raw**: `mol_raw.openfda_labels`
- **Bronze**: `mol_bronze.openfda_labels`
- **Silver**: `mol_silver.drug_labels` (INCREMENTAL_BY_UNIQUE_KEY on spl_id)
- **Schedule**: weekly
- **Query params**: `drug_name`, `inchi_key`

#### ChEMBL
- **Source key**: `chembl`
- **Raw**: `mol_raw.chembl`
- **Bronze**: `mol_bronze.chembl_molecules`
- **Silver**: `mol_silver.molecules` (master entity registry), `mol_silver.chembl`
- **Schedule**: monthly
- **Notes**: Provides deterministic `molecule_id = md5(chembl_id)::uuid`. The master molecule registry is built from ChEMBL.

#### DrugBank
- **Source key**: `drugbank`
- **Raw**: `mol_raw.drugbank`
- **Bronze**: `mol_bronze.drugbank`
- **Silver**: `mol_silver.drugbank`
- **Schedule**: startup (file-based)
- **File**: `data/drugbank/drugbank_all_full_database.xml.zip` — bundled in container image
- **Loading**: FastAPI startup handler loads from ZIP if `mol_raw.drugbank` is empty. XML parser uses depth tracking to skip nested `<drug>` elements inside targets/interactions — only top-level `<drug>` elements (depth=1) are processed, yielding ~14,000 clean unique entries. Requires XML reload if bundled file is outdated.

#### EuropePMC
- **Source key**: `europepmc`
- **Raw**: `mol_raw.europepmc`
- **Bronze**: `mol_bronze.europepmc`
- **Silver**: `mol_silver.publications`
- **Schedule**: weekly
- **Query params**: `drug_name`

#### OpenAlex
- **Source key**: `openalex`
- **Raw**: `mol_raw.openalex`
- **Bronze**: `mol_bronze.openalex`
- **Silver**: `mol_silver.publications`
- **Schedule**: weekly

#### SEC EDGAR
- **Source key**: `sec_edgar`
- **Raw**: `mol_raw.sec_edgar`
- **Bronze**: `mol_bronze.sec_edgar`
- **Silver**: `mol_silver.financial_data`, `mol_silver.indication_revenue`
- **Schedule**: quarterly
- **Notes**: Downloads and parses 10-K / 20-F HTML filings. Extracts MD&A text (revenue mentions) and risk_factors_excerpt. AstraZeneca files 20-F (foreign private issuer, CIK 0000901832) — revenue references an exhibit PDF rather than embedding numbers directly in HTML; no per-indication breakdown is available.

#### EPO Patents
- **Source key**: `epo_patents`
- **Raw**: `mol_raw.epo_patents`
- **Bronze**: `mol_bronze.epo_patents`
- **Silver**: `mol_silver.patents`
- **Schedule**: monthly

#### USPTO Patents
- **Source key**: `uspto_patents`
- **Raw**: `mol_raw.uspto_patents`
- **Bronze**: `mol_bronze.uspto_patents`
- **Silver**: `mol_silver.patent_exclusivities`
- **Schedule**: monthly
- **Notes**: USPTO PatentsView API returns 410 Gone (deprecated). Orange Book / Purple Book are the active sources for NDA/BLA patent exclusivity data.

#### Orange Book / Purple Book
- **Source key**: `fda_drugsfda`
- **Raw**: `mol_raw.orange_book`, `mol_raw.purple_book`
- **Bronze**: `mol_bronze.orange_book`, `mol_bronze.purple_book`
- **Silver**: `mol_silver.patent_exclusivities`, `mol_silver.regulatory_milestones`
- **Schedule**: monthly

#### NIH Reporter
- **Source key**: `nih_reporter`
- **Raw**: `mol_raw.nih_reporter`
- **Bronze**: `mol_bronze.nih_reporter`
- **Silver**: `mol_silver.research_grants`
- **Schedule**: monthly
- **Query params**: `drug_name`

#### NICE HTA / HTA Decisions
- **Source key**: `nice_hta` / `hta_decisions`
- **Raw**: `mol_raw.nice_hta`
- **Bronze**: `mol_bronze.nice_hta`, `mol_bronze.hta_decisions`
- **Silver**: `mol_silver.hta_decisions`
- **Schedule**: monthly

#### CMS Open Payments
- **Source key**: `cms_open_payments`
- **Raw**: `mol_raw.cms_open_payments`
- **Bronze**: `mol_bronze.cms_open_payments`
- **Silver**: `mol_silver.physician_payments`
- **Schedule**: annual (CMS updates annually)

#### CMS Medicare Part B/D Spending
- **Source key**: `cms_medicare`
- **Raw**: `mol_raw.cms_medicare`
- **Bronze**: `mol_bronze.cms_medicare`
- **Silver**: `mol_silver.drug_spending`
- **Schedule**: annual

#### WHO GHO (Epidemiology)
- **Source key**: `who_gho`
- **Raw**: `mol_raw.who_gho`
- **Bronze**: `mol_bronze.who_gho`
- **Silver**: `ind_silver.epidemiology`
- **Schedule**: monthly
- **Notes**: ~300 disease burden indicators. Linked to `ind_silver.icd10_indicator_mapping` for ICD-10 mapping.

#### PubChem
- **Source key**: `pubchem`
- **Raw**: `mol_raw.pubchem`
- **Bronze**: `mol_bronze.pubchem`
- **Silver**: `mol_silver.pubchem`
- **Schedule**: monthly
- **Query params**: `inchi_key` (small molecules only; biologics with NULL inchi_key are skipped for PubChem)

#### Cochrane Reviews
- **Source key**: `cochrane_reviews`
- **Raw**: `mol_raw.cochrane_reviews`
- **Bronze**: `mol_bronze.cochrane_reviews`
- **Silver**: `mol_silver.cochrane_reviews`
- **Schedule**: monthly

#### EMA
- **Source key**: `ema_regulatory`
- **Raw**: `mol_raw.ema`
- **Bronze**: `mol_bronze.ema`
- **Silver**: `mol_silver.ema_regulatory`
- **Schedule**: monthly

#### NPI Registry
- **Source key**: `npi_registry`
- **Raw**: `mol_raw.npi_registry`
- **Bronze**: `mol_bronze.npi_registry`
- **Silver**: `mol_silver.physician_profiles`
- **Schedule**: monthly

### Sources That Skip Biologics

The following sources require a non-null `inchi_key` and are skipped for biologics (antibodies, ADCs, cell/gene therapies):

```python
SOURCES_REQUIRING_INCHI_KEY = {'pubchem', 'chembl', 'openfda_labels', 'uniprot', 'openalex'}
```

FAERS (`openfda_faers`) does NOT require `inchi_key` — it falls back to canonical name search for biologics.

## On-Demand API

```bash
# Trigger ingestion for a molecule
curl -X POST http://localhost:8000/api/v1/data-platform/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source": "openfda_faers",
    "molecule_id": "3a4b5c6d-...",
    "drug_name": "durvalumab"
  }'
# Returns: {"job_id": "abc123", "status": "queued"}

# Poll job status
curl http://localhost:8000/api/v1/data-platform/jobs/abc123

# List available sources
curl http://localhost:8000/api/v1/data-platform/sources
```

## Environment Variables

```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=dk_data
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secret>

# Optional but needed for FAERS limit=1000:
OPENFDA_API_KEY=<key>
```

## File-Based Sources

Two sources are not API-driven and load at container startup:

**DrugBank**: Bundled as `data/drugbank/drugbank_all_full_database.xml.zip` in the container image. The FastAPI startup handler (`batch/api.py on_event("startup")`) loads it if `mol_raw.drugbank` is empty.

To force reload:
```bash
# Truncate all layers
psql -c "TRUNCATE mol_raw.drugbank; TRUNCATE mol_bronze.drugbank; TRUNCATE mol_silver.drugbank;"
# Restart job-trigger to trigger startup handler
docker compose restart job-trigger
```

**CMS USP**: Bundled as `data/usp/usp_mmg_v9_alignment.xlsx`. Loads to `hcs_raw.cms_usp` if empty. 11,016 rows.

## Scheduled Ingestion (Kubernetes CronJobs)

In production, cron schedules run via K8s CronJobs that invoke `sync_runner.py`:

```bash
# Daily
python -m sync_runner --tier daily
# Sources: clinicaltrials_gov, openfda_faers, openfda_labels

# Weekly
python -m sync_runner --tier weekly
# Sources: europepmc, openalex, ema_regulatory

# Monthly
python -m sync_runner --tier monthly
# Sources: chembl, drugbank, epo_patents, nih_reporter, nice_hta, pubchem, cochrane_reviews, who_gho, npi_registry

# Annual
python -m sync_runner --tier annual
# Sources: cms_open_payments, cms_medicare
```
