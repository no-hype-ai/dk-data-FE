-- Migration 109: Add missing columns to mol_silver.clinical_trials and fix drug_labels clinical_studies
-- Issue: bronze has locations, primary_outcomes, secondary_outcomes but silver drops them
-- Issue: drug_labels.clinical_studies and dosage_and_administration always set to NULL in entity_linking

BEGIN;

-- 1. Add missing columns to mol_silver.clinical_trials
ALTER TABLE mol_silver.clinical_trials
  ADD COLUMN IF NOT EXISTS locations JSONB,
  ADD COLUMN IF NOT EXISTS location_countries TEXT[],
  ADD COLUMN IF NOT EXISTS primary_outcomes JSONB,
  ADD COLUMN IF NOT EXISTS secondary_outcomes JSONB,
  ADD COLUMN IF NOT EXISTS acronym VARCHAR(50),
  ADD COLUMN IF NOT EXISTS eligibility_criteria TEXT,
  ADD COLUMN IF NOT EXISTS arms JSONB;

-- 2. Backfill from bronze where data exists
UPDATE mol_silver.clinical_trials ct SET
  locations = b.locations,
  location_countries = (
    SELECT array_agg(DISTINCT country)
    FROM jsonb_array_elements(b.locations) elem,
    LATERAL (SELECT elem->>'country' AS country) sub
    WHERE country IS NOT NULL
  ),
  primary_outcomes = b.primary_outcomes,
  secondary_outcomes = b.secondary_outcomes,
  acronym = b.acronym,
  eligibility_criteria = b.eligibility_criteria,
  arms = b.arms_groups
FROM bronze.clinicaltrials b
WHERE b.nct_id = ct.nct_id
  AND (b.locations IS NOT NULL OR b.primary_outcomes IS NOT NULL OR b.secondary_outcomes IS NOT NULL);

COMMIT;
