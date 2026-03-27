-- Migration: 097_hcs_raw_facility_tables.sql
-- Purpose: Create hcs_raw tables for 18 CMS facility/reference sources ported
--          from 016-cms-puf-datasource-integration. All use the JSONB response_body
--          pattern (matching migration 085 CMS PUF pattern for API-based sources).
--
-- Sources: cms_care_compare, cms_chow, cms_ddinter, cms_dmepos, cms_formulary,
--          cms_hcris, cms_hospital_affiliation, cms_hospital_quality, cms_magnet,
--          cms_ndc, cms_nucc, cms_pecos, cms_pos, cms_post_acute, cms_rbcs,
--          cms_stabilis, cms_usp
--
-- Date: 2026-03-27
-- Feature: 019-cms-puf-platform-reconciliation

BEGIN;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_care_compare (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_care_compare',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_care_compare',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_care_compare_ingested ON hcs_raw.cms_care_compare(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_chow (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_chow',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_chow',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_chow_ingested ON hcs_raw.cms_chow(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_ddinter (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_ddinter',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_ddinter',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_ddinter_ingested ON hcs_raw.cms_ddinter(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_dmepos (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_dmepos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_dmepos',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_dmepos_ingested ON hcs_raw.cms_dmepos(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_formulary (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_formulary',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_formulary',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_formulary_ingested ON hcs_raw.cms_formulary(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hcris (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hcris',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_hcris',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_hcris_ingested ON hcs_raw.cms_hcris(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_affiliation (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_affiliation',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_affiliation',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_hospital_affil_ingested ON hcs_raw.cms_hospital_affiliation(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_quality (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_hospital_quality',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_hospital_quality',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_hospital_qual_ingested ON hcs_raw.cms_hospital_quality(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_magnet (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_magnet',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_magnet',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_magnet_ingested ON hcs_raw.cms_magnet(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_ndc (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_ndc',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_ndc',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_ndc_ingested ON hcs_raw.cms_ndc(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_nucc (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_nucc',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_nucc',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_nucc_ingested ON hcs_raw.cms_nucc(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_pecos (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_pecos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_pecos',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_pecos_ingested ON hcs_raw.cms_pecos(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_pos (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_pos',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_pos',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_pos_ingested ON hcs_raw.cms_pos(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_post_acute (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_post_acute',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_post_acute',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_post_acute_ingested ON hcs_raw.cms_post_acute(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_rbcs (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_rbcs',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_rbcs',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_rbcs_ingested ON hcs_raw.cms_rbcs(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_stabilis (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_stabilis',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_stabilis',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_stabilis_ingested ON hcs_raw.cms_stabilis(ingested_at);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_usp (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    api_endpoint        TEXT NOT NULL DEFAULT 'cms_usp',
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  TEXT,
    source_id           TEXT NOT NULL DEFAULT 'cms_usp',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (response_body_hash) NULLS NOT DISTINCT
);
CREATE INDEX IF NOT EXISTS idx_hcs_raw_cms_usp_ingested ON hcs_raw.cms_usp(ingested_at);

-- Register in meta.data_sources
INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES
    ('cms_care_compare',     'api', 'https://data.cms.gov/provider-data',  'CMS Care Compare physician/facility quality data',     'quarterly', true),
    ('cms_chow',             'api', 'https://data.cms.gov',                'CMS Change of Ownership records',                      'monthly',   true),
    ('cms_ddinter',          'api', 'https://data.cms.gov',                'CMS Drug-Drug Interaction reference data',              'monthly',   true),
    ('cms_dmepos',           'api', 'https://data.cms.gov',                'CMS DMEPOS supplier directory',                        'quarterly', true),
    ('cms_formulary',        'api', 'https://data.cms.gov',                'CMS Part D formulary drug coverage data',              'annual',    true),
    ('cms_hcris',            'api', 'https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/Cost-Reports', 'CMS Healthcare Cost Report Information System', 'annual', true),
    ('cms_hospital_affiliation', 'api', 'https://data.cms.gov',           'CMS hospital-physician affiliation data',              'annual',    true),
    ('cms_hospital_quality', 'api', 'https://data.cms.gov/provider-data', 'CMS Hospital Quality Initiative measures',             'quarterly', true),
    ('cms_magnet',           'api', 'https://data.cms.gov',               'CMS Magnet status nursing excellence data',             'annual',    true),
    ('cms_ndc',              'api', 'https://data.cms.gov',               'CMS National Drug Code directory',                     'monthly',   true),
    ('cms_nucc',             'api', 'https://www.nucc.org',               'NUCC Health Care Provider Taxonomy code set',          'annual',    true),
    ('cms_pecos',            'api', 'https://data.cms.gov',               'CMS Provider Enrollment Chain and Ownership System',   'quarterly', true),
    ('cms_pos',              'api', 'https://www.cms.gov/Medicare/Provider-Enrollment-and-Certification/CertificationandComplianc/Downloads/usproviderfacilities.zip', 'CMS Provider of Services facility file', 'annual', true),
    ('cms_post_acute',       'api', 'https://data.cms.gov',               'CMS Post-Acute care provider data',                    'quarterly', true),
    ('cms_rbcs',             'api', 'https://data.cms.gov',               'CMS Restructured BETOS Classification System',         'annual',    true),
    ('cms_stabilis',         'api', 'https://data.cms.gov',               'CMS drug stability reference data',                    'annual',    true),
    ('cms_usp',              'api', 'https://data.cms.gov',               'CMS United States Pharmacopeia drug standards',        'annual',    true)
ON CONFLICT (source_name) DO UPDATE
    SET is_active         = EXCLUDED.is_active,
        source_url        = EXCLUDED.source_url,
        description       = EXCLUDED.description,
        refresh_frequency = EXCLUDED.refresh_frequency;

-- Grant analyst read access
GRANT SELECT ON hcs_raw.cms_care_compare         TO analyst;
GRANT SELECT ON hcs_raw.cms_chow                 TO analyst;
GRANT SELECT ON hcs_raw.cms_ddinter              TO analyst;
GRANT SELECT ON hcs_raw.cms_dmepos               TO analyst;
GRANT SELECT ON hcs_raw.cms_formulary            TO analyst;
GRANT SELECT ON hcs_raw.cms_hcris                TO analyst;
GRANT SELECT ON hcs_raw.cms_hospital_affiliation TO analyst;
GRANT SELECT ON hcs_raw.cms_hospital_quality     TO analyst;
GRANT SELECT ON hcs_raw.cms_magnet               TO analyst;
GRANT SELECT ON hcs_raw.cms_ndc                  TO analyst;
GRANT SELECT ON hcs_raw.cms_nucc                 TO analyst;
GRANT SELECT ON hcs_raw.cms_pecos                TO analyst;
GRANT SELECT ON hcs_raw.cms_pos                  TO analyst;
GRANT SELECT ON hcs_raw.cms_post_acute           TO analyst;
GRANT SELECT ON hcs_raw.cms_rbcs                 TO analyst;
GRANT SELECT ON hcs_raw.cms_stabilis             TO analyst;
GRANT SELECT ON hcs_raw.cms_usp                  TO analyst;

COMMIT;
