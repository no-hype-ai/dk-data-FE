-- Migration 242: TAVR benchmark inputs (denormalized scoring inputs)
-- Spec: .dk/specs/010-tavr-benchmark-inputs-provisioning/spec.md
-- Handoff: 2026-05-14-edwards-meadow-to-dk-data-fe-provision-tavr-benchmark-inputs.md
-- Composite parent: 2026-05-13-edwards-meadow-to-dk-data-fe-confirm-hcs-tavr-gold-provisioning-ownership (closed)
--
-- Phase 1B — read-optimized scoring inputs. One row per (ccn × year) with
-- denormalized identity + program facts + catchment + payment-adjustment
-- context so peer-matching and target-scoring queries are a single SELECT.
--
-- Source datasets: hcs_gold.tavr_hospital_profile + hcs_gold.tavr_program_year
-- (own outputs from Phase 1A) + CMS Hospital Service Area + MSPB + VBP +
-- HRRP + HAC (financial/quality pressure context).

BEGIN;

CREATE TABLE IF NOT EXISTS hcs_gold.tavr_benchmark_inputs (
  ccn                       TEXT NOT NULL,
  year                      INTEGER NOT NULL,

  -- Identity (denormalized from tavr_hospital_profile).
  facility_name             TEXT,
  cbsa                      TEXT,
  hrr                       TEXT,
  state                     TEXT,
  facility_scale_band       TEXT,
  bed_count                 INTEGER,
  ownership                 TEXT,
  system_parent             TEXT,
  teaching_proxy            BOOLEAN,
  cardiac_surgery_signal    BOOLEAN,
  cath_lab_signal           BOOLEAN,

  -- Program facts (denormalized from tavr_program_year).
  drg_266_discharges        INTEGER,
  drg_267_discharges        INTEGER,
  total_tavr_proxy          INTEGER,  -- 266 + 267
  avg_payment               NUMERIC(12,2),
  avg_charge                NUMERIC(12,2),
  mcc_capture_proxy         NUMERIC(4,3),
  yoy_growth                NUMERIC(6,3),
  national_percentile       NUMERIC(4,3),
  state_percentile          NUMERIC(4,3),

  -- Catchment proxy: top-N ZIPs from CMS Hospital Service Area. JSONB array
  -- of objects {zip, share}. NOT a referrer list — proximity-only inference
  -- is explicitly NOT supported here (red-flag gate
  -- top_referrer_inferred_from_proximity in table comment).
  catchment_top_zips        JSONB DEFAULT '[]'::jsonb,

  -- Payment-adjustment context.
  vbp_adjustment_factor     NUMERIC(6,4),
  hrrp_adjustment_factor    NUMERIC(6,4),
  hac_reduction_flag        BOOLEAN,
  mspb_score                NUMERIC(6,3),

  -- Lineage map: per-input field → source gold table name (or 'null').
  source_lineage            JSONB NOT NULL DEFAULT '{}'::jsonb,

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
    'Denormalized scoring inputs. Source lineage in source_lineage JSONB. Top-N ZIPs are CMS Hospital Service Area catchment shares, NOT inferred referrers.',

  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (ccn, year)
);

CREATE INDEX IF NOT EXISTS tavr_benchmark_inputs_ccn_year_idx
  ON hcs_gold.tavr_benchmark_inputs (ccn, year DESC);
CREATE INDEX IF NOT EXISTS tavr_benchmark_inputs_cbsa_idx
  ON hcs_gold.tavr_benchmark_inputs (cbsa, year DESC);
CREATE INDEX IF NOT EXISTS tavr_benchmark_inputs_volume_idx
  ON hcs_gold.tavr_benchmark_inputs (year DESC, total_tavr_proxy DESC NULLS LAST);

COMMENT ON TABLE hcs_gold.tavr_benchmark_inputs IS
  'Phase 1B denormalized scoring inputs per (ccn, year). All inputs required by edwards-meadow''s peer-matching + target-scoring code in a single SELECT. catchment_top_zips is CMS Hospital Service Area-derived; this table does NOT and MUST NOT contain referrer inferences (red-flag gate top_referrer_inferred_from_proximity). Source lineage map in source_lineage JSONB per-field. See .dk/specs/010-tavr-benchmark-inputs-provisioning/spec.md.';

DO $perms$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO readonly';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_benchmark_inputs TO readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_user') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA hcs_gold TO api_user';
    EXECUTE 'GRANT SELECT ON hcs_gold.tavr_benchmark_inputs TO api_user';
  END IF;
END $perms$;

COMMIT;
