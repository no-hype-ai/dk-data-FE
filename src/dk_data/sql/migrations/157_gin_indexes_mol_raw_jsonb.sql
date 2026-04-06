-- Migration 157: GIN indexes on mol_raw response_body columns (item 4)
-- Post-backfill performance improvement. Each mol_raw table now holds millions
-- of rows; bronze models filter heavily on response_body JSONB keys/values.
-- GIN indexes accelerate these JSONB containment (@>) and key-exist (?) operators.
-- CONCURRENTLY avoids table locks so indexes build while pipelines are running.

-- Core molecule sources
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_raw_pubchem_body_gin
    ON mol_raw.pubchem USING gin(response_body);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_raw_chembl_molecules_body_gin
    ON mol_raw.chembl_molecules USING gin(response_body);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_raw_bindingdb_body_gin
    ON mol_raw.bindingdb USING gin(response_body);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_raw_sider_body_gin
    ON mol_raw.sider USING gin(response_body);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_raw_uniprot_body_gin
    ON mol_raw.uniprot USING gin(response_body);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_raw_openfda_labels_body_gin
    ON mol_raw.openfda_labels USING gin(response_body);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_raw_pdb_body_gin
    ON mol_raw.pdb USING gin(response_body);
