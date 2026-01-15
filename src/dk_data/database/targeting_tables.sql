-- Targeting Schema - Internal Business Data Tables
-- These tables store Edwards-specific business data that is NOT derived from public sources.
-- Data should be populated from CRM, sales systems, or manual entry.
--
-- Feature: 001-data-layer-postgrest-gitops
-- Created: 2026-01-15

CREATE SCHEMA IF NOT EXISTS targeting;

-- ============================================================================
-- 1. Biome Relationships
-- Tracks Edwards Biome platform adoption status per hospital
-- Source: Internal CRM / contract management system
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.biome_relationships (
    hospital_id VARCHAR(10) PRIMARY KEY,
    is_current_client BOOLEAN DEFAULT FALSE,
    echo_surveillance_active BOOLEAN DEFAULT FALSE,  -- Echo surveillance module
    workflow_active BOOLEAN DEFAULT FALSE,           -- Workflow management module
    analytics_active BOOLEAN DEFAULT FALSE,          -- Analytics dashboard module
    pilot_phase VARCHAR(50),                         -- 'Phase 1', 'Phase 2', NULL
    contract_type VARCHAR(50),                       -- 'Full', 'Pilot', 'Trial', NULL
    phase_2_tokens_needed INTEGER,                   -- Tokens needed for Phase 2 expansion
    contract_start_date DATE,
    contract_end_date DATE,
    _updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE targeting.biome_relationships IS
    'Edwards Biome platform relationship status by hospital. Source: CRM/contract system.';

-- ============================================================================
-- 2. Sales Coverage
-- Sales team territory assignments and engagement tracking
-- Source: CRM / sales territory management
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.sales_coverage (
    hospital_id VARCHAR(10) PRIMARY KEY,
    regional_director VARCHAR(100),
    area_vp VARCHAR(100),
    territory VARCHAR(100),
    expressed_interest BOOLEAN DEFAULT FALSE,        -- Has expressed interest in Biome
    last_contact_date DATE,
    notes TEXT,
    _updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE targeting.sales_coverage IS
    'Sales team assignments and engagement status. Source: CRM system.';

-- ============================================================================
-- 3. Volume History
-- TAVR procedure volumes over time for growth analysis
-- Can be populated from: CMS data (automated) or internal tracking (manual)
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.volume_history (
    hospital_id VARCHAR(10),
    fiscal_year INTEGER,
    total_tavr_volume INTEGER,
    medicare_volume INTEGER,
    yoy_growth_pct DECIMAL(8,2),
    market_share_pct DECIMAL(5,2),
    _updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (hospital_id, fiscal_year)
);

COMMENT ON TABLE targeting.volume_history IS
    'Historical TAVR volumes for growth scoring. Auto-populated from CMS or manual entry.';

-- ============================================================================
-- 4. EMR Systems
-- Hospital EMR information for integration planning
-- Source: Manual research / sales intelligence
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.emr_systems (
    hospital_id VARCHAR(10) PRIMARY KEY,
    primary_emr VARCHAR(100),                        -- 'Epic', 'Cerner', 'Meditech', etc.
    emr_version VARCHAR(50),
    integration_ready BOOLEAN DEFAULT FALSE,
    integration_notes TEXT,
    _updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE targeting.emr_systems IS
    'Hospital EMR systems for integration compatibility scoring. Source: Sales research.';

-- ============================================================================
-- 5. Champions
-- Key clinical and administrative contacts at hospitals
-- Source: CRM / sales activity tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS targeting.champions (
    id SERIAL PRIMARY KEY,
    hospital_id VARCHAR(10),
    champion_type VARCHAR(50),                       -- 'Clinical', 'Administrative'
    champion_name VARCHAR(200),
    title VARCHAR(200),
    email VARCHAR(200),
    phone VARCHAR(50),
    engagement_level VARCHAR(50),                    -- 'Advocating', 'Interested', 'Passive'
    last_contact_date DATE,
    notes TEXT,
    _updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_champions_hospital ON targeting.champions(hospital_id);
CREATE INDEX IF NOT EXISTS idx_champions_type ON targeting.champions(hospital_id, champion_type);

COMMENT ON TABLE targeting.champions IS
    'Key contacts at hospitals for relationship tracking. Source: CRM system.';

-- ============================================================================
-- Seed volume_history from staging.tavr_volumes (run after initial data load)
-- ============================================================================
-- INSERT INTO targeting.volume_history (hospital_id, fiscal_year, total_tavr_volume, medicare_volume)
-- SELECT
--     hospital_id,
--     fiscal_year,
--     SUM(estimated_total_discharges) as total_tavr_volume,
--     SUM(medicare_discharges) as medicare_volume
-- FROM staging.tavr_volumes
-- GROUP BY hospital_id, fiscal_year
-- ON CONFLICT (hospital_id, fiscal_year) DO UPDATE SET
--     total_tavr_volume = EXCLUDED.total_tavr_volume,
--     medicare_volume = EXCLUDED.medicare_volume,
--     _updated_at = NOW();
