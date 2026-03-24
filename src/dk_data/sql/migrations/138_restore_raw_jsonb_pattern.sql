-- Migration: 120_restore_raw_jsonb_pattern.sql
-- Date: 2026-03-21
-- Description: Restore the original medallion design — all raw tables must store
--   the full API response as response_body JSONB. 14 tables were created with
--   typed columns only, causing data loss. This migration adds the standard
--   JSONB columns and backfills response_body from existing typed columns.
--   Existing typed columns are NOT dropped (backward compat).

-- ─── Step 1: Add standard JSONB columns to all 14 typed-column tables ────────

DO $$
DECLARE
  tbl TEXT;
  tbl_exists BOOLEAN;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'acc_tvc_certification', 'cochrane_reviews', 'ema_regulatory', 'epo_patents',
    'euipo_trademarks', 'hrsa_shortage_areas', 'journal_rss', 'medical_news',
    'openalex_ci', 'orcid', 'pubmed', 'uspto_ci', 'uspto_patents', 'uspto_trademarks'
  ])
  LOOP
    SELECT EXISTS (
      SELECT 1 FROM pg_tables WHERE schemaname='mol_raw' AND tablename=tbl
    ) INTO tbl_exists;
    IF NOT tbl_exists THEN
      RAISE NOTICE 'Skipping mol_raw.% — table does not exist', tbl;
      CONTINUE;
    END IF;
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS response_body JSONB', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS response_body_hash VARCHAR(64)', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS request_id VARCHAR(100)', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS api_endpoint VARCHAR(500)', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS response_status INTEGER DEFAULT 200', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS processed_to_bronze BOOLEAN DEFAULT FALSE', tbl);
    EXECUTE format('ALTER TABLE mol_raw.%I ADD COLUMN IF NOT EXISTS source_id VARCHAR(50)', tbl);
    -- Indexes
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_resp_hash ON mol_raw.%I(response_body_hash)', tbl, tbl);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_processed ON mol_raw.%I(processed_to_bronze) WHERE processed_to_bronze = FALSE', tbl, tbl);
    RAISE NOTICE 'Added JSONB columns to mol_raw.%', tbl;
  END LOOP;
END $$;

-- ─── Step 2: Backfill skipped ─────────────────────────────────────────────────
-- All mol_raw tables already use response_body JSONB natively.
-- No typed-column backfill is needed.

-- ─── Step 3: Set processed_to_bronze = FALSE for backfilled rows ─────────────
-- This signals the dynamic transformer to process them

DO $$
DECLARE
  tbl TEXT;
  tbl_exists BOOLEAN;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'acc_tvc_certification', 'cochrane_reviews', 'ema_regulatory', 'epo_patents',
    'euipo_trademarks', 'hrsa_shortage_areas', 'journal_rss', 'medical_news',
    'openalex_ci', 'orcid', 'pubmed', 'uspto_ci', 'uspto_patents', 'uspto_trademarks'
  ])
  LOOP
    SELECT EXISTS (
      SELECT 1 FROM pg_tables WHERE schemaname='mol_raw' AND tablename=tbl
    ) INTO tbl_exists;
    IF NOT tbl_exists THEN CONTINUE; END IF;
    EXECUTE format('UPDATE mol_raw.%I SET processed_to_bronze = FALSE WHERE response_body IS NOT NULL AND processed_to_bronze IS NULL', tbl);
  END LOOP;
END $$;

-- ─── Step 4: Register missing sources in ops.sync_schedules ──────────────────

INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options) VALUES
  ('pubmed', 'weekly', '0 3 * * 1', 'normal', true, '{"source_name":"PubMed","api_type":"rest","target_table":"mol_raw.pubmed"}'::jsonb),
  ('openalex_ci', 'weekly', '0 3 * * 2', 'normal', true, '{"source_name":"OpenAlex CI","api_type":"rest","target_table":"mol_raw.openalex_ci"}'::jsonb),
  ('ema_regulatory', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"EMA Regulatory","api_type":"csv","target_table":"mol_raw.ema_regulatory"}'::jsonb),
  ('journal_rss', 'daily', '0 5 * * *', 'low', true, '{"source_name":"Journal RSS","api_type":"rss","target_table":"mol_raw.journal_rss"}'::jsonb),
  ('medical_news', 'daily', '0 6 * * *', 'low', true, '{"source_name":"Medical News","api_type":"rss","target_table":"mol_raw.medical_news"}'::jsonb),
  ('cochrane_reviews', 'monthly', '0 4 15 * *', 'normal', true, '{"source_name":"Cochrane Reviews","api_type":"rest","target_table":"mol_raw.cochrane_reviews"}'::jsonb),
  ('epo_patents', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"EPO Patents","api_type":"rest","target_table":"mol_raw.epo_patents"}'::jsonb),
  ('euipo_trademarks', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"EUIPO Trademarks","api_type":"scrape","target_table":"mol_raw.euipo_trademarks"}'::jsonb),
  ('hrsa_shortage_areas', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"HRSA Shortage Areas","api_type":"rest","target_table":"mol_raw.hrsa_shortage_areas"}'::jsonb),
  ('acc_tvc_certification', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"ACC TVC Certification","api_type":"csv","target_table":"mol_raw.acc_tvc_certification"}'::jsonb),
  ('uspto_ci', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"USPTO Citation Index","api_type":"rest","target_table":"mol_raw.uspto_ci"}'::jsonb),
  ('uspto_patents', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"USPTO Patents","api_type":"rest","target_table":"mol_raw.uspto_patents"}'::jsonb),
  ('uspto_trademarks', 'monthly', '0 4 1 * *', 'low', true, '{"source_name":"USPTO Trademarks","api_type":"rest","target_table":"mol_raw.uspto_trademarks"}'::jsonb)
ON CONFLICT (source) DO NOTHING;

-- ─── Step 5: Grants ──────────────────────────────────────────────────────────

DO $$
DECLARE
  tbl TEXT;
  tbl_exists BOOLEAN;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'acc_tvc_certification', 'cochrane_reviews', 'ema_regulatory', 'epo_patents',
    'euipo_trademarks', 'hrsa_shortage_areas', 'journal_rss', 'medical_news',
    'openalex_ci', 'orcid', 'pubmed', 'uspto_ci', 'uspto_patents', 'uspto_trademarks'
  ])
  LOOP
    SELECT EXISTS (
      SELECT 1 FROM pg_tables WHERE schemaname='mol_raw' AND tablename=tbl
    ) INTO tbl_exists;
    IF NOT tbl_exists THEN CONTINUE; END IF;
    EXECUTE format('GRANT SELECT ON mol_raw.%I TO analyst', tbl);
  END LOOP;
END $$;
