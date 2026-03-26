-- Migration: 084_add_response_hash_columns
-- Purpose: Add response_body_hash to CI source tables for deduplication
-- Tables: raw.openalex_ci, raw.pubmed, raw.journal_rss, raw.medical_news

ALTER TABLE raw.openalex_ci ADD COLUMN IF NOT EXISTS response_body_hash VARCHAR(64);
ALTER TABLE raw.pubmed ADD COLUMN IF NOT EXISTS response_body_hash VARCHAR(64);
ALTER TABLE raw.journal_rss ADD COLUMN IF NOT EXISTS response_body_hash VARCHAR(64);
ALTER TABLE raw.medical_news ADD COLUMN IF NOT EXISTS response_body_hash VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_openalex_ci_response_hash ON raw.openalex_ci(response_body_hash);
CREATE INDEX IF NOT EXISTS idx_pubmed_response_hash ON raw.pubmed(response_body_hash);
CREATE INDEX IF NOT EXISTS idx_journal_rss_response_hash ON raw.journal_rss(response_body_hash);
CREATE INDEX IF NOT EXISTS idx_medical_news_response_hash ON raw.medical_news(response_body_hash);

DO $$ BEGIN RAISE NOTICE 'Migration 084: Added response_body_hash to CI source tables'; END $$;
