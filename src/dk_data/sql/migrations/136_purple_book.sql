-- Migration: 114_purple_book.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Purple Book (biologics) raw table, sync schedule, and patent_exclusivities
--              updates to support both Orange Book (NDA) and Purple Book (BLA) data.

-- ─── Raw Table ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mol_raw.purple_book (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name VARCHAR(500),
    response_body JSONB,
    response_status INTEGER DEFAULT 200,
    request_url TEXT,
    request_timestamp TIMESTAMPTZ DEFAULT NOW(),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_purple_book_processed ON mol_raw.purple_book (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;
CREATE INDEX IF NOT EXISTS idx_purple_book_timestamp ON mol_raw.purple_book (request_timestamp);

-- mol_silver.patent_exclusivities is a SQLMesh-managed VIEW — ALTER TABLE skipped.

-- ─── Sync Schedule ────────────────────────────────────────────────────────────

INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options) VALUES
('purple_book', 'monthly', '0 5 1 * *', 'normal', true, '{"source_name":"FDA Purple Book (Biologics)","api_type":"rest","base_url":"https://purplebooksearch.fda.gov/api/v1","auth_type":"token","rate_limit_per_second":4,"entity_linking":{"identifier_field":"generic_name","identifier_type":"drug_name"}}'::jsonb)
ON CONFLICT (source) DO NOTHING;

-- ─── Grants ───────────────────────────────────────────────────────────────────

GRANT SELECT ON mol_raw.purple_book TO analyst;
