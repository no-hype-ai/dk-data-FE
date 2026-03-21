-- Migration 085: CMS PUF Silver Tables (016-cms-puf-datasource-integration)
-- Purpose: Create silver enrichment target tables that agents write to
-- Date: 2026-03-11

BEGIN;

-- Ensure silver schema exists
CREATE SCHEMA IF NOT EXISTS silver;

-- =============================================================================
-- hcs_silver.cms_provider_profile — Composite of NPPES + prescribing + procedures + payments
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_provider_profile (
    npi                         TEXT PRIMARY KEY,
    entity_type                 TEXT,
    name_first                  TEXT,
    name_last                   TEXT,
    name_org                    TEXT,
    credential                  TEXT,
    primary_taxonomy            TEXT,
    primary_specialty           TEXT,
    practice_state              TEXT,
    practice_zip                TEXT,
    total_part_d_claims         INTEGER,
    total_part_d_cost           NUMERIC,
    unique_drugs_prescribed     INTEGER,
    total_procedures            NUMERIC,
    unique_hcpcs_billed         INTEGER,
    total_medicare_payments     NUMERIC,
    total_open_payments         NUMERIC,
    open_payments_general_count INTEGER,
    open_payments_research_count INTEGER,
    latest_data_year            INTEGER,
    updated_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_silver_provider_profile_state ON hcs_silver.cms_provider_profile (practice_state);
CREATE INDEX IF NOT EXISTS idx_silver_provider_profile_specialty ON hcs_silver.cms_provider_profile (primary_specialty);

-- =============================================================================
-- hcs_silver.cms_facility_profile — Composite of POS + quality + cost
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_facility_profile (
    ccn                         TEXT PRIMARY KEY,
    facility_name               TEXT,
    facility_type               TEXT,
    state                       TEXT,
    city                        TEXT,
    bed_count                   INTEGER,
    overall_quality_rating      INTEGER,
    ownership_type              TEXT,
    total_discharges            INTEGER,
    total_costs                 NUMERIC,
    total_revenue               NUMERIC,
    net_income                  NUMERIC,
    is_magnet                   BOOLEAN DEFAULT FALSE,
    latest_data_year            INTEGER,
    updated_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_silver_facility_profile_state ON hcs_silver.cms_facility_profile (state);
CREATE INDEX IF NOT EXISTS idx_silver_facility_profile_type ON hcs_silver.cms_facility_profile (facility_type);

-- =============================================================================
-- hcs_silver.cms_drug_market — Composite of NDC + spending + formulary
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_drug_market (
    ndc                         TEXT PRIMARY KEY,
    proprietary_name            TEXT,
    nonproprietary_name         TEXT,
    labeler_name                TEXT,
    dosage_form                 TEXT,
    route                       TEXT,
    total_part_d_spending       NUMERIC,
    total_part_b_spending       NUMERIC,
    total_claims                INTEGER,
    total_beneficiaries         INTEGER,
    formulary_coverage_pct      NUMERIC,
    avg_tier_level              NUMERIC,
    prior_auth_pct              NUMERIC,
    latest_data_year            INTEGER,
    updated_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_silver_drug_market_name ON hcs_silver.cms_drug_market (nonproprietary_name);

-- =============================================================================
-- hcs_silver.cms_geographic — State/county level geographic composite
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_geographic (
    state                       TEXT NOT NULL,
    county                      TEXT NOT NULL,
    bene_count                  INTEGER,
    per_capita_costs            NUMERIC,
    total_actual_costs          NUMERIC,
    top_chronic_conditions      JSONB,
    latest_data_year            INTEGER,
    updated_at                  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (state, county)
);

CREATE INDEX IF NOT EXISTS idx_silver_geographic_state ON hcs_silver.cms_geographic (state);

-- =============================================================================
-- hcs_silver.ref_drg_service_line — Agent-derived DRG to service line mapping
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.ref_drg_service_line (
    drg_code                    TEXT PRIMARY KEY,
    drg_description             TEXT,
    service_line                TEXT,
    confidence_score            NUMERIC,
    agent_version               TEXT
);

-- =============================================================================
-- hcs_silver.ref_hcpcs_equipment — Agent-derived HCPCS to equipment mapping
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.ref_hcpcs_equipment (
    hcpcs_code                  TEXT PRIMARY KEY,
    hcpcs_description           TEXT,
    equipment_category          TEXT,
    confidence_score            NUMERIC,
    agent_version               TEXT
);

-- =============================================================================
-- hcs_silver.ref_nucc_taxonomy — NUCC taxonomy reference
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.ref_nucc_taxonomy (
    taxonomy_code               TEXT PRIMARY KEY,
    classification              TEXT,
    specialization              TEXT,
    grouping_name               TEXT
);

-- =============================================================================
-- hcs_silver.cms_health_system_hierarchy — Agent-derived health system rollups
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_health_system_hierarchy (
    system_id                   TEXT PRIMARY KEY,
    system_name                 TEXT,
    parent_system_id            TEXT,
    member_ccns                 TEXT[],
    hierarchy_level             INTEGER,
    confidence_score            NUMERIC,
    agent_version               TEXT
);

CREATE INDEX IF NOT EXISTS idx_silver_health_system_parent ON hcs_silver.cms_health_system_hierarchy (parent_system_id);

-- =============================================================================
-- hcs_silver.cms_referral_edges — Agent-derived referral network edges
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_referral_edges (
    source_npi                  TEXT NOT NULL,
    target_npi                  TEXT NOT NULL,
    relationship_type           TEXT,
    strength_score              NUMERIC,
    shared_patient_count        INTEGER,
    confidence_score            NUMERIC,
    agent_version               TEXT,
    PRIMARY KEY (source_npi, target_npi)
);

CREATE INDEX IF NOT EXISTS idx_silver_referral_edges_source ON hcs_silver.cms_referral_edges (source_npi);
CREATE INDEX IF NOT EXISTS idx_silver_referral_edges_target ON hcs_silver.cms_referral_edges (target_npi);

-- =============================================================================
-- hcs_silver.cms_verified_contacts — Agent-verified contact information
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_verified_contacts (
    npi                         TEXT PRIMARY KEY,
    phone_normalized            TEXT,
    phone_valid                 BOOLEAN,
    address_normalized          JSONB,
    address_valid               BOOLEAN,
    confidence_score            NUMERIC,
    agent_version               TEXT
);

-- =============================================================================
-- hcs_silver.cms_staffing_profiles — Agent-derived staffing from HCRIS
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_staffing_profiles (
    ccn                         TEXT NOT NULL,
    staffing_category           TEXT NOT NULL,
    fte_count                   NUMERIC,
    salary_cost                 NUMERIC,
    benefits_cost               NUMERIC,
    contract_labor_cost         NUMERIC,
    confidence_score            NUMERIC,
    agent_version               TEXT,
    PRIMARY KEY (ccn, staffing_category)
);

CREATE INDEX IF NOT EXISTS idx_silver_staffing_profiles_ccn ON hcs_silver.cms_staffing_profiles (ccn);

-- =============================================================================
-- hcs_silver.cms_equipment_inventory — Agent-derived equipment from DMEPOS/HCPCS
-- =============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.cms_equipment_inventory (
    ccn                         TEXT NOT NULL,
    equipment_category          TEXT NOT NULL,
    equipment_type              TEXT,
    evidence_hcpcs              TEXT[],
    volume_indicator            TEXT,
    confidence_score            NUMERIC,
    agent_version               TEXT,
    PRIMARY KEY (ccn, equipment_category)
);

CREATE INDEX IF NOT EXISTS idx_silver_equipment_inventory_ccn ON hcs_silver.cms_equipment_inventory (ccn);

COMMIT;
