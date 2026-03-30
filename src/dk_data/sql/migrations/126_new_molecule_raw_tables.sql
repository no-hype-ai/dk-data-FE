-- Migration 126: Raw tables for chembl_activities, fda_rems, fda_ndc
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Three new mol_raw tables to back stubbed silver models:
--   mol_raw.chembl_activities — ChEMBL /api/data/activity page blobs
--   mol_raw.fda_rems          — FDA REMS program records (via OpenFDA drugsfda REMS search)
--   mol_raw.fda_ndc           — OpenFDA /drug/ndc product records
--
-- All tables follow the standard mol_raw pattern (migration 096 / 121).

BEGIN;

-- ============================================================================
-- 1. mol_raw.chembl_activities
-- ============================================================================
CREATE TABLE IF NOT EXISTS mol_raw.chembl_activities (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'chembl_activities',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'chembl_activities'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_chembl_activities_request_id
    ON mol_raw.chembl_activities(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_chembl_activities_ts
    ON mol_raw.chembl_activities(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_chembl_activities_bronze
    ON mol_raw.chembl_activities(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- 2. mol_raw.fda_rems
-- ============================================================================
CREATE TABLE IF NOT EXISTS mol_raw.fda_rems (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'fda_rems',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'fda_rems'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_fda_rems_request_id
    ON mol_raw.fda_rems(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_rems_ts
    ON mol_raw.fda_rems(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_rems_bronze
    ON mol_raw.fda_rems(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- 3. mol_raw.fda_ndc
-- ============================================================================
CREATE TABLE IF NOT EXISTS mol_raw.fda_ndc (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'fda_ndc',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'fda_ndc'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_fda_ndc_request_id
    ON mol_raw.fda_ndc(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_ndc_ts
    ON mol_raw.fda_ndc(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_ndc_bronze
    ON mol_raw.fda_ndc(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- 4. meta.data_sources registrations
-- ============================================================================
INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES
    ('chembl_activities', 'api', 'https://www.ebi.ac.uk/chembl/api/data/activity',
     'ChEMBL bioactivity assay measurements (IC50, Ki, EC50, etc.)', 'weekly', TRUE),
    ('fda_rems', 'api', 'https://api.fda.gov/drug/drugsfda.json',
     'FDA Risk Evaluation and Mitigation Strategy (REMS) programs', 'monthly', TRUE),
    ('fda_ndc', 'api', 'https://api.fda.gov/drug/ndc.json',
     'FDA National Drug Code directory — product_ndc to generic/brand name mapping', 'monthly', TRUE)
ON CONFLICT (source_name) DO UPDATE
    SET is_active         = EXCLUDED.is_active,
        source_url        = EXCLUDED.source_url,
        description       = EXCLUDED.description,
        refresh_frequency = EXCLUDED.refresh_frequency;

-- ============================================================================
-- 5. Grants
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        GRANT SELECT ON mol_raw.chembl_activities TO analyst;
        GRANT SELECT ON mol_raw.fda_rems          TO analyst;
        GRANT SELECT ON mol_raw.fda_ndc           TO analyst;
    END IF;
END
$$;

COMMIT;
