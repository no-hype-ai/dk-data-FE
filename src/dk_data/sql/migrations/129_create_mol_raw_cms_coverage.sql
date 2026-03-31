-- Migration 129: Create mol_raw.cms_coverage
-- Feature: 021-post-deploy-fixes
--
-- CMS Medicare Coverage Database — National Coverage Determinations (NCDs),
-- National Coverage Analyses (NCAs), and Technology Assessments from the
-- CMS Coverage API (https://api.coverage.cms.gov/v1/data/).
--
-- US equivalent of NICE HTA: authoritative Medicare coverage policy decisions
-- for drugs, devices, and medical services. Free public REST API, no auth
-- required for NCD/NCA/TA endpoints.
--
-- Follows the standard mol_raw JSONB envelope schema.
-- Unique index on (id, _endpoint) — IDs are unique per endpoint type.

BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.cms_coverage (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'cms_coverage',
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
    source_id           VARCHAR(50) NOT NULL DEFAULT 'cms_coverage'
);

-- One record per (coverage_id, endpoint) — prevents re-inserting unchanged decisions
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_cms_coverage_id_endpoint
    ON mol_raw.cms_coverage ((response_body->>'id'), (response_body->>'_endpoint'))
    WHERE response_body->>'id' IS NOT NULL
      AND response_body->>'_endpoint' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mol_raw_cms_coverage_ts
    ON mol_raw.cms_coverage(ingested_at);

CREATE INDEX IF NOT EXISTS idx_mol_raw_cms_coverage_bronze
    ON mol_raw.cms_coverage(processed_to_bronze)
    WHERE NOT processed_to_bronze;

CREATE INDEX IF NOT EXISTS idx_mol_raw_cms_coverage_endpoint
    ON mol_raw.cms_coverage((response_body->>'_endpoint'));

GRANT SELECT ON mol_raw.cms_coverage TO web_anon, analyst;

COMMIT;
