-- Migration 102: Fix schema mismatches for cms_ddinter, cms_stabilis, cms_usp,
-- cms_chronic_conditions, and cms_formulary.
-- The raw table schemas diverged from what the fetchers/loaders actually produce.
-- This migration aligns the DB with the loader INSERT statements.
--
-- Part of: 016-cms-puf-datasource-integration

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. hcs_raw.cms_ddinter — fetcher returns interaction_type + severity,
--    but the table had interaction_level (and no severity column).
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE hcs_raw.cms_ddinter
    ADD COLUMN IF NOT EXISTS interaction_type TEXT,
    ADD COLUMN IF NOT EXISTS severity TEXT;

-- Migrate any existing data from old column
UPDATE hcs_raw.cms_ddinter
    SET interaction_type = interaction_level
    WHERE interaction_level IS NOT NULL
      AND interaction_type IS NULL;

-- Drop dependent views before dropping the old column
DROP VIEW IF EXISTS hcs_gold.cms_ddinter CASCADE;

ALTER TABLE hcs_raw.cms_ddinter
    DROP COLUMN IF EXISTS interaction_level;


-- ═══════════════════════════════════════════════════════════════════════════
-- 2. hcs_raw.cms_stabilis — fetcher scrapes drug-drug compatibility pairs,
--    but the table was designed for single-drug stability data.
--    Recreate with the correct schema matching the fetcher output.
-- ═══════════════════════════════════════════════════════════════════════════

DROP TABLE IF EXISTS hcs_raw.cms_stabilis CASCADE;

CREATE TABLE hcs_raw.cms_stabilis (
    drug_a                  TEXT NOT NULL,
    drug_b                  TEXT NOT NULL,
    compatibility           TEXT,
    solvent                 TEXT,
    concentration           TEXT,
    reference               TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (drug_a, drug_b)
);


-- ═══════════════════════════════════════════════════════════════════════════
-- 3. hcs_raw.cms_usp — fetcher returns drug_names (plural, comma-separated),
--    but the table had drug_name (singular) + ndc.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE hcs_raw.cms_usp
    ADD COLUMN IF NOT EXISTS drug_names TEXT;

UPDATE hcs_raw.cms_usp
    SET drug_names = drug_name
    WHERE drug_name IS NOT NULL
      AND drug_names IS NULL;


-- ═══════════════════════════════════════════════════════════════════════════
-- 4. hcs_raw.cms_chronic_conditions — loader uses total_beneficiaries_with_condition
--    and per_capita_spending, but the table had bene_count + year as PK.
--    Loader ON CONFLICT is (state, condition), not (state, condition, year).
-- ═══════════════════════════════════════════════════════════════════════════

-- Add the columns the loader expects
ALTER TABLE hcs_raw.cms_chronic_conditions
    ADD COLUMN IF NOT EXISTS total_beneficiaries_with_condition INTEGER,
    ADD COLUMN IF NOT EXISTS per_capita_spending NUMERIC;

-- Migrate existing data from old column name
UPDATE hcs_raw.cms_chronic_conditions
    SET total_beneficiaries_with_condition = bene_count
    WHERE bene_count IS NOT NULL
      AND total_beneficiaries_with_condition IS NULL;

-- Drop the old PK (state, condition, year) and replace with (state, condition)
-- to match the loader's ON CONFLICT clause
ALTER TABLE hcs_raw.cms_chronic_conditions DROP CONSTRAINT IF EXISTS cms_chronic_conditions_pkey;
ALTER TABLE hcs_raw.cms_chronic_conditions
    ADD CONSTRAINT cms_chronic_conditions_pkey PRIMARY KEY (state, condition);


-- ═══════════════════════════════════════════════════════════════════════════
-- 5. hcs_raw.cms_formulary — loader uses (contract_id, plan_id, rxcui) PK with
--    drug_name, prior_auth (TEXT), but table had (formulary_id, ndc) PK
--    with prior_authorization (BOOLEAN).
--    Recreate to match the loader INSERT.
-- ═══════════════════════════════════════════════════════════════════════════

DROP TABLE IF EXISTS hcs_raw.cms_formulary CASCADE;

CREATE TABLE hcs_raw.cms_formulary (
    contract_id             TEXT,
    plan_id                 TEXT,
    formulary_id            TEXT,
    rxcui                   TEXT NOT NULL,
    drug_name               TEXT,
    tier_level              TEXT,
    prior_auth              TEXT,
    step_therapy            TEXT,
    quantity_limit           TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT,
    PRIMARY KEY (contract_id, plan_id, rxcui)
);

CREATE INDEX IF NOT EXISTS idx_cms_formulary_rxcui ON hcs_raw.cms_formulary (rxcui);


-- ═══════════════════════════════════════════════════════════════════════════
-- 6. Update gold views to match new schemas
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW hcs_gold.cms_ddinter AS
SELECT
    drug_a,
    drug_b,
    interaction_type,
    severity,
    description,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_ddinter;

CREATE OR REPLACE VIEW hcs_gold.cms_stabilis AS
SELECT
    drug_a,
    drug_b,
    compatibility,
    solvent,
    concentration,
    reference,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_stabilis;

CREATE OR REPLACE VIEW hcs_gold.cms_formulary AS
SELECT
    contract_id,
    plan_id,
    formulary_id,
    rxcui,
    drug_name,
    tier_level,
    prior_auth,
    step_therapy,
    quantity_limit,
    _loaded_at AS last_refreshed
FROM hcs_raw.cms_formulary;

COMMIT;
