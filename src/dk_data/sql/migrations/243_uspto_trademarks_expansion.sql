-- Migration 243: USPTO trademarks IP field expansion (Item 28, T063)
-- Feature: 006-claims-engine-data-gaps
-- Adds prosecution history, assignments, TTA proceedings, renewal, and Madrid fields

BEGIN;

ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS case_file_statements JSONB;
ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS owner_events JSONB;
ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS assignments JSONB;
ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS prosecution_history JSONB;
ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS tta_proceedings JSONB;
ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS renewal_events JSONB;
ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS madrid_linkage TEXT;
ALTER TABLE ip_raw.uspto_trademarks ADD COLUMN IF NOT EXISTS mark_image_url TEXT;

COMMIT;
