# Data Loaders Reference

Last Updated: 2026-03-28

## Overview

Data is ingested via the fetcher + loader pattern:

1. **Fetcher** (`src/dk_data/ingestion/fetchers/<source>.py`) — downloads data from the external API or file, normalizes to a list of dicts.
2. **Loader** (`src/dk_data/ingestion/sources/<source>.py`) — inserts/upserts records into the `mol_raw.*` or `hcs_raw.*` tables using the JSONB envelope schema.
3. **Orchestrator** (`src/dk_data/ingestion/main.py`) — ties fetcher + loader together, handles checkpoint state from `meta.data_sources.last_successful_refresh`.

## Running a Source

```bash
# Run a single source (inside the job-trigger container)
python -m dk_data.ingestion.main <source_key>

# Examples
python -m dk_data.ingestion.main pubmed
python -m dk_data.ingestion.main bindingdb
python -m dk_data.ingestion.main cms_part_d_prescriber

# File-based sources (require --file path)
python -m dk_data.ingestion.main cms_inpatient --file /data/MedPAR_FY2023.csv --fiscal-year 2023
python -m dk_data.ingestion.main acc_tvc --file /data/acc_tvc_certs.xlsx

# Run all API sources (non-file)
python -m dk_data.ingestion.main --all
```

## Source Inventory

### Molecule / Drug Data

| Source Key | Description | Raw Table | Schedule | Rate Limit |
|------------|-------------|-----------|----------|------------|
| `pubmed` | PubMed via NCBI E-utilities | `mol_raw.pubmed` | Daily | 10/s (auth), 3/s (anon) |
| `europepmc` | Europe PMC biomedical literature | `mol_raw.europepmc` | Daily | 10/s |
| `openalex_ci` | OpenAlex pharma publications | `mol_raw.openalex_ci` | Daily | 10/s (auth) |
| `journal_rss` | Journal RSS feeds (NEJM, Lancet, JAMA…) | `mol_raw.journal_rss` | Daily | No limit |
| `medical_news` | Medical news RSS (Medscape, Healio…) | `mol_raw.medical_news` | Daily | No limit |
| `nih_reporter` | NIH Reporter grant data | `mol_raw.nih_reporter` | Daily | ~1/s |
| `sec_edgar` | SEC pharma filings (10-K, 10-Q, 8-K) | `mol_raw.sec_edgar` | Daily | 10/s |
| `ema_regulatory` | EMA CHMP opinions and EPARs | `mol_raw.ema` | Weekly | No stated limit |
| `hta_bodies` | HTA decisions (NICE, G-BA, HAS, PBAC) | `mol_raw.hta_decisions` | Weekly | ~0.5/s |
| `cochrane` | Cochrane Library systematic reviews | `mol_raw.cochrane_reviews` | Monthly | ~0.5/s |
| `uspto_patents` | USPTO PatentsView pharma patents | `mol_raw.uspto_patents` | Weekly | No stated limit |
| `uspto_ci` | USPTO PatentsView CI patents | `mol_raw.uspto_ci` | Weekly | No stated limit |
| `uspto_trademarks` | USPTO TSDR trademark status | `mol_raw.uspto_trademarks` | Weekly | 1/s |
| `euipo_trademarks` | EUIPO trademarks | `mol_raw.euipo_trademarks` | Weekly | 30/min |
| `euipo_designs` | EUIPO registered designs | `mol_raw.euipo_designs` | Weekly | 30/min |
| `epo_ops` | EPO Open Patent Services | `mol_raw.epo_patents` | Weekly | 10/min (registered) |
| `uniprot` | UniProt protein targets | `mol_raw.uniprot` | Weekly | No stated limit |
| `pdb` | RCSB PDB protein structures | `mol_raw.pdb` | Weekly | No stated limit |
| `orcid` | ORCID researcher profiles | `mol_raw.orcid` | Weekly | 24/s |
| `drugbank` | DrugBank XML full database | `mol_raw.drugbank` | Monthly | N/A (file download) |
| `bindingdb` | BindingDB binding affinities (2.8M rows) | `mol_raw.bindingdb` | Monthly | N/A (bulk TSV download) |
| `sider` | SIDER drug side effects | `mol_raw.sider` | Monthly | N/A (bulk TSV download) |
| `who_icd` | WHO ICD-11 / ICD-10 disease codes | `mol_raw.who_icd` | Monthly | 1/s |
| `rxnorm` | NLM RxNorm drug vocabulary | `mol_raw.rxnorm` | Monthly | ~10/s |
| `who_inn` | WHO INN drug names (via PubChem) | `mol_raw.who_inn` | Monthly | 5/s |
| `pharmgkb` | PharmGKB pharmacogenomics | `mol_raw.pharmgkb` | Monthly | Credential-gated |
| `kegg_drug` | KEGG Drug compound database | `mol_raw.kegg_drug` | Weekly | ~3/s |
| `tdc_admet` | TDC ADMET benchmark datasets | `mol_raw.tdc_admet` | Monthly | N/A (static files) |

### CMS / Healthcare System (API-based, no file needed)

| Source Key | Description | Raw Table | Schedule |
|------------|-------------|-----------|----------|
| `cms_geographic_variation` | CMS Geographic Variation PUF | `hcs_raw.cms_geographic_variation` | Monthly |
| `cms_part_d_prescriber` | Part D by Prescriber PUF | `hcs_raw.cms_part_d_prescriber` | Monthly |
| `cms_care_compare` | Hospital Compare star ratings | `hcs_raw.cms_care_compare` | Monthly |
| `cms_chow` | Change of Ownership records | `hcs_raw.cms_chow` | Monthly |
| `cms_ddinter` | Drug-drug interaction data | `hcs_raw.cms_ddinter` | Monthly |
| `cms_dmepos` | DMEPOS supplier utilization | `hcs_raw.cms_dmepos` | Monthly |
| `cms_formulary` | Medicare Part D formulary | `hcs_raw.cms_formulary` | Monthly |
| `cms_hcris` | Hospital Cost Report Info System | `hcs_raw.cms_hcris` | Monthly |
| `cms_hospital_affiliation` | Hospital system affiliations | `hcs_raw.cms_hospital_affiliation` | Monthly |
| `cms_hospital_quality` | HCAHPS quality measures | `hcs_raw.cms_hospital_quality` | Monthly |
| `cms_magnet` | Magnet hospital designations | `hcs_raw.cms_magnet` | Monthly |
| `cms_ndc` | National Drug Code directory | `hcs_raw.cms_ndc` | Monthly |
| `cms_nucc` | NUCC provider taxonomy codes | `hcs_raw.cms_nucc` | Monthly |
| `cms_pecos` | Provider Enrollment Chain & Ownership | `hcs_raw.cms_pecos` | Monthly |
| `cms_pos` | Place of Service codes | `hcs_raw.cms_pos` | Monthly |
| `cms_post_acute` | SNF/IRF/LTACH post-acute care | `hcs_raw.cms_post_acute` | Monthly |
| `cms_rbcs` | Restructured BETOS Classification | `hcs_raw.cms_rbcs` | Monthly |
| `cms_stabilis` | IV drug compatibility / stability | `hcs_raw.cms_stabilis` | Monthly |
| `cms_usp` | USP drug classifications | `hcs_raw.cms_usp` | Monthly |

### CMS PUF File Sources (downloaded via CMS CKAN/data.json)

These are large file downloads managed by `seed_samples.py` or the `cronjob-cms-all` CronJob.

| Source Key | Description |
|------------|-------------|
| `cms_nppes` | National Provider Identifier registry |
| `cms_physician_puf` | Physician utilization PUF |
| `cms_physician_puf_services` | Physician utilization by service |
| `cms_part_d_spending` | Part D drug spending PUF |
| `cms_part_b_spending` | Part B drug spending PUF |
| `cms_open_payments` | Sunshine Act open payments |
| `cms_inpatient_puf` | Inpatient hospital utilization PUF |
| `cms_hospital_general_info` | Hospital General Information |
| `cms_medicare_advantage` | Medicare Advantage enrollment |
| `cms_medicaid_drug_spending` | Medicaid drug spending |
| `cms_dme_puf` | DME utilization PUF |
| `cms_home_health` | Home health agency PUF |
| `cms_hospice_puf` | Hospice utilization PUF |
| `cms_snf_puf` | Skilled nursing facility PUF |
| `cms_outpatient_puf` | Outpatient hospital PUF |
| `cms_referring_providers` | Referring provider PUF |
| `cms_ordering_providers` | Ordering provider PUF |
| `cms_lab_services` | Lab services PUF |
| `cms_imaging_puf` | Imaging services PUF |
| `cms_mental_health_puf` | Mental health services PUF |
| `cms_opioid_puf` | Opioid prescribing PUF |
| `cms_telehealth_puf` | Telehealth services PUF |
| `cms_chronic_conditions` | Chronic conditions PUF |
| `cms_dual_eligible` | Dual eligible beneficiaries |
| `cms_enrollment_puf` | Medicare enrollment PUF |
| `cms_claim_type_puf` | Claims by type PUF |
| `cms_utilization_puf` | General utilization PUF |
| `cms_cost_reports_puf` | Cost Reports PUF |
| `cms_cost_reports_puf_lines` | Cost Reports PUF (line-level) |

### Legacy File Sources (manual file path required)

| Source Key | Description | Raw Table | `--file` required |
|------------|-------------|-----------|-------------------|
| `cms_inpatient` | CMS Medicare Inpatient (TAVR DRGs) | `hcs_raw.cms_medicare_inpatient` | Yes + `--fiscal-year` |
| `cms_hospital_info` | CMS Hospital General Information | `hcs_raw.cms_hospital_info` | Yes |
| `cms_cost_reports` | CMS HCRIS cost reports | `hcs_raw.cms_cost_reports` | Yes |
| `acc_tvc` | ACC Transcatheter Valve Certifications | `hcs_raw.acc_tvc_certification` | Yes |
| `hrsa` | HRSA shortage areas | `hcs_raw.hrsa_shortage_areas` | Optional |

## Credential-Gated Sources

These sources require API keys in Doppler. The fetcher fails gracefully (logs error, returns `status: failed`) if the key is absent.

| Source | Required Secret |
|--------|----------------|
| `drugbank` | `DRUGBANK_API_KEY` |
| `epo_ops` | `EPO_CONSUMER_KEY`, `EPO_CONSUMER_SECRET` |
| `pharmgkb` | `PHARMGKB_API_KEY` |
| `pubmed` | `NCBI_API_KEY` (optional — increases rate limit from 3/s to 10/s) |
| `openalex_ci` | `OPENALEX_API_KEY` (required since Feb 2026) |
| `who_icd` | `WHO_ICD_CLIENT_ID`, `WHO_ICD_CLIENT_SECRET` (optional — falls back to ICD-10 public API) |
| `sec_edgar` | `SEC_EDGAR_USER_AGENT` (required per SEC policy — use `Name email@company.com` format) |
| `uspto_patents` | `PATENTSVIEW_API_KEY` |

## Loader Pattern (for new sources)

Every loader follows the JSONB envelope upsert pattern:

```python
# Stable request_id — critical for correct ON CONFLICT deduplication
request_id = f"{source_name}_{natural_key}"
body_json = json.dumps(record)
body_hash = hashlib.sha256(body_json.encode()).hexdigest()

cur.execute("""
    INSERT INTO mol_raw.my_source (
        request_id, request_timestamp, api_endpoint, api_version,
        request_params, response_status, response_body,
        response_body_hash, response_size_bytes,
        processed_to_bronze, ingested_at, source_id
    ) VALUES (%s, %s, %s, %s, %s, 200, %s, %s, %s, FALSE, NOW(), 'my_source')
    ON CONFLICT (request_id)
    DO UPDATE SET
        response_body      = EXCLUDED.response_body,
        response_body_hash = EXCLUDED.response_body_hash,
        processed_to_bronze = FALSE,
        ingested_at        = NOW()
    WHERE mol_raw.my_source.response_body_hash IS DISTINCT FROM EXCLUDED.response_body_hash
""", (request_id, timestamp, endpoint, version, params_json,
      body_json, body_hash, len(body_json.encode())))
```

The `WHERE ... IS DISTINCT FROM` clause means records with unchanged content are **not** overwritten — `processed_to_bronze` stays `TRUE` for already-processed unchanged records.

## Adding a New Source

See `PLATFORM_GUIDE.md` § "Adding a New Data Source" for the full checklist.

Quick summary:
1. `src/dk_data/ingestion/fetchers/<source>.py` — fetcher class extending `BaseFetcher`
2. `src/dk_data/ingestion/sources/<source>.py` — loader function
3. `src/dk_data/sql/migrations/<NNN>_<source>_raw_table.sql` — raw table DDL
4. Register in `src/dk_data/ingestion/main.py` `SOURCES` dict
5. `k8s/apps/cronjobs/base/cronjob-fetch-<source>.yaml` + add to `kustomization.yaml`
6. Add to `seed_samples.py` `API_SOURCES` or `CMS_SOURCES`
