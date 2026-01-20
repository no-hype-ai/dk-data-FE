# Data Sources Inventory

**Generated:** 2026-01-09
**Repositories:** Pharma-Bench, trials-predictor
**Organization:** DataKinetic

---

## Executive Summary

This document catalogs all data sources and datasets used or planned across both DataKinetic pharmaceutical repositories. The data infrastructure spans **30+ external sources** providing drug information, clinical trials, adverse events, binding affinities, and regulatory guidance.

| Metric | Count |
|--------|-------|
| Total Data Sources | 30+ |
| Currently Implemented | 25 |
| Planned/TODO (Tier 3 Embeddings) | 3 |
| Planned/TODO (Tier 4 Predictions) | 3 |
| Deprecated | 1 |
| Total Database Records | ~20M+ |

### Status Legend

| Icon | Status | Description |
|------|--------|-------------|
| ✅ Loaded | Data loaded in database | |
| ✅ Ready | Loader implemented, ready to run | |
| ⚠️ API Issues | API experiencing errors | |
| 🔐 Registration | Requires free registration | |
| 📋 Schema only | Database schema defined, loader TODO | |
| 🔜 TODO | Not yet implemented | |
| ❌ Deprecated | No longer supported | |

---

## Data Sources by Category

### 1. Drug & Compound Information

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **DrugBank** | Comprehensive drug database (17.4K drugs, 2.86M DDIs, targets, pathways, products) | XML download (licensed) | trials-predictor | ✅ Loaded | License required |
| **ChEMBL** | Bioactivity database (2.73M activities, 808K compounds) | REST API | Both | ⚠️ API Issues | Server 500 errors |
| **PubChem** | Chemical compound properties (965K+ compounds) | PUG-REST API | Both | ✅ Ready | |
| **OpenFDA Drugs@FDA** | FDA drug approvals, active ingredients, brand names | REST API | Pharma-Bench | ✅ Ready | Optional API key |
| **FDA Drug Labels** | Prescribing information, indications, dosage | OpenFDA + DailyMed API | Both | ✅ Ready | |
| **DailyMed** | Structured Product Labeling (SPL) documents | REST API | Pharma-Bench | ✅ Ready | |
| **RxNorm** | Drug identifiers, NDC codes, ATC codes | NLMAPI | trials-predictor | 📋 Schema only | Loader TODO |
| **WHO INN** | International Nonproprietary Names, drug stems | Excel download | trials-predictor | ✅ Implemented | |

### 2. Binding & Activity Data

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **BindingDB** | Protein-ligand binding affinities (2.28M records) | TSV download + API | trials-predictor | ✅ Loaded | |
| **ChEMBL Activities** | Experimental Ki, IC50, EC50, Kd values | REST API | trials-predictor | ⚠️ API Issues | Server 500 errors |
| **PDBbind** | 3D protein-ligand complex structures (23.5K) | Download (registration required) | trials-predictor | 🔐 Registration | Free registration at pdbbind.org.cn |
| **PLIP** | Computed protein-ligand interactions | Python library | trials-predictor | ✅ Ready | Needs PDB files |
| **PDSP Ki Database** | Receptor binding Ki values | Web interface | trials-predictor | ❌ Deprecated | Server down Dec 2025, use BindingDB |

### 3. Adverse Events & Safety

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **SIDER** | Drug-adverse effect pairs (310K reactions, 1.4K drugs) | TSV download | trials-predictor | ✅ Loaded | NC license |
| **FAERS** | FDA Adverse Event Reporting System (100K+ events) | OpenFDA API | trials-predictor | ✅ Ready | |
| **MedDRA** | Medical Dictionary for Regulatory Activities | Via SIDER | trials-predictor | ✅ Loaded | Via SIDER integration |

### 4. Clinical Trials

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **ClinicalTrials.gov** | Trial registry (95.5K trials with outcomes) | REST API v2 | Both | ✅ Loaded | |
| **TDC TOP** | Trial Outcome Prediction dataset (17.5K trials) | PyTDC package | trials-predictor | ✅ Loaded | |

### 5. ADMET & Benchmark Data

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **TDC ADMET** | 41 ADMET benchmark endpoints (~82K records) | PyTDC package | trials-predictor | ✅ Loaded | |
| **Medicaid NADAC** | Drug acquisition cost data | REST API | Pharma-Bench | ✅ Ready | |

### 6. Regulatory Guidance

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **FDA Guidance** | FDA guidance documents (1000s) | Regulations.gov API | Pharma-Bench | ✅ Ready | API key required |
| **ICH Guidelines** | Q/E/S/M series guidelines (352 documents) | Web scraping + PDF | Pharma-Bench | ✅ Loaded | 352 local docs |

### 7. Molecular Descriptors & Embeddings (Tier 2-3)

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **RDKit Descriptors** | MW, LogP, TPSA, HBD, HBA, QED, etc. | Computed locally | trials-predictor | ✅ Ready | |
| **RDKit Fingerprints** | Morgan (2048-bit), MACCS (167-bit) | Computed locally | trials-predictor | ✅ Ready | |
| **ESM-2** | Protein sequence embeddings (1280-dim) | HuggingFace | trials-predictor | 🔜 TODO | Tier 3 |
| **Chemprop** | Molecular graph embeddings (300-dim) | PyTorch | trials-predictor | 🔜 TODO | Tier 3 |
| **PubMedBERT** | Biomedical text embeddings (768-dim) | HuggingFace | trials-predictor | 🔜 TODO | Tier 3 |

### 8. Model Predictions (Tier 4 - For Novel Compounds)

Used when experimental data is unavailable for novel compounds.

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **ADMET-AI** | ADMET property predictions | ML model | trials-predictor | 🔜 TODO | For novel compounds |
| **DTI Model** | Drug-target interaction predictions | ML model | trials-predictor | 🔜 TODO | For novel compounds |
| **Formulation Model** | Drug formulation predictions | ML model | trials-predictor | 🔜 TODO | For novel compounds |

### 9. Drug Interactions

| Source | Description | Access Method | Repository | Status | Notes |
|--------|-------------|---------------|------------|--------|-------|
| **DrugBank DDI** | Drug-drug interactions (2.86M pairs) | DrugBank XML | trials-predictor | ✅ Loaded | |
| **DDInter** | Drug-drug interaction database | Web scraping | trials-predictor | ✅ Ready | |

---

## Detailed Source Descriptions

### DrugBank (trials-predictor)

**URL:** https://go.drugbank.com/
**License:** Academic/Commercial license required
**Data File:** XML database (~1.6GB compressed)

**Tables Populated:**
| Table | Records | Description |
|-------|---------|-------------|
| drugbank_data | 17,430 | Core drug information |
| drugbank_interactions | 2,855,848 | Drug-drug interaction pairs |
| drugbank_targets | 22,697 | Drug-target relationships |
| drugbank_carriers | 964 | Drug carrier proteins |
| drugbank_enzymes | 5,898 | Metabolizing enzymes |
| drugbank_transporters | 3,516 | Drug transporters |
| drugbank_pathways | 3,780 | Metabolic pathways |
| drugbank_products | 462,851 | Commercial products |
| drugbank_patents | 12,214 | Patent information |
| drugbank_categories | 101,512 | Drug categories |
| drugbank_atc_codes | 5,656 | ATC classification |
| drugbank_snp_effects | 310 | SNP pharmacogenomics |

**Loader:** `/app/backend/src/data/load_drugbank.py`

---

### ChEMBL (Both Repositories)

**URL:** https://www.ebi.ac.uk/chembl/
**Access:** Public REST API
**Rate Limit:** 10 requests/second

**Data Provided:**
- Molecule structures and identifiers
- Bioactivity data (Ki, IC50, EC50, Kd)
- Drug mechanisms of action
- Therapeutic targets
- Drug indications

**Pharma-Bench Files:**
- `/src/integrations/drug_apis/chembl_connector.py`
- `/src/integrations/drug_apis/chembl_client.py`

**trials-predictor Files:**
- `/app/backend/src/data/comprehensive_loader.py`
- Table: `chembl_activities` (2.73M records)

---

### BindingDB (trials-predictor)

**URL:** https://www.bindingdb.org/
**Access:** TSV download + REST API
**Rate Limit:** 1 request/second

**Data Provided:**
- Protein-ligand binding affinities
- Ki, Kd, IC50, EC50 values
- 2.28M binding records
- 970K unique compounds

**Table:** `bindingdb_affinities`
**Loader:** `/app/backend/src/data/load_bindingdb.py`

---

### PubChem (Both Repositories)

**URL:** https://pubchem.ncbi.nlm.nih.gov/
**Access:** PUG-REST API
**Rate Limit:** 5 requests/second

**Data Provided:**
- Compound properties (MW, LogP, TPSA)
- Chemical structures (SMILES, InChI)
- Bioassay data
- Cross-references

**trials-predictor Files:**
- `/app/backend/src/data/load_pubchem_bulk.py`
- `/app/backend/src/data/enrich_pubchem_batch.py`
- Table: `pubchem_compounds` (965K+ records)

---

### ClinicalTrials.gov (Both Repositories)

**URL:** https://clinicaltrials.gov/
**Access:** REST API v2
**Rate Limit:** No documented limit

**Data Provided:**
- Trial registration (NCT numbers)
- Study phases (1, 2, 3, 4)
- Conditions and interventions
- Outcome measures
- Enrollment numbers
- Completion status

**Pharma-Bench Files:**
- `/src/integrations/clinical_trials/clinical_trials_service.py`
- Table: `clinical_trials_cache`

**trials-predictor Files:**
- `/app/backend/src/data/clinical_trials_loader.py`
- Table: `clinical_trials` (95.5K trials)

---

### TDC (Therapeutics Data Commons) (trials-predictor)

**URL:** https://tdcommons.ai/
**Access:** PyTDC Python package

**Datasets Used:**

| Dataset | Records | Description |
|---------|---------|-------------|
| ADMET Benchmark | ~82K | 41 ADMET endpoints |
| TOP (Trial Outcome) | 17,538 | Clinical trial outcomes by phase |

**Tables:**
- `tdc_admet_data`
- `tdc_trial_outcomes`

**Loaders:**
- `/app/backend/src/data/load_tdc_data.py`
- `/app/backend/src/data/load_tdc_admet.py`

---

### SIDER (trials-predictor)

**URL:** http://sideeffects.embl.de/
**Access:** TSV file download

**Data Provided:**
- Drug-adverse effect relationships (310K)
- Drug indications (with MedDRA/UMLS codes)
- 1,430 drugs covered

**Tables:**
- `sider_adverse_reactions`
- `sider_indications`

**Loader:** `/app/backend/src/data/external_loaders.py` (SIDERLoader)

---

### FAERS (trials-predictor)

**URL:** https://open.fda.gov/apis/drug/event/
**Access:** OpenFDA API

**Data Provided:**
- Adverse event reports (100K+)
- Drug-event associations
- Patient demographics
- Outcomes (hospitalization, death, etc.)

**Table:** `faers_events`
**Loader:** `/app/backend/src/data/external_loaders.py` (FAERSLoader)

---

### OpenFDA (Pharma-Bench)

**URL:** https://open.fda.gov/
**Access:** REST API (optional API key)
**Rate Limit:** 240 req/min (with key: 120K/day)

**Endpoints Used:**
| Endpoint | Description |
|----------|-------------|
| /drug/drugsfda | FDA drug approvals |
| /drug/ndc | National Drug Codes |
| /drug/label | Drug labeling |
| /other/substance | UNII substance data |

**Files:**
- `/src/integrations/drug_apis/openfda_connector.py`
- `/src/utils/openfda_connector.py`
- `/src/utils/fda_substance_connector.py`

---

### DailyMed (Pharma-Bench)

**URL:** https://dailymed.nlm.nih.gov/
**Access:** REST API v2

**Data Provided:**
- Structured Product Labeling (SPL)
- Drug labeling (alternative to OpenFDA)
- Pharmacological classes

**File:** `/src/utils/dailymed_connector.py`

---

### FDA Guidance Documents (Pharma-Bench)

**URL:** https://api.regulations.gov/
**Access:** Regulations.gov API (requires key)

**Data Provided:**
- FDA guidance documents
- Policy and scientific guidance
- Posted dates and status

**Files:**
- `/src/integrations/fda_guidance/fda_guidance_manager.py`
- `/config/generator/fda_guidance_mappings.yaml`
- Table: `fda_guidance_cache`

---

### ICH Guidelines (Pharma-Bench)

**URL:** https://www.ich.org/
**Access:** Web scraping + PDF parsing

**Guideline Series:**
| Series | Topic | Documents |
|--------|-------|-----------|
| Q | Quality | Drug substance/product quality |
| E | Efficacy | Clinical trial design |
| S | Safety | Non-clinical safety |
| M | Multidisciplinary | Cross-functional |

**Local Repository:** 352 documents in `/data/ich_upload/`
**Files:**
- `/src/integrations/ich_guidelines/ich_guidance_service.py`
- Table: `ich_guidelines_cache`

---

### Medicaid NADAC (Pharma-Bench)

**URL:** https://data.medicaid.gov/
**Access:** REST API

**Data Provided:**
- National Average Drug Acquisition Cost
- NDC codes
- Active ingredients
- Pricing by month/year

**File:** `/src/integrations/drug_apis/medicaid_nadac_connector.py`

---

## Database Summary

### trials-predictor Database (pharma_predictor)

**Total Records:** ~16.7M across 42 populated tables

| Category | Tables | Total Records |
|----------|--------|---------------|
| DrugBank | 12 | ~3.5M |
| Binding Data | 2 | ~5M |
| Clinical Trials | 2 | ~113K |
| Adverse Events | 3 | ~410K |
| Compounds | 2 | ~965K |
| TDC Benchmark | 2 | ~100K |
| Cross-reference | 5 | Variable |
| Computed Features | 2 | Variable |

### Pharma-Bench Database

| Category | Tables | Description |
|----------|--------|-------------|
| FDA Drug Data | 4 | Labels, products |
| Guidance Cache | 2 | FDA + ICH |
| Clinical Trials | 1 | Trial cache |
| Drug Selection | 2 | Run tracking |

---

## API Rate Limits Summary

| API | Rate Limit | Authentication |
|-----|------------|----------------|
| ChEMBL | 10/sec | None required |
| PubChem | 5/sec | None required |
| BindingDB | 1/sec | None required |
| OpenFDA | 240/min (with key) | Optional API key |
| ClinicalTrials.gov | Standard HTTP | None required |
| Regulations.gov | Standard HTTP | API key required |
| Medicaid NADAC | Standard HTTP | None required |
| RxNorm | Standard HTTP | None required |

---

## Data Quality Notes

### High-Quality Sources (Primary)
- **DrugBank**: Curated, comprehensive, requires license
- **BindingDB**: Experimental data, well-structured
- **ClinicalTrials.gov**: Authoritative registry
- **TDC**: Benchmark datasets, peer-reviewed

### Good Quality (Secondary)
- **ChEMBL**: Large but API occasionally unstable
- **PubChem**: Comprehensive but requires filtering
- **SIDER/FAERS**: Good coverage, some noise

### Planned Enhancements (Tier 3)
- **ESM-2 embeddings**: Protein sequence representation
- **Chemprop embeddings**: Molecular graph learning
- **PubMedBERT**: Biomedical text understanding

### Prediction Models (Tier 4 - For Novel Compounds)
- **ADMET-AI**: ADMET property predictions for novel compounds
- **DTI Model**: Drug-target interaction predictions
- **Formulation Model**: Drug formulation property predictions

---

## Deprecated Sources

| Source | Deprecation Date | Replacement |
|--------|-----------------|-------------|
| PDSP Ki Database | December 2025 | BindingDB |

---

## Environment Variables

### Required
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=pharma_predictor
POSTGRES_USER=pharma
POSTGRES_PASSWORD=<password>
```

### Optional (Recommended)
```env
OPENFDA_API_KEY=<key>           # Higher rate limits
REGULATIONS_GOV_API_KEY=<key>   # FDA guidance access
HF_TOKEN=<token>                # HuggingFace models
OPENAI_API_KEY=<key>            # LLM extraction
ANTHROPIC_API_KEY=<key>         # LLM extraction
```

---

## File Locations Summary

### Pharma-Bench
```
/src/integrations/drug_apis/        # Drug API connectors
/src/integrations/clinical_trials/  # Trial service
/src/integrations/fda_guidance/     # FDA guidance
/src/integrations/ich_guidelines/   # ICH service
/src/utils/                         # Utility connectors
/config/seeds/                      # Seed configurations
/config/generator/                  # Mapping configs
/data/ich_upload/                   # ICH documents
```

### trials-predictor
```
/app/backend/src/data/              # All data loaders
/app/backend/src/data/migrations/   # Database schema
/app/backend/src/data/cache/        # File cache
```

---

## Recommendations

1. **Complete Tier 3 Embeddings**: Implement ESM-2, Chemprop, and PubMedBERT loaders for enhanced feature representation

2. **PDBbind Registration**: Complete registration to access 3D structure data

3. **RxNorm Integration**: Fully implement RxNorm loader for standardized drug naming

4. **Monitor ChEMBL API**: Address intermittent 500 errors in ChEMBL API calls

5. **Data Refresh Schedule**: Establish periodic refresh for:
   - ClinicalTrials.gov (weekly)
   - FDA Labels (monthly)
   - DrugBank (quarterly with license renewal)
   - SIDER/BindingDB (semi-annually)

---

*Document generated from codebase analysis of both repositories.*
