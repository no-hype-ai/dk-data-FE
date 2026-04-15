-- Migration 240: Treatment guidelines raw table (Item 8, T048)
-- Feature: 006-claims-engine-data-gaps
-- Stores curated treatment guideline data for rules engine indication matching

BEGIN;

CREATE TABLE IF NOT EXISTS mol_raw.guidelines (
    id                UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    body              TEXT,
    title             TEXT,
    publication_date  DATE,
    version           TEXT,
    indication_icd11  TEXT,
    indication_name   TEXT,
    source_url        TEXT,
    full_text         TEXT,
    sections          JSONB,
    recommendations   JSONB,
    ingested_at       TIMESTAMPTZ DEFAULT NOW()
);

GRANT SELECT, INSERT, UPDATE ON mol_raw.guidelines TO mol_data_ops;

COMMIT;
