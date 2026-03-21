-- Migration: 119_gold_indication_revenue_summary.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Create mol_gold.indication_revenue_summary — aggregated per-indication
--   revenue from SEC MD&A parsing. Xenon reads this instead of mol_silver.indication_revenue.

CREATE TABLE IF NOT EXISTS mol_gold.indication_revenue_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id TEXT NOT NULL,          -- TEXT to match other gold tables (no FK)
    icd10_code VARCHAR(20) NOT NULL,
    indication_name VARCHAR(500),
    product_name VARCHAR(500),

    -- Aggregated metrics
    latest_revenue_usd NUMERIC(14,2),   -- Most recent year's indication revenue ($M)
    peak_revenue_usd NUMERIC(14,2),     -- Highest revenue observed ($M)
    latest_total_product_usd NUMERIC(14,2), -- Total product revenue for share calc
    revenue_share_pct NUMERIC(6,2),     -- Indication share of total product revenue (%)
    year_of_peak INTEGER,               -- Year when peak revenue occurred
    latest_year INTEGER,                -- Most recent data year
    trend VARCHAR(20),                  -- 'increasing', 'stable', 'declining'
    cagr_pct NUMERIC(6,2),             -- Compound annual growth rate (%)
    filing_count INTEGER DEFAULT 0,     -- Number of SEC filings mentioning this indication
    confidence_score NUMERIC(4,2),      -- 0.0–1.0 based on filing_count + pattern match quality

    -- Metadata
    source VARCHAR(50) DEFAULT 'sec_edgar',
    snapshot_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, icd10_code)
);

CREATE INDEX IF NOT EXISTS idx_gold_ind_rev_molecule ON mol_gold.indication_revenue_summary(molecule_id);
CREATE INDEX IF NOT EXISTS idx_gold_ind_rev_icd10 ON mol_gold.indication_revenue_summary(icd10_code);

-- PostgREST grants
GRANT SELECT ON mol_gold.indication_revenue_summary TO analyst;
