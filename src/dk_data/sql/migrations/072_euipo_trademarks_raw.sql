-- Migration: 072_euipo_trademarks_raw
-- Feature: 014-uspto-euipo-model-datasource
-- Purpose: Create raw table for EUIPO trademark data (TMview/IBM Gateway)

CREATE TABLE IF NOT EXISTS raw.euipo_trademarks (
    application_number VARCHAR(30) NOT NULL,
    mark_name TEXT,
    mark_kind VARCHAR(50),
    mark_feature VARCHAR(50),
    mark_basis VARCHAR(50),
    applicant_name TEXT,
    applicant_country VARCHAR(10),
    representative_name TEXT,
    status VARCHAR(100),
    filing_date DATE,
    registration_date DATE,
    expiry_date DATE,
    nice_classes INTEGER[],
    goods_and_services TEXT,
    image_url TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (application_number)
);

CREATE INDEX IF NOT EXISTS idx_euipo_tm_filing
    ON raw.euipo_trademarks(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_euipo_tm_nice
    ON raw.euipo_trademarks USING GIN(nice_classes);
CREATE INDEX IF NOT EXISTS idx_euipo_tm_status
    ON raw.euipo_trademarks(status);

DO $$
BEGIN
    RAISE NOTICE 'Migration 072_euipo_trademarks_raw complete.';
END
$$;
