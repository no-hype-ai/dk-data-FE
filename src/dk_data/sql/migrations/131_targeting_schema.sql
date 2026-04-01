-- Migration 131: Create targeting schema and tables
--
-- targeting_import.py writes to targeting.biome_relationships,
-- targeting.sales_coverage, targeting.champions, targeting.emr_systems,
-- and targeting.financial_details. None of these were created by any
-- prior migration, causing silent INSERT failures on fresh clusters.
--
-- Ref: issue #171 M4

CREATE SCHEMA IF NOT EXISTS targeting;

CREATE TABLE IF NOT EXISTS targeting.biome_relationships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi             VARCHAR(20),
    facility_id     VARCHAR(50),
    relationship    VARCHAR(100),
    source          VARCHAR(50),
    effective_date  DATE,
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_targeting_biome_npi         ON targeting.biome_relationships(npi);
CREATE INDEX IF NOT EXISTS idx_targeting_biome_facility    ON targeting.biome_relationships(facility_id);

CREATE TABLE IF NOT EXISTS targeting.sales_coverage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi             VARCHAR(20),
    territory_id    VARCHAR(50),
    rep_id          VARCHAR(50),
    coverage_type   VARCHAR(50),
    effective_date  DATE,
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_targeting_sales_npi ON targeting.sales_coverage(npi);

CREATE TABLE IF NOT EXISTS targeting.champions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi             VARCHAR(20),
    product_id      VARCHAR(50),
    champion_type   VARCHAR(50),
    score           NUMERIC(5,2),
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_targeting_champions_npi ON targeting.champions(npi);

CREATE TABLE IF NOT EXISTS targeting.emr_systems (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi             VARCHAR(20),
    facility_id     VARCHAR(50),
    emr_vendor      VARCHAR(100),
    emr_product     VARCHAR(100),
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_targeting_emr_npi ON targeting.emr_systems(npi);

CREATE TABLE IF NOT EXISTS targeting.financial_details (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi             VARCHAR(20),
    facility_id     VARCHAR(50),
    metric_name     VARCHAR(100),
    metric_value    NUMERIC,
    fiscal_year     INTEGER,
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_targeting_financial_npi ON targeting.financial_details(npi);

GRANT USAGE ON SCHEMA targeting TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA targeting TO analyst;
