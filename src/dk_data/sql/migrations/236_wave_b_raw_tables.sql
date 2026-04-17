-- Migration 236: Create raw tables for Wave B sources (top-15 onboarding).
-- Applied manually to prod on 2026-04-17; this file ensures reproducibility
-- on staging and future environments.
-- All tables are idempotent (CREATE TABLE IF NOT EXISTS).

BEGIN;

-- CMS Quality trio (PRs #324-#326)
CREATE TABLE IF NOT EXISTS hcs_raw.cms_hac_reduction (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  source_year INT,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cms_hac_reduction_ingested ON hcs_raw.cms_hac_reduction (ingested_at DESC);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hrrp (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  source_year INT,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cms_hrrp_ingested ON hcs_raw.cms_hrrp (ingested_at DESC);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_vbp (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  source_year INT,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cms_vbp_ingested ON hcs_raw.cms_vbp (ingested_at DESC);

-- FDA pair (PRs #330-#331)
CREATE TABLE IF NOT EXISTS mol_raw.fda_enforcement (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fda_enforcement_ingested ON mol_raw.fda_enforcement (ingested_at DESC);

CREATE TABLE IF NOT EXISTS mol_raw.fda_shortages (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fda_shortages_ingested ON mol_raw.fda_shortages (ingested_at DESC);

-- International health spend (PRs #334-#337)
CREATE TABLE IF NOT EXISTS hcs_raw.who_ghed (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_who_ghed_ingested ON hcs_raw.who_ghed (ingested_at DESC);

CREATE TABLE IF NOT EXISTS hcs_raw.worldbank_health (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  indicator_code TEXT,
  response_body JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_worldbank_health_ingested ON hcs_raw.worldbank_health (ingested_at DESC);

CREATE TABLE IF NOT EXISTS hcs_raw.oecd_health (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oecd_health_ingested ON hcs_raw.oecd_health (ingested_at DESC);

CREATE TABLE IF NOT EXISTS mol_raw.pbs_australia (
  id BIGSERIAL PRIMARY KEY,
  api_endpoint TEXT,
  response_body JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pbs_australia_ingested ON mol_raw.pbs_australia (ingested_at DESC);

COMMIT;
