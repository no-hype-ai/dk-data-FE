-- Migration: 115_fix_openfda_pharm_class.sql
-- Date: 2026-03-21
-- Description: Fix openfda pharm_class data loss in silver layer.
--   - Add pharm_class columns to mol_silver.drug_labels
--   - Backfill from mol_bronze.openfda_labels
--   - Fix entity_linking to carry these columns through

-- ─── 1. Add pharm_class columns to mol_silver.drug_labels ────────────────────

ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_cs TEXT[];
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_epc TEXT[];
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_moa TEXT[];
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_substance_name TEXT[];

-- ─── 2. Add corresponding columns to mol_bronze.openfda_labels if missing ────

ALTER TABLE mol_bronze.openfda_labels ADD COLUMN IF NOT EXISTS openfda_substance_name TEXT[];

-- ─── 3. Backfill pharm_class from bronze to silver ───────────────────────────

UPDATE mol_silver.drug_labels dl
SET
  openfda_pharm_class_cs = b.openfda_pharm_class_cs::text[],
  openfda_pharm_class_epc = b.openfda_pharm_class_epc::text[],
  openfda_pharm_class_moa = b.openfda_pharm_class_moa::text[],
  openfda_substance_name = COALESCE(b.openfda_substance_name, dl.openfda_substance_name)
FROM mol_bronze.openfda_labels b
WHERE dl.set_id = b.set_id
AND dl.openfda_pharm_class_epc IS NULL
AND b.openfda_pharm_class_epc IS NOT NULL;

-- Also try matching by brand_name + generic_name for labels without matching set_id
UPDATE mol_silver.drug_labels dl
SET
  openfda_pharm_class_cs = b.openfda_pharm_class_cs::text[],
  openfda_pharm_class_epc = b.openfda_pharm_class_epc::text[],
  openfda_pharm_class_moa = b.openfda_pharm_class_moa::text[],
  application_number = COALESCE(dl.application_number, b.application_number),
  product_type = COALESCE(dl.product_type, b.product_type)
FROM mol_bronze.openfda_labels b
WHERE LOWER(dl.generic_name) = LOWER(b.generic_name)
AND dl.openfda_pharm_class_epc IS NULL
AND b.openfda_pharm_class_epc IS NOT NULL;

-- ─── 4. Fix application_number for labels that have it in bronze but not silver ─

UPDATE mol_silver.drug_labels dl
SET
  application_number = b.application_number,
  product_type = COALESCE(dl.product_type, b.product_type)
FROM mol_bronze.openfda_labels b
WHERE LOWER(dl.generic_name) = LOWER(b.generic_name)
AND (dl.application_number IS NULL OR dl.application_number = '')
AND b.application_number IS NOT NULL
AND b.application_number != '';

-- ─── 5. Grants ──────────────────────────────────────────────────────────────

GRANT SELECT ON mol_silver.drug_labels TO analyst;
