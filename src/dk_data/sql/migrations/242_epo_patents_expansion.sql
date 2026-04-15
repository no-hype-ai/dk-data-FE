-- Migration 242: EPO patents IP field expansion (Item 28, T059)
-- Feature: 006-claims-engine-data-gaps
-- Adds priority claims, family members, multilingual abstracts, legal status,
-- designated states, grant date, and cited documents fields

BEGIN;

ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS priority_claims JSONB;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS family_members JSONB;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS abstract_en TEXT;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS abstract_fr TEXT;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS abstract_de TEXT;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS legal_status_events JSONB;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS designated_states JSONB;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS grant_date DATE;
ALTER TABLE ip_raw.epo_patents ADD COLUMN IF NOT EXISTS cited_documents JSONB;

COMMIT;
