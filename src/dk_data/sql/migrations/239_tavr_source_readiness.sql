-- Migration 239: TAVR source readiness
-- Spec: .dk/specs/007-tavr-source-readiness-provisioning/spec.md
-- Handoff: 2026-05-14-edwards-meadow-to-dk-data-fe-provision-tavr-source-readiness.md
-- Composite parent: 2026-05-13-edwards-meadow-to-dk-data-fe-confirm-hcs-tavr-gold-provisioning-ownership (closed)
--
-- Phase 1A — identity + readiness flags. One row per source_id classifying
-- the source as claim-eligible / context-only / blocked / absent, driven by
-- meta.refresh_log + meta.table_health + the upstream catalog manifest.
--
-- This is a derived gold table — the loader composes it from existing meta.*
-- and hcs_gold.tavr_catalog_candidate_manifest rows. No new bronze/silver
-- layer; the bronze/silver state already lives in meta (refresh_log,
-- table_health) and is the canonical source of truth.

BEGIN;

-- ----------------------------------------------------------------------------
-- Gold: per-source claim-eligibility classifier with provenance discipline.
-- Every row carries the eight required columns (source_class, coverage_class,
-- use_class, grain, as_of_date, source_id, confidence, caveat_text).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hcs_gold.tavr_source_readiness (
  source_id               TEXT PRIMARY KEY,

  -- Classifier output.
  status                  TEXT NOT NULL CHECK (status IN (
                            'claim_eligible',
                            'context_only',
                            'blocked',
                            'absent'
                          )),

  -- Health + freshness pulled from meta.refresh_log / meta.table_health.
  row_count               BIGINT,
  last_refresh_at         TIMESTAMPTZ,
  age_hours               NUMERIC,
  health_status           TEXT,

  -- Provenance discipline — NOT NULL, controlled vocabularies.
  source_class            TEXT NOT NULL CHECK (source_class IN (
                            'public_machine_readable',
                            'public_abstractable',
                            'licensed_commercial',
                            'private_or_partner'
                          )),
  coverage_class          TEXT NOT NULL,
  use_class               TEXT NOT NULL,
  grain                   TEXT NOT NULL DEFAULT 'source'
                            CHECK (grain = 'source'),
  as_of_date              TIMESTAMPTZ NOT NULL,
  confidence              NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  caveat_text             TEXT NOT NULL DEFAULT '',

  -- Lifecycle.
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tavr_source_readiness_status_idx
  ON hcs_gold.tavr_source_readiness (status);
CREATE INDEX IF NOT EXISTS tavr_source_readiness_source_class_idx
  ON hcs_gold.tavr_source_readiness (source_class);
CREATE INDEX IF NOT EXISTS tavr_source_readiness_last_refresh_idx
  ON hcs_gold.tavr_source_readiness (last_refresh_at DESC NULLS LAST);

COMMENT ON TABLE hcs_gold.tavr_source_readiness IS
  'Phase 1A per-source claim-eligibility classifier for the TAVR Benchmark Lab. One row per source_id with status (claim_eligible/context_only/blocked/absent), freshness from meta.refresh_log, and health from meta.table_health. Required for tavr-bench run --suite dk-data-origin-readiness. Provenance discipline: every row carries the eight NOT NULL columns. See .dk/specs/007-tavr-source-readiness-provisioning/spec.md.';

COMMENT ON COLUMN hcs_gold.tavr_source_readiness.status IS
  'claim_eligible: source can be used as a citation in TAVR benchmark output. context_only: useful background but not citable on its own. blocked: licensing/access prevents use. absent: source not yet provisioned in dk-data.';

-- ----------------------------------------------------------------------------
-- Permissions — match the pattern in migration 238.
-- ----------------------------------------------------------------------------
DO $perms$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO readonly';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_source_readiness TO readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO api_user';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_source_readiness TO api_user';
  END IF;
END $perms$;

COMMIT;
