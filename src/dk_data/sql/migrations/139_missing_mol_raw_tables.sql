-- Migration 131: Create all missing mol_raw tables for unimplemented sources
-- These sources have fetchers, pipeline adapters, and bronze SQLMesh models
-- but were never registered in the database. All use the standard medallion
-- raw schema (matching mol_raw.openalex as the authoritative template).
-- Also runs migration 128 content (mol_raw.ema) since it may not have been applied.

BEGIN;

-- Standard raw table schema:
--   id, request_id, request_timestamp, api_endpoint, api_version,
--   request_params, request_headers, response_status, response_headers,
--   response_body (JSONB — the authoritative raw API payload),
--   response_body_hash, response_size_bytes, response_time_ms,
--   processed_to_bronze, processed_at, processing_error, ingested_at, source_id

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.ema  (EMA authorized medicines — may have been created by migration 128)
-- ══════════════════════════════════════════════════════════════════════════════
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
CREATE INDEX IF NOT EXISTS idx_ema_raw_ts    ON mol_raw.ema(ingested_at);
CREATE INDEX IF NOT EXISTS idx_ema_raw_flag  ON mol_raw.ema(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_ema_raw_drug  ON mol_raw.ema((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.orange_book  (FDA Orange Book patent/exclusivity)
-- ══════════════════════════════════════════════════════════════════════════════
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
CREATE INDEX IF NOT EXISTS idx_orange_book_raw_ts   ON mol_raw.orange_book(ingested_at);
CREATE INDEX IF NOT EXISTS idx_orange_book_raw_flag ON mol_raw.orange_book(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_orange_book_raw_drug ON mol_raw.orange_book((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.orcid  (ORCID researcher profiles)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.orcid (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'orcid',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'orcid'
);
CREATE INDEX IF NOT EXISTS idx_orcid_raw_ts   ON mol_raw.orcid(ingested_at);
CREATE INDEX IF NOT EXISTS idx_orcid_raw_flag ON mol_raw.orcid(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_orcid_raw_drug ON mol_raw.orcid((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.pdb_structures  (RCSB PDB protein structures)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.pdb_structures (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'pdb_structures',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'pdb_structures'
);
CREATE INDEX IF NOT EXISTS idx_pdb_raw_ts   ON mol_raw.pdb_structures(ingested_at);
CREATE INDEX IF NOT EXISTS idx_pdb_raw_flag ON mol_raw.pdb_structures(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_pdb_raw_drug ON mol_raw.pdb_structures((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.pubmed  (PubMed literature)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.pubmed (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'pubmed',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'pubmed'
);
CREATE INDEX IF NOT EXISTS idx_pubmed_raw_ts   ON mol_raw.pubmed(ingested_at);
CREATE INDEX IF NOT EXISTS idx_pubmed_raw_flag ON mol_raw.pubmed(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_pubmed_raw_drug ON mol_raw.pubmed((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.who_icd  (WHO ICD-11 disease classifications)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.who_icd (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'who_icd',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'who_icd'
);
CREATE INDEX IF NOT EXISTS idx_who_icd_raw_ts   ON mol_raw.who_icd(ingested_at);
CREATE INDEX IF NOT EXISTS idx_who_icd_raw_flag ON mol_raw.who_icd(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_who_icd_raw_drug ON mol_raw.who_icd((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.journal_rss  (Journal RSS/Atom feeds)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.journal_rss (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'journal_rss',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'journal_rss'
);
CREATE INDEX IF NOT EXISTS idx_journal_rss_raw_ts   ON mol_raw.journal_rss(ingested_at);
CREATE INDEX IF NOT EXISTS idx_journal_rss_raw_flag ON mol_raw.journal_rss(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_journal_rss_raw_drug ON mol_raw.journal_rss((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.medical_news  (Medical news feeds)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.medical_news (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'medical_news',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'medical_news'
);
CREATE INDEX IF NOT EXISTS idx_medical_news_raw_ts   ON mol_raw.medical_news(ingested_at);
CREATE INDEX IF NOT EXISTS idx_medical_news_raw_flag ON mol_raw.medical_news(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_medical_news_raw_drug ON mol_raw.medical_news((request_params->>'drug_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.hrsa_shortage_areas  (HRSA Health Professional Shortage Areas)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.hrsa_shortage_areas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'hrsa',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'hrsa'
);
CREATE INDEX IF NOT EXISTS idx_hrsa_raw_ts   ON mol_raw.hrsa_shortage_areas(ingested_at);
CREATE INDEX IF NOT EXISTS idx_hrsa_raw_flag ON mol_raw.hrsa_shortage_areas(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.euipo_trademarks  (EUIPO trademark registry)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.euipo_trademarks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'euipo_trademarks',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'euipo_trademarks'
);
CREATE INDEX IF NOT EXISTS idx_euipo_tm_raw_ts   ON mol_raw.euipo_trademarks(ingested_at);
CREATE INDEX IF NOT EXISTS idx_euipo_tm_raw_flag ON mol_raw.euipo_trademarks(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_euipo_tm_raw_appno ON mol_raw.euipo_trademarks((response_body->>'application_number'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.uspto_patents  (USPTO PatentsView pharmaceutical patents)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.uspto_patents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'uspto_patents',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'uspto_patents'
);
CREATE INDEX IF NOT EXISTS idx_uspto_pat_raw_ts   ON mol_raw.uspto_patents(ingested_at);
CREATE INDEX IF NOT EXISTS idx_uspto_pat_raw_flag ON mol_raw.uspto_patents(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_uspto_pat_raw_num  ON mol_raw.uspto_patents((response_body->>'patent_number'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.uspto_ci  (USPTO CI/competitive intelligence patent queries)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.uspto_ci (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'uspto_ci',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'uspto_ci'
);
CREATE INDEX IF NOT EXISTS idx_uspto_ci_raw_ts   ON mol_raw.uspto_ci(ingested_at);
CREATE INDEX IF NOT EXISTS idx_uspto_ci_raw_flag ON mol_raw.uspto_ci(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_uspto_ci_raw_num  ON mol_raw.uspto_ci((response_body->>'patent_id'));

-- ══════════════════════════════════════════════════════════════════════════════
-- mol_raw.acc_tvc_certification  (ACC/NCDR TAVR site certifications)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mol_raw.acc_tvc_certification (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'acc_tvc',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    -- response_body stores one certification record per row as JSONB:
    -- { facility_name, city, state, zip_code, certification_type,
    --   certification_date, expiration_date, facility_id, volumes: {...} }
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'acc_tvc'
);
CREATE INDEX IF NOT EXISTS idx_acc_tvc_raw_ts       ON mol_raw.acc_tvc_certification(ingested_at);
CREATE INDEX IF NOT EXISTS idx_acc_tvc_raw_flag     ON mol_raw.acc_tvc_certification(processed_to_bronze) WHERE NOT processed_to_bronze;
CREATE INDEX IF NOT EXISTS idx_acc_tvc_raw_facility ON mol_raw.acc_tvc_certification((response_body->>'facility_name'));

-- ══════════════════════════════════════════════════════════════════════════════
-- Register all new sources in ops.sync_schedules
-- ══════════════════════════════════════════════════════════════════════════════
INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options)
VALUES
    ('ema_regulatory', 'monthly', '0 4 10 * *', 'normal', true,
     '{"source_name":"EMA Medicines","api_type":"rest","target_table":"mol_raw.ema","supports_per_molecule":true}'::jsonb),
    ('orange_book', 'monthly', '0 4 15 * *', 'normal', true,
     '{"source_name":"FDA Orange Book","api_type":"rest","target_table":"mol_raw.orange_book","supports_per_molecule":true}'::jsonb),
    ('orcid', 'monthly', '0 3 20 * *', 'low', true,
     '{"source_name":"ORCID Researchers","api_type":"rest","target_table":"mol_raw.orcid","supports_per_molecule":true}'::jsonb),
    ('pdb_structures', 'weekly', '0 3 * * 1', 'low', true,
     '{"source_name":"PDB Structures","api_type":"rest","target_table":"mol_raw.pdb_structures","supports_per_molecule":true}'::jsonb),
    ('pubmed', 'weekly', '0 4 * * 2', 'normal', true,
     '{"source_name":"PubMed","api_type":"rest","target_table":"mol_raw.pubmed","supports_per_molecule":true}'::jsonb),
    ('who_icd', 'monthly', '0 3 5 * *', 'low', true,
     '{"source_name":"WHO ICD-11","api_type":"rest","target_table":"mol_raw.who_icd","supports_per_molecule":true}'::jsonb),
    ('journal_rss', 'daily', '0 7 * * *', 'normal', true,
     '{"source_name":"Journal RSS","api_type":"rss","target_table":"mol_raw.journal_rss","supports_per_molecule":true}'::jsonb),
    ('medical_news', 'daily', '0 8 * * *', 'normal', true,
     '{"source_name":"Medical News","api_type":"rss","target_table":"mol_raw.medical_news","supports_per_molecule":true}'::jsonb),
    ('hrsa', 'monthly', '0 3 25 * *', 'low', true,
     '{"source_name":"HRSA Shortage Areas","api_type":"rest","target_table":"mol_raw.hrsa_shortage_areas","supports_per_molecule":false}'::jsonb),
    ('euipo_trademarks', 'weekly', '0 3 * * 3', 'low', true,
     '{"source_name":"EUIPO Trademarks","api_type":"rest","target_table":"mol_raw.euipo_trademarks","supports_per_molecule":true}'::jsonb),
    ('uspto_patents', 'weekly', '0 3 * * 4', 'normal', true,
     '{"source_name":"USPTO Patents","api_type":"rest","target_table":"mol_raw.uspto_patents","supports_per_molecule":true}'::jsonb),
    ('uspto_ci', 'weekly', '0 4 * * 4', 'normal', true,
     '{"source_name":"USPTO CI Patents","api_type":"rest","target_table":"mol_raw.uspto_ci","supports_per_molecule":true}'::jsonb),
    ('acc_tvc_certification', 'monthly', '0 3 1 * *', 'normal', true,
     '{"source_name":"ACC TVC Certifications","api_type":"csv","target_table":"mol_raw.acc_tvc_certification","supports_per_molecule":false}'::jsonb)
ON CONFLICT (source) DO UPDATE
    SET tier            = EXCLUDED.tier,
        cron_expression = EXCLUDED.cron_expression,
        enabled         = EXCLUDED.enabled,
        options         = EXCLUDED.options;

-- ══════════════════════════════════════════════════════════════════════════════
-- Grants
-- ══════════════════════════════════════════════════════════════════════════════
GRANT SELECT ON mol_raw.ema                  TO analyst;
GRANT SELECT ON mol_raw.orange_book          TO analyst;
GRANT SELECT ON mol_raw.orcid                TO analyst;
GRANT SELECT ON mol_raw.pdb_structures       TO analyst;
GRANT SELECT ON mol_raw.pubmed               TO analyst;
GRANT SELECT ON mol_raw.who_icd              TO analyst;
GRANT SELECT ON mol_raw.journal_rss          TO analyst;
GRANT SELECT ON mol_raw.medical_news         TO analyst;
GRANT SELECT ON mol_raw.hrsa_shortage_areas  TO analyst;
GRANT SELECT ON mol_raw.euipo_trademarks     TO analyst;
GRANT SELECT ON mol_raw.uspto_patents        TO analyst;
GRANT SELECT ON mol_raw.uspto_ci             TO analyst;
GRANT SELECT ON mol_raw.acc_tvc_certification TO analyst;

COMMIT;
