-- Migration 135: Fix openfda pharm_class data loss in silver layer
-- Corrected version of 115_fix_openfda_pharm_class.sql (which was never applied
-- because migration prefix 115 was taken by 115_fix_deduplication.sql).
-- Note: mol_bronze.openfda_labels is a VIEW — column adds are skipped.
--       Backfill uses actual view column names (pharm_class_epc, pharm_class_moa).

-- mol_silver.drug_labels is a SQLMesh-managed VIEW — ALTER TABLE and UPDATE are not
-- applicable. The underlying model already exposes pharm_class_epc / pharm_class_moa.
-- Only the grant is applied here.

GRANT SELECT ON mol_silver.drug_labels TO analyst;
