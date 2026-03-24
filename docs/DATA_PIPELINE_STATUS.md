# DK Data Platform — Molecule Pipeline Status

## Architecture Summary

dk-data-FE is a pharmaceutical data platform. It ingests data from ~50 external APIs and files, transforms it through a medallion pipeline (raw → bronze → silver → gold), and exposes `mol_silver.*` and `mol_gold.*` via PostgREST (port 3030) for consumption by Xenon.

```
External APIs / Files
        │  Python fetchers (cron + on-demand)
        ▼
mol_raw.*          — raw JSONB responses, one row per API call
        │  SQLMesh INCREMENTAL_BY_TIME_RANGE
        ▼
mol_bronze.*       — typed, source-native columns
        │  SQLMesh FULL or INCREMENTAL_BY_UNIQUE_KEY
        ▼
mol_silver.*       — entity-linked to mol_silver.molecules (UUID)
        │  SQLMesh FULL
        ▼
mol_gold.*         — aggregated, report-ready views
        │
        ▼
PostgREST (port 3030) — read by Xenon
```

## Layer Status

### Raw Layer (`mol_raw.*`)

| Source | Table | Row count | Cron tier | Notes |
|---|---|---|---|---|
| ClinicalTrials.gov | `mol_raw.clinicaltrials` | populated | daily | v2 API |
| openFDA FAERS | `mol_raw.openfda_faers` | populated | daily | Uses `openfda.generic_name` (not `medicinalproduct`) |
| openFDA Labels | `mol_raw.openfda_labels` | populated | weekly | |
| ChEMBL | `mol_raw.chembl` | populated | monthly | |
| DrugBank | `mol_raw.drugbank` | ~50,000 rows | startup | XML file-based; depth-tracking parser prevents nested element duplicates |
| EuropePMC | `mol_raw.europepmc` | populated | weekly | |
| OpenAlex | `mol_raw.openalex` | populated | weekly | |
| SEC EDGAR | `mol_raw.sec_edgar` | populated | quarterly | Parses 10-K / 20-F HTML + MD&A |
| EPO Patents | `mol_raw.epo_patents` | populated | monthly | |
| NIH Reporter | `mol_raw.nih_reporter` | populated | monthly | |
| NICE HTA | `mol_raw.nice_hta` | populated | monthly | |
| FDA Drugs@FDA | `mol_raw.fda_drugsfda` | populated | monthly | |
| Orange Book | `mol_raw.orange_book` | populated | monthly | |
| Purple Book | `mol_raw.purple_book` | populated | monthly | |
| CMS Open Payments | `mol_raw.cms_open_payments` | populated | annual | |
| CMS Medicare | `mol_raw.cms_medicare` | populated | annual | Part B + Part D spending |
| NPI Registry | `mol_raw.npi_registry` | populated | monthly | |
| WHO GHO | `mol_raw.who_gho` | populated | monthly | ~300 disease burden indicators |
| Cochrane | `mol_raw.cochrane_reviews` | populated | monthly | |
| ClinicalTrials.gov (indication stats) | `mol_raw.ct_gov_indication_stats` | populated | monthly | Per-indication trial counts |
| PubChem | `mol_raw.pubchem` | populated | monthly | |
| UniProt | `mol_raw.uniprot` | populated | monthly | |
| EMA | `mol_raw.ema` | populated | monthly | |
| CMS USP | `hcs_raw.cms_usp` | 11,016 rows | startup | XLSX file-based |

### Bronze Layer (`mol_bronze.*`)

All bronze models use `INCREMENTAL_BY_TIME_RANGE`, processing only new raw rows since last run. One SQLMesh model per source.

Important name mapping: the FAERS bronze model is `mol_bronze.openfda_faers` (not `mol_bronze.faers_events`).

| Model | Source |
|---|---|
| `mol_bronze.clinicaltrials` | ClinicalTrials.gov |
| `mol_bronze.openfda_faers` | openFDA FAERS |
| `mol_bronze.openfda_labels` | openFDA Labels |
| `mol_bronze.chembl_molecules` | ChEMBL |
| `mol_bronze.drugbank` | DrugBank |
| `mol_bronze.europepmc` | EuropePMC |
| `mol_bronze.openalex` | OpenAlex |
| `mol_bronze.sec_edgar` | SEC EDGAR |
| `mol_bronze.epo_patents` | EPO |
| `mol_bronze.nih_reporter` | NIH Reporter |
| `mol_bronze.hta_decisions` | NICE / G-BA / PBAC |
| `mol_bronze.nice_hta` | NICE specifically |
| `mol_bronze.fda_drugsfda` | FDA Drugs@FDA |
| `mol_bronze.orange_book` | Orange Book |
| `mol_bronze.purple_book` | Purple Book |
| `mol_bronze.cms_open_payments` | CMS Open Payments |
| `mol_bronze.cms_medicare` | CMS Medicare Part B/D |
| `mol_bronze.npi_registry` | NPI Registry |
| `mol_bronze.who_gho` | WHO GHO |
| `mol_bronze.cochrane_reviews` | Cochrane |
| `mol_bronze.ct_gov_indication_stats` | CT.gov indication stats |
| `mol_bronze.pubchem` | PubChem |
| `mol_bronze.uniprot` | UniProt |
| `mol_bronze.ema` | EMA |
| `mol_bronze.pubmed` | PubMed |
| `mol_bronze.pdb_structures` | RCSB PDB |
| `mol_bronze.sider` | SIDER |
| `mol_bronze.bindingdb` | BindingDB |
| `mol_bronze.tdc_admet` | TDC |
| `mol_bronze.kegg_drug` | KEGG |
| `mol_bronze.reactome` | Reactome |
| `mol_bronze.uspto_patents` | USPTO |
| `mol_bronze.euipo_trademarks` | EUIPO |
| `mol_bronze.pharmgkb` | PharmGKB |
| `mol_bronze.ttd` | Therapeutic Target Database |
| `mol_bronze.dailymed` | DailyMed |
| `mol_bronze.imgt` | IMGT |

### Silver Layer (`mol_silver.*`)

All silver models join bronze data to `mol_silver.molecules` via `molecule_id = md5(chembl_id)::uuid`. `needs_review = FALSE` molecules are the live population.

| Table | Kind | Linkage | Notes |
|---|---|---|---|
| `mol_silver.molecules` | FULL | — | Master registry; built from ChEMBL; deterministic UUIDs |
| `mol_silver.clinical_trials` | INCREMENTAL_BY_UNIQUE_KEY | nct_id | Phase, status, primary endpoints, results |
| `mol_silver.drug_labels` | INCREMENTAL_BY_UNIQUE_KEY | spl_id | FDA labeling, boxed warnings, clinical studies section |
| `mol_silver.adverse_events` | INCREMENTAL_BY_TIME_RANGE | safety_report_id | Report-level; FAERS MedDRA PTs stored as JSONB array |
| `mol_silver.targets` | FULL | molecule_id | Drug targets (DrugBank + ChEMBL) |
| `mol_silver.bioactivity` | FULL | molecule_id | IC50, Ki, EC50 (ChEMBL + BindingDB) |
| `mol_silver.publications` | FULL | molecule_id | OpenAlex + EuropePMC |
| `mol_silver.molecule_publications` | FULL | molecule_id | M:N link table |
| `mol_silver.molecule_targets` | FULL | molecule_id | M:N link table |
| `mol_silver.molecule_aliases` | FULL | molecule_id | Synonyms, brand names |
| `mol_silver.identifier_mappings` | FULL | molecule_id | Cross-source ID table |
| `mol_silver.patents` | FULL | molecule_id | EPO patents |
| `mol_silver.patent_exclusivities` | FULL | molecule_id | Orange Book + Purple Book |
| `mol_silver.trademarks` | FULL | molecule_id | USPTO + EUIPO |
| `mol_silver.financial_data` | FULL | molecule_id | SEC EDGAR filings; MD&A + risk factors |
| `mol_silver.indication_revenue` | FULL | molecule_id | Per-indication revenue from MD&A text parsing |
| `mol_silver.hta_decisions` | FULL | molecule_id | NICE, G-BA, PBAC decisions |
| `mol_silver.regulatory_milestones` | FULL | molecule_id | FDA/EMA approval dates and indications |
| `mol_silver.ema_regulatory` | FULL | molecule_id | EMA authorized medicines + EPARs |
| `mol_silver.rems_programs` | FULL | molecule_id | FDA REMS requirements |
| `mol_silver.drug_spending` | FULL | molecule_id | CMS Part B/D annual spending |
| `mol_silver.physician_payments` | FULL | molecule_id | CMS Open Payments |
| `mol_silver.physician_profiles` | FULL | — | NPI prescriber profiles (no molecule_id) |
| `mol_silver.research_grants` | FULL | molecule_id | NIH / BARDA grants |
| `mol_silver.protein_targets` | FULL | molecule_id | UniProt + PDB structural data |
| `mol_silver.pathways` | FULL | molecule_id | Reactome + KEGG |
| `mol_silver.cochrane_reviews` | FULL | molecule_id | Cochrane systematic reviews |
| `mol_silver.pubchem` | FULL | molecule_id | Molecular weight, CID, structure |
| `mol_silver.drugbank` | FULL | molecule_id | Pharmacology, interactions, half-life |
| `mol_silver.chembl` | FULL | molecule_id | Compound + bioactivity summary |
| `mol_silver.dailymed_labels` | FULL | molecule_id | DailyMed SPL metadata |
| `mol_silver.news_signals` | FULL | molecule_id | Medical news |
| `mol_silver.side_effects` | FULL | molecule_id | SIDER (joined via pubchem_cid = cid::TEXT) |
| `mol_silver.admet_properties` | FULL | molecule_id | TDC ADMET predictions |
| `mol_silver.pharmacogenomics` | FULL | molecule_id | PharmGKB PGx |

**Indication tables** (`ind_silver.*`):

| Table | Description |
|---|---|
| `ind_silver.epidemiology` | WHO GHO disease burden per ICD-10 |
| `ind_silver.indication_ontology` | ICD-10 full ontology |
| `ind_silver.icd10_indicator_mapping` | ICD-10 ↔ WHO GHO indicator map |
| `ind_silver.ct_gov_indication_stats` | CT.gov trial counts per indication |

### Gold Layer (`mol_gold.*`)

All gold models use `FULL` kind. `molecule_id` is stored as TEXT (not UUID FK).

| Table | Kind | Description |
|---|---|---|
| `mol_gold.safety_signals` | FULL | FAERS aggregate: total/serious/death reports, top 20 MedDRA PTs, risk level |
| `mol_gold.market_summary` | FULL | Revenue, Medicare spending, competitor count, HTA decisions, growth rate |
| `mol_gold.molecule_profile` | FULL | Wide denormalized: classification, targets, mechanism, approvals |
| `mol_gold.competitive_landscape` | FULL | Competing drugs by pharmacological class, per-competitor trial/exclusivity |
| `mol_gold.company_pipeline` | FULL | Sponsor pipeline programs |
| `mol_gold.lifecycle_stages` | FULL | Stage detection, approval_date, trial counts |
| `mol_gold.lifecycle_evidence` | FULL | Evidence supporting stage classification |
| `mol_gold.regulatory_timeline` | FULL | All FDA/EMA approvals chronologically |
| `mol_gold.financial_summary` | FULL | Revenue trajectory from SEC filings |
| `mol_gold.advocacy_groups` | FULL | Patient advocacy groups (no molecule_id) |
| `mol_gold.advocacy_sentiment` | FULL | Sentiment per molecule |
| `mol_gold.kol_drug_associations` | FULL | KOL ↔ drug associations |

## Known Limitations

**DrugBank XML coverage**: The bundled XML must be kept current. Biologics introduced after the bundled version (e.g. Durvalumab DB14392 in older XML versions) will have no DrugBank rows until the XML file is updated and the startup reload is re-triggered (truncate `mol_raw.drugbank` / `mol_bronze.drugbank` / `mol_silver.drugbank`, restart job-trigger container).

**openFDA rate limiting**: Without `OPENFDA_API_KEY`, unauthenticated calls are limited to ~100 results per request. Set `OPENFDA_API_KEY` in the environment to enable limit=1000 requests. FAERS uses `openfda.generic_name` (FDA-normalized, case-insensitive) for molecule matching.

**SEC EDGAR per-indication revenue**: AstraZeneca files 20-F (foreign private issuer). Revenue is reported at product level, not per-indication. No per-indication breakdown (e.g. NSCLC vs HCC) exists in public filings.

**SQLMesh transform timeouts**: clinicaltrials_gov, openfda_labels, and europepmc transforms can exceed Xenon's 120s poll window when run on-demand (data arrives in raw/bronze but silver/gold complete after the timeout). Xenon retries automatically on next pipeline run.

**`INCREMENTAL_BY_UNIQUE_KEY` idempotency**: `mol_silver.clinical_trials` and `mol_silver.drug_labels` use this kind. Row counts should be monitored across consecutive SQLMesh runs to confirm no duplicate accumulation (SQLMesh snapshot tables have no physical UNIQUE index).

## Refresh Procedures

### On-Demand (xenon-triggered)

```bash
# Trigger ingestion for a specific source + molecule
curl -X POST http://localhost:8000/api/v1/data-platform/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "openfda_faers", "molecule_id": "<uuid>", "drug_name": "durvalumab"}'

# Check job status
curl http://localhost:8000/api/v1/data-platform/jobs/<job_id>
```

### Scheduled (CLI)

```bash
# Run all daily sources
python -m sync_runner --tier daily

# Run specific sources
python -m sync_runner --sources clinicaltrials,openfda_faers

# Run SQLMesh transforms only
uv run sqlmesh -p src/dk_data/sqlmesh plan --auto-apply
```

### Container Restart

```bash
# Rebuild and restart job-trigger (picks up code changes)
docker compose build job-trigger && docker compose up -d --force-recreate job-trigger

# Restart PostgREST after schema changes
docker compose restart postgrest
```
