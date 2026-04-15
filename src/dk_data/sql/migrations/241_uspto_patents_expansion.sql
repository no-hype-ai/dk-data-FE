-- Migration 241: USPTO patents IP field expansion (Item 28, T055)
-- Feature: 006-claims-engine-data-gaps
-- Adds citation, family, continuity, claims, assignment, and examiner fields

BEGIN;

ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS cited_patents JSONB;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS citing_patents JSONB;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS npl_citations JSONB;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS parent_application TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS child_applications JSONB;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS continuation_type TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS claims_full_text TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS assignment_events JSONB;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS examiner_first_name TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS examiner_last_name TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS examiner_art_unit TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS family_id TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS equivalent_foreign_patents JSONB;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS application_number TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS publication_number TEXT;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS priority_date DATE;
ALTER TABLE ip_raw.uspto_patents ADD COLUMN IF NOT EXISTS ipc_codes JSONB;

COMMIT;
