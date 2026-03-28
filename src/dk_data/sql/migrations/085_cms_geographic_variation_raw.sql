-- Migration 085: CMS Geographic Variation raw table
-- Purpose: Store CMS Medicare Geographic Variation Public Use File (GV PUF) data
-- Source: https://www.cms.gov/Research-Statistics-Data-and-Systems/Statistics-Trends-and-Reports/Medicare-Geographic-Variation
-- Feature: 019-cms-puf-platform-reconciliation

CREATE SCHEMA IF NOT EXISTS raw;

-- raw.cms_geographic_variation
-- Stores one row per geographic area / beneficiary demographic slice per year.
-- Key fields per CMS GV PUF documentation:
--   Bene_Geo_Lvl:    Geographic level (National / State / County)
--   Bene_Geo_Desc:   Geographic description (state name, county name, or "National")
--   Bene_Geo_Cd:     FIPS state or county code (TEXT to preserve leading zeros)
--   Bene_Age_Lvl:    Age level (All / <65 / 65-74 / 75-84 / 85+)
--   Bene_Demo_Lvl:   Demographic level (All / Sex / Race)
--   Bene_Demo_Desc:  Demographic description (Male/Female/White/Black/etc.)
--   Bene_MCC_Lvl:    Multiple chronic condition level (All / 0 / 1-2 / 3-4 / 5+)
--   Year:            Reference year (INTEGER)
CREATE TABLE IF NOT EXISTS raw.cms_geographic_variation (
    id                              SERIAL PRIMARY KEY,

    -- Geographic identifiers
    year                            INTEGER NOT NULL,
    bene_geo_lvl                    TEXT NOT NULL,          -- National / State / County
    bene_geo_desc                   TEXT NOT NULL,          -- Geographic description
    bene_geo_cd                     TEXT,                   -- FIPS code (TEXT, leading zeros)

    -- Beneficiary demographic slice
    bene_age_lvl                    TEXT,                   -- All / <65 / 65-74 / 75-84 / 85+
    bene_demo_lvl                   TEXT,                   -- All / Sex / Race
    bene_demo_desc                  TEXT,                   -- Male / Female / White / Black / etc.
    bene_mcc_lvl                    TEXT,                   -- All / 0 / 1-2 / 3-4 / 5+

    -- Beneficiary counts
    tot_benes                       INTEGER,                -- Total beneficiaries

    -- Utilization rates
    ip_cvrd_stays_per_1000_benes    NUMERIC,                -- Inpatient covered stays per 1,000
    er_visits_per_1000_benes        NUMERIC,                -- ER visits per 1,000 beneficiaries
    readmsn_rate                    NUMERIC,                -- 30-day readmission rate
    acute_hosp_readmsn_rate         NUMERIC,                -- Acute hospital readmission rate

    -- Spending (per-capita, standardized and actual)
    tot_mdcr_stdzd_pymt_pc          NUMERIC,                -- Total Medicare standardized payment per capita
    tot_mdcr_pymt_pc                NUMERIC,                -- Total Medicare payment per capita
    tot_mdcr_alowd_amt_pc           NUMERIC,                -- Total Medicare allowed amount per capita

    -- Medicare Advantage participation
    ma_prtcptn_rate                 NUMERIC,                -- Medicare Advantage participation rate

    -- Source metadata
    _loaded_at                      TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file                    VARCHAR(500),
    _source_hash                    VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_cms_geo_var_year
    ON raw.cms_geographic_variation (year);
CREATE INDEX IF NOT EXISTS idx_cms_geo_var_lvl
    ON raw.cms_geographic_variation (bene_geo_lvl);
CREATE INDEX IF NOT EXISTS idx_cms_geo_var_cd
    ON raw.cms_geographic_variation (bene_geo_cd)
    WHERE bene_geo_cd IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cms_geo_var_hash
    ON raw.cms_geographic_variation (_source_hash);
CREATE INDEX IF NOT EXISTS idx_cms_geo_var_year_lvl_cd
    ON raw.cms_geographic_variation (year, bene_geo_lvl, bene_geo_cd);

-- Register source in meta.data_sources (idempotent)
DO $$
BEGIN
    INSERT INTO meta.data_sources (source_name, source_type, description, refresh_frequency, is_active)
    VALUES ('cms_geographic_variation', 'file', 'CMS Medicare Geographic Variation Public Use File', 'yearly', true)
    ON CONFLICT (source_name) DO NOTHING;
EXCEPTION WHEN undefined_table THEN
    NULL;  -- meta.data_sources not yet created in this environment
END $$;

DO $$
BEGIN
    RAISE NOTICE 'Migration 085 complete: raw.cms_geographic_variation created.';
END
$$;
