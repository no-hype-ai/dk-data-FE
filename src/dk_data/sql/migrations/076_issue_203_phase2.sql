-- Migration 076: Issue #203 Phase 2 root-cause fixes
-- Idempotent schema and metadata corrections plus type/index drift fix.

-- Root Cause A: meta.refresh_log missing source_name -------------------------
ALTER TABLE meta.refresh_log
ADD COLUMN IF NOT EXISTS source_name TEXT;

CREATE INDEX IF NOT EXISTS idx_refresh_log_source_name
  ON meta.refresh_log(source_name);

-- Root Cause B: mol_raw.reactome missing request_id --------------------------
-- Guard: reactome is a live-only table (not created by migrations 001-075);
-- skip gracefully if it doesn't exist in this environment.
DO $$
BEGIN
  IF to_regclass('mol_raw.reactome') IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'mol_raw'
        AND table_name = 'reactome'
        AND column_name = 'request_id'
    ) THEN
      EXECUTE 'ALTER TABLE mol_raw.reactome ADD COLUMN request_id TEXT';
      RAISE NOTICE 'Added mol_raw.reactome.request_id';
    END IF;

    EXECUTE '
      CREATE UNIQUE INDEX IF NOT EXISTS uq_mol_raw_reactome_request_id
      ON mol_raw.reactome(request_id)
      WHERE request_id IS NOT NULL
    ';
    RAISE NOTICE 'Created uq_mol_raw_reactome_request_id';
  ELSE
    RAISE NOTICE 'mol_raw.reactome does not exist — skipping Root Cause B';
  END IF;
END
$$;

-- Root Cause D: Ensure CMS sources exist in meta.data_sources ----------------
INSERT INTO meta.data_sources (
  source_name,
  source_type,
  description,
  is_active,
  refresh_frequency
)
VALUES
  ('cms_hcris', 'batch', 'CMS Hospital Cost Reports (HCRIS)', true, 'annual'),
  ('cms_hospital_general_info', 'batch', 'CMS Hospital General Information', true, 'annual')
ON CONFLICT (source_name) DO NOTHING;

-- Root Cause E: raw.pubmed.mesh_terms JSONB -> TEXT[] (if needed) -----------
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'raw'
      AND table_name = 'pubmed'
      AND column_name = 'mesh_terms'
      AND data_type = 'jsonb'
  ) THEN
    -- Drop potentially incompatible index before type conversion.
    DROP INDEX IF EXISTS idx_pubmed_mesh;

    ALTER TABLE raw.pubmed
    ALTER COLUMN mesh_terms TYPE TEXT[]
    USING (
      CASE
        WHEN mesh_terms IS NULL THEN NULL
        ELSE ARRAY(SELECT jsonb_array_elements_text(mesh_terms))
      END
    );

    CREATE INDEX IF NOT EXISTS idx_pubmed_mesh
      ON raw.pubmed USING GIN(mesh_terms);

    RAISE NOTICE 'Converted raw.pubmed.mesh_terms from JSONB to TEXT[]';
  ELSE
    RAISE NOTICE 'raw.pubmed.mesh_terms already TEXT[] — skipping';
  END IF;
END
$$;
