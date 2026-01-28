"""
Data loaders for external pharmaceutical and scientific data sources.

Available loaders:

Regulatory & Approved Drugs:
- load_orange_book: FDA Orange Book data (approved products, patents, exclusivities)
- load_ema: EMA authorized medicines
- load_drugbank: DrugBank database (drugs, interactions, targets)
- load_openfda_labels: OpenFDA drug labels (SPL/structured product labeling)
- load_openfda_faers: OpenFDA FAERS adverse event reports

Chemical & Molecular Data:
- load_bindingdb: BindingDB binding affinity data
- load_tdc_data: TDC ADMET datasets with molecular descriptors
- load_tdc_admet: TDC ADMET benchmark datasets with Y labels
- load_pubchem_bulk: PubChem compound properties (bulk loader)
- load_pubchem_extended: PubChem bioassays, xrefs, safety data
- load_chembl_bulk: ChEMBL activities from SQLite bulk download
- load_chembl_extended: ChEMBL mechanisms, indications, warnings

Protein & Target Data:
- load_uniprot: Protein targets from UniProt
- load_pdb: Protein structures from RCSB PDB

Clinical & Safety Data:
- load_clinicaltrials: ClinicalTrials.gov clinical trial data
- load_sider: SIDER side effects and drug indications

Patent & Publication Data:
- load_uspto_patents: USPTO patent data (requires API key)
- load_openalex: Scientific publications from OpenAlex

Usage:
    # Regulatory data
    python -m dk_data.data.load_orange_book --download
    python -m dk_data.data.load_ema --download
    python -m dk_data.data.load_drugbank --xml /path/to/drugbank.xml
    python -m dk_data.data.load_openfda_labels --limit 5000
    python -m dk_data.data.load_openfda_faers --limit 10000

    # Chemical data
    python -m dk_data.data.load_bindingdb /path/to/BindingDB_All.tsv
    python -m dk_data.data.load_tdc_data
    python -m dk_data.data.load_tdc_admet
    python -m dk_data.data.load_pubchem_bulk --limit 1000
    python -m dk_data.data.load_pubchem_extended --all
    python -m dk_data.data.load_chembl_bulk
    python -m dk_data.data.load_chembl_extended

    # Protein data
    python -m dk_data.data.load_uniprot --mode drug-targets
    python -m dk_data.data.load_pdb --mode drug-targets

    # Clinical & Safety
    python -m dk_data.data.load_clinicaltrials --limit 10000
    python -m dk_data.data.load_sider --download

    # Patents & Publications
    python -m dk_data.data.load_uspto_patents --mode drugs
    python -m dk_data.data.load_openalex --mode drugs --limit 100
"""
