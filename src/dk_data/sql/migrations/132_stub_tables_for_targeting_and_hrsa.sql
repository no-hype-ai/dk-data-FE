-- Migration 132: Create stub tables for targeting and HRSA modules
-- These tables are referenced by SQLMesh models but populated externally.

-- HRSA shortage areas (referenced by hcs_silver.geographic_designations)
CREATE TABLE IF NOT EXISTS hcs_raw.hrsa_shortage_areas (
    id              SERIAL PRIMARY KEY,
    state_abbr      TEXT,
    county_name     TEXT,
    hpsa_type       TEXT,   -- 'Primary Care' | 'Mental Health' | 'Dental'
    hpsa_score      NUMERIC,
    rural_status    TEXT,
    _loaded_at      TIMESTAMP DEFAULT NOW()
);

-- Targeting module tables (referenced by targeting.targeting_scores)
CREATE SCHEMA IF NOT EXISTS targeting;

CREATE TABLE IF NOT EXISTS targeting.biome_relationships (
    hospital_id              TEXT PRIMARY KEY,
    is_current_client        BOOLEAN DEFAULT FALSE,
    echo_surveillance_active BOOLEAN DEFAULT FALSE,
    workflow_active          BOOLEAN DEFAULT FALSE,
    analytics_active         BOOLEAN DEFAULT FALSE,
    pilot_phase              TEXT,
    contract_type            TEXT,
    phase_2_tokens_needed    INTEGER,
    created_at               TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS targeting.sales_coverage (
    hospital_id       TEXT PRIMARY KEY,
    regional_director TEXT,
    area_vp           TEXT,
    expressed_interest BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS targeting.volume_history (
    id               SERIAL PRIMARY KEY,
    hospital_id      TEXT NOT NULL,
    fiscal_year      INTEGER NOT NULL,
    total_tavr_volume INTEGER,
    yoy_growth_pct   NUMERIC,
    market_share_pct NUMERIC,
    created_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE (hospital_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS targeting.emr_systems (
    hospital_id  TEXT PRIMARY KEY,
    primary_emr  TEXT,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS targeting.champions (
    id               SERIAL PRIMARY KEY,
    hospital_id      TEXT NOT NULL,
    champion_type    TEXT NOT NULL,  -- 'Clinical' | 'Administrative'
    champion_name    TEXT,
    engagement_level TEXT,           -- 'Advocating' | 'Interested' | 'Passive'
    created_at       TIMESTAMP DEFAULT NOW()
);
