-- Migration 161: Add missing columns to mol_raw.purple_book
--
-- The purple_book table was created with a minimal 4-column schema
-- (id, response_body, source_id, ingested_at) but the loader expects
-- the standard old-schema columns (request_id, api_endpoint, api_version,
-- response_status). Without these columns, all inserts fail with:
--   "column "request_id" of relation "purple_book" does not exist"
--
-- Also adds the expression index needed for ON CONFLICT deduplication
-- by application_number extracted from the response_body JSONB.

ALTER TABLE mol_raw.purple_book
    ADD COLUMN IF NOT EXISTS request_id TEXT,
    ADD COLUMN IF NOT EXISTS api_endpoint TEXT,
    ADD COLUMN IF NOT EXISTS api_version TEXT,
    ADD COLUMN IF NOT EXISTS response_status INTEGER DEFAULT 200;

CREATE UNIQUE INDEX IF NOT EXISTS idx_purple_book_app_num
    ON mol_raw.purple_book ((response_body->>'application_number'))
    WHERE (response_body->>'application_number') IS NOT NULL;
