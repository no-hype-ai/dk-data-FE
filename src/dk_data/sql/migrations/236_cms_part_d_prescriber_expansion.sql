-- Migration 236: Expand hcs_raw.cms_part_d_prescriber with opioid/antibiotic/branded/generic
-- metrics and beneficiary demographic breakdowns.
-- Feature: 006-claims-engine-data-gaps (T036, Item 27a)

BEGIN;

ALTER TABLE hcs_raw.cms_part_d_prescriber
    ADD COLUMN IF NOT EXISTS opioid_prescriber_rate         NUMERIC,
    ADD COLUMN IF NOT EXISTS opioid_day_supply              NUMERIC,
    ADD COLUMN IF NOT EXISTS long_acting_opioid_claims      NUMERIC,
    ADD COLUMN IF NOT EXISTS long_acting_opioid_cost        NUMERIC,
    ADD COLUMN IF NOT EXISTS antibiotic_claims              NUMERIC,
    ADD COLUMN IF NOT EXISTS antibiotic_cost                NUMERIC,
    ADD COLUMN IF NOT EXISTS branded_claims                 NUMERIC,
    ADD COLUMN IF NOT EXISTS branded_cost                   NUMERIC,
    ADD COLUMN IF NOT EXISTS generic_claims                 NUMERIC,
    ADD COLUMN IF NOT EXISTS generic_cost                   NUMERIC,
    ADD COLUMN IF NOT EXISTS beneficiary_age_65_74_count    INTEGER,
    ADD COLUMN IF NOT EXISTS beneficiary_age_75_84_count    INTEGER,
    ADD COLUMN IF NOT EXISTS beneficiary_age_85plus_count   INTEGER,
    ADD COLUMN IF NOT EXISTS beneficiary_female_count       INTEGER,
    ADD COLUMN IF NOT EXISTS beneficiary_male_count         INTEGER;

COMMIT;
