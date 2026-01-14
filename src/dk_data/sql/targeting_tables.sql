-- TAVR Targeting Tool Schema
-- Feature: 002-tavr-targeting-tool
-- Created: January 2026
--
-- This script creates the targeting schema and all related tables
-- for the Edwards Lifesciences TAVR hospital targeting tool.

-- ============================================================================
-- T001: Create targeting schema
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS targeting;

COMMENT ON SCHEMA targeting IS 'Sales targeting data for TAVR hospitals including Biome relationships, sales coverage, champions, and volume history';

-- ============================================================================
-- T002: targeting.biome_relationships
-- Purpose: Track Edwards Biome Platform relationship status for each hospital
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.biome_relationships (
    hospital_id VARCHAR(10) PRIMARY KEY,

    -- Biome Platform Status
    is_current_client BOOLEAN NOT NULL DEFAULT FALSE,
    echo_surveillance_active BOOLEAN NOT NULL DEFAULT FALSE,
    workflow_active BOOLEAN NOT NULL DEFAULT FALSE,
    analytics_active BOOLEAN NOT NULL DEFAULT FALSE,
    pilot_phase VARCHAR(20),

    -- Contract Information
    contract_type VARCHAR(50),
    phase_2_tokens_needed INTEGER,
    contracting_speed VARCHAR(20),

    -- Relationship Dates
    first_contract_date DATE,
    contract_expiration DATE,

    -- Audit columns
    _updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    _updated_by VARCHAR(100),

    -- Constraints
    CONSTRAINT chk_pilot_phase CHECK (pilot_phase IS NULL OR pilot_phase IN ('Pilot 1.0', 'Phase 2')),
    CONSTRAINT chk_contract_type CHECK (contract_type IS NULL OR contract_type IN ('Amendment', 'New', 'TBA')),
    CONSTRAINT chk_contracting_speed CHECK (contracting_speed IS NULL OR contracting_speed IN ('Fast', 'Medium', 'Slow')),
    CONSTRAINT chk_tokens_positive CHECK (phase_2_tokens_needed IS NULL OR phase_2_tokens_needed >= 0)
);

COMMENT ON TABLE targeting.biome_relationships IS 'Track Edwards Biome Platform relationship status for each hospital';
COMMENT ON COLUMN targeting.biome_relationships.hospital_id IS 'CMS Medicare provider ID (FK to mart.dim_hospital)';
COMMENT ON COLUMN targeting.biome_relationships.is_current_client IS 'Active Biome client flag';
COMMENT ON COLUMN targeting.biome_relationships.echo_surveillance_active IS 'Echo Surveillance component active';
COMMENT ON COLUMN targeting.biome_relationships.workflow_active IS 'Biome Workflow component active';
COMMENT ON COLUMN targeting.biome_relationships.analytics_active IS 'Biome Analytics component active';
COMMENT ON COLUMN targeting.biome_relationships.pilot_phase IS 'Pilot phase: Pilot 1.0, Phase 2, or NULL';
COMMENT ON COLUMN targeting.biome_relationships.contract_type IS 'Contract type: Amendment, New, TBA, or NULL';
COMMENT ON COLUMN targeting.biome_relationships.phase_2_tokens_needed IS 'Tokens required for Phase 2 deployment';

-- ============================================================================
-- T003: targeting.sales_coverage
-- Purpose: Track sales territory assignments and engagement
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.sales_coverage (
    hospital_id VARCHAR(10) PRIMARY KEY,

    -- Territory Assignment
    region VARCHAR(50),
    territory VARCHAR(50),

    -- Sales Team
    regional_director VARCHAR(100),
    rd_email VARCHAR(255),
    area_vp VARCHAR(100),
    avp_email VARCHAR(255),
    account_manager VARCHAR(100),

    -- Engagement Status
    expressed_interest BOOLEAN NOT NULL DEFAULT FALSE,
    last_contact_date DATE,
    next_scheduled_contact DATE,
    engagement_notes TEXT,

    -- Audit columns
    _updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE targeting.sales_coverage IS 'Sales territory assignments and engagement tracking';
COMMENT ON COLUMN targeting.sales_coverage.hospital_id IS 'CMS Medicare provider ID (FK to mart.dim_hospital)';
COMMENT ON COLUMN targeting.sales_coverage.regional_director IS 'Regional Director name';
COMMENT ON COLUMN targeting.sales_coverage.area_vp IS 'Area Vice President name';
COMMENT ON COLUMN targeting.sales_coverage.expressed_interest IS 'Hospital has expressed interest in Biome';

-- ============================================================================
-- T004: targeting.champions
-- Purpose: Track clinical and administrative champions for each target
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.champions (
    id SERIAL PRIMARY KEY,
    hospital_id VARCHAR(10) NOT NULL,

    -- Champion Details
    champion_type VARCHAR(20) NOT NULL,
    champion_name VARCHAR(200),
    title VARCHAR(200),
    specialty VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(20),
    linkedin_url VARCHAR(500),

    -- Engagement Tracking
    engagement_level VARCHAR(20) NOT NULL DEFAULT 'None',
    last_engagement_date DATE,
    engagement_notes TEXT,

    -- Conference/Publication Activity
    conference_speaker BOOLEAN NOT NULL DEFAULT FALSE,
    published_with_edwards BOOLEAN NOT NULL DEFAULT FALSE,
    kol_status BOOLEAN NOT NULL DEFAULT FALSE,

    -- Audit columns
    _created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    _updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_champion_type CHECK (champion_type IN ('Clinical', 'Administrative')),
    CONSTRAINT chk_engagement_level CHECK (engagement_level IN ('None', 'Passive', 'Interested', 'Advocating'))
);

COMMENT ON TABLE targeting.champions IS 'Clinical and administrative champions for each target hospital';
COMMENT ON COLUMN targeting.champions.hospital_id IS 'CMS Medicare provider ID (FK to mart.dim_hospital)';
COMMENT ON COLUMN targeting.champions.champion_type IS 'Type: Clinical or Administrative';
COMMENT ON COLUMN targeting.champions.engagement_level IS 'Engagement level: None, Passive, Interested, Advocating';
COMMENT ON COLUMN targeting.champions.kol_status IS 'Key Opinion Leader flag';

-- ============================================================================
-- T005: targeting.volume_history
-- Purpose: Store historical TAVR volume data with growth calculations
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.volume_history (
    hospital_id VARCHAR(10) NOT NULL,
    fiscal_year INTEGER NOT NULL,

    -- Volume Metrics
    drg_266_volume INTEGER DEFAULT 0,
    drg_267_volume INTEGER DEFAULT 0,
    total_tavr_volume INTEGER GENERATED ALWAYS AS (COALESCE(drg_266_volume, 0) + COALESCE(drg_267_volume, 0)) STORED,

    -- Market Share
    market_share_pct DECIMAL(5,2),

    -- Derived Metrics
    yoy_growth_pct DECIMAL(5,2),

    -- Audit columns
    _loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Primary key
    PRIMARY KEY (hospital_id, fiscal_year),

    -- Constraints
    CONSTRAINT chk_fiscal_year CHECK (fiscal_year >= 2018 AND fiscal_year <= 2030),
    CONSTRAINT chk_drg_266_positive CHECK (drg_266_volume IS NULL OR drg_266_volume >= 0),
    CONSTRAINT chk_drg_267_positive CHECK (drg_267_volume IS NULL OR drg_267_volume >= 0),
    CONSTRAINT chk_market_share_range CHECK (market_share_pct IS NULL OR (market_share_pct >= 0 AND market_share_pct <= 100))
);

COMMENT ON TABLE targeting.volume_history IS 'Historical TAVR volume data with growth calculations';
COMMENT ON COLUMN targeting.volume_history.hospital_id IS 'CMS Medicare provider ID (FK to mart.dim_hospital)';
COMMENT ON COLUMN targeting.volume_history.fiscal_year IS 'Fiscal year (e.g., 2023)';
COMMENT ON COLUMN targeting.volume_history.drg_266_volume IS 'DRG 266 (TAVR with MCC) volume';
COMMENT ON COLUMN targeting.volume_history.drg_267_volume IS 'DRG 267 (TAVR without MCC) volume';
COMMENT ON COLUMN targeting.volume_history.total_tavr_volume IS 'Total TAVR volume (computed: drg_266 + drg_267)';
COMMENT ON COLUMN targeting.volume_history.yoy_growth_pct IS 'Year-over-year growth percentage';

-- ============================================================================
-- T006: targeting.emr_systems
-- Purpose: Track EMR vendor and integration readiness
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.emr_systems (
    hospital_id VARCHAR(10) PRIMARY KEY,

    -- EMR Details
    primary_emr VARCHAR(50),
    emr_version VARCHAR(50),
    emr_standardized_network BOOLEAN NOT NULL DEFAULT FALSE,

    -- Integration Readiness
    api_available BOOLEAN,
    fhir_enabled BOOLEAN,

    -- Notes
    integration_notes TEXT,

    -- Audit columns
    _updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE targeting.emr_systems IS 'EMR vendor and integration readiness tracking';
COMMENT ON COLUMN targeting.emr_systems.hospital_id IS 'CMS Medicare provider ID (FK to mart.dim_hospital)';
COMMENT ON COLUMN targeting.emr_systems.primary_emr IS 'Primary EMR vendor: Epic, Cerner, Meditech, etc.';
COMMENT ON COLUMN targeting.emr_systems.emr_standardized_network IS 'EMR standardized across health system network';

-- ============================================================================
-- T007: targeting.financial_details
-- Purpose: Store financial metrics for capacity assessment
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.financial_details (
    hospital_id VARCHAR(10) PRIMARY KEY,
    fiscal_year INTEGER,

    -- CMS Data
    wage_index DECIMAL(6,4),
    drg_266_payment DECIMAL(12,2),
    drg_267_payment DECIMAL(12,2),

    -- Financial Health
    operating_margin_pct DECIMAL(5,2),
    days_cash_on_hand INTEGER,
    debt_to_equity DECIMAL(6,2),

    -- Investment Indicators
    recent_capital_investment BOOLEAN,
    technology_adoption_score INTEGER,

    -- Audit columns
    _loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_wage_index_range CHECK (wage_index IS NULL OR (wage_index >= 0.5 AND wage_index <= 2.5)),
    CONSTRAINT chk_operating_margin_range CHECK (operating_margin_pct IS NULL OR (operating_margin_pct >= -100 AND operating_margin_pct <= 100)),
    CONSTRAINT chk_tech_adoption_range CHECK (technology_adoption_score IS NULL OR (technology_adoption_score >= 1 AND technology_adoption_score <= 5))
);

COMMENT ON TABLE targeting.financial_details IS 'Financial metrics for hospital capacity assessment';
COMMENT ON COLUMN targeting.financial_details.hospital_id IS 'CMS Medicare provider ID (FK to mart.dim_hospital)';
COMMENT ON COLUMN targeting.financial_details.wage_index IS 'CMS wage index';
COMMENT ON COLUMN targeting.financial_details.operating_margin_pct IS 'Operating margin percentage';
COMMENT ON COLUMN targeting.financial_details.technology_adoption_score IS '1-5 technology adoption scale';

-- ============================================================================
-- T008: Create indexes for all targeting tables
-- ============================================================================

-- biome_relationships indexes
CREATE INDEX IF NOT EXISTS idx_biome_current_client ON targeting.biome_relationships(is_current_client);
CREATE INDEX IF NOT EXISTS idx_biome_pilot_phase ON targeting.biome_relationships(pilot_phase) WHERE pilot_phase IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_biome_contract_type ON targeting.biome_relationships(contract_type) WHERE contract_type IS NOT NULL;

-- sales_coverage indexes
CREATE INDEX IF NOT EXISTS idx_coverage_rd ON targeting.sales_coverage(regional_director) WHERE regional_director IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_coverage_avp ON targeting.sales_coverage(area_vp) WHERE area_vp IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_coverage_interest ON targeting.sales_coverage(expressed_interest);
CREATE INDEX IF NOT EXISTS idx_coverage_region ON targeting.sales_coverage(region) WHERE region IS NOT NULL;

-- champions indexes
CREATE INDEX IF NOT EXISTS idx_champions_hospital ON targeting.champions(hospital_id);
CREATE INDEX IF NOT EXISTS idx_champions_type ON targeting.champions(champion_type);
CREATE INDEX IF NOT EXISTS idx_champions_engagement ON targeting.champions(engagement_level);
CREATE INDEX IF NOT EXISTS idx_champions_kol ON targeting.champions(kol_status) WHERE kol_status = TRUE;

-- Unique constraint for champions (hospital_id, champion_type, champion_name)
CREATE UNIQUE INDEX IF NOT EXISTS idx_champions_unique
    ON targeting.champions(hospital_id, champion_type, champion_name)
    WHERE champion_name IS NOT NULL;

-- volume_history indexes
CREATE INDEX IF NOT EXISTS idx_volume_year ON targeting.volume_history(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_volume_total ON targeting.volume_history(total_tavr_volume);
CREATE INDEX IF NOT EXISTS idx_volume_growth ON targeting.volume_history(yoy_growth_pct) WHERE yoy_growth_pct IS NOT NULL;

-- emr_systems indexes
CREATE INDEX IF NOT EXISTS idx_emr_vendor ON targeting.emr_systems(primary_emr) WHERE primary_emr IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_emr_standardized ON targeting.emr_systems(emr_standardized_network);

-- financial_details indexes
CREATE INDEX IF NOT EXISTS idx_financial_margin ON targeting.financial_details(operating_margin_pct) WHERE operating_margin_pct IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_financial_year ON targeting.financial_details(fiscal_year);

-- ============================================================================
-- T009: Grant API user permissions on targeting schema
-- ============================================================================

-- Grant usage on targeting schema
GRANT USAGE ON SCHEMA targeting TO api_user;

-- Grant SELECT on all current tables
GRANT SELECT ON ALL TABLES IN SCHEMA targeting TO api_user;

-- Grant SELECT on future tables in targeting schema
ALTER DEFAULT PRIVILEGES IN SCHEMA targeting GRANT SELECT ON TABLES TO api_user;

-- Grant usage on sequences (for champions.id)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA targeting TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA targeting GRANT USAGE ON SEQUENCES TO api_user;

-- ============================================================================
-- Update trigger for _updated_at columns
-- ============================================================================
CREATE OR REPLACE FUNCTION targeting.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW._updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for tables with _updated_at
DROP TRIGGER IF EXISTS trg_biome_updated_at ON targeting.biome_relationships;
CREATE TRIGGER trg_biome_updated_at
    BEFORE UPDATE ON targeting.biome_relationships
    FOR EACH ROW
    EXECUTE FUNCTION targeting.update_updated_at();

DROP TRIGGER IF EXISTS trg_coverage_updated_at ON targeting.sales_coverage;
CREATE TRIGGER trg_coverage_updated_at
    BEFORE UPDATE ON targeting.sales_coverage
    FOR EACH ROW
    EXECUTE FUNCTION targeting.update_updated_at();

DROP TRIGGER IF EXISTS trg_champions_updated_at ON targeting.champions;
CREATE TRIGGER trg_champions_updated_at
    BEFORE UPDATE ON targeting.champions
    FOR EACH ROW
    EXECUTE FUNCTION targeting.update_updated_at();

DROP TRIGGER IF EXISTS trg_emr_updated_at ON targeting.emr_systems;
CREATE TRIGGER trg_emr_updated_at
    BEFORE UPDATE ON targeting.emr_systems
    FOR EACH ROW
    EXECUTE FUNCTION targeting.update_updated_at();

-- ============================================================================
-- Verify schema creation
-- ============================================================================
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'targeting';

    IF table_count >= 6 THEN
        RAISE NOTICE 'SUCCESS: targeting schema created with % tables', table_count;
    ELSE
        RAISE WARNING 'WARNING: Expected 6 tables, found %', table_count;
    END IF;
END $$;
