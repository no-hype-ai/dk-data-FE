-- Migration: 116_dailymed_hta_fix.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: DailyMed full pipeline (raw/silver) + HTA raw table in mol_raw

-- ─── DailyMed Raw Table ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mol_raw.dailymed (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name VARCHAR(500),
    response_body JSONB,
    response_status INTEGER DEFAULT 200,
    request_url TEXT,
    request_timestamp TIMESTAMPTZ DEFAULT NOW(),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dailymed_processed ON mol_raw.dailymed (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;

-- ─── DailyMed Silver Table ────────────────────────────────────────────────────
-- Entity linking: setid = drug_labels.spl_set_id

CREATE TABLE IF NOT EXISTS mol_silver.dailymed_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    setid VARCHAR(100) NOT NULL UNIQUE,  -- SPL set ID (links to drug_labels.spl_set_id)
    molecule_id UUID,                     -- filled by entity linking
    spl_version INTEGER,
    published_date VARCHAR(50),
    title VARCHAR(1000),
    brand_name VARCHAR(500),
    generic_name VARCHAR(500),
    manufacturer VARCHAR(500),
    source VARCHAR(50) DEFAULT 'dailymed',
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dailymed_labels_molecule ON mol_silver.dailymed_labels (molecule_id);
CREATE INDEX IF NOT EXISTS idx_dailymed_labels_setid ON mol_silver.dailymed_labels (setid);

-- ─── HTA Raw Table (mol_raw, replacing raw.hta_decisions) ─────────────────────

CREATE TABLE IF NOT EXISTS mol_raw.hta_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name VARCHAR(500),
    response_body JSONB,
    response_status INTEGER DEFAULT 200,
    request_url TEXT,
    request_timestamp TIMESTAMPTZ DEFAULT NOW(),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mol_raw_hta_processed ON mol_raw.hta_decisions (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;

-- ─── Sync Schedules ──────────────────────────────────────────────────────────

INSERT INTO raw.sync_schedules (source, tier, cron_expression, priority, enabled, options) VALUES
('dailymed', 'monthly', '0 6 1 * *', 'normal', true, '{"source_name":"DailyMed SPL Drug Labels","api_type":"rest","base_url":"https://dailymed.nlm.nih.gov/dailymed/services/v2","auth_type":"none","rate_limit_per_second":4,"entity_linking":{"identifier_field":"setid","identifier_type":"spl_set_id"}}'::jsonb)
ON CONFLICT (source) DO NOTHING;

-- ─── Grants ───────────────────────────────────────────────────────────────────

GRANT SELECT ON mol_raw.dailymed TO analyst;
GRANT SELECT ON mol_raw.hta_decisions TO analyst;
GRANT SELECT ON mol_silver.dailymed_labels TO analyst;
