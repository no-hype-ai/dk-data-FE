-- Migration: 096_missing_mol_raw_tables.sql
-- Purpose: Ensure all mol_raw tables referenced by bronze SQLMesh models exist.
--
-- Two categories:
--   1. Tables that were created in raw.* by earlier migrations but never moved to
--      mol_raw.* (SQLMesh maps raw → mol_raw, so physical tables must be in mol_raw)
--   2. Tables that were never created in any schema
--
-- Standard mol_raw schema follows mol_raw.openalex as the authoritative template:
--   id, request_id, request_timestamp, api_endpoint, api_version,
--   request_params, request_headers, response_status, response_headers,
--   response_body (JSONB), response_body_hash, response_size_bytes,
--   response_time_ms, processed_to_bronze, processed_at, processing_error,
--   ingested_at, source_id
--
-- Date: 2026-03-27
-- Feature: 019-cms-puf-platform-reconciliation

BEGIN;

-- ============================================================================
-- STEP 1: Move existing raw.* tables to mol_raw (data preserved)
-- ============================================================================

ALTER TABLE IF EXISTS raw.cdc_vaccines  SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.dailymed      SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.fda_drugs     SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.imgt          SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.orange_book   SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.ttd           SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.bindingdb     SET SCHEMA mol_raw;
ALTER TABLE IF EXISTS raw.ema           SET SCHEMA mol_raw;

-- ============================================================================
-- STEP 2: Create mol_raw tables that don't exist in any schema yet
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_raw.cms_medicare (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'cms_medicare',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'cms_medicare'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cms_medicare_ts    ON mol_raw.cms_medicare(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cms_medicare_flag  ON mol_raw.cms_medicare(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.cms_open_payments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'cms_open_payments',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'cms_open_payments'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cms_open_payments_ts    ON mol_raw.cms_open_payments(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cms_open_payments_flag  ON mol_raw.cms_open_payments(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.ct_gov_indication_stats (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'ct_gov',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'ct_gov_indication_stats'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ct_gov_ind_ts    ON mol_raw.ct_gov_indication_stats(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ct_gov_ind_flag  ON mol_raw.ct_gov_indication_stats(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.fda_drugsfda (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'fda_drugsfda',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'fda_drugsfda'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_drugsfda_ts    ON mol_raw.fda_drugsfda(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_drugsfda_flag  ON mol_raw.fda_drugsfda(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.nice_hta (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'nice_hta',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'nice_hta'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_nice_hta_ts    ON mol_raw.nice_hta(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_nice_hta_flag  ON mol_raw.nice_hta(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.npi_registry (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'npi_registry',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'npi_registry'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_npi_registry_ts    ON mol_raw.npi_registry(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_npi_registry_flag  ON mol_raw.npi_registry(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.purple_book (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'purple_book',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'purple_book'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_purple_book_ts    ON mol_raw.purple_book(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_purple_book_flag  ON mol_raw.purple_book(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.reactome (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'reactome',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'reactome'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_reactome_ts    ON mol_raw.reactome(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_reactome_flag  ON mol_raw.reactome(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.who_gho (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'who_gho',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'who_gho'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_who_gho_ts    ON mol_raw.who_gho(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_who_gho_flag  ON mol_raw.who_gho(processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE IF NOT EXISTS mol_raw.euipo_designs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'euipo_designs',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'euipo_designs'
);
CREATE INDEX IF NOT EXISTS idx_mol_raw_euipo_designs_ts    ON mol_raw.euipo_designs(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_euipo_designs_flag  ON mol_raw.euipo_designs(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- STEP 3: Register new mol sources in meta.data_sources
-- ============================================================================

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES
    ('cdc_vaccines',          'api',  'https://data.cdc.gov',                           'CDC vaccine coverage and immunization data',                'monthly',   true),
    ('cms_medicare',          'api',  'https://data.cms.gov',                           'CMS Medicare claims and utilization data',                  'quarterly', true),
    ('cms_open_payments',     'api',  'https://openpaymentsdata.cms.gov',               'CMS Open Payments physician payment data',                  'annual',    true),
    ('ct_gov_indication_stats','api', 'https://clinicaltrials.gov/api',                 'ClinicalTrials.gov aggregated indication statistics',       'weekly',    true),
    ('dailymed',              'api',  'https://dailymed.nlm.nih.gov',                   'NLM DailyMed structured drug label information',           'weekly',    true),
    ('fda_drugs',             'api',  'https://api.fda.gov/drug',                       'FDA drug product database',                                 'weekly',    true),
    ('fda_drugsfda',          'api',  'https://api.fda.gov/drug/drugsfda.json',         'FDA Drugs@FDA NDA/ANDA application data',                  'weekly',    true),
    ('imgt',                  'api',  'https://www.imgt.org',                           'IMGT immunoglobulin and T-cell receptor gene data',         'monthly',   true),
    ('nice_hta',              'api',  'https://www.nice.org.uk/guidance',               'NICE UK health technology assessment decisions',            'monthly',   true),
    ('npi_registry',          'api',  'https://npiregistry.cms.hhs.gov/api',            'CMS National Provider Identifier registry',                 'monthly',   true),
    ('orange_book',           'api',  'https://api.fda.gov/drug/drugsfda.json',         'FDA Orange Book patent and exclusivity data',               'monthly',   true),
    ('purple_book',           'api',  'https://api.fda.gov/biologics/biosimilars.json', 'FDA Purple Book biologics license applications',            'monthly',   true),
    ('reactome',              'api',  'https://reactome.org/ContentService',            'Reactome biological pathway data',                         'monthly',   true),
    ('ttd',                   'api',  'https://db.idrblab.net/ttd',                     'Therapeutic Target Database drug-target interactions',      'quarterly', true),
    ('who_gho',               'api',  'https://ghoapi.azureedge.net/api',               'WHO Global Health Observatory health statistics',           'monthly',   true),
    ('euipo_designs',         'api',  'https://euipo.europa.eu/eSearchCAS',             'EUIPO registered industrial design applications',           'weekly',    true)
ON CONFLICT (source_name) DO UPDATE
    SET is_active         = EXCLUDED.is_active,
        source_url        = EXCLUDED.source_url,
        description       = EXCLUDED.description,
        refresh_frequency = EXCLUDED.refresh_frequency;

-- ============================================================================
-- STEP 4: Grant analyst read access
-- ============================================================================

GRANT SELECT ON mol_raw.cms_medicare           TO analyst;
GRANT SELECT ON mol_raw.cms_open_payments      TO analyst;
GRANT SELECT ON mol_raw.ct_gov_indication_stats TO analyst;
GRANT SELECT ON mol_raw.fda_drugsfda           TO analyst;
GRANT SELECT ON mol_raw.nice_hta               TO analyst;
GRANT SELECT ON mol_raw.npi_registry           TO analyst;
GRANT SELECT ON mol_raw.purple_book            TO analyst;
GRANT SELECT ON mol_raw.reactome               TO analyst;
GRANT SELECT ON mol_raw.who_gho                TO analyst;
GRANT SELECT ON mol_raw.euipo_designs          TO analyst;

COMMIT;
