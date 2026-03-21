-- Migration: 113_indication_epidemiology.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Indication-level epidemiology from WHO GHO + ClinicalTrials.gov,
--              plus per-indication revenue from SEC EDGAR MD&A parsing.

-- ─── Raw Tables ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mol_raw.who_gho (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name VARCHAR(500),          -- repurposed: actually indication name
    response_body JSONB,
    response_status INTEGER DEFAULT 200,
    request_url TEXT,
    request_timestamp TIMESTAMPTZ DEFAULT NOW(),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_who_gho_processed ON mol_raw.who_gho (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;
CREATE INDEX IF NOT EXISTS idx_who_gho_timestamp ON mol_raw.who_gho (request_timestamp);

CREATE TABLE IF NOT EXISTS mol_raw.ct_gov_indication_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name VARCHAR(500),          -- repurposed: actually indication/condition name
    response_body JSONB,
    response_status INTEGER DEFAULT 200,
    request_url TEXT,
    request_timestamp TIMESTAMPTZ DEFAULT NOW(),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ct_gov_ind_stats_processed ON mol_raw.ct_gov_indication_stats (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;
CREATE INDEX IF NOT EXISTS idx_ct_gov_ind_stats_timestamp ON mol_raw.ct_gov_indication_stats (request_timestamp);

-- ─── Silver Tables ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mol_silver.indication_epidemiology (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    icd10_code VARCHAR(10) NOT NULL,
    indication_name VARCHAR(500),
    country_code VARCHAR(3) DEFAULT 'USA',
    data_year INTEGER NOT NULL,
    incidence_rate DECIMAL(12,4),
    incidence_count INTEGER,
    prevalence_rate DECIMAL(12,4),
    prevalence_count INTEGER,
    mortality_rate DECIMAL(12,4),
    mortality_count INTEGER,
    five_year_survival DECIMAL(5,2),
    median_age_diagnosis INTEGER,
    trial_count INTEGER,
    trial_enrollment_total INTEGER,
    source VARCHAR(50) NOT NULL,
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (icd10_code, country_code, data_year, source)
);

CREATE INDEX IF NOT EXISTS idx_indication_epi_icd10 ON mol_silver.indication_epidemiology (icd10_code);
CREATE INDEX IF NOT EXISTS idx_indication_epi_year ON mol_silver.indication_epidemiology (data_year DESC);

CREATE TABLE IF NOT EXISTS mol_silver.indication_revenue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    icd10_code VARCHAR(10),
    molecule_id UUID,
    product_name VARCHAR(500),
    indication_revenue_usd DECIMAL(12,2),    -- in $M
    total_product_revenue_usd DECIMAL(12,2), -- in $M
    indication_revenue_share DECIMAL(5,2),   -- %
    data_year INTEGER,
    source_filing VARCHAR(100),
    source VARCHAR(50) DEFAULT 'sec_edgar',
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (molecule_id, icd10_code, product_name, data_year)
);

CREATE INDEX IF NOT EXISTS idx_indication_rev_molecule ON mol_silver.indication_revenue (molecule_id);
CREATE INDEX IF NOT EXISTS idx_indication_rev_icd10 ON mol_silver.indication_revenue (icd10_code);

-- ─── ICD-10 ↔ WHO Indicator Mapping ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mol_silver.icd10_indicator_mapping (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    icd10_code VARCHAR(10) NOT NULL,
    who_indicator VARCHAR(50) NOT NULL,
    indicator_description VARCHAR(500),
    metric_type VARCHAR(50) NOT NULL,  -- 'mortality_rate', 'incidence_rate', etc.
    UNIQUE (icd10_code, who_indicator, metric_type)
);

-- Seed known mappings for common oncology + disease indications
INSERT INTO mol_silver.icd10_indicator_mapping (icd10_code, who_indicator, indicator_description, metric_type) VALUES
-- NCD Mortality (30-70, broad coverage)
('C34.9', 'NCDMORT3070', 'NCD mortality 30-70 — lung cancer proxy', 'mortality_rate'),
('C67.9', 'NCDMORT3070', 'NCD mortality 30-70 — bladder cancer proxy', 'mortality_rate'),
('C50.9', 'SA_0000001438', 'Breast cancer deaths', 'mortality_count'),
('C18.9', 'NCDMORT3070', 'NCD mortality 30-70 — colorectal cancer proxy', 'mortality_rate'),
('C22.0', 'NCDMORT3070', 'NCD mortality 30-70 — HCC proxy', 'mortality_rate'),
('C25.9', 'NCDMORT3070', 'NCD mortality 30-70 — pancreatic cancer proxy', 'mortality_rate'),
('C61',   'NCDMORT3070', 'NCD mortality 30-70 — prostate cancer proxy', 'mortality_rate'),
('C43.9', 'NCDMORT3070', 'NCD mortality 30-70 — melanoma proxy', 'mortality_rate'),
('C64.9', 'NCDMORT3070', 'NCD mortality 30-70 — renal cell carcinoma proxy', 'mortality_rate'),
('C71.9', 'NCDMORT3070', 'NCD mortality 30-70 — brain cancer proxy', 'mortality_rate'),
-- Non-oncology
('J44.1', 'NCDMORT3070', 'NCD mortality 30-70 — COPD proxy', 'mortality_rate'),
('E11.9', 'NCDMORT3070', 'NCD mortality 30-70 — T2DM proxy', 'mortality_rate'),
('I25.9', 'NCDMORT3070', 'NCD mortality 30-70 — coronary artery disease proxy', 'mortality_rate'),
('M05.9', 'NCDMORT3070', 'NCD mortality 30-70 — RA proxy', 'mortality_rate'),
('G35',   'NCDMORT3070', 'NCD mortality 30-70 — multiple sclerosis proxy', 'mortality_rate'),
('L40.0', 'NCDMORT3070', 'NCD mortality 30-70 — psoriasis proxy', 'mortality_rate'),
('K50.9', 'NCDMORT3070', 'NCD mortality 30-70 — Crohn disease proxy', 'mortality_rate')
ON CONFLICT (icd10_code, who_indicator, metric_type) DO NOTHING;

-- ─── Add mda_excerpt columns to financial_filings if missing ─────────────────

ALTER TABLE mol_silver.financial_filings ADD COLUMN IF NOT EXISTS mda_excerpt TEXT;
ALTER TABLE mol_silver.financial_filings ADD COLUMN IF NOT EXISTS risk_factors_excerpt TEXT;

-- ─── Grants for PostgREST (analyst role) ─────────────────────────────────────

GRANT SELECT ON mol_silver.indication_epidemiology TO analyst;
GRANT SELECT ON mol_silver.indication_revenue TO analyst;
GRANT SELECT ON mol_silver.icd10_indicator_mapping TO analyst;

-- ─── Sync Schedule Registration ──────────────────────────────────────────────

INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options) VALUES
('who_gho', 'monthly', '0 3 1 * *', 'normal', true, '{"source_name":"WHO Global Health Observatory","api_type":"rest","base_url":"https://ghoapi.azureedge.net/api","auth_type":"none","rate_limit_per_second":4,"entity_linking":{"identifier_field":"indication_name","identifier_type":"icd10"}}'::jsonb),
('ct_gov_indication_stats', 'monthly', '0 4 1 * *', 'normal', true, '{"source_name":"ClinicalTrials.gov Indication Statistics","api_type":"rest","base_url":"https://clinicaltrials.gov/api/v2","auth_type":"none","rate_limit_per_second":3,"entity_linking":{"identifier_field":"condition","identifier_type":"icd10"}}'::jsonb)
ON CONFLICT (source) DO NOTHING;
