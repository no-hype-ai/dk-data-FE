-- Migration 031/035: BRIN indexes on ingested_at/request_timestamp
-- Feature: 001-silver-medallion-rebuild / T160
--
-- Adds BRIN indexes on ingested_at/request_timestamp for the 5 heavy bronze tables.
-- Drops existing btree indexes on the same columns if they exist.
--
-- BRIN (Block Range INdex) is optimal for monotonically-increasing columns like
-- ingested_at: much smaller than btree, minimal WAL overhead, never bloats.

-- ----------------------------------------------------------------
-- mol_bronze.chembl_activities
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_chembl_activities_ingested_at;
CREATE INDEX IF NOT EXISTS idx_chembl_activities_ingested_brin
    ON mol_bronze.chembl_activities USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.bindingdb
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_bindingdb_ingested_at;
CREATE INDEX IF NOT EXISTS idx_bindingdb_ingested_brin
    ON mol_bronze.bindingdb USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.clinicaltrials
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_clinicaltrials_ingested_at;
CREATE INDEX IF NOT EXISTS idx_clinicaltrials_ingested_brin
    ON mol_bronze.clinicaltrials USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.pubchem
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_pubchem_ingested_at;
CREATE INDEX IF NOT EXISTS idx_pubchem_ingested_brin
    ON mol_bronze.pubchem USING BRIN (ingested_at)
    WITH (pages_per_range = 128);

-- ----------------------------------------------------------------
-- mol_bronze.chembl_molecules
-- ----------------------------------------------------------------
DROP INDEX IF EXISTS mol_bronze.idx_chembl_molecules_ingested_at;
CREATE INDEX IF NOT EXISTS idx_chembl_molecules_ingested_brin
    ON mol_bronze.chembl_molecules USING BRIN (ingested_at)
    WITH (pages_per_range = 128);
