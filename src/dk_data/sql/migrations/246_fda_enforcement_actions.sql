-- Migration 246: mol_raw FDA enforcement action tables
-- 5 tables: warning letters, untitled letters, 483 observations,
-- dear HCP letters, complete response letters (CRLs).
-- Feature: 006-claims-engine-data-gaps (T072)

BEGIN;

-- ============================================================
-- 1. FDA Warning Letters
-- ============================================================
CREATE TABLE IF NOT EXISTS mol_raw.fda_warning_letters (
    id                    BIGSERIAL PRIMARY KEY,
    letter_id             TEXT,
    letter_date           DATE,
    company_name          TEXT,
    company_address       TEXT,
    subject               TEXT,
    issuing_office        TEXT,
    response_letter_url   TEXT,
    closeout_letter_url   TEXT,
    full_text             TEXT,
    drug_mentions         JSONB,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_warning_letters_company
    ON mol_raw.fda_warning_letters (company_name);

-- ============================================================
-- 2. FDA Untitled Letters
-- ============================================================
CREATE TABLE IF NOT EXISTS mol_raw.fda_untitled_letters (
    id                    BIGSERIAL PRIMARY KEY,
    letter_id             TEXT,
    letter_date           DATE,
    company_name          TEXT,
    company_address       TEXT,
    subject               TEXT,
    issuing_office        TEXT,
    response_letter_url   TEXT,
    closeout_letter_url   TEXT,
    full_text             TEXT,
    drug_mentions         JSONB,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_untitled_letters_company
    ON mol_raw.fda_untitled_letters (company_name);

-- ============================================================
-- 3. FDA 483 Observations
-- ============================================================
CREATE TABLE IF NOT EXISTS mol_raw.fda_483_observations (
    id                    BIGSERIAL PRIMARY KEY,
    observation_id        TEXT,
    inspection_date       DATE,
    company_name          TEXT,
    facility              TEXT,
    observations          JSONB,
    full_text             TEXT,
    drug_mentions         JSONB,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_483_observations_company
    ON mol_raw.fda_483_observations (company_name);

-- ============================================================
-- 4. FDA Dear Healthcare Professional Letters
-- ============================================================
CREATE TABLE IF NOT EXISTS mol_raw.fda_dear_hcp_letters (
    id                    BIGSERIAL PRIMARY KEY,
    letter_id             TEXT,
    letter_date           DATE,
    company_name          TEXT,
    subject               TEXT,
    drug_name             TEXT,
    full_text             TEXT,
    drug_mentions         JSONB,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_dear_hcp_letters_company
    ON mol_raw.fda_dear_hcp_letters (company_name);

-- ============================================================
-- 5. FDA Complete Response Letters (CRLs)
-- ============================================================
CREATE TABLE IF NOT EXISTS mol_raw.fda_crls (
    id                    BIGSERIAL PRIMARY KEY,
    crl_id                TEXT,
    crl_date              DATE,
    company_name          TEXT,
    drug_name             TEXT,
    application_number    TEXT,
    reason                TEXT,
    full_text             TEXT,
    drug_mentions         JSONB,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_crls_company
    ON mol_raw.fda_crls (company_name);

-- ============================================================
-- Grants to mol_data_ops
-- ============================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_warning_letters    TO mol_data_ops;
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_untitled_letters   TO mol_data_ops;
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_483_observations   TO mol_data_ops;
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_dear_hcp_letters   TO mol_data_ops;
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_crls               TO mol_data_ops;

        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_warning_letters_id_seq    TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_untitled_letters_id_seq   TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_483_observations_id_seq   TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_dear_hcp_letters_id_seq   TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_crls_id_seq              TO mol_data_ops;
    END IF;
END
$$;

COMMIT;
