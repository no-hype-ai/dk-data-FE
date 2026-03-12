-- Migration: 091_euipo_designs_raw
-- Feature: 014-uspto-euipo-model-datasource
-- Purpose: Create raw table for EUIPO registered community design data

CREATE TABLE IF NOT EXISTS raw.euipo_designs (
    application_number VARCHAR(30) NOT NULL,
    design_title TEXT,
    applicant_name TEXT,
    applicant_country VARCHAR(10),
    representative_name TEXT,
    designer_name TEXT,
    status VARCHAR(100),
    filing_date DATE,
    registration_date DATE,
    expiry_date DATE,
    publication_date DATE,
    locarno_classes TEXT[],
    product_indication TEXT,
    image_url TEXT,
    number_of_designs INTEGER,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (application_number)
);

CREATE INDEX IF NOT EXISTS idx_euipo_design_filing
    ON raw.euipo_designs(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_euipo_design_locarno
    ON raw.euipo_designs USING GIN(locarno_classes);
CREATE INDEX IF NOT EXISTS idx_euipo_design_status
    ON raw.euipo_designs(status);
CREATE INDEX IF NOT EXISTS idx_euipo_design_applicant
    ON raw.euipo_designs(applicant_name);

DO $$
BEGIN
    RAISE NOTICE 'Migration 091_euipo_designs_raw complete.';
END
$$;
