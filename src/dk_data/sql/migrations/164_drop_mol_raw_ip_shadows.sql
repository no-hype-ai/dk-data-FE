-- Migration 164: Drop the mol_raw.* IP shadow tables
--
-- These tables were created in migrations 096 / 137 / 152 as the original
-- landing place for IP fetchers, but the actual fetcher loaders
-- (src/dk_data/ingestion/sources/uspto_*.py, epo_ops.py, euipo_*.py) all
-- INSERT INTO ip_raw.<table>. Migration 163 created the ip_raw.* tables
-- and copied any rows that existed in mol_raw.*. The ip_bronze SQLMesh
-- models have been re-pointed to read from ip_raw.* in the same change.
--
-- This migration removes the now-unused mol_raw.* shadow tables. Apply it
-- ONLY after the SQLMesh ip_bronze.* models have been re-deployed and
-- verified to be reading from ip_raw.*.

BEGIN;

DROP TABLE IF EXISTS mol_raw.uspto_patents;
DROP TABLE IF EXISTS mol_raw.uspto_ci;
DROP TABLE IF EXISTS mol_raw.uspto_trademarks;
DROP TABLE IF EXISTS mol_raw.epo_patents;
DROP TABLE IF EXISTS mol_raw.euipo_trademarks;
DROP TABLE IF EXISTS mol_raw.euipo_designs;
DROP TABLE IF EXISTS mol_raw.trademark_status_history;

COMMIT;
