-- Migration 134: Convert all hcs_raw CMS tables to canonical JSONB schema
-- Drops all typed CMS raw tables (and orphans) and recreates them with the
-- same JSONB pattern used by mol_raw: response_body + response_body_hash dedup.
-- Part of: 016-cms-puf-datasource-integration

BEGIN;

-- ─── 1. Drop orphan tables (never written to) ─────────────────────────────────
DROP TABLE IF EXISTS hcs_raw.cms_care_compare_physicians CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_open_payments_general CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_open_payments_research CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_open_payments_ownership CASCADE;

-- ─── 2. Drop all active CMS typed tables ──────────────────────────────────────
DROP TABLE IF EXISTS hcs_raw.cms_care_compare CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_chow CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_chronic_conditions CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_cost_reports CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_ddinter CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_dmepos CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_formulary CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_geographic_variation CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hcris CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hospital_affiliation CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hospital_general_info CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hospital_info CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_hospital_quality CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_inpatient_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_magnet CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_medicare_inpatient CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_ndc CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_nppes CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_nucc CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_open_payments CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_outpatient_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_part_b_spending CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_part_d_prescriber CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_part_d_spending CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_pecos CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_physician_puf CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_pos CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_post_acute CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_rbcs CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_stabilis CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_usp CASCADE;

-- ─── 3. Recreate all tables with canonical JSONB schema ───────────────────────
-- Standard columns:
--   id UUID PK, request_id TEXT, api_endpoint TEXT,
--   response_status INT DEFAULT 200, response_body JSONB NOT NULL,
--   response_body_hash VARCHAR(64) UNIQUE WHERE NOT NULL,
--   processed_to_bronze BOOLEAN DEFAULT false, ingested_at TIMESTAMPTZ,
--   source_id TEXT

CREATE TABLE hcs_raw.cms_care_compare (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_care_compare',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_care_compare'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_care_compare (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_care_compare (ingested_at);
CREATE INDEX ON hcs_raw.cms_care_compare (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_chow (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_chow',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_chow'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_chow (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_chow (ingested_at);
CREATE INDEX ON hcs_raw.cms_chow (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_chronic_conditions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_chronic_conditions',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_chronic_conditions'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_chronic_conditions (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_chronic_conditions (ingested_at);
CREATE INDEX ON hcs_raw.cms_chronic_conditions (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_cost_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_cost_reports',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_cost_reports'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_cost_reports (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_cost_reports (ingested_at);
CREATE INDEX ON hcs_raw.cms_cost_reports (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_ddinter (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_ddinter',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_ddinter'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_ddinter (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_ddinter (ingested_at);
CREATE INDEX ON hcs_raw.cms_ddinter (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_dmepos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_dmepos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_dmepos'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_dmepos (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_dmepos (ingested_at);
CREATE INDEX ON hcs_raw.cms_dmepos (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_formulary (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_formulary',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_formulary'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_formulary (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_formulary (ingested_at);
CREATE INDEX ON hcs_raw.cms_formulary (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_geographic_variation (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_geographic_variation',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_geographic_variation'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_geographic_variation (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_geographic_variation (ingested_at);
CREATE INDEX ON hcs_raw.cms_geographic_variation (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_hcris (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hcris',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_hcris'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_hcris (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_hcris (ingested_at);
CREATE INDEX ON hcs_raw.cms_hcris (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_hospital_affiliation (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_affiliation',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_affiliation'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_hospital_affiliation (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_hospital_affiliation (ingested_at);
CREATE INDEX ON hcs_raw.cms_hospital_affiliation (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_hospital_general_info (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_general_info',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_general_info'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_hospital_general_info (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_hospital_general_info (ingested_at);
CREATE INDEX ON hcs_raw.cms_hospital_general_info (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_hospital_info (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_info',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_info'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_hospital_info (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_hospital_info (ingested_at);
CREATE INDEX ON hcs_raw.cms_hospital_info (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_hospital_quality (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_quality',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_quality'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_hospital_quality (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_hospital_quality (ingested_at);
CREATE INDEX ON hcs_raw.cms_hospital_quality (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_inpatient_puf (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_inpatient_puf',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_inpatient_puf'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_inpatient_puf (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_inpatient_puf (ingested_at);
CREATE INDEX ON hcs_raw.cms_inpatient_puf (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_magnet (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_magnet',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_magnet'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_magnet (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_magnet (ingested_at);
CREATE INDEX ON hcs_raw.cms_magnet (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_medicare_inpatient (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_medicare_inpatient',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_medicare_inpatient'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_medicare_inpatient (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_medicare_inpatient (ingested_at);
CREATE INDEX ON hcs_raw.cms_medicare_inpatient (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_ndc (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_ndc',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_ndc'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_ndc (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_ndc (ingested_at);
CREATE INDEX ON hcs_raw.cms_ndc (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_nppes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_nppes',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_nppes'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_nppes (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_nppes (ingested_at);
CREATE INDEX ON hcs_raw.cms_nppes (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_nucc (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_nucc',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_nucc'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_nucc (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_nucc (ingested_at);
CREATE INDEX ON hcs_raw.cms_nucc (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_open_payments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_open_payments',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_open_payments'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_open_payments (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_open_payments (ingested_at);
CREATE INDEX ON hcs_raw.cms_open_payments (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_outpatient_puf (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_outpatient_puf',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_outpatient_puf'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_outpatient_puf (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_outpatient_puf (ingested_at);
CREATE INDEX ON hcs_raw.cms_outpatient_puf (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_part_b_spending (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_part_b_spending',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_part_b_spending'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_part_b_spending (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_part_b_spending (ingested_at);
CREATE INDEX ON hcs_raw.cms_part_b_spending (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_part_d_prescriber (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_part_d_prescriber',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_part_d_prescriber'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_part_d_prescriber (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_part_d_prescriber (ingested_at);
CREATE INDEX ON hcs_raw.cms_part_d_prescriber (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_part_d_spending (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_part_d_spending',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_part_d_spending'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_part_d_spending (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_part_d_spending (ingested_at);
CREATE INDEX ON hcs_raw.cms_part_d_spending (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_pecos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_pecos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_pecos'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_pecos (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_pecos (ingested_at);
CREATE INDEX ON hcs_raw.cms_pecos (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_physician_puf (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_physician_puf',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_physician_puf'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_physician_puf (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_physician_puf (ingested_at);
CREATE INDEX ON hcs_raw.cms_physician_puf (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_pos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_pos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_pos'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_pos (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_pos (ingested_at);
CREATE INDEX ON hcs_raw.cms_pos (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_post_acute (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_post_acute',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_post_acute'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_post_acute (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_post_acute (ingested_at);
CREATE INDEX ON hcs_raw.cms_post_acute (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_rbcs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_rbcs',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_rbcs'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_rbcs (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_rbcs (ingested_at);
CREATE INDEX ON hcs_raw.cms_rbcs (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_stabilis (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_stabilis',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_stabilis'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_stabilis (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_stabilis (ingested_at);
CREATE INDEX ON hcs_raw.cms_stabilis (processed_to_bronze) WHERE NOT processed_to_bronze;

CREATE TABLE hcs_raw.cms_usp (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          TEXT,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_usp',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    processed_to_bronze BOOLEAN NOT NULL DEFAULT false,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           TEXT NOT NULL DEFAULT 'cms_usp'
);
CREATE UNIQUE INDEX ON hcs_raw.cms_usp (response_body_hash) WHERE response_body_hash IS NOT NULL;
CREATE INDEX ON hcs_raw.cms_usp (ingested_at);
CREATE INDEX ON hcs_raw.cms_usp (processed_to_bronze) WHERE NOT processed_to_bronze;

-- ─── 4. Grants ────────────────────────────────────────────────────────────────
GRANT SELECT ON hcs_raw.cms_care_compare        TO analyst;
GRANT SELECT ON hcs_raw.cms_chow                TO analyst;
GRANT SELECT ON hcs_raw.cms_chronic_conditions  TO analyst;
GRANT SELECT ON hcs_raw.cms_cost_reports        TO analyst;
GRANT SELECT ON hcs_raw.cms_ddinter             TO analyst;
GRANT SELECT ON hcs_raw.cms_dmepos              TO analyst;
GRANT SELECT ON hcs_raw.cms_formulary           TO analyst;
GRANT SELECT ON hcs_raw.cms_geographic_variation TO analyst;
GRANT SELECT ON hcs_raw.cms_hcris               TO analyst;
GRANT SELECT ON hcs_raw.cms_hospital_affiliation TO analyst;
GRANT SELECT ON hcs_raw.cms_hospital_general_info TO analyst;
GRANT SELECT ON hcs_raw.cms_hospital_info       TO analyst;
GRANT SELECT ON hcs_raw.cms_hospital_quality    TO analyst;
GRANT SELECT ON hcs_raw.cms_inpatient_puf       TO analyst;
GRANT SELECT ON hcs_raw.cms_magnet              TO analyst;
GRANT SELECT ON hcs_raw.cms_medicare_inpatient  TO analyst;
GRANT SELECT ON hcs_raw.cms_ndc                 TO analyst;
GRANT SELECT ON hcs_raw.cms_nppes               TO analyst;
GRANT SELECT ON hcs_raw.cms_nucc                TO analyst;
GRANT SELECT ON hcs_raw.cms_open_payments       TO analyst;
GRANT SELECT ON hcs_raw.cms_outpatient_puf      TO analyst;
GRANT SELECT ON hcs_raw.cms_part_b_spending     TO analyst;
GRANT SELECT ON hcs_raw.cms_part_d_prescriber   TO analyst;
GRANT SELECT ON hcs_raw.cms_part_d_spending     TO analyst;
GRANT SELECT ON hcs_raw.cms_pecos               TO analyst;
GRANT SELECT ON hcs_raw.cms_physician_puf       TO analyst;
GRANT SELECT ON hcs_raw.cms_pos                 TO analyst;
GRANT SELECT ON hcs_raw.cms_post_acute          TO analyst;
GRANT SELECT ON hcs_raw.cms_rbcs                TO analyst;
GRANT SELECT ON hcs_raw.cms_stabilis            TO analyst;
GRANT SELECT ON hcs_raw.cms_usp                 TO analyst;

COMMIT;
