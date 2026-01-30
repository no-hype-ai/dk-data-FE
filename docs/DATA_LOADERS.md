# Data Loaders Reference

This document describes the available data loaders for populating the bronze layer.

## Overview

Data loaders fetch data from external sources and populate bronze layer tables. Each loader:
- Creates required tables if they don't exist
- Supports incremental loading (upsert on conflict)
- Includes progress tracking
- Handles rate limiting

## Quick Reference

| Loader | Data Source | Tables | Priority |
|--------|-------------|--------|----------|
| `load_clinicaltrials` | ClinicalTrials.gov | `bronze.clinicaltrials` | Critical |
| `load_openfda_faers` | OpenFDA FAERS | `bronze.openfda_faers` | Critical |
| `load_openfda_labels` | OpenFDA Labels | `bronze.openfda_labels` | High |
| `load_orange_book` | FDA Orange Book | `bronze.orange_book_*` | High |
| `load_ema` | EMA | `bronze.ema` | High |
| `load_drugbank` | DrugBank | `bronze.drugbank_*` | High |
| `load_chembl_bulk` | ChEMBL | `bronze.chembl_activities` | High |
| `load_chembl_extended` | ChEMBL | `bronze.chembl_drug_*` | Medium |
| `load_pubchem_bulk` | PubChem | `bronze.pubchem_compounds` | High |
| `load_pubchem_extended` | PubChem | `bronze.pubchem_*` | Medium |
| `load_bindingdb` | BindingDB | `bronze.bindingdb_affinities` | High |
| `load_sider` | SIDER | `bronze.sider_*` | High |
| `load_tdc_data` | TDC | `bronze.tdc_*` | Medium |
| `load_tdc_admet` | TDC | `bronze.tdc_admet_*` | Medium |
| `load_uniprot` | UniProt | `bronze.uniprot` | Medium |
| `load_pdb` | RCSB PDB | `bronze.pdb` | Medium |
| `load_uspto_patents` | USPTO | `bronze.uspto_patents` | High |
| `load_openalex` | OpenAlex | `bronze.openalex` | Medium |

## Available Loaders

### Clinical & Safety Data

#### `load_clinicaltrials.py` - ClinicalTrials.gov

Loads clinical trial data from ClinicalTrials.gov API v2.

```bash
# Load all trials (paginated)
python -m dk_data.data.load_clinicaltrials

# Search by condition
python -m dk_data.data.load_clinicaltrials --condition "diabetes"

# Search by drug
python -m dk_data.data.load_clinicaltrials --intervention "metformin"

# Limit records
python -m dk_data.data.load_clinicaltrials --limit 10000
```

**Tables**:
- `bronze.clinicaltrials`

**Data Source**: https://clinicaltrials.gov/

---

#### `load_openfda_faers.py` - FDA Adverse Events

Loads adverse event reports from OpenFDA FAERS API.

```bash
# Load all recent events
python -m dk_data.data.load_openfda_faers --limit 10000

# Filter by drug
python -m dk_data.data.load_openfda_faers --drug "aspirin"

# Filter by reaction
python -m dk_data.data.load_openfda_faers --reaction "headache"

# Only serious events
python -m dk_data.data.load_openfda_faers --serious
```

**Tables**:
- `bronze.openfda_faers`

**Data Source**: https://open.fda.gov/apis/drug/event/

**Environment**: `OPENFDA_API_KEY` (optional, for higher rate limits)

---

#### `load_openfda_labels.py` - FDA Drug Labels

Loads structured product labeling (SPL) from OpenFDA.

```bash
# Load all labels
python -m dk_data.data.load_openfda_labels --limit 5000

# Filter by drug
python -m dk_data.data.load_openfda_labels --drug "lipitor"

# Filter by manufacturer
python -m dk_data.data.load_openfda_labels --manufacturer "pfizer"
```

**Tables**:
- `bronze.openfda_labels`

**Data Source**: https://open.fda.gov/apis/drug/label/

**Environment**: `OPENFDA_API_KEY` (optional)

---

#### `load_sider.py` - SIDER Side Effects

Loads side effects and indications from SIDER database.

```bash
# Download and load all SIDER data
python -m dk_data.data.load_sider --download

# Load from existing files
python -m dk_data.data.load_sider --data-dir /path/to/sider

# Load only side effects
python -m dk_data.data.load_sider --side-effects-only
```

**Tables**:
- `bronze.sider_drugs`
- `bronze.sider_side_effects`
- `bronze.sider_indications`
- `bronze.sider_frequencies`

**Data Source**: http://sideeffects.embl.de/

---

### Regulatory & Approved Drugs

#### `load_orange_book.py` - FDA Orange Book

Loads FDA-approved drug products, patents, and exclusivities.

```bash
# Download and load
python -m dk_data.data.load_orange_book --download

# Search products
python -m dk_data.data.load_orange_book --search "lipitor"

# Limit records
python -m dk_data.data.load_orange_book --limit 1000
```

**Tables**:
- `bronze.orange_book_products`
- `bronze.orange_book_patents`
- `bronze.orange_book_exclusivities`

**Data Source**: https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files

---

#### `load_ema.py` - EMA Medicines

Loads European Medicines Agency authorized medicines.

```bash
# Download and load
python -m dk_data.data.load_ema --download

# Load from cache
python -m dk_data.data.load_ema
```

**Tables**:
- `bronze.ema`

**Data Source**: https://www.ema.europa.eu/en/medicines/download-medicine-data

---

#### `load_drugbank.py` - DrugBank Database

Loads DrugBank XML database including drugs, interactions, and targets.

```bash
# Load all data
python -m dk_data.data.load_drugbank --xml /path/to/full_database.xml

# Drugs only (skip interactions)
python -m dk_data.data.load_drugbank --xml /path/to/full_database.xml --drugs-only

# Test with limit
python -m dk_data.data.load_drugbank --xml /path/to/full_database.xml --limit 100
```

**Tables**:
- `bronze.drugbank_data`
- `bronze.drugbank_interactions`
- `bronze.drugbank_targets`

**Data Source**: https://go.drugbank.com/releases/latest (requires license)

---

### Chemical & Molecular Data

#### `load_chembl_bulk.py` - ChEMBL Bulk Loader

Loads ChEMBL bioactivity data from the bulk SQLite download (~3GB).

```bash
# Download and load ChEMBL data
python -m dk_data.data.load_chembl_bulk

# Just download the database
python -m dk_data.data.load_chembl_bulk --download-only

# Load all activities (standalone, ~20M records)
python -m dk_data.data.load_chembl_bulk --standalone

# Limit activities
python -m dk_data.data.load_chembl_bulk --limit 100000
```

**Tables**:
- `bronze.chembl_activities`
- `bronze.chembl_targets`

**Data Source**: https://www.ebi.ac.uk/chembl/

**Requirements**: `pip install chembl-downloader`

---

#### `load_chembl_extended.py` - ChEMBL Extended Data

Loads additional ChEMBL tables: mechanisms, indications, warnings.

```bash
# Load all extended tables
python -m dk_data.data.load_chembl_extended

# Load specific table
python -m dk_data.data.load_chembl_extended --table drug_mechanism

# List available tables
python -m dk_data.data.load_chembl_extended --list-tables
```

**Tables**:
- `bronze.chembl_drug_mechanism`
- `bronze.chembl_drug_indication`
- `bronze.chembl_drug_warning`
- `bronze.chembl_component_sequences`

**Data Source**: https://www.ebi.ac.uk/chembl/

---

#### `load_pubchem_bulk.py` - PubChem Bulk Loader

Bulk loads PubChem compound properties using FTP mapping files.

```bash
# Download mapping and load
python -m dk_data.data.load_pubchem_bulk

# Download only
python -m dk_data.data.load_pubchem_bulk --download-only

# Limit compounds
python -m dk_data.data.load_pubchem_bulk --limit 10000
```

**Tables**:
- `bronze.pubchem_compounds`

**Data Source**: https://pubchem.ncbi.nlm.nih.gov/

---

#### `load_pubchem_extended.py` - PubChem Extended Data

Loads PubChem bioassays, cross-references, and safety data.

```bash
# Load all data types
python -m dk_data.data.load_pubchem_extended --all

# Load specific types
python -m dk_data.data.load_pubchem_extended --bioassays --limit 1000
python -m dk_data.data.load_pubchem_extended --xrefs --limit 1000
python -m dk_data.data.load_pubchem_extended --safety --limit 1000
```

**Tables**:
- `bronze.pubchem_bioassays`
- `bronze.pubchem_xrefs`
- `bronze.pubchem_safety`
- `bronze.pubchem_pharmacology`

**Data Source**: https://pubchem.ncbi.nlm.nih.gov/

---

#### `load_bindingdb.py` - BindingDB

Loads binding affinity data (Ki, IC50, Kd, EC50).

```bash
# Load from TSV
python -m dk_data.data.load_bindingdb /path/to/BindingDB_All.tsv

# Limit rows
python -m dk_data.data.load_bindingdb --max-rows 100000
```

**Tables**:
- `bronze.bindingdb_affinities`

**Data Source**: https://www.bindingdb.org/rwd/bind/index.jsp

---

#### `load_tdc_data.py` - TDC ADMET Datasets

Loads Therapeutics Data Commons datasets with molecular descriptors.

```bash
# Load all datasets
python -m dk_data.data.load_tdc_data

# Load specific category
python -m dk_data.data.load_tdc_data --category absorption

# Load specific dataset
python -m dk_data.data.load_tdc_data --dataset Caco2_Wang
```

**Tables**:
- `bronze.tdc_datasets`
- `bronze.tdc_compounds`
- `bronze.compounds` (shared)

**Data Source**: https://tdcommons.ai/

**Requirements**: `pip install PyTDC rdkit`

---

#### `load_tdc_admet.py` - TDC ADMET Benchmarks

Loads all 22 TDC ADMET benchmark datasets with Y labels and scaffold splits.

```bash
# Load all 22 datasets
python -m dk_data.data.load_tdc_admet

# Load specific datasets
python -m dk_data.data.load_tdc_admet --datasets caco2_wang hia_hou herg

# Show dataset information
python -m dk_data.data.load_tdc_admet --info
```

**Tables**:
- `bronze.tdc_admet_datasets`
- `bronze.tdc_admet_values`

**Available Datasets**:
- Absorption: caco2_wang, hia_hou, pgp_broccatelli, bioavailability_ma
- Distribution: bbb_martins, ppbr_az, vdss_lombardo
- Metabolism: cyp2c9_veith, cyp2d6_veith, cyp3a4_veith, half_life_obach, clearance_*
- Toxicity: herg, ames, dili, ld50_zhu
- Physicochemical: lipophilicity_astrazeneca, solubility_aqsoldb

**Data Source**: https://tdcommons.ai/

**Requirements**: `pip install PyTDC rdkit`

---

### Protein & Target Data

#### `load_uniprot.py` - UniProt Proteins

Loads protein target data from UniProt.

```bash
# Drug targets
python -m dk_data.data.load_uniprot --mode drug-targets

# By gene names
python -m dk_data.data.load_uniprot --mode genes --genes EGFR,VEGFA

# Human reviewed proteins
python -m dk_data.data.load_uniprot --mode human-reviewed --limit 1000
```

**Tables**:
- `bronze.uniprot`

**Data Source**: https://www.uniprot.org/

---

#### `load_pdb.py` - Protein Structures

Loads protein structure data from RCSB PDB.

```bash
# Drug-target structures
python -m dk_data.data.load_pdb --mode drug-targets

# By UniProt accessions
python -m dk_data.data.load_pdb --mode uniprot --accessions P05112,P01308
```

**Tables**:
- `bronze.pdb`

**Data Source**: https://www.rcsb.org/

---

### Patent & Publication Data

#### `load_uspto_patents.py` - USPTO Patents

Loads patent data from USPTO PatentsView API.

```bash
# Patents for drugs
python -m dk_data.data.load_uspto_patents --mode drugs

# By assignee
python -m dk_data.data.load_uspto_patents --mode assignee --assignee "Pfizer"

# Recent pharma patents
python -m dk_data.data.load_uspto_patents --mode recent --days 365
```

**Tables**:
- `bronze.uspto_patents`

**Data Source**: https://patentsview.org/

**Requirements**: `PATENTSVIEW_API_KEY` environment variable

---

#### `load_openalex.py` - Scientific Publications

Loads scientific publications from OpenAlex.

```bash
# Publications for drugs
python -m dk_data.data.load_openalex --mode drugs

# By concept
python -m dk_data.data.load_openalex --mode concept --concept C89423630

# Recent publications
python -m dk_data.data.load_openalex --mode recent --days 30
```

**Tables**:
- `bronze.openalex`

**Data Source**: https://openalex.org/

---

## Environment Variables

All loaders use these database connection settings:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=dk_data
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

Some loaders require additional credentials:

```bash
# USPTO PatentsView
PATENTSVIEW_API_KEY=your-api-key

# OpenAlex (optional, for polite pool)
OPENALEX_EMAIL=your-email@example.com
```

## Adding New Loaders

To add a new data loader:

1. Create `load_<source>.py` in `dk_data/data/`
2. Follow the pattern:
   ```python
   def ensure_tables(conn): ...
   def load_data(conn, ...): ...
   def main(): ...
   ```
3. Add entry to `dk_data/data/__init__.py`
4. Register in `raw.sync_schedules` for scheduling
