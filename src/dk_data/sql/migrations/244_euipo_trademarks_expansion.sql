-- Migration 244: EUIPO trademarks IP field expansion (Item 28, T066)
-- Feature: 006-claims-engine-data-gaps
-- Adds oppositions, cancellations, seniorities, priority claims, Vienna codes,
-- publication events, owner change history, and acquired distinctiveness flag

BEGIN;

ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS oppositions JSONB;
ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS cancellations JSONB;
ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS seniorities JSONB;
ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS priority_claims JSONB;
ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS vienna_codes JSONB;
ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS publication_events JSONB;
ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS owner_change_history JSONB;
ALTER TABLE ip_raw.euipo_trademarks ADD COLUMN IF NOT EXISTS acquired_distinctiveness_flag BOOLEAN;

COMMIT;
