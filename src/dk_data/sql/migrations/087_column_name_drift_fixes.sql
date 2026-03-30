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
-- 1. mol_bronze.chembl_molecules OR mol_bronze.chembl: chembl_id → molecule_chembl_id
--    (table may have been created as either name depending on migration order)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='chembl_molecules' AND column_name='chembl_id') THEN
        ALTER TABLE mol_bronze.chembl_molecules RENAME COLUMN chembl_id TO molecule_chembl_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='chembl' AND column_name='chembl_id') THEN
        ALTER TABLE mol_bronze.chembl RENAME COLUMN chembl_id TO molecule_chembl_id;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. mol_silver.molecules: chembl_id → molecule_chembl_id
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_silver' AND table_name='molecules' AND column_name='chembl_id') THEN
        ALTER TABLE mol_silver.molecules RENAME COLUMN chembl_id TO molecule_chembl_id;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. mol_bronze.nih_reporter: project_number → project_num
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='nih_reporter' AND column_name='project_number') THEN
        ALTER TABLE mol_bronze.nih_reporter RENAME COLUMN project_number TO project_num;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. mol_bronze.europepmc: date/year field renames
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='europepmc' AND column_name='publication_date') THEN
        ALTER TABLE mol_bronze.europepmc RENAME COLUMN publication_date TO first_publication_date;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='europepmc' AND column_name='publication_year') THEN
        ALTER TABLE mol_bronze.europepmc RENAME COLUMN publication_year TO pub_year;
    END IF;
END;
$$;

COMMIT;
