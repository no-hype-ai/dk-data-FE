-- Migration 251: TGA (Therapeutic Goods Administration, Australia) raw tables — Tier A sources
-- Feature: TGA datasource integration (drug-device combo analysis, AU regulatory coverage)
-- Date:    2026-04-21
--
-- Tier A = sources with stable export endpoints (CSV/JSON/RSS). 5 sources, 5 raw tables.
-- Tier B (DAEN, AusPAR, PI/CMI, provisional, black triangle, CTN, UDI, biosimilars)
-- deferred to follow-up GitHub issue — requires scraping / PDF parsing.
--
-- Domain mapping per CLAUDE.md rules:
--   mol_raw.tga_artg_medicines       — prescription + OTC + biologicals + complementary (all medicines)
--   dev_raw.tga_artg_devices         — ARTG medical device entries (12th hub domain)
--   mol_raw.tga_sara_recalls         — System for Australian Recall Actions; router splits at silver
--                                      into mol_silver.tga_medicine_recalls + dev_silver.tga_device_recalls
--                                      based on regulatory_type column
--   mol_raw.tga_medicine_shortages   — Medicine Shortages Information portal (MSI)
--   mol_raw.tga_orphan_designations  — Orphan drug designations (annual list)
--
-- Entity linking (silver layer):
--   All medicines models → resolve_molecule / resolve_drug_product / resolve_company
--   Devices model        → resolve_device / resolve_company
--   Orphan designations  → resolve_molecule / resolve_company / resolve_condition
--
-- Auth: no API key required; endpoints are public-read. Rate-limit politeness via
--       REQUEST_DELAY in fetchers. No TGA_API_KEY env var needed.

BEGIN;

-- ===========================================================================
-- mol_raw.tga_artg_medicines — unified medicines (prescription/OTC/biologicals/complementary)
-- One raw row per ARTG medicine export page; medicine_type column distinguishes subtypes.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS mol_raw.tga_artg_medicines (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://www.tga.gov.au/resources/artg/artg-search-visualisation-tool',
    api_version         VARCHAR(20),
    request_params      JSONB,                                     -- {medicine_type: prescription|otc|biological|complementary, page, limit}
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,        -- {results: [...], medicine_type: '...'}
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'tga_artg_medicines'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_tga_artg_medicines_request_id ON mol_raw.tga_artg_medicines (request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_artg_medicines_ts     ON mol_raw.tga_artg_medicines (ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_artg_medicines_bronze ON mol_raw.tga_artg_medicines (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ===========================================================================
-- dev_raw.tga_artg_devices — ARTG medical devices (12th hub domain)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS dev_raw.tga_artg_devices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://www.tga.gov.au/resources/artg/artg-search-visualisation-tool',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'tga_artg_devices'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_dev_raw_tga_artg_devices_request_id ON dev_raw.tga_artg_devices (request_id);
CREATE INDEX IF NOT EXISTS idx_dev_raw_tga_artg_devices_ts     ON dev_raw.tga_artg_devices (ingested_at);
CREATE INDEX IF NOT EXISTS idx_dev_raw_tga_artg_devices_bronze ON dev_raw.tga_artg_devices (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ===========================================================================
-- mol_raw.tga_sara_recalls — System for Australian Recall Actions (both medicines + devices)
-- Rows flagged by regulatory_type. Silver models split into mol/dev domains.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS mol_raw.tga_sara_recalls (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://apps.tga.gov.au/prod/sara/',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'tga_sara_recalls'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_tga_sara_recalls_request_id ON mol_raw.tga_sara_recalls (request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_sara_recalls_ts     ON mol_raw.tga_sara_recalls (ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_sara_recalls_bronze ON mol_raw.tga_sara_recalls (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ===========================================================================
-- mol_raw.tga_medicine_shortages — Medicine Shortages Information portal (MSI)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS mol_raw.tga_medicine_shortages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://apps.tga.gov.au/prod/MSI/search',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'tga_medicine_shortages'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_tga_medicine_shortages_request_id ON mol_raw.tga_medicine_shortages (request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_medicine_shortages_ts     ON mol_raw.tga_medicine_shortages (ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_medicine_shortages_bronze ON mol_raw.tga_medicine_shortages (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ===========================================================================
-- mol_raw.tga_orphan_designations — Orphan drug designations (annual list)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS mol_raw.tga_orphan_designations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://www.tga.gov.au/resources/orphan-drug-designations',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'tga_orphan_designations'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_tga_orphan_designations_request_id ON mol_raw.tga_orphan_designations (request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_orphan_designations_ts     ON mol_raw.tga_orphan_designations (ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tga_orphan_designations_bronze ON mol_raw.tga_orphan_designations (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ===========================================================================
-- Grants
-- ===========================================================================
GRANT SELECT ON mol_raw.tga_artg_medicines        TO web_anon, analyst;
GRANT SELECT ON dev_raw.tga_artg_devices          TO web_anon, analyst;
GRANT SELECT ON mol_raw.tga_sara_recalls          TO web_anon, analyst;
GRANT SELECT ON mol_raw.tga_medicine_shortages    TO web_anon, analyst;
GRANT SELECT ON mol_raw.tga_orphan_designations   TO web_anon, analyst;

-- ===========================================================================
-- meta.backfill_state registration (orchestrator queue; priority 50 = reference)
-- ===========================================================================
INSERT INTO meta.backfill_state (source_name, status, priority, fetcher_args)
VALUES
    ('tga_artg_medicines',      'active', 50, '{"full_backfill": true}'::jsonb),
    ('tga_artg_devices',        'active', 50, '{"full_backfill": true}'::jsonb),
    ('tga_sara_recalls',        'active', 60, '{"days_back": 365}'::jsonb),
    ('tga_medicine_shortages',  'active', 60, '{}'::jsonb),
    ('tga_orphan_designations', 'active', 50, '{"full_backfill": true}'::jsonb)
ON CONFLICT (source_name) DO UPDATE
SET status       = EXCLUDED.status,
    priority     = EXCLUDED.priority,
    fetcher_args = EXCLUDED.fetcher_args;

COMMIT;
