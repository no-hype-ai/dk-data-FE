-- =============================================================================
-- Migration 087 ROLLBACK: Restore original column names
-- Idempotent: only renames if the source column name still exists
-- =============================================================================

BEGIN;

DO $$
BEGIN
    -- chembl_molecules: molecule_chembl_id -> chembl_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='chembl_molecules'
               AND column_name='molecule_chembl_id') THEN
        ALTER TABLE mol_bronze.chembl_molecules RENAME COLUMN molecule_chembl_id TO chembl_id;
    END IF;

    -- mol_silver.molecules: molecule_chembl_id -> chembl_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_silver' AND table_name='molecules'
               AND column_name='molecule_chembl_id') THEN
        ALTER TABLE mol_silver.molecules RENAME COLUMN molecule_chembl_id TO chembl_id;
    END IF;

    -- nih_reporter: project_num -> project_number
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='nih_reporter'
               AND column_name='project_num') THEN
        ALTER TABLE mol_bronze.nih_reporter RENAME COLUMN project_num TO project_number;
    END IF;

    -- europepmc: first_publication_date -> publication_date
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='europepmc'
               AND column_name='first_publication_date') THEN
        ALTER TABLE mol_bronze.europepmc RENAME COLUMN first_publication_date TO publication_date;
    END IF;

    -- europepmc: pub_year -> publication_year
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_bronze' AND table_name='europepmc'
               AND column_name='pub_year') THEN
        ALTER TABLE mol_bronze.europepmc RENAME COLUMN pub_year TO publication_year;
    END IF;
END $$;

COMMIT;
