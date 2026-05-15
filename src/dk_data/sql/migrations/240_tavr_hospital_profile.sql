-- Migration 240: TAVR hospital profile (AHD-like facility profile)
-- Spec: .dk/specs/008-tavr-hospital-profile-provisioning/spec.md
-- Handoff: 2026-05-14-edwards-meadow-to-dk-data-fe-provision-tavr-hospital-profile.md
-- Composite parent: 2026-05-13-edwards-meadow-to-dk-data-fe-confirm-hcs-tavr-gold-provisioning-ownership (closed)
--
-- Phase 1A — identity + readiness flags. One row per active IPPS CCN
-- (~5,400 hospitals) with identity, ownership cascade, scale band, and
-- proxy signals for teaching / cardiac-surgery / cath-lab / TVT.
--
-- Proxy method: data-researcher §4.1 (AHD-like hospital facility profile).
-- Sources: CMS Hospital General Information + PoS + HCRIS + HRSA AHRF +
-- USDA RUCA + Census CBSA/ZCTA/TIGER + IRS 990. All public, machine readable.

BEGIN;

CREATE TABLE IF NOT EXISTS hcs_gold.tavr_hospital_profile (
  ccn                     TEXT PRIMARY KEY,

  facility_name           TEXT NOT NULL,
  address                 TEXT NOT NULL,
  county_fips             TEXT NOT NULL,
  cbsa                    TEXT NOT NULL,
  hrr                     TEXT NOT NULL,
  hsa                     TEXT NOT NULL,
  zcta                    TEXT NOT NULL,
  ruca                    TEXT NOT NULL,

  ownership               TEXT,
  system_parent           TEXT,
  source_confidence       JSONB NOT NULL DEFAULT '{}'::jsonb,

  facility_scale_band     TEXT,
  bed_count               INTEGER,
  inpatient_days          INTEGER,
  teaching_proxy          BOOLEAN NOT NULL DEFAULT false,
  cardiac_surgery_signal  BOOLEAN NOT NULL DEFAULT false,
  cath_lab_signal         BOOLEAN NOT NULL DEFAULT false,
  tvt_signal              BOOLEAN NOT NULL DEFAULT false,

  source_class            TEXT NOT NULL CHECK (source_class IN (
                            'public_machine_readable',
                            'public_abstractable',
                            'licensed_commercial',
                            'private_or_partner'
                          )),
  coverage_class          TEXT NOT NULL,
  use_class               TEXT NOT NULL,
  grain                   TEXT NOT NULL DEFAULT 'facility'
                            CHECK (grain = 'facility'),
  as_of_date              TIMESTAMPTZ NOT NULL,
  source_id               TEXT NOT NULL,
  confidence              NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  caveat_text             TEXT NOT NULL DEFAULT
    'AHD-like public facility profile derived from CMS + HRSA + Census; not equivalent to AHD subscription data',

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tavr_hospital_profile_state_idx
  ON hcs_gold.tavr_hospital_profile (county_fips);
CREATE INDEX IF NOT EXISTS tavr_hospital_profile_cbsa_idx
  ON hcs_gold.tavr_hospital_profile (cbsa);
CREATE INDEX IF NOT EXISTS tavr_hospital_profile_system_idx
  ON hcs_gold.tavr_hospital_profile (system_parent)
  WHERE system_parent IS NOT NULL;
CREATE INDEX IF NOT EXISTS tavr_hospital_profile_tvt_idx
  ON hcs_gold.tavr_hospital_profile (tvt_signal)
  WHERE tvt_signal = true;

COMMENT ON TABLE hcs_gold.tavr_hospital_profile IS
  'Phase 1A AHD-like hospital facility profile for the TAVR Benchmark Lab. One row per active IPPS CCN. Identity fields NOT NULL; ownership cascade (CMS-first) recorded with per-field source_confidence. Red-flag gate: system_filing_applied_to_facility — system-level IRS 990 / EMMA rows MUST NOT populate facility-grain fields without an explicit facility-named quote span. See .dk/specs/008-tavr-hospital-profile-provisioning/spec.md.';

DO $perms$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO readonly';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_hospital_profile TO readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO api_user';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_hospital_profile TO api_user';
  END IF;
END $perms$;

COMMIT;
