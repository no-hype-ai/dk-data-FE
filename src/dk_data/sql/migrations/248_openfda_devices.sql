-- Migration 248: Medical devices domain (dev_*) — schemas + raw tables
-- Feature: FDA medical devices ingestion (drug-device combination analysis)
-- Date:    2026-04-21
--
-- Establishes the medical-devices domain as the 12th canonical hub-bearing
-- domain (alongside mol_, hcs_, ind_, hcp_, ip_). Devices are distinct from
-- molecules (a surgical stapler has no molecule); per CLAUDE.md domain-prefix
-- rule they get their own schema family rather than parasite on mol_*.
--
-- Schemas created:
--   dev_raw, dev_bronze, dev_silver, dev_gold
--
-- Raw tables (standardized JSONB page-blob pattern):
--   dev_raw.openfda_device_510k           — 510(k) premarket notifications (~250K)
--   dev_raw.openfda_device_pma            — PMA premarket approvals (~20K)
--   dev_raw.openfda_device_classification — device classification catalog (~6K)
--
-- Hub architecture (migrations 249 resolve_device, 250 bootstrap_devices):
--   dev_silver.devices              — hub table, bigint PK
--   dev_silver.device_identifiers   — k_number / pma_number / fei_number / udi_di / name
--   dev_silver.device_names         — canonical + aliases with normalized_name
--   dev_silver.resolve_device(...)  — STABLE PARALLEL SAFE, p99 ≤10ms (SC-004)
--
-- Auth: reuses OPENFDA_API_KEY from dk-data-secrets (shared with openfda_faers/labels).

BEGIN;

-- ---------------------------------------------------------------------------
-- Domain schemas
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS dev_raw;
CREATE SCHEMA IF NOT EXISTS dev_bronze;
CREATE SCHEMA IF NOT EXISTS dev_silver;
CREATE SCHEMA IF NOT EXISTS dev_gold;

COMMENT ON SCHEMA dev_raw    IS 'Medical devices — raw API responses from FDA openFDA device endpoints (510k, PMA, classification, plus future UDI/MAUDE)';
COMMENT ON SCHEMA dev_bronze IS 'Medical devices — typed, deduplicated records extracted from dev_raw JSONB';
COMMENT ON SCHEMA dev_silver IS 'Medical devices — entity-resolved hub (devices, device_identifiers, device_names) plus regulatory fact tables (fda_510k, fda_pma, fda_classification)';
COMMENT ON SCHEMA dev_gold   IS 'Medical devices — aggregated dossiers, competitive landscape, drug-device combination views';

-- Default privileges — analyst role gets SELECT on all future tables.
-- web_anon is NOT granted per migration 218 (JWT-required). api_user gets grants
-- when specific gold/api views are published.
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
    ALTER DEFAULT PRIVILEGES IN SCHEMA dev_raw    GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA dev_bronze GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA dev_silver GRANT SELECT ON TABLES TO analyst;
    ALTER DEFAULT PRIVILEGES IN SCHEMA dev_gold   GRANT SELECT ON TABLES TO analyst;
    GRANT USAGE ON SCHEMA dev_raw, dev_bronze, dev_silver, dev_gold TO analyst;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- dev_raw.openfda_device_510k
-- Premarket Notifications (K-numbers). Year-partitioned on decision_date.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dev_raw.openfda_device_510k (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://api.fda.gov/device/510k.json',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'openfda_device_510k'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_dev_raw_openfda_device_510k_request_id
    ON dev_raw.openfda_device_510k (request_id);
CREATE INDEX IF NOT EXISTS idx_dev_raw_openfda_device_510k_ts
    ON dev_raw.openfda_device_510k (ingested_at);
CREATE INDEX IF NOT EXISTS idx_dev_raw_openfda_device_510k_bronze
    ON dev_raw.openfda_device_510k (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ---------------------------------------------------------------------------
-- dev_raw.openfda_device_pma
-- Premarket Approvals (P-numbers). Small (~20K); full-scan each run.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dev_raw.openfda_device_pma (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://api.fda.gov/device/pma.json',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'openfda_device_pma'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_dev_raw_openfda_device_pma_request_id
    ON dev_raw.openfda_device_pma (request_id);
CREATE INDEX IF NOT EXISTS idx_dev_raw_openfda_device_pma_ts
    ON dev_raw.openfda_device_pma (ingested_at);
CREATE INDEX IF NOT EXISTS idx_dev_raw_openfda_device_pma_bronze
    ON dev_raw.openfda_device_pma (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ---------------------------------------------------------------------------
-- dev_raw.openfda_device_classification
-- Device classification reference catalog (~6K rows). Full-scan quarterly.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dev_raw.openfda_device_classification (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'https://api.fda.gov/device/classification.json',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'openfda_device_classification'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_dev_raw_openfda_device_classification_request_id
    ON dev_raw.openfda_device_classification (request_id);
CREATE INDEX IF NOT EXISTS idx_dev_raw_openfda_device_classification_ts
    ON dev_raw.openfda_device_classification (ingested_at);
CREATE INDEX IF NOT EXISTS idx_dev_raw_openfda_device_classification_bronze
    ON dev_raw.openfda_device_classification (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ---------------------------------------------------------------------------
-- Register in meta.backfill_state for orchestrator queue
-- ---------------------------------------------------------------------------
INSERT INTO meta.backfill_state (source_name, status, priority, fetcher_args)
VALUES
    ('openfda_device_510k',           'active', 50, '{"full_backfill": true, "start_year": 2000}'::jsonb),
    ('openfda_device_pma',            'active', 50, '{"full_backfill": true}'::jsonb),
    ('openfda_device_classification', 'active', 50, '{}'::jsonb)
ON CONFLICT (source_name) DO UPDATE
SET status       = EXCLUDED.status,
    priority     = EXCLUDED.priority,
    fetcher_args = EXCLUDED.fetcher_args;

COMMIT;
