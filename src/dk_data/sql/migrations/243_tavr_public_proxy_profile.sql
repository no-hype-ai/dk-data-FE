-- Migration 243: TAVR public proxy profile (Phase 1B)
-- Spec: .dk/specs/011-tavr-public-proxy-profile-provisioning/spec.md
-- Handoff: 2026-05-14-edwards-meadow-to-dk-data-fe-provision-tavr-public-proxy-profile.md
-- Composite parent: 2026-05-13-edwards-meadow-to-dk-data-fe-confirm-hcs-tavr-gold-provisioning-ownership (closed)
--
-- Phase 1B — Public approximation layer for licensed-style fields. One row
-- per (ccn × year). The schema includes a side-by-side public/licensed/
-- selected structure so Stage 4.5 can layer in licensed overlays without
-- schema migration.
--
-- Source datasets: hcs_gold.tavr_program_year + hcs_gold.tavr_hospital_profile
-- (own outputs) + CMS HCRIS + CMS Hospital Service Area + Medicare Physician
-- PUF + NPPES + Doctors & Clinicians + Open Payments.

BEGIN;

CREATE TABLE IF NOT EXISTS hcs_gold.tavr_public_proxy_profile (
  ccn                       TEXT NOT NULL,
  year                      INTEGER NOT NULL,

  -- Volume proxy.
  volume_proxy_public       INTEGER,
  volume_proxy_licensed     INTEGER,
  volume_proxy_selected     INTEGER,
  volume_selected_source    TEXT,

  -- Payment proxy (CCR-based from HCRIS).
  payment_proxy_public      NUMERIC(12,2),
  payment_proxy_licensed    NUMERIC(12,2),
  payment_proxy_selected    NUMERIC(12,2),
  payment_selected_source   TEXT,

  -- Catchment proxy. JSONB array of {zip, share}. Population-routed
  -- catchment shares ONLY — proximity-inferred referrers are forbidden
  -- (red-flag gate top_referrer_inferred_from_proximity).
  catchment_proxy_public    JSONB DEFAULT '[]'::jsonb,
  catchment_proxy_licensed  JSONB DEFAULT '[]'::jsonb,
  catchment_proxy_selected  JSONB DEFAULT '[]'::jsonb,
  catchment_selected_source TEXT,

  -- Readiness proxy (cardiac / cath / TVT / cert signals).
  readiness_proxy_public    JSONB DEFAULT '{}'::jsonb,
  readiness_proxy_licensed  JSONB DEFAULT '{}'::jsonb,
  readiness_proxy_selected  JSONB DEFAULT '{}'::jsonb,
  readiness_selected_source TEXT,

  -- Physician signal proxy (NPI count, structural-heart hits, KOL signal).
  physician_signal_public   JSONB DEFAULT '{}'::jsonb,
  physician_signal_licensed JSONB DEFAULT '{}'::jsonb,
  physician_signal_selected JSONB DEFAULT '{}'::jsonb,
  physician_selected_source TEXT,

  -- Completeness score 0.0–1.0 — fraction of (volume, payment, catchment,
  -- readiness, physician) proxies with a non-null selected value.
  completeness              NUMERIC(3,2) NOT NULL DEFAULT 0
                              CHECK (completeness BETWEEN 0 AND 1),

  -- Provenance discipline — NOT NULL, controlled vocabularies.
  -- IMPORTANT: coverage_class is FIXED to 'public_proxy' here (NOT
  -- 'baseline_public'); use_class is FIXED to 'benchmark_shape_or_load'.
  -- Both are CHECK-constrained so a future migration cannot relax them
  -- without an explicit code change + reviewer ack.
  source_class              TEXT NOT NULL CHECK (source_class IN (
                              'public_machine_readable',
                              'public_abstractable',
                              'licensed_commercial',
                              'private_or_partner'
                            )),
  coverage_class            TEXT NOT NULL DEFAULT 'public_proxy'
                              CHECK (coverage_class = 'public_proxy'),
  use_class                 TEXT NOT NULL DEFAULT 'benchmark_shape_or_load'
                              CHECK (use_class = 'benchmark_shape_or_load'),
  grain                     TEXT NOT NULL DEFAULT 'hospital_year'
                              CHECK (grain = 'hospital_year'),
  as_of_date                TIMESTAMPTZ NOT NULL,
  source_id                 TEXT NOT NULL,
  confidence                NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  caveat_text               TEXT NOT NULL DEFAULT
    'Public proxy layer; benchmark-shape-or-load only. Side-by-side licensed columns NULL in v1. Stage 4.5 will layer licensed overlays without schema migration.',

  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (ccn, year)
);

CREATE INDEX IF NOT EXISTS tavr_public_proxy_profile_ccn_year_idx
  ON hcs_gold.tavr_public_proxy_profile (ccn, year DESC);
CREATE INDEX IF NOT EXISTS tavr_public_proxy_profile_completeness_idx
  ON hcs_gold.tavr_public_proxy_profile (year DESC, completeness DESC);

COMMENT ON TABLE hcs_gold.tavr_public_proxy_profile IS
  'Phase 1B public approximation layer for licensed-style TAVR fields. Side-by-side public/licensed/selected schema so Stage 4.5 can layer licensed overlays without schema migration. coverage_class is CHECK-constrained to public_proxy; use_class to benchmark_shape_or_load. All seven red-flag detectors apply to this layer. caveat_text is binding. See .dk/specs/011-tavr-public-proxy-profile-provisioning/spec.md.';

COMMENT ON COLUMN hcs_gold.tavr_public_proxy_profile.catchment_proxy_public IS
  'Top-N ZIPs from CMS Hospital Service Area. Population-routed catchment shares ONLY. proximity-inferred referrers are NOT allowed and would violate red-flag gate top_referrer_inferred_from_proximity.';

DO $perms$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO readonly';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_public_proxy_profile TO readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO api_user';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_public_proxy_profile TO api_user';
  END IF;
END $perms$;

COMMIT;
