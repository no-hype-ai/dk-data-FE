-- Migration 231: Create mol_raw.fda_orphan_designation table
-- Feature: 006-claims-engine-data-gaps (T018)
-- Source: FDA Orphan Drug Designations and Approvals

BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.fda_orphan_designation (
    id                      BIGSERIAL PRIMARY KEY,
    designation_number      TEXT,
    generic_name            TEXT,
    trade_name              TEXT,
    sponsor                 TEXT,
    designation_date        DATE,
    designated_indication   TEXT,
    marketing_approval_date DATE,
    ingested_at             TIMESTAMPTZ DEFAULT NOW()
);

-- Index on designation_number for bronze model INCREMENTAL_BY_UNIQUE_KEY
CREATE INDEX IF NOT EXISTS idx_fda_orphan_designation_number
    ON mol_raw.fda_orphan_designation (designation_number);

-- Grant to mol_data_ops if the role exists (non-fatal if it doesn't)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON mol_raw.fda_orphan_designation TO mol_data_ops;
        GRANT USAGE, SELECT ON SEQUENCE mol_raw.fda_orphan_designation_id_seq TO mol_data_ops;
    END IF;
END
$$;

COMMIT;
