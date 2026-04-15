-- Migration 237: CMS Hospital General Info loader expansion (Item 27b)
-- Feature: 006-claims-engine-data-gaps
-- Adds ~15 per-measure quality rating columns from Hospital Compare

BEGIN;

ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS mortality_heart_attack TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS mortality_heart_failure TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS mortality_pneumonia TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS mortality_stroke TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS mortality_copd TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS readmission_heart_attack TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS readmission_heart_failure TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS readmission_pneumonia TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS readmission_stroke TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS safety_of_care_rating TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS patient_experience_rating TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS timeliness_of_care_rating TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS efficient_use_of_imaging TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS hai_rate TEXT;
ALTER TABLE hcs_raw.cms_hospital_general_info ADD COLUMN IF NOT EXISTS overall_rating TEXT;

COMMIT;
