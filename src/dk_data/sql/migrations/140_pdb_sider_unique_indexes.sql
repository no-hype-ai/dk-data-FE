-- Migration 140: Add unique indexes for pdb and sider deduplication
-- Required by ON CONFLICT clauses in their loaders.

-- mol_raw.pdb deduplicates on response_body_hash (content hash of the PDB response)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_pdb_body_hash
    ON mol_raw.pdb (response_body_hash)
    WHERE response_body_hash IS NOT NULL;

-- mol_raw.sider deduplicates on request_id (compound+side-effect composite key)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_sider_request_id
    ON mol_raw.sider (request_id)
    WHERE request_id IS NOT NULL;
