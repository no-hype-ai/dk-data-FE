# Data Sources Integration Roadmap

> **Generated**: 2026-02-14
> **Skill**: `/add-datasource`
> **Purpose**: Complete inventory of all data sources — implemented, deferred, and planned — with implementation guidance for each.

---

## How to Use This Document

Each data source below includes its current status, what work remains, and the exact `/add-datasource` invocation to implement it. The workflow is:

1. **Pick a source** from the tables below
2. **Run the skill**: `/add-datasource <description or API URL>`
3. **The skill generates**: fetcher, loader, validator, SQL migration, CronJob, Doppler secrets, catalog metadata, tests
4. **Commit, push, and sync** — ArgoCD deploys the CronJob

For sources that already have ingestion code in `raw_ingestion.py`, the skill will detect existing code and only generate the missing pieces (CronJob manifest, seed SQL, Doppler secrets).

---

## Platform Architecture

```
External APIs
     ↓
 Fetcher (BaseFetcher or RawIngestionService)
     ↓
 raw.* / mol_raw.* tables (unmodified source data)
     ↓
 SQLMesh transforms (bronze → silver → gold)
     ↓
 staging.* / mol_silver.* / mol_gold.* tables
     ↓
 PostgREST api.* views
     ↓
 Consumers (Admin App, behavior-labs-ai, dashboards)
```

**Two ingestion paths exist**:
- **TAVR/Hospital sources** → `src/dk_data/ingestion/fetchers/` (BaseFetcher pattern) → `fetch_data.py` CLI
- **Molecule/Pharma sources** → `src/dk_data/services/data_platform/raw_ingestion.py` (RawIngestionService pattern) → `fetch_molecules.py` CLI

---

## Tier 0: Active & Healthy (5 sources)

These are running in production. No `/add-datasource` action needed unless rebuilding.

| Source | Type | Frequency | CronJob | Records | Notes |
|--------|------|-----------|---------|---------|-------|
| `cms_medicare_inpatient` | csv/api | quarterly | `fetch-cms-all` | 3,494 | TAVR DRG 266/267 volumes |
| `cms_hospital_info` | csv | monthly | `fetch-cms-all` | 5,421 | Hospital demographics & ratings |
| `cms_cost_reports` | csv | annual | `fetch-cms-all` | 24,412 | HCRIS financial metrics |
| `hrsa_shortage_areas` | api | monthly | `fetch-cms-all` | 110,361 | HPSA designations |
| `acc_tvc` | scrape | quarterly | `fetch-cms-all` | 0 | **BROKEN** — API discontinued, needs fix |

### Fix Required: `acc_tvc`

The ACC TVC certification fetcher is broken. The website no longer offers CSV downloads and the scraping fallback fails. Options:
1. Find the new ACC data source URL
2. Switch to manual CSV upload
3. Disable the source

```bash
/add-datasource "Fix ACC TVC certification data source — current scraper broken, need to find new ACC API or data download"
```

---

## Tier 1: Molecule Core — Active CronJobs (6 sources)

These have code in `raw_ingestion.py` and are running via `mol-fetch-daily` and `mol-fetch-weekly` CronJobs. They may need seed SQL and catalog metadata updates.

| Source | Class | Frequency | CronJob | Auth | Issue |
|--------|-------|-----------|---------|------|-------|
| `clinicaltrials` | `ClinicalTrialsIngestion` | daily | `mol-fetch-daily` | none | — |
| `openfda` | `OpenFDAIngestion` | daily/weekly | `mol-fetch-daily` | optional key | — |
| `chembl` | `ChEMBLIngestion` | monthly | `mol-fetch-weekly` | none | — |
| `pubchem` | `PubChemIngestion` | monthly | `mol-fetch-weekly` | none | — |
| `uniprot` | `UniProtIngestion` | monthly | `mol-fetch-weekly` | none | #42 |
| `openalex` | `OpenAlexIngestion` | weekly | `mol-fetch-weekly` | none | #43 |

### Remaining Work

These sources need:
- [ ] `meta.data_sources` seed entries (for catalog tracking)
- [ ] `catalog_refresh.py` SOURCE_METADATA entries
- [ ] Verify data is actually landing in `mol_raw.*` tables

```bash
# Verify molecule ingestion is working
KUBECONFIG=~/.kube/k3s-master-1.yaml kubectl exec postgres-cluster-1 -n infra -- \
  psql -U postgres -d dk_data -c "SELECT table_name, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'mol_raw' ORDER BY table_name;"
```

---

## Tier 2: Deferred Molecule Sources — Code Exists, No CronJobs (9 sources)

These have full ingestion classes in `raw_ingestion.py` but are **not scheduled**. Each needs: Doppler secrets (if auth required), individual CronJob manifest or addition to `fetch_molecules.py` schedule, and seed SQL.

### Priority A — No Blockers (enable immediately)

| # | Source | Class | API URL | Auth | Frequency | Issue | Action |
|---|--------|-------|---------|------|-----------|-------|--------|
| 1 | **BindingDB** | `BindingDBIngestion` | `bindingdb.org/axis2/services/BDBService` | none | monthly | #44 | CronJob + seed SQL |
| 2 | **Orange Book** | `OrangeBookIngestion` | `fda.gov/media/76860/download` (CSV) | none | weekly | #46 | CronJob + seed SQL |
| 3 | **SIDER** | `SIDERIngestion` | `sideeffects.embl.de/media/download` | none (NC license) | monthly | #45, #82 | CronJob + seed SQL |
| 4 | **TDC ADMET** | `TDCAdmetIngestion` | `dataverse.harvard.edu` | none | monthly | #49 | CronJob + seed SQL |
| 5 | **EMA** | `EMAIngestion` | `api.ema.europa.eu/api` | none | weekly | #48 | CronJob + seed SQL |

**Invocations**:

```bash
/add-datasource "Enable BindingDB protein-ligand binding affinity data. Code exists in raw_ingestion.py (BindingDBIngestion class). API: https://www.bindingdb.org/axis2/services/BDBService. No auth. Monthly refresh. Needs CronJob manifest and seed SQL only. Issue #44."

/add-datasource "Enable FDA Orange Book approved drug products with patent/exclusivity data. Code exists in raw_ingestion.py (OrangeBookIngestion class). CSV downloads from fda.gov. No auth. Weekly refresh. Issue #46."

/add-datasource "Enable SIDER side effects database. Code exists in raw_ingestion.py (SIDERIngestion class). TSV downloads from sideeffects.embl.de. No auth (NC license). Monthly refresh. Issues #45, #82."

/add-datasource "Enable TDC ADMET benchmark datasets for drug property predictions. Code exists in raw_ingestion.py (TDCAdmetIngestion class). 22 ADMET datasets from Harvard Dataverse. No auth. Monthly refresh. Issue #49."

/add-datasource "Enable EMA European Medicines Agency regulatory data. Code exists in raw_ingestion.py (EMAIngestion class). API: https://api.ema.europa.eu/api. No auth. Weekly refresh. Issue #48."
```

### Priority B — Requires Credentials

| # | Source | Class | API URL | Auth | Frequency | Issue | Blocker |
|---|--------|-------|---------|------|-----------|-------|---------|
| 6 | **DrugBank** | — | XML download | License + API key | monthly | #41 | Commercial license required |
| 7 | **USPTO Patents** | `USPTOPatentsIngestion` | `api.patentsview.org/patents/query` | API key | weekly | #47, #83 | API key needed |
| 8 | **PDB** | — | `pdbbind.org.cn` | Free registration | monthly | #50 | Registration required |
| 9 | **ORCID** | — | `pub.orcid.org/v3.0` | OAuth2 | monthly | #51 | OAuth app registration |

**Invocations** (once credentials are obtained):

```bash
/add-datasource "Enable DrugBank pharmaceutical database. Requires commercial license. XML download with API key. 17.4K drugs, 2.86M DDIs, targets, pathways. Monthly refresh. Issue #41. API key goes in Doppler as DRUGBANK_API_KEY."

/add-datasource "Enable USPTO PatentsView API for pharmaceutical patent monitoring. Code exists in raw_ingestion.py (USPTOPatentsIngestion class). API: https://api.patentsview.org/patents/query. Requires API key. Weekly refresh. Issues #47, #83. API key goes in Doppler as USPTO_API_KEY."

/add-datasource "Enable PDB Protein Data Bank for 3D protein-ligand structures. Requires free registration at pdbbind.org.cn. Monthly refresh. Issue #50."

/add-datasource "Enable ORCID researcher profiles for KOL identification. API: https://pub.orcid.org/v3.0. Requires OAuth2 app registration. Monthly refresh. Issue #51."
```

---

## Tier 3: Additional Molecule Sources — Code Exists, No Issues (8 sources)

These have ingestion classes in `raw_ingestion.py` but no GitHub issues tracking them. They should be enabled as part of the molecule platform rollout.

| # | Source | Class | API URL | Auth | Frequency | Data |
|---|--------|-------|---------|------|-----------|------|
| 1 | **RxNorm** | `RxNormIngestion` | `rxnav.nlm.nih.gov/REST` | none | weekly | Drug identifiers, NDC codes, ATC codes |
| 2 | **DailyMed** | `DailyMedIngestion` | `dailymed.nlm.nih.gov/dailymed/services/v2` | none | weekly | FDA drug labeling, SPL documents |
| 3 | **FDA Drugs@FDA** | `FDADrugsIngestion` | `api.fda.gov/drug` | none | weekly | FDA approvals, NDA/ANDA/BLA applications |
| 4 | **KEGG Drug** | `KEGGDrugIngestion` | `rest.kegg.jp` | none | monthly | Drug pathways, targets, DDI |
| 5 | **TTD** | `TTDIngestion` | `db.idrblab.net/ttd` | none | monthly | Therapeutic targets |
| 6 | **PharmGKB** | `PharmGKBIngestion` | `api.pharmgkb.org/v1/data` | none | monthly | Pharmacogenomics, drug-gene interactions |
| 7 | **IMGT** | `IMGTIngestion` | `imgt.org/3Dstructure-DB` | none | monthly | Antibody sequences & structures |
| 8 | **CDC Vaccines** | `CDCVaccinesIngestion` | `data.cdc.gov/api/views` | none | monthly | Vaccine schedules, CVX codes |

**Invocations**:

```bash
/add-datasource "Enable RxNorm drug nomenclature service. Code exists in raw_ingestion.py (RxNormIngestion class). API: https://rxnav.nlm.nih.gov/REST. No auth. Weekly refresh. Provides RxCUI identifiers, NDC codes, drug class mappings."

/add-datasource "Enable DailyMed FDA drug labeling. Code exists in raw_ingestion.py (DailyMedIngestion class). API: https://dailymed.nlm.nih.gov/dailymed/services/v2. No auth. Weekly refresh. SPL documents and labeling changes."

/add-datasource "Enable FDA Drugs@FDA approvals database. Code exists in raw_ingestion.py (FDADrugsIngestion class). API: https://api.fda.gov/drug. No auth. Weekly refresh. NDA/ANDA/BLA applications with approval dates."

/add-datasource "Enable KEGG Drug pathway database. Code exists in raw_ingestion.py (KEGGDrugIngestion class). API: https://rest.kegg.jp. No auth. Monthly refresh. Drug pathways, targets, DDI."

/add-datasource "Enable TTD Therapeutic Target Database. Code exists in raw_ingestion.py (TTDIngestion class). API: http://db.idrblab.net/ttd. No auth. Monthly refresh. Therapeutic targets and biologics."

/add-datasource "Enable PharmGKB pharmacogenomics database. Code exists in raw_ingestion.py (PharmGKBIngestion class). API: https://api.pharmgkb.org/v1/data. No auth. Monthly refresh. Drug-gene interactions, dosing guidelines."

/add-datasource "Enable IMGT immunoglobulin database for biologic drugs. Code exists in raw_ingestion.py (IMGTIngestion class). API: https://www.imgt.org/3Dstructure-DB. No auth. Monthly refresh. Antibody sequences and structures."

/add-datasource "Enable CDC Vaccines data source. Code exists in raw_ingestion.py (CDCVaccinesIngestion class). API: https://data.cdc.gov/api/views. No auth. Monthly refresh. Vaccine schedules, CVX codes, manufacturer info."
```

---

## Tier 4: Competitive Intelligence Sources — No Code Exists (10 sources)

These are tracked in GitHub issues #26-35. They require **full implementation** via `/add-datasource` — fetcher, loader, validator, tables, CronJob, tests, everything.

### Priority A — High Impact CI Sources

| # | Source | Issue | API URL | Auth | Frequency | CI Volume |
|---|--------|-------|---------|------|-----------|-----------|
| 1 | **PubMed/MEDLINE** | #26 | `eutils.ncbi.nlm.nih.gov/entrez/eutils` | API key (free) | daily | 15-20% |
| 2 | **OpenAlex** (CI) | #27 | `api.openalex.org` | none | daily | overlaps PubMed |
| 3 | **EMA Regulatory** (CI) | #28 | `medicines.ema.europa.eu` | none | weekly | 4-5% |

**Invocations**:

```bash
/add-datasource "Add PubMed/MEDLINE API fetcher for publication monitoring. API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils. Endpoints: esearch.fcgi (search), efetch.fcgi (retrieve), einfo.fcgi (database info). Free API key from NCBI increases rate limit from 3/sec to 10/sec. Daily refresh. Returns article metadata: PMID, title, abstract, authors, journal, MeSH terms, publication date. Issue #26. Doppler secret: NCBI_API_KEY."

/add-datasource "Add OpenAlex API fetcher for publication metadata and citations. API: https://api.openalex.org. Endpoints: /works (publications), /authors (researchers), /institutions, /concepts. No auth required (polite pool with mailto). Daily refresh. Returns: DOI, title, abstract, citation count, open access status, author affiliations, concept tags. Issue #27."

/add-datasource "Add EMA regulatory data fetcher for European drug approvals. CHMP opinions, EPAR documents, referrals, safety signals. API: https://www.ema.europa.eu/en/medicines/download-medicine-data. Also: https://api.ema.europa.eu/api. No auth. Weekly refresh. Note: EMAIngestion class exists in raw_ingestion.py for molecule data — this CI fetcher needs separate endpoints for regulatory decisions and committee opinions. Issue #28."
```

### Priority B — Medium Impact CI Sources

| # | Source | Issue | API URL | Auth | Frequency | CI Volume |
|---|--------|-------|---------|------|-----------|-----------|
| 4 | **Journal RSS/Atom** | #29 | configurable feeds | none | daily | 15-20% |
| 5 | **USPTO PatentsView** (CI) | #30 | `api.patentsview.org/api/v1` | API key | weekly | 2-3% |
| 6 | **HTA Bodies** | #33 | multiple (NICE, G-BA, HAS, PBAC) | varies | weekly | 3-4% |

**Invocations**:

```bash
/add-datasource "Add configurable journal RSS/Atom feed framework for medical publication monitoring. Needs to support multiple configurable feeds (NEJM, Lancet, JAMA, Nature Medicine, etc.) with per-project journal selection. Parse RSS/Atom XML, extract article metadata (title, authors, DOI, abstract, publication date). Daily refresh. No auth for most feeds. Store feed configs in meta schema. Issue #29."

/add-datasource "Add USPTO PatentsView API fetcher for US patent monitoring. API: https://api.patentsview.org/api/v1. Endpoints: /patents, /inventors, /assignees. Requires API key. Weekly refresh. Filter by CPC codes A61K (medicinal preparations), A61P (therapeutic activity), C07D (heterocyclic compounds). Track patent grants, applications, assignments. Issue #30. Doppler secret: USPTO_PATENTSVIEW_API_KEY."

/add-datasource "Add HTA body decision fetchers for health technology assessment monitoring. Multiple sources: NICE (nice.org.uk/guidance), G-BA (g-ba.de), HAS (has-sante.fr), PBAC (pbs.gov.au). Each has different access patterns (API, RSS, scraping). Weekly refresh. Track appraisal decisions, technology assessments, pricing recommendations. Issue #33."
```

### Priority C — Lower Impact CI Sources

| # | Source | Issue | API URL | Auth | Frequency | CI Volume |
|---|--------|-------|---------|------|-----------|-----------|
| 7 | **EPO OPS** | #31 | `ops.epo.org` | OAuth2 | weekly | <2% |
| 8 | **Cochrane** | #32 | `cochranelibrary.com` | API key | monthly | 2-3% |
| 9 | **Medical News** | #34 | RSS/scraping | varies | daily | 10-15% |
| 10 | **SEC EDGAR** | #35 | `efts.sec.gov/LATEST` | none | daily | 1-2% |

**Invocations**:

```bash
/add-datasource "Add EPO Open Patent Services API fetcher for European patent monitoring. API: https://ops.epo.org/3.2/rest-services. OAuth2 authentication (consumer key + secret). Weekly refresh. Endpoints: published-data/search, family, biblio. Track European pharma patents. Issue #31. Doppler secrets: EPO_CONSUMER_KEY, EPO_CONSUMER_SECRET."

/add-datasource "Add Cochrane Library fetcher for systematic reviews and network meta-analyses. Website: https://www.cochranelibrary.com. May require API key or use search interface. Monthly refresh. Track systematic reviews, NMAs, clinical answers relevant to drug comparisons. Issue #32."

/add-datasource "Add medical news aggregator framework for Medscape, Healio, FiercePharma, and similar sources. RSS feeds where available, scraping as fallback. Daily refresh. Extract headlines, summaries, drug mentions, therapeutic areas. Configurable source list stored in meta schema. Issue #34."

/add-datasource "Add SEC EDGAR API fetcher for pharmaceutical earnings and financial signals. API: https://efts.sec.gov/LATEST/search-index. No auth required. Daily refresh. Track 10-K, 10-Q, 8-K filings for pharma companies. Extract pipeline mentions, market share data from earnings transcripts. Issue #35."
```

---

## Tier 5: Computed / ML Sources — Future (6 sources)

These are not traditional data sources — they generate embeddings or predictions from existing data. They require ML infrastructure and are out of scope for `/add-datasource`.

| # | Source | Type | Depends On | Status |
|---|--------|------|------------|--------|
| 1 | ESM-2 protein embeddings | HuggingFace model | UniProt data | Not started |
| 2 | Chemprop molecular graphs | PyTorch model | PubChem/ChEMBL SMILES | Not started |
| 3 | PubMedBERT text embeddings | HuggingFace model | PubMed abstracts | Not started |
| 4 | ADMET-AI property predictions | ML model | TDC ADMET training data | Not started |
| 5 | DTI predictions | ML model | ChEMBL/BindingDB data | Not started |
| 6 | Formulation predictions | ML model | Drug formulation data | Not started |

---

## Deprecated Sources

| Source | Reason | Replacement |
|--------|--------|-------------|
| PDSP Ki Database | Server down since Dec 2025 | BindingDB |
| WHO INN (Excel) | Unreliable download | PubChem synonym lookup via `WHOINNIngestion` |

---

## Implementation Priority Order

Recommended sequence for maximum platform value:

### Sprint 1: Enable No-Blocker Molecule Sources (Tier 2A)
**Effort**: Low (code exists, just CronJobs + config)
**Sources**: BindingDB, Orange Book, SIDER, TDC ADMET, EMA
**Issues**: #44, #46, #45/#82, #49, #48

### Sprint 2: High-Impact CI Sources (Tier 4A)
**Effort**: Medium (full implementation needed)
**Sources**: PubMed/MEDLINE, OpenAlex CI, EMA Regulatory CI
**Issues**: #26, #27, #28

### Sprint 3: Additional Molecule Sources (Tier 3)
**Effort**: Low-Medium (code exists, need CronJobs + seed SQL)
**Sources**: RxNorm, DailyMed, FDA Drugs, KEGG, TTD, PharmGKB, IMGT, CDC Vaccines

### Sprint 4: Credential-Gated Sources (Tier 2B)
**Effort**: Medium (need credentials first)
**Sources**: DrugBank, USPTO Patents, PDB, ORCID
**Issues**: #41, #47/#83, #50, #51

### Sprint 5: Medium-Impact CI Sources (Tier 4B)
**Effort**: Medium-High (full implementation)
**Sources**: Journal RSS, USPTO PatentsView CI, HTA Bodies
**Issues**: #29, #30, #33

### Sprint 6: Remaining CI Sources (Tier 4C)
**Effort**: Medium-High (full implementation)
**Sources**: EPO OPS, Cochrane, Medical News, SEC EDGAR
**Issues**: #31, #32, #34, #35

### Sprint 7: Fix Broken Source
**Effort**: Variable (depends on new ACC data availability)
**Source**: acc_tvc
**Action**: Research new ACC data source or implement alternative

---

## Quick Reference: Source Counts

| Category | Count | Code Exists | CronJob Exists | Fully Active |
|----------|-------|-------------|----------------|--------------|
| Tier 0: Active | 5 | 5 | 5 | 4 (+1 broken) |
| Tier 1: Molecule Core | 6 | 6 | 6 | 6 |
| Tier 2: Deferred Molecule | 9 | 9 | 0 | 0 |
| Tier 3: Additional Molecule | 8 | 8 | 0 | 0 |
| Tier 4: CI Sources | 10 | 0 | 0 | 0 |
| Tier 5: ML/Computed | 6 | 0 | 0 | 0 |
| **Total** | **44** | **28** | **11** | **10** |

---

## Doppler Secrets Summary

All source-specific secrets go in Doppler project `dk-data-fe`, configs `prd` and `stg`:

| Secret Key | Source | Required By |
|------------|--------|-------------|
| `NCBI_API_KEY` | PubMed/MEDLINE | Tier 4A, Sprint 2 |
| `OPENFDA_API_KEY` | OpenFDA | Optional (higher rate limits) |
| `USPTO_API_KEY` | USPTO PatentsView | Tier 2B + Tier 4B |
| `EPO_CONSUMER_KEY` | EPO OPS | Tier 4C |
| `EPO_CONSUMER_SECRET` | EPO OPS | Tier 4C |
| `DRUGBANK_API_KEY` | DrugBank | Tier 2B (license required) |
| `NEWSAPI_KEY` | Medical News | Tier 4C |
| `SERPAPI_KEY` | Web Search | Tier 3 (optional) |
| `ORCID_CLIENT_ID` | ORCID | Tier 2B |
| `ORCID_CLIENT_SECRET` | ORCID | Tier 2B |

---

## CronJob Schedule Map

Existing schedules (to avoid conflicts when adding new sources):

```
Hour  Day         Job                    Source
────  ──────────  ─────────────────────  ──────────
02    Sun         fetch-cms-all          CMS + HRSA + ACC
03    1st month   fetch-cms-hospitals    CMS Hospital Info
03    1st quarter fetch-cms-inpatient    CMS Medicare Inpatient
04    1st quarter fetch-acc-tvc          ACC TVC
05    15th month  fetch-hrsa             HRSA Shortage Areas
06    Daily       catalog-refresh        All sources metadata
07    Daily       sqlmesh-run            All transforms
08    Daily       mol-fetch-daily        ClinicalTrials, OpenFDA
09    Weekly      mol-fetch-weekly       ChEMBL, PubChem, UniProt, OpenAlex
10    Daily       mol-transform          Bronze→Silver→Gold
──── AVAILABLE SLOTS ────
11    *           (available)            Tier 2A batch
12    *           (available)            Tier 3 batch
13    *           (available)            CI daily sources
14    *           (available)            CI weekly sources
15-23 *           (available)            Future sources
```
