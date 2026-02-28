-- 081: Extend gold tables with columns needed by the silver→gold refresher.
-- All gold tables are currently empty, so this is purely additive.

-- ─── gold.molecule_profile ──────────────────────────────────────────────────
ALTER TABLE gold.molecule_profile
  ADD COLUMN IF NOT EXISTS molecule_type          TEXT,
  ADD COLUMN IF NOT EXISTS inchi_key              TEXT,
  ADD COLUMN IF NOT EXISTS lifecycle_stage        TEXT,
  ADD COLUMN IF NOT EXISTS lifecycle_stage_confidence NUMERIC,
  ADD COLUMN IF NOT EXISTS lifecycle_last_detected    TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS drugbank_id            TEXT,
  ADD COLUMN IF NOT EXISTS chembl_id              TEXT,
  ADD COLUMN IF NOT EXISTS pubchem_cid            TEXT,
  ADD COLUMN IF NOT EXISTS pipeline_indications   JSONB,
  ADD COLUMN IF NOT EXISTS serious_ae_count       INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ae_summary             JSONB,
  ADD COLUMN IF NOT EXISTS earliest_patent_expiry TEXT,
  ADD COLUMN IF NOT EXISTS patent_count           INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS data_completeness_score NUMERIC,
  ADD COLUMN IF NOT EXISTS data_sources           JSONB,
  ADD COLUMN IF NOT EXISTS last_data_update       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS updated_at             TIMESTAMPTZ DEFAULT NOW();

-- ─── gold.safety_signals ────────────────────────────────────────────────────
ALTER TABLE gold.safety_signals
  ADD COLUMN IF NOT EXISTS reaction_name     TEXT,
  ADD COLUMN IF NOT EXISTS reaction_meddra_pt TEXT,
  ADD COLUMN IF NOT EXISTS case_count        INT,
  ADD COLUMN IF NOT EXISTS serious_count     INT,
  ADD COLUMN IF NOT EXISTS fatal_count       INT,
  ADD COLUMN IF NOT EXISTS pro_score         NUMERIC,
  ADD COLUMN IF NOT EXISTS ror_score         NUMERIC,
  ADD COLUMN IF NOT EXISTS is_signal         BOOLEAN DEFAULT FALSE;

-- ─── gold.lifecycle_stages ──────────────────────────────────────────────────
ALTER TABLE gold.lifecycle_stages
  ADD COLUMN IF NOT EXISTS indication           TEXT,
  ADD COLUMN IF NOT EXISTS stage_confidence      NUMERIC,
  ADD COLUMN IF NOT EXISTS evidence_count        INT,
  ADD COLUMN IF NOT EXISTS primary_evidence_type TEXT,
  ADD COLUMN IF NOT EXISTS updated_at            TIMESTAMPTZ DEFAULT NOW();

-- Add unique constraint on (molecule_id, indication) for upsert
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'lifecycle_stages_molecule_indication_uq'
  ) THEN
    ALTER TABLE gold.lifecycle_stages
      ADD CONSTRAINT lifecycle_stages_molecule_indication_uq
      UNIQUE (molecule_id, indication);
  END IF;
END $$;

-- ─── gold.competitive_landscape ─────────────────────────────────────────────
ALTER TABLE gold.competitive_landscape
  ADD COLUMN IF NOT EXISTS indication     TEXT,
  ADD COLUMN IF NOT EXISTS total_molecules INT,
  ADD COLUMN IF NOT EXISTS phase_3_count  INT,
  ADD COLUMN IF NOT EXISTS phase_2_count  INT,
  ADD COLUMN IF NOT EXISTS phase_1_count  INT,
  ADD COLUMN IF NOT EXISTS snapshot_date  DATE,
  ADD COLUMN IF NOT EXISTS updated_at     TIMESTAMPTZ DEFAULT NOW();

-- Add unique constraint on (indication, snapshot_date) for upsert
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'competitive_landscape_indication_date_uq'
  ) THEN
    ALTER TABLE gold.competitive_landscape
      ADD CONSTRAINT competitive_landscape_indication_date_uq
      UNIQUE (indication, snapshot_date);
  END IF;
END $$;

-- ─── gold.trial_outcomes ────────────────────────────────────────────────────
ALTER TABLE gold.trial_outcomes
  ADD COLUMN IF NOT EXISTS phase       TEXT,
  ADD COLUMN IF NOT EXISTS status      TEXT,
  ADD COLUMN IF NOT EXISTS enrollment  INT,
  ADD COLUMN IF NOT EXISTS sponsor     TEXT,
  ADD COLUMN IF NOT EXISTS conditions  JSONB,
  ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ DEFAULT NOW();

-- Add unique constraint on nct_id for upsert
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'trial_outcomes_nct_id_uq'
  ) THEN
    ALTER TABLE gold.trial_outcomes
      ADD CONSTRAINT trial_outcomes_nct_id_uq
      UNIQUE (nct_id);
  END IF;
END $$;

-- Grants
GRANT SELECT, INSERT, UPDATE ON gold.molecule_profile     TO dk_app;
GRANT SELECT, INSERT, UPDATE ON gold.safety_signals       TO dk_app;
GRANT SELECT, INSERT, UPDATE ON gold.lifecycle_stages     TO dk_app;
GRANT SELECT, INSERT, UPDATE ON gold.competitive_landscape TO dk_app;
GRANT SELECT, INSERT, UPDATE ON gold.trial_outcomes       TO dk_app;

GRANT SELECT ON gold.molecule_profile      TO web_anon;
GRANT SELECT ON gold.safety_signals        TO web_anon;
GRANT SELECT ON gold.lifecycle_stages      TO web_anon;
GRANT SELECT ON gold.competitive_landscape TO web_anon;
GRANT SELECT ON gold.trial_outcomes        TO web_anon;
