-- Rollback for migration 089: Entity Linking Gaps
-- Run this to undo migration 089_entity_linking_gaps.sql

BEGIN;

-- Gap 1: drop Part D Prescriber table and its meta row
DROP TABLE IF EXISTS hcs_raw.cms_part_d_prescriber;
DELETE FROM meta.data_sources WHERE source_name = 'cms_part_d_prescriber';

-- Gap 4: remove added columns from cms_open_payments
ALTER TABLE hcs_raw.cms_open_payments
    DROP COLUMN IF EXISTS covered_drug_or_biological_name_1,
    DROP COLUMN IF EXISTS covered_drug_or_biological_name_2,
    DROP COLUMN IF EXISTS covered_drug_or_biological_name_3,
    DROP COLUMN IF EXISTS covered_drug_or_biological_name_4,
    DROP COLUMN IF EXISTS covered_drug_or_biological_name_5,
    DROP COLUMN IF EXISTS associated_drug_or_biological_ndc_1,
    DROP COLUMN IF EXISTS associated_drug_or_biological_ndc_2,
    DROP COLUMN IF EXISTS associated_drug_or_biological_ndc_3,
    DROP COLUMN IF EXISTS associated_drug_or_biological_ndc_4,
    DROP COLUMN IF EXISTS associated_drug_or_biological_ndc_5,
    DROP COLUMN IF EXISTS covered_drug_name_1_normalized,
    DROP COLUMN IF EXISTS covered_drug_name_2_normalized,
    DROP COLUMN IF EXISTS covered_drug_name_3_normalized,
    DROP COLUMN IF EXISTS covered_drug_name_4_normalized,
    DROP COLUMN IF EXISTS covered_drug_name_5_normalized,
    DROP COLUMN IF EXISTS record_id;

ALTER TABLE hcs_raw.cms_open_payments
    DROP CONSTRAINT IF EXISTS cms_open_payments_record_id_year_key;

COMMIT;
