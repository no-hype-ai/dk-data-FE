-- Migration 157: GIN indexes on mol_raw response_body columns (item 4)
-- Post-backfill performance improvement. Each mol_raw table now holds millions
-- of rows; bronze models filter heavily on response_body JSONB keys/values.
-- GIN indexes accelerate JSONB containment (@>) and key-exist (?) operators.
--
-- NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction block, so
-- standard CREATE INDEX is used here. On a live production cluster with large
-- tables, drop and recreate with CONCURRENTLY to avoid table locks:
--   DROP INDEX IF EXISTS idx_mol_raw_pubchem_body_gin;
--   CREATE INDEX CONCURRENTLY idx_mol_raw_pubchem_body_gin ON mol_raw.pubchem USING gin(response_body);
--   (repeat for each table)

CREATE INDEX IF NOT EXISTS idx_mol_raw_pubchem_body_gin
    ON mol_raw.pubchem USING gin(response_body);

CREATE INDEX IF NOT EXISTS idx_mol_raw_chembl_molecules_body_gin
    ON mol_raw.chembl_molecules USING gin(response_body);

CREATE INDEX IF NOT EXISTS idx_mol_raw_bindingdb_body_gin
    ON mol_raw.bindingdb USING gin(response_body);

CREATE INDEX IF NOT EXISTS idx_mol_raw_sider_body_gin
    ON mol_raw.sider USING gin(response_body);

CREATE INDEX IF NOT EXISTS idx_mol_raw_uniprot_body_gin
    ON mol_raw.uniprot USING gin(response_body);

CREATE INDEX IF NOT EXISTS idx_mol_raw_openfda_labels_body_gin
    ON mol_raw.openfda_labels USING gin(response_body);

CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_body_gin
    ON mol_raw.pdb USING gin(response_body);
