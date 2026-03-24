-- Migration 135: Fix openfda pharm_class data loss in silver layer
-- Corrected version of 115_fix_openfda_pharm_class.sql (which was never applied
-- because migration prefix 115 was taken by 115_fix_deduplication.sql).
-- Note: mol_bronze.openfda_labels is a VIEW — column adds are skipped.
--       Backfill uses actual view column names (pharm_class_epc, pharm_class_moa).

BEGIN;

-- ─── 1. Add pharm_class columns to mol_silver.drug_labels ────────────────────
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_cs  TEXT[];
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_epc TEXT[];
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_pharm_class_moa TEXT[];
ALTER TABLE mol_silver.drug_labels ADD COLUMN IF NOT EXISTS openfda_substance_name  TEXT[];

-- ─── 2. Backfill pharm_class_epc and pharm_class_moa from bronze view ─────────
-- mol_bronze.openfda_labels is a view with pharm_class_epc / pharm_class_moa as JSONB arrays.
-- Cast to TEXT[] for storage in silver.

UPDATE mol_silver.drug_labels dl
SET
    openfda_pharm_class_epc = ARRAY(SELECT jsonb_array_elements_text(b.pharm_class_epc)),
    openfda_pharm_class_moa = ARRAY(SELECT jsonb_array_elements_text(b.pharm_class_moa))
FROM mol_bronze.openfda_labels b
WHERE dl.set_id = b.set_id
  AND dl.openfda_pharm_class_epc IS NULL
  AND b.pharm_class_epc IS NOT NULL
  AND jsonb_array_length(b.pharm_class_epc) > 0;

-- Also match by generic_name for labels without a matching set_id
UPDATE mol_silver.drug_labels dl
SET
    openfda_pharm_class_epc = ARRAY(SELECT jsonb_array_elements_text(b.pharm_class_epc)),
    openfda_pharm_class_moa = ARRAY(SELECT jsonb_array_elements_text(b.pharm_class_moa)),
    application_number = COALESCE(dl.application_number, b.application_numbers->>0),
    product_type       = COALESCE(dl.product_type, b.product_type)
FROM mol_bronze.openfda_labels b
WHERE LOWER(dl.generic_name) = LOWER(b.generic_name)
  AND dl.openfda_pharm_class_epc IS NULL
  AND b.pharm_class_epc IS NOT NULL
  AND jsonb_array_length(b.pharm_class_epc) > 0;

-- ─── 3. Fix application_number / product_type gaps ────────────────────────────
UPDATE mol_silver.drug_labels dl
SET
    application_number = b.application_numbers->>0,
    product_type       = COALESCE(dl.product_type, b.product_type)
FROM mol_bronze.openfda_labels b
WHERE LOWER(dl.generic_name) = LOWER(b.generic_name)
  AND (dl.application_number IS NULL OR dl.application_number = '')
  AND b.application_numbers IS NOT NULL
  AND jsonb_array_length(b.application_numbers) > 0;

-- ─── 4. Grants ────────────────────────────────────────────────────────────────
GRANT SELECT ON mol_silver.drug_labels TO analyst;

COMMIT;
