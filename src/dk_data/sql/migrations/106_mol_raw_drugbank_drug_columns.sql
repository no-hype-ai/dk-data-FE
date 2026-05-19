-- Migration 106: Add drug data columns to mol_raw.drugbank
-- mol_raw.drugbank was created as a generic API request-log table.
-- DrugBank XML ingestion needs flat drug columns for upsert by drugbank_id.

ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS drugbank_id  VARCHAR(20);
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS name          VARCHAR(500);
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS description   TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS cas_number    VARCHAR(50);
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS categories    TEXT[];
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS targets       JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS enzymes       JSONB;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS indication    TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS pharmacodynamics TEXT;
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS _loaded_at    TIMESTAMP DEFAULT NOW();
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS _source_file  VARCHAR(500);
ALTER TABLE mol_raw.drugbank ADD COLUMN IF NOT EXISTS _source_hash  VARCHAR(64);

-- The original API-log columns have NOT NULL constraints that prevent drug inserts.
-- Drug records don't have request_id/api_endpoint/etc — make them nullable.
ALTER TABLE mol_raw.drugbank ALTER COLUMN request_id        DROP NOT NULL;
ALTER TABLE mol_raw.drugbank ALTER COLUMN request_timestamp DROP NOT NULL;
ALTER TABLE mol_raw.drugbank ALTER COLUMN api_endpoint      DROP NOT NULL;
ALTER TABLE mol_raw.drugbank ALTER COLUMN response_status   DROP NOT NULL;
ALTER TABLE mol_raw.drugbank ALTER COLUMN response_body     DROP NOT NULL;
ALTER TABLE mol_raw.drugbank ALTER COLUMN ingested_at       DROP NOT NULL;
ALTER TABLE mol_raw.drugbank ALTER COLUMN source_id         DROP NOT NULL;

-- Unique index required for ON CONFLICT (drugbank_id) DO UPDATE.
-- Must be non-partial so PostgreSQL can match the ON CONFLICT target.
DROP INDEX IF EXISTS idx_mol_raw_drugbank_uq_drugbank_id;
CREATE UNIQUE INDEX idx_mol_raw_drugbank_uq_drugbank_id
    ON mol_raw.drugbank (drugbank_id);

CREATE INDEX IF NOT EXISTS idx_mol_raw_drugbank_name
    ON mol_raw.drugbank (name);

DO $$ BEGIN
    RAISE NOTICE 'Migration 106 complete: mol_raw.drugbank drug columns added.';
END $$;
