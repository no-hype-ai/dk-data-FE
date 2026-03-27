-- =============================================================================
-- Migration 087: Column Name Drift Fixes — No Aliases, Raw API Names
-- Feature: 019-cms-puf-platform-reconciliation
-- =============================================================================
-- Fixes column name drift where bronze/silver table columns were renamed from
-- the raw API field names. Policy: no drift allowed — all layers must use the
-- column names from the raw API response (camelCase→snake_case is acceptable).
--
-- Changes:
-- 1. mol_bronze.chembl_molecules: chembl_id → molecule_chembl_id
--    (raw API: molecule_chembl_id)
-- 2. mol_silver.molecules: chembl_id → molecule_chembl_id
--    (propagated from bronze; stable molecule_id UUID unaffected)
-- 3. mol_bronze.nih_reporter: project_number → project_num
--    (raw API: project_num)
-- 4. mol_bronze.europepmc: publication_date → first_publication_date,
--                          publication_year → pub_year
--    (raw API: firstPublicationDate → snake: first_publication_date;
--              pubYear → snake: pub_year)
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. mol_bronze.chembl_molecules: chembl_id → molecule_chembl_id
-- ---------------------------------------------------------------------------
ALTER TABLE mol_bronze.chembl_molecules
    RENAME COLUMN chembl_id TO molecule_chembl_id;

-- ---------------------------------------------------------------------------
-- 2. mol_silver.molecules: chembl_id → molecule_chembl_id
-- ---------------------------------------------------------------------------
ALTER TABLE mol_silver.molecules
    RENAME COLUMN chembl_id TO molecule_chembl_id;

-- ---------------------------------------------------------------------------
-- 3. mol_bronze.nih_reporter: project_number → project_num
-- ---------------------------------------------------------------------------
ALTER TABLE mol_bronze.nih_reporter
    RENAME COLUMN project_number TO project_num;

-- ---------------------------------------------------------------------------
-- 4. mol_bronze.europepmc: date/year field renames
-- ---------------------------------------------------------------------------
ALTER TABLE mol_bronze.europepmc
    RENAME COLUMN publication_date TO first_publication_date;

ALTER TABLE mol_bronze.europepmc
    RENAME COLUMN publication_year TO pub_year;

COMMIT;
