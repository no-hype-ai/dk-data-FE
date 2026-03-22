-- Migration: 123_create_gold_trial_outcomes.sql
-- Date: 2026-03-22
-- Description: Create mol_gold.trial_outcomes table referenced by SilverGoldRefresher.
--   This table was referenced in code but never created, causing silent failures
--   on every molecule onboarding. Column names match mol_silver.clinical_trials
--   after migration 122 alignment.

CREATE TABLE IF NOT EXISTS mol_gold.trial_outcomes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id     UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id) ON DELETE CASCADE,
    nct_id          VARCHAR(20) NOT NULL,
    endpoint_name   TEXT,
    result          TEXT,
    phase           VARCHAR(50),
    overall_status  VARCHAR(100),
    enrollment_count INTEGER,
    lead_sponsor_name TEXT,
    conditions      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_trial_outcomes_nct_id UNIQUE (nct_id)
);

CREATE INDEX IF NOT EXISTS idx_trial_outcomes_molecule_id
    ON mol_gold.trial_outcomes(molecule_id);

CREATE INDEX IF NOT EXISTS idx_trial_outcomes_nct_id
    ON mol_gold.trial_outcomes(nct_id);

GRANT SELECT ON mol_gold.trial_outcomes TO analyst;
GRANT SELECT ON mol_gold.trial_outcomes TO authenticator;
GRANT SELECT ON mol_gold.trial_outcomes TO web_anon;
