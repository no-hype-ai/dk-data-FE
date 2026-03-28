-- Migration 100: Add ChEMBL prodrug / natural_product / usan_stem to mol_silver.molecules
-- Feature: 019-cms-puf-platform-reconciliation
-- Reason: Zero column loss policy — these LOW_QUERY_VALUE columns were not promoted to
--   silver in prior work. Now added so they are directly queryable without touching bronze.
--   Source: mol_bronze.chembl_molecules (ChEMBL sources only; NULL for PubChem / DrugBank).

BEGIN;

ALTER TABLE mol_silver.molecules
    ADD COLUMN IF NOT EXISTS prodrug         BOOLEAN,
    ADD COLUMN IF NOT EXISTS natural_product BOOLEAN,
    ADD COLUMN IF NOT EXISTS usan_stem       TEXT;

COMMENT ON COLUMN mol_silver.molecules.prodrug IS
    'ChEMBL: molecule is a prodrug (requires metabolic activation). NULL for non-ChEMBL sources.';
COMMENT ON COLUMN mol_silver.molecules.natural_product IS
    'ChEMBL: molecule is a natural product. NULL for non-ChEMBL sources.';
COMMENT ON COLUMN mol_silver.molecules.usan_stem IS
    'ChEMBL: USAN stem code identifying drug class by naming suffix (e.g. -mab, -tinib). NULL for non-ChEMBL sources.';

COMMIT;
