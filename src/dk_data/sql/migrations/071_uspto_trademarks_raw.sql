-- Migration: 071_uspto_trademarks_raw
-- Feature: 014-uspto-euipo-model-datasource
-- Purpose: Create raw table for USPTO TSDR trademark data

CREATE TABLE IF NOT EXISTS raw.uspto_trademarks (
    serial_number VARCHAR(20) NOT NULL,
    mark_element TEXT,
    mark_type VARCHAR(50),
    status VARCHAR(100),
    status_code INTEGER,
    status_date DATE,
    filing_date DATE,
    registration_number VARCHAR(20),
    registration_date DATE,
    nice_classes INTEGER[],
    us_classes TEXT[],
    owner_name TEXT,
    owner_entity_type VARCHAR(50),
    goods_and_services TEXT,
    description_of_mark TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (serial_number)
);

CREATE INDEX IF NOT EXISTS idx_uspto_tm_filing
    ON raw.uspto_trademarks(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_uspto_tm_nice
    ON raw.uspto_trademarks USING GIN(nice_classes);
CREATE INDEX IF NOT EXISTS idx_uspto_tm_status
    ON raw.uspto_trademarks(status);

DO $$
BEGIN
    RAISE NOTICE 'Migration 071_uspto_trademarks_raw complete.';
END
$$;
