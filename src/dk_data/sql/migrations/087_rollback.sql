-- =============================================================================
-- Migration 087 ROLLBACK: Restore original column names
-- =============================================================================

BEGIN;

ALTER TABLE mol_bronze.chembl_molecules
    RENAME COLUMN molecule_chembl_id TO chembl_id;

ALTER TABLE mol_silver.molecules
    RENAME COLUMN molecule_chembl_id TO chembl_id;

ALTER TABLE mol_bronze.nih_reporter
    RENAME COLUMN project_num TO project_number;

ALTER TABLE mol_bronze.europepmc
    RENAME COLUMN first_publication_date TO publication_date;

ALTER TABLE mol_bronze.europepmc
    RENAME COLUMN pub_year TO publication_year;

COMMIT;
