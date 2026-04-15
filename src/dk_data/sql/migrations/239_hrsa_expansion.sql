-- Migration 239: HRSA shortage areas loader expansion (Item 27d)
-- Feature: 006-claims-engine-data-gaps
-- Adds ~9 missing columns from the HRSA HPSA/MUA datasets

BEGIN;

ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS hpsa_status_code TEXT;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS designation_history JSONB;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS provider_count INTEGER;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS primary_care_physician_count INTEGER;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS dental_provider_count INTEGER;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS mental_health_provider_count INTEGER;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS mua_status TEXT;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS mua_score NUMERIC;
ALTER TABLE hcs_raw.hrsa_shortage_areas ADD COLUMN IF NOT EXISTS withdrawn_date DATE;

COMMIT;
