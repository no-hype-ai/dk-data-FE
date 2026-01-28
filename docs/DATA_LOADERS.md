# Data Loaders Reference

This document describes the available data loaders for populating the bronze layer.

## Overview

Data loaders fetch data from external sources and populate bronze layer tables. Each loader:
- Creates required tables if they don't exist
- Supports incremental loading (upsert on conflict)
- Includes progress tracking
- Handles rate limiting

## Available Loaders

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
