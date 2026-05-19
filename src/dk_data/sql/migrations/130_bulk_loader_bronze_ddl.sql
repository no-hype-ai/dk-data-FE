-- Migration 130: Ensure bulk-loader bronze tables exist before SQLMesh runs
--
-- mol_bronze.chembl_targets and mol_bronze.drugbank_data are populated by
-- load_chembl_bulk.py and load_drugbank.py respectively. Those scripts use
-- CREATE TABLE IF NOT EXISTS internally, but if they have not been run in a
-- fresh cluster SQLMesh plan/apply fails because silver models reference these
-- tables as external sources (_external_sources.yaml).
--
-- This migration guarantees the table DDL is applied idempotently at deploy
-- time, independent of whether the bulk loaders have run.
--
-- Refs: issue #171 C3/C4/M6

-- ChEMBL bulk-load targets (populated by load_chembl_bulk.py)
CREATE TABLE IF NOT EXISTS mol_bronze.chembl_targets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chembl_target_id VARCHAR(20),
    protein_name     TEXT,
    organism         VARCHAR(200),
    target_type      VARCHAR(50),
    uniprot_id       VARCHAR(20) UNIQUE,
    source_updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_chembl_targets_uniprot ON mol_bronze.chembl_targets(uniprot_id);
CREATE INDEX IF NOT EXISTS idx_chembl_targets_chembl  ON mol_bronze.chembl_targets(chembl_target_id);

-- DrugBank XML bulk-load data (populated by load_drugbank.py)
CREATE TABLE IF NOT EXISTS mol_bronze.drugbank_data (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drugbank_id             VARCHAR(20) UNIQUE NOT NULL,
    drug_name               TEXT,
    drug_type               VARCHAR(50),
    drug_groups             TEXT[],
    smiles                  TEXT,
    inchi_key               VARCHAR(27),
    cas_number              VARCHAR(20),
    unii                    VARCHAR(20),
    indication              TEXT,
    pharmacodynamics        TEXT,
    mechanism_of_action     TEXT,
    absorption              TEXT,
    metabolism              TEXT,
    half_life               TEXT,
    clearance               TEXT,
    pubchem_cid             VARCHAR(20),
    chembl_id               VARCHAR(20),
    kegg_id                 VARCHAR(20),
    molecular_weight        DOUBLE PRECISION,
    molecular_formula       VARCHAR(200),
    toxicity                TEXT,
    protein_binding         TEXT,
    route_of_elimination    TEXT,
    volume_of_distribution  TEXT,
    food_interactions       TEXT[],
    raw_data                JSONB,
    source_updated_at       TIMESTAMPTZ DEFAULT NOW(),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver     BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_drugbank_data_smiles  ON mol_bronze.drugbank_data(smiles)    WHERE smiles IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drugbank_data_inchi   ON mol_bronze.drugbank_data(inchi_key) WHERE inchi_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drugbank_data_pubchem ON mol_bronze.drugbank_data(pubchem_cid);
CREATE INDEX IF NOT EXISTS idx_drugbank_data_chembl  ON mol_bronze.drugbank_data(chembl_id);

-- DrugBank drug-drug interactions (populated by load_drugbank.py)
CREATE TABLE IF NOT EXISTS mol_bronze.drugbank_interactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drugbank_id_1           VARCHAR(20) NOT NULL,
    drugbank_id_2           VARCHAR(20) NOT NULL,
    drug_name_1             TEXT,
    drug_name_2             TEXT,
    interaction_description TEXT,
    inchi_key_1             VARCHAR(27),
    inchi_key_2             VARCHAR(27),
    source_updated_at       TIMESTAMPTZ DEFAULT NOW(),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(drugbank_id_1, drugbank_id_2)
);
CREATE INDEX IF NOT EXISTS idx_drugbank_interactions_drug1 ON mol_bronze.drugbank_interactions(drugbank_id_1);
CREATE INDEX IF NOT EXISTS idx_drugbank_interactions_drug2 ON mol_bronze.drugbank_interactions(drugbank_id_2);

-- DrugBank drug-target associations (populated by load_drugbank.py)
CREATE TABLE IF NOT EXISTS mol_bronze.drugbank_targets (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drugbank_id       VARCHAR(20) NOT NULL,
    target_id         VARCHAR(20),
    target_name       TEXT,
    organism          VARCHAR(200),
    uniprot_id        VARCHAR(20),
    gene_name         VARCHAR(50),
    actions           TEXT[],
    known_action      VARCHAR(10),
    general_function  TEXT,
    specific_function TEXT,
    source_updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(drugbank_id, uniprot_id)
);
CREATE INDEX IF NOT EXISTS idx_drugbank_targets_drug   ON mol_bronze.drugbank_targets(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_drugbank_targets_uniprot ON mol_bronze.drugbank_targets(uniprot_id);

-- Grant read access to analyst role
GRANT SELECT ON mol_bronze.chembl_targets         TO analyst;
GRANT SELECT ON mol_bronze.drugbank_data          TO analyst;
GRANT SELECT ON mol_bronze.drugbank_interactions  TO analyst;
GRANT SELECT ON mol_bronze.drugbank_targets       TO analyst;
