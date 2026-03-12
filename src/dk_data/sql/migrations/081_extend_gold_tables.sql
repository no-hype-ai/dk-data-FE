-- 081: Create gold schema tables for the silver->gold refresher.
-- The refresher (silver_gold_refresher.py) writes to gold.* tables.
-- These are separate from mol_gold.* (migration 020) which are SQLMesh-managed.
-- The gold schema is used by the MCP on-demand pipeline for per-molecule aggregation.

BEGIN;

CREATE SCHEMA IF NOT EXISTS gold;

-- gold.molecule_profile
CREATE TABLE IF NOT EXISTS gold.molecule_profile (
    molecule_id TEXT PRIMARY KEY,
    molecule_name TEXT,
    molecule_type TEXT,
    inchi_key TEXT,
    lifecycle_stage TEXT,
    lifecycle_stage_confidence NUMERIC,
    lifecycle_last_detected TIMESTAMPTZ,
    drugbank_id TEXT,
    chembl_id TEXT,
    pubchem_cid TEXT,
    pipeline_indications JSONB,
    serious_ae_count INT DEFAULT 0,
    ae_summary JSONB,
    therapeutic_area TEXT,
    mechanism_of_action TEXT,
    earliest_patent_expiry TEXT,
    patent_count INT DEFAULT 0,
    data_completeness_score NUMERIC,
    data_sources JSONB,
    last_data_update TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- gold.safety_signals
CREATE TABLE IF NOT EXISTS gold.safety_signals (
    id TEXT PRIMARY KEY,
    molecule_id TEXT NOT NULL,
    event_name TEXT,
    event_category TEXT,
    report_count INT,
    seriousness TEXT,
    outcome TEXT,
    reaction_name TEXT,
    reaction_meddra_pt TEXT,
    case_count INT,
    serious_count INT,
    fatal_count INT,
    pro_score NUMERIC,
    ror_score NUMERIC,
    is_signal BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_gold_safety_mol ON gold.safety_signals(molecule_id);

-- gold.lifecycle_stages
CREATE TABLE IF NOT EXISTS gold.lifecycle_stages (
    id TEXT PRIMARY KEY,
    molecule_id TEXT NOT NULL,
    stage TEXT,
    event_type TEXT,
    indication TEXT,
    stage_confidence NUMERIC,
    evidence_count INT,
    primary_evidence_type TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (molecule_id, indication)
);

-- gold.competitive_landscape
CREATE TABLE IF NOT EXISTS gold.competitive_landscape (
    id TEXT PRIMARY KEY,
    molecule_id TEXT,
    indication TEXT,
    total_molecules INT,
    phase_3_count INT,
    phase_2_count INT,
    phase_1_count INT,
    snapshot_date DATE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (indication, snapshot_date)
);

-- gold.trial_outcomes
CREATE TABLE IF NOT EXISTS gold.trial_outcomes (
    id TEXT PRIMARY KEY,
    molecule_id TEXT NOT NULL,
    nct_id TEXT,
    endpoint_name TEXT,
    result TEXT,
    phase TEXT,
    status TEXT,
    enrollment INT,
    sponsor TEXT,
    conditions JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (nct_id)
);
CREATE INDEX IF NOT EXISTS idx_gold_trial_mol ON gold.trial_outcomes(molecule_id);

-- Grants (web_anon excluded per security policy — migration 077, commit 4b78e3c)
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'dk_app') THEN
        GRANT USAGE ON SCHEMA gold TO dk_app;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA gold TO dk_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT, INSERT, UPDATE ON TABLES TO dk_app;
    END IF;

    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        GRANT USAGE ON SCHEMA gold TO analyst;
        GRANT SELECT ON ALL TABLES IN SCHEMA gold TO analyst;
        ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO analyst;
    END IF;

    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        GRANT USAGE ON SCHEMA gold TO authenticator;
        GRANT SELECT ON ALL TABLES IN SCHEMA gold TO authenticator;
    END IF;
END $$;

COMMIT;
