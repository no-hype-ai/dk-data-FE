-- Migration 121: mol_raw tables for 7 new molecule sources
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Creates mol_raw tables for:
--   ema, orange_book, dailymed, fda_drugs, ttd, imgt, cdc_vaccines
--
-- Also adds meta.data_sources registration for 'ema' (missed in migration 096).
--
-- Pattern: matches migration 096 standardised mol_raw schema
-- (id UUID, request_id VARCHAR UNIQUE, ..., response_body JSONB, source_id VARCHAR)

BEGIN;

-- ============================================================================
-- 1. MOL_RAW TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_raw.ema (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'ema',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'ema'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_ema_request_id
    ON mol_raw.ema(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ema_ts
    ON mol_raw.ema(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ema_bronze
    ON mol_raw.ema(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.orange_book (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'orange_book',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'orange_book'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_orange_book_request_id
    ON mol_raw.orange_book(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_orange_book_ts
    ON mol_raw.orange_book(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_orange_book_bronze
    ON mol_raw.orange_book(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.dailymed (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'dailymed',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'dailymed'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_dailymed_request_id
    ON mol_raw.dailymed(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_dailymed_ts
    ON mol_raw.dailymed(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_dailymed_bronze
    ON mol_raw.dailymed(processed_to_bronze) WHERE NOT processed_to_bronze;

-- Note: mol_raw.fda_drugsfda exists (migration 096) but targets the /drug/drugsfda endpoint.
-- mol_raw.fda_drugs is the bulk FDA drug product database (separate table, same pattern).
CREATE TABLE IF NOT EXISTS mol_raw.fda_drugs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'fda_drugs',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'fda_drugs'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_fda_drugs_request_id
    ON mol_raw.fda_drugs(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_drugs_ts
    ON mol_raw.fda_drugs(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_drugs_bronze
    ON mol_raw.fda_drugs(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.ttd (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'ttd',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'ttd'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_ttd_request_id
    ON mol_raw.ttd(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ttd_ts
    ON mol_raw.ttd(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ttd_bronze
    ON mol_raw.ttd(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.imgt (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'imgt',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'imgt'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_imgt_request_id
    ON mol_raw.imgt(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_imgt_ts
    ON mol_raw.imgt(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_imgt_bronze
    ON mol_raw.imgt(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.cdc_vaccines (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'cdc_vaccines',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'cdc_vaccines'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_cdc_vaccines_request_id
    ON mol_raw.cdc_vaccines(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cdc_vaccines_ts
    ON mol_raw.cdc_vaccines(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cdc_vaccines_bronze
    ON mol_raw.cdc_vaccines(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- 2. META.DATA_SOURCES — add 'ema' (missed in migration 096)
-- The other 6 sources (cdc_vaccines, dailymed, fda_drugs, imgt, orange_book, ttd)
-- were registered in migration 096.
-- ============================================================================

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES
    ('ema', 'api', 'https://www.ema.europa.eu', 'EMA European Public Assessment Reports (authorised medicines)', 'monthly', TRUE)
ON CONFLICT (source_name) DO UPDATE
    SET is_active         = EXCLUDED.is_active,
        source_url        = EXCLUDED.source_url,
        description       = EXCLUDED.description,
        refresh_frequency = EXCLUDED.refresh_frequency;

-- ============================================================================
-- 3. GRANTS — analyst read access
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        GRANT SELECT ON mol_raw.ema           TO analyst;
        GRANT SELECT ON mol_raw.orange_book   TO analyst;
        GRANT SELECT ON mol_raw.dailymed      TO analyst;
        GRANT SELECT ON mol_raw.fda_drugs     TO analyst;
        GRANT SELECT ON mol_raw.ttd           TO analyst;
        GRANT SELECT ON mol_raw.imgt          TO analyst;
        GRANT SELECT ON mol_raw.cdc_vaccines  TO analyst;
    END IF;
END
$$;

COMMIT;
