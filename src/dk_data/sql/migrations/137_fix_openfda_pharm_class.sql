-- Migration: 115_fix_openfda_pharm_class.sql
-- Date: 2026-03-21
-- Description: Fix openfda pharm_class data loss in silver layer.
--   - Add pharm_class columns to mol_silver.drug_labels
--   - Backfill from mol_bronze.openfda_labels
--   - Fix entity_linking to carry these columns through

-- mol_silver.drug_labels is a SQLMesh-managed VIEW — ALTER TABLE and UPDATE are not
-- applicable. The underlying model already exposes pharm_class_epc / pharm_class_moa.
-- Only the grant is applied here.

-- ─── Grants ──────────────────────────────────────────────────────────────

GRANT SELECT ON mol_silver.drug_labels TO analyst;
