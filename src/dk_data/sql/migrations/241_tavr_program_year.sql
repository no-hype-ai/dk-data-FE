-- Migration 241: TAVR program-year facts (DRG 266/267 MedPAR-like proxy)
-- Spec: .dk/specs/009-tavr-program-year-provisioning/spec.md
-- Handoff: 2026-05-14-edwards-meadow-to-dk-data-fe-provision-tavr-program-year.md
-- Composite parent: 2026-05-13-edwards-meadow-to-dk-data-fe-confirm-hcs-tavr-gold-provisioning-ownership (closed)
--
-- Phase 1A — DRG-grain program facts. One row per (ccn × year) with DRG 266
-- and DRG 267 discharges, payment / charge averages, MCC capture proxy,
-- YoY growth, national/state percentile.
--
-- Proxy method: data-researcher §4.5 (MedPAR-like baseline). Sources:
-- CMS Medicare Inpatient Hospitals by Provider and Service (annual; DRG
-- 266/267) + CMS Medicare Inpatient by Provider (totals) + CMS Medicare
-- Inpatient by Geography and Service (peer denominators).

BEGIN;

CREATE TABLE IF NOT EXISTS hcs_gold.tavr_program_year (
  ccn                       TEXT NOT NULL,
  year                      INTEGER NOT NULL CHECK (year BETWEEN 2018 AND 2100),

  -- Volume.
  drg_266_discharges        INTEGER NOT NULL DEFAULT 0,
  drg_267_discharges        INTEGER NOT NULL DEFAULT 0,

  -- Financial proxies. Units are usd_per_discharge — NOT a rate. The
  -- column comment makes this explicit so downstream consumers can't
  -- treat them as rate-bearing (red-flag gate: maude_used_as_rate).
  avg_payment               NUMERIC(12,2),
  avg_charge                NUMERIC(12,2),

  -- MCC capture proxy = drg_266 / (drg_266 + drg_267); NULL when denom=0.
  mcc_capture_proxy         NUMERIC(4,3) CHECK (
                              mcc_capture_proxy IS NULL
                              OR mcc_capture_proxy BETWEEN 0 AND 1
                            ),

  -- Year-over-year + percentile precomputed for read-side speed.
  yoy_growth                NUMERIC(6,3),
  national_percentile       NUMERIC(4,3) CHECK (
                              national_percentile IS NULL
                              OR national_percentile BETWEEN 0 AND 1
                            ),
  state_percentile          NUMERIC(4,3) CHECK (
                              state_percentile IS NULL
                              OR state_percentile BETWEEN 0 AND 1
                            ),

  -- TVT signal column present so Phase 4 abstracted evidence can backfill;
  -- NULL = no abstracted evidence available, false = explicitly negative.
  tvt_signal                BOOLEAN,

  source_class              TEXT NOT NULL CHECK (source_class IN (
                              'public_machine_readable',
                              'public_abstractable',
                              'licensed_commercial',
                              'private_or_partner'
                            )),
  coverage_class            TEXT NOT NULL,
  use_class                 TEXT NOT NULL,
  grain                     TEXT NOT NULL DEFAULT 'hospital_year'
                              CHECK (grain = 'hospital_year'),
  as_of_date                TIMESTAMPTZ NOT NULL,
  source_id                 TEXT NOT NULL,
  confidence                NUMERIC(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  caveat_text               TEXT NOT NULL DEFAULT
    'DRG 266/267 Medicare FFS proxy; hospital-year; benchmark-shape only; not all-payer TAVR volume',

  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (ccn, year)
);

CREATE INDEX IF NOT EXISTS tavr_program_year_year_idx
  ON hcs_gold.tavr_program_year (year DESC);
CREATE INDEX IF NOT EXISTS tavr_program_year_ccn_idx
  ON hcs_gold.tavr_program_year (ccn, year DESC);
CREATE INDEX IF NOT EXISTS tavr_program_year_volume_idx
  ON hcs_gold.tavr_program_year ((drg_266_discharges + drg_267_discharges) DESC);

COMMENT ON TABLE hcs_gold.tavr_program_year IS
  'Phase 1A DRG-grain TAVR program facts per (ccn, year). DRG 266/267 Medicare FFS proxy (data-researcher §4.5). Year coverage 2018–latest per CMS public release cadence. caveat_text is binding: not all-payer TAVR volume.';

COMMENT ON COLUMN hcs_gold.tavr_program_year.avg_payment IS
  'Average Medicare payment per discharge in USD. Unit: usd_per_discharge. NOT a rate; do not divide or multiply against population denominators.';
COMMENT ON COLUMN hcs_gold.tavr_program_year.avg_charge IS
  'Average submitted charge per discharge in USD. Unit: usd_per_discharge. NOT a rate.';
COMMENT ON COLUMN hcs_gold.tavr_program_year.tvt_signal IS
  'Three-state: NULL = no Phase 4 abstracted evidence available; true/false = explicit evidence found by Phase 4 backfill.';

DO $perms$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO readonly';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_program_year TO readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO api_user';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_program_year TO api_user';
  END IF;
END $perms$;

COMMIT;
