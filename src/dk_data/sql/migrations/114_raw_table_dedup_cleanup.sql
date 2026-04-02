-- Migration 114: Raw layer deduplication cleanup
-- 
-- 1. Drop orphaned mol_raw.openalex
--    - Created by migration 020 as a generic API response table
--    - mol_bronze.openalex reads from mol_raw.openalex_ci (not this table)
--    - No loader has ever written to this table
--
-- 2. Rename mol_raw.europepmc_raw → mol_raw.europepmc
--    - Normalises naming: all mol_raw tables use plain source names, no _raw suffix
--    - Loader: src/dk_data/ingestion/sources/europepmc.py (updated)
--    - Bronze model: src/dk_data/sqlmesh/models/molecules/bronze/europepmc.sql (updated)
--
-- 3. Rename mol_raw.nih_reporter_raw → mol_raw.nih_reporter
--    - Same normalisation as europepmc
--    - Loader: src/dk_data/ingestion/sources/nih_reporter.py (updated)
--    - Bronze model: src/dk_data/sqlmesh/models/molecules/bronze/nih_reporter.sql (updated)

-- 1. Drop orphan
DROP TABLE IF EXISTS mol_raw.openalex CASCADE;

-- Remove from meta.data_sources
DELETE FROM meta.data_sources WHERE source_name = 'openalex';

-- 2. Rename europepmc
ALTER TABLE IF EXISTS mol_raw.europepmc_raw RENAME TO europepmc;

-- 3. Rename nih_reporter
ALTER TABLE IF EXISTS mol_raw.nih_reporter_raw RENAME TO nih_reporter;
