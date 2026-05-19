-- Migration 135: CREATE TABLE IF NOT EXISTS for mol_bronze PubChem extended tables
--
-- These tables are populated by load_pubchem_extended.py (not by a SQLMesh model)
-- and referenced via LEFT JOIN in mol_bronze.pubchem. Without DDL they never exist
-- on a fresh cluster, causing those LEFT JOINs to silently NULL out all xref/bioassay/
-- synonym columns at runtime and fail SQLMesh plan if strict dependency checking is on.
--
-- Populated by:
--   mol_bronze.pubchem_xrefs      <- load_pubchem_extended.py (xref endpoint)
--   mol_bronze.pubchem_bioassays  <- load_pubchem_extended.py (bioassay endpoint)
--   mol_bronze.pubchem_synonyms   <- load_pubchem_extended.py --synonyms
--
-- Column shapes derived from mol_bronze.pubchem CTEs (cid_xrefs, cid_bioassays,
-- cid_synonyms) and the loader source.
-- Ref: issue #172 S3

CREATE TABLE IF NOT EXISTS mol_bronze.pubchem_xrefs (
    id          BIGSERIAL   PRIMARY KEY,
    cid         BIGINT      NOT NULL,
    xref_type   TEXT        NOT NULL,   -- 'DrugBank', 'ChEMBL', 'KEGG', 'UNII', 'CAS', etc.
    xref_id     TEXT        NOT NULL,
    _loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pubchem_xrefs_cid
    ON mol_bronze.pubchem_xrefs (cid);

CREATE TABLE IF NOT EXISTS mol_bronze.pubchem_bioassays (
    id          BIGSERIAL   PRIMARY KEY,
    cid         BIGINT      NOT NULL,
    aid         BIGINT      NOT NULL,   -- PubChem Assay ID
    activity    TEXT,                   -- 'Active', 'Inactive', 'Inconclusive'
    _loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (cid, aid)
);

CREATE INDEX IF NOT EXISTS idx_pubchem_bioassays_cid
    ON mol_bronze.pubchem_bioassays (cid);

CREATE TABLE IF NOT EXISTS mol_bronze.pubchem_synonyms (
    id              BIGSERIAL   PRIMARY KEY,
    cid             BIGINT      NOT NULL,
    synonym_name    TEXT        NOT NULL,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pubchem_synonyms_cid
    ON mol_bronze.pubchem_synonyms (cid);
