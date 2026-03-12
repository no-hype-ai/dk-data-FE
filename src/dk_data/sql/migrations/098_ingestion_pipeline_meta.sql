-- 098_ingestion_pipeline_meta.sql
-- Add columns for hash-skip, conditional HTTP, and pagination checkpoint support.

-- meta.data_sources: persist hash + HTTP cache headers between runs
ALTER TABLE meta.data_sources ADD COLUMN IF NOT EXISTS last_content_hash VARCHAR(64);
ALTER TABLE meta.data_sources ADD COLUMN IF NOT EXISTS last_etag VARCHAR(256);
ALTER TABLE meta.data_sources ADD COLUMN IF NOT EXISTS last_modified_header VARCHAR(128);

-- meta.refresh_log: per-run hash, checkpoint offset, skip flag
ALTER TABLE meta.refresh_log ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE meta.refresh_log ADD COLUMN IF NOT EXISTS pagination_offset INTEGER;
ALTER TABLE meta.refresh_log ADD COLUMN IF NOT EXISTS skipped_by_hash BOOLEAN DEFAULT FALSE;
