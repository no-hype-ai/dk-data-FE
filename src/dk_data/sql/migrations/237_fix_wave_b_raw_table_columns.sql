-- Migration 237: Add standard raw-layer columns to Wave B tables.
-- Applied to prod on 2026-04-17. Migration 236 created tables with a minimal
-- schema (id, api_endpoint, response_body, source_year, ingested_at) but the
-- Wave B loaders expect the full raw-layer pattern with request_id,
-- response_status, response_body_hash (idempotency), source_id (lineage),
-- api_version, and request_params.

BEGIN;

DO $$
DECLARE
  tbls TEXT[] := ARRAY[
    'hcs_raw.cms_hac_reduction', 'hcs_raw.cms_hrrp', 'hcs_raw.cms_vbp',
    'mol_raw.fda_enforcement', 'mol_raw.fda_shortages',
    'hcs_raw.who_ghed', 'hcs_raw.worldbank_health', 'hcs_raw.oecd_health',
    'mol_raw.pbs_australia'
  ];
  t TEXT;
BEGIN
  FOREACH t IN ARRAY tbls LOOP
    EXECUTE format('ALTER TABLE %s ADD COLUMN IF NOT EXISTS request_id TEXT', t);
    EXECUTE format('ALTER TABLE %s ADD COLUMN IF NOT EXISTS response_status INTEGER', t);
    EXECUTE format('ALTER TABLE %s ADD COLUMN IF NOT EXISTS response_body_hash TEXT', t);
    EXECUTE format('ALTER TABLE %s ADD COLUMN IF NOT EXISTS source_id TEXT', t);
    EXECUTE format('ALTER TABLE %s ADD COLUMN IF NOT EXISTS api_version TEXT', t);
    EXECUTE format('ALTER TABLE %s ADD COLUMN IF NOT EXISTS request_params JSONB', t);
    BEGIN
      EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %s_hash_idx ON %s (response_body_hash) WHERE response_body_hash IS NOT NULL',
        replace(replace(t, '.', '_'), 'raw_', ''), t);
    EXCEPTION WHEN duplicate_table THEN NULL;
    END;
  END LOOP;
END $$;

COMMIT;
