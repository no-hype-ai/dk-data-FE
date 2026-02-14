-- TAVR Data Infrastructure Platform - Database Initialization
-- Run this script to create all schemas and tables
-- Usage: psql -h localhost -p 5433 -U postgres -d dk_data -v AUTHENTICATOR_PASSWORD="'your_password'" -f init_database.sql
--
-- Required psql variables:
--   AUTHENTICATOR_PASSWORD - Password for the PostgREST authenticator role
--
-- The caller must specify the target database via psql -d flag.

-- =============================================================================
-- SCHEMA CREATION
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS scoring;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS api;

-- =============================================================================
-- RAW SCHEMA TABLES
-- Purpose: Store unmodified source data with ingestion metadata
-- =============================================================================

-- CMS Medicare Inpatient Data (DRG-level procedure volumes)
CREATE TABLE IF NOT EXISTS raw.cms_medicare_inpatient (
    id SERIAL PRIMARY KEY,
    provider_id VARCHAR(10) NOT NULL,
    provider_name VARCHAR(255),
    provider_street_address VARCHAR(255),
    provider_city VARCHAR(100),
    provider_state VARCHAR(2),
    provider_zip_code VARCHAR(10),
    drg_code VARCHAR(10) NOT NULL,
    drg_description VARCHAR(255),
    total_discharges INTEGER NOT NULL,
    average_covered_charges DECIMAL(12,2),
    average_total_payments DECIMAL(12,2),
    average_medicare_payments DECIMAL(12,2),
    fiscal_year INTEGER NOT NULL,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(255),
    _source_hash VARCHAR(64),
    UNIQUE (provider_id, fiscal_year, drg_code)
);

-- ACC TVC Certification Data
CREATE TABLE IF NOT EXISTS raw.acc_tvc_certification (
    id SERIAL PRIMARY KEY,
    facility_name VARCHAR(255) NOT NULL,
    facility_address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    zip_code VARCHAR(10),
    certification_type VARCHAR(100) NOT NULL,
    certification_date DATE,
    expiration_date DATE,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(255),
    _source_hash VARCHAR(64)
);

-- HRSA Shortage Area Designations
CREATE TABLE IF NOT EXISTS raw.hrsa_shortage_areas (
    id SERIAL PRIMARY KEY,
    hpsa_id VARCHAR(20) NOT NULL,
    hpsa_name VARCHAR(255),
    hpsa_type VARCHAR(50),
    designation_type VARCHAR(50),
    state_abbr VARCHAR(2) NOT NULL,
    county_name VARCHAR(100),
    hpsa_score INTEGER,
    designation_date DATE,
    rural_status VARCHAR(20),
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_hash VARCHAR(64)
);

-- CMS Hospital General Information
CREATE TABLE IF NOT EXISTS raw.cms_hospital_info (
    id SERIAL PRIMARY KEY,
    provider_id VARCHAR(10) NOT NULL,
    hospital_name VARCHAR(255) NOT NULL,
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2) NOT NULL,
    zip_code VARCHAR(10),
    county_name VARCHAR(100),
    phone_number VARCHAR(20),
    hospital_type VARCHAR(100),
    hospital_ownership VARCHAR(100),
    emergency_services BOOLEAN,
    hospital_overall_rating INTEGER,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_hash VARCHAR(64)
);

-- CMS Cost Reports (Financial Metrics)
CREATE TABLE IF NOT EXISTS raw.cms_cost_reports (
    id SERIAL PRIMARY KEY,
    provider_id VARCHAR(10) NOT NULL,
    fiscal_year_begin DATE,
    fiscal_year_end DATE,
    total_beds INTEGER,
    total_discharges INTEGER,
    net_patient_revenue DECIMAL(15,2),
    total_operating_expenses DECIMAL(15,2),
    operating_margin DECIMAL(8,4),
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_hash VARCHAR(64)
);

-- =============================================================================
-- STAGING SCHEMA TABLES
-- Purpose: Cleaned, standardized, deduplicated data
-- =============================================================================

CREATE TABLE IF NOT EXISTS staging.hospitals (
    hospital_id VARCHAR(10) PRIMARY KEY,
    hospital_name VARCHAR(255) NOT NULL,
    street_address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2) NOT NULL,
    zip_code VARCHAR(10),
    county VARCHAR(100),
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    hospital_type VARCHAR(100),
    ownership_type VARCHAR(100),
    bed_count INTEGER,
    has_emergency_services BOOLEAN,
    cms_overall_rating INTEGER,
    health_system_name VARCHAR(255),
    emr_system VARCHAR(100),
    _updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.tavr_volumes (
    hospital_id VARCHAR(10) NOT NULL REFERENCES staging.hospitals(hospital_id),
    fiscal_year INTEGER NOT NULL,
    drg_code VARCHAR(10) NOT NULL,
    medicare_discharges INTEGER NOT NULL,
    estimated_total_discharges INTEGER,
    average_charges DECIMAL(12,2),
    average_medicare_payment DECIMAL(12,2),
    _updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (hospital_id, fiscal_year, drg_code)
);

CREATE TABLE IF NOT EXISTS staging.certifications (
    hospital_id VARCHAR(10) NOT NULL,
    certification_type VARCHAR(100) NOT NULL,
    certifying_body VARCHAR(100) NOT NULL,
    certification_date DATE,
    expiration_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    _updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (hospital_id, certification_type, certifying_body)
);

CREATE TABLE IF NOT EXISTS staging.geographic_designations (
    hospital_id VARCHAR(10) PRIMARY KEY,
    is_hpsa_primary_care BOOLEAN,
    is_hpsa_mental_health BOOLEAN,
    is_mua BOOLEAN,
    hpsa_score INTEGER,
    rural_status VARCHAR(20),
    _updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- MART SCHEMA TABLES
-- Purpose: Analytics-ready dimension and fact tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS mart.dim_hospital (
    hospital_key SERIAL PRIMARY KEY,
    hospital_id VARCHAR(10) NOT NULL,
    hospital_name VARCHAR(255) NOT NULL,
    health_system_name VARCHAR(255),
    network_tier VARCHAR(20),
    state VARCHAR(2) NOT NULL,
    city VARCHAR(100),
    county VARCHAR(100),
    hospital_type VARCHAR(100),
    ownership_type VARCHAR(100),
    bed_count INTEGER,
    has_tavr_certification BOOLEAN,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dim_hospital_current ON mart.dim_hospital(hospital_id) WHERE is_current = TRUE;

CREATE TABLE IF NOT EXISTS mart.fact_tavr_program (
    program_key SERIAL PRIMARY KEY,
    hospital_key INTEGER NOT NULL REFERENCES mart.dim_hospital(hospital_key),
    fiscal_year INTEGER NOT NULL,
    medicare_tavr_volume INTEGER,
    estimated_total_volume INTEGER,
    yoy_volume_change DECIMAL(8,4),
    tvt_star_rating INTEGER,
    has_active_certification BOOLEAN,
    _updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (hospital_key, fiscal_year)
);

CREATE TABLE IF NOT EXISTS mart.fact_financial_metrics (
    hospital_key INTEGER NOT NULL REFERENCES mart.dim_hospital(hospital_key),
    fiscal_year INTEGER NOT NULL,
    operating_margin DECIMAL(8,4),
    margin_quartile INTEGER,
    _updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (hospital_key, fiscal_year)
);

-- =============================================================================
-- SCORING SCHEMA TABLES
-- Purpose: Target Readiness Score calculations
-- =============================================================================

CREATE TABLE IF NOT EXISTS scoring.target_scores (
    score_id SERIAL PRIMARY KEY,
    hospital_key INTEGER NOT NULL REFERENCES mart.dim_hospital(hospital_key),
    score_date DATE NOT NULL,
    clinical_readiness_score INTEGER,
    operational_readiness_score INTEGER,
    strategic_alignment_score INTEGER,
    financial_capacity_score INTEGER,
    champion_access_score INTEGER,
    bonus_points INTEGER NOT NULL DEFAULT 0,
    penalty_points INTEGER NOT NULL DEFAULT 0,
    total_trs INTEGER NOT NULL,
    tier_classification CHAR(1) NOT NULL,
    data_completeness DECIMAL(5,4),
    _calculated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (hospital_key, score_date),
    CONSTRAINT valid_tier CHECK (tier_classification IN ('A', 'B', 'C', 'D', 'E'))
);

CREATE TABLE IF NOT EXISTS scoring.score_factors (
    factor_id SERIAL PRIMARY KEY,
    score_id INTEGER NOT NULL REFERENCES scoring.target_scores(score_id),
    domain VARCHAR(50) NOT NULL,
    factor_name VARCHAR(100) NOT NULL,
    raw_value VARCHAR(255),
    points_awarded INTEGER NOT NULL,
    max_points INTEGER NOT NULL,
    confidence_level VARCHAR(20),
    data_source VARCHAR(100),
    _calculated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scoring.score_history (
    history_id SERIAL PRIMARY KEY,
    hospital_key INTEGER NOT NULL,
    score_date DATE NOT NULL,
    total_trs INTEGER NOT NULL,
    tier_classification CHAR(1) NOT NULL,
    change_reason VARCHAR(255),
    _recorded_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- META SCHEMA TABLES
-- Purpose: Data catalog and audit trail
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.data_sources (
    source_id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL UNIQUE,
    source_type VARCHAR(50),
    source_url VARCHAR(500),
    description TEXT,
    refresh_frequency VARCHAR(50),
    last_successful_refresh TIMESTAMP,
    last_refresh_attempt TIMESTAMP,
    last_refresh_status VARCHAR(20),
    record_count INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    -- New fields for enhanced catalog (T005)
    topic_tags TEXT[] DEFAULT '{}',
    column_descriptions JSONB DEFAULT '{}',
    staleness_threshold_hours INTEGER DEFAULT 24,
    table_size_bytes BIGINT,
    ai_description TEXT,
    target_tables TEXT[] DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS meta.refresh_log (
    log_id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES meta.data_sources(source_id),
    refresh_started_at TIMESTAMP,
    refresh_completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    records_fetched INTEGER,
    records_inserted INTEGER,
    records_updated INTEGER,
    error_message TEXT,
    _logged_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.data_quality (
    quality_id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES meta.data_sources(source_id),
    check_date DATE NOT NULL,
    completeness_pct DECIMAL(5,2),
    validity_pct DECIMAL(5,2),
    freshness_days INTEGER,
    quality_score DECIMAL(5,2),
    issues_found JSONB,
    _checked_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- T006: Table Health Tracking
-- Purpose: Track health status based on freshness and data quality metrics
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.table_health (
    health_id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES meta.data_sources(source_id),
    check_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    health_status VARCHAR(20) NOT NULL,
    freshness_hours INTEGER,
    null_rate DECIMAL(5,4),
    validation_error_count INTEGER DEFAULT 0,
    row_count INTEGER,
    row_count_change INTEGER,
    details JSONB,
    CONSTRAINT valid_health_status CHECK (health_status IN ('healthy', 'stale', 'unhealthy')),
    CONSTRAINT valid_null_rate CHECK (null_rate >= 0 AND null_rate <= 1)
);

-- =============================================================================
-- T007: Batch Job Definitions
-- Purpose: Track batch job configurations and execution status
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.batch_jobs (
    job_id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    cron_schedule VARCHAR(50),
    source_ids INTEGER[],
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMP,
    last_run_status VARCHAR(20),
    last_run_duration_seconds INTEGER,
    next_scheduled_run TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- T008: Batch Job Execution History
-- Purpose: Detailed execution history for batch jobs
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.batch_job_runs (
    run_id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES meta.batch_jobs(job_id),
    triggered_by VARCHAR(50) NOT NULL,
    triggered_by_user VARCHAR(100),
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    records_processed INTEGER,
    error_message TEXT,
    k8s_job_name VARCHAR(255),
    CONSTRAINT valid_run_status CHECK (status IN ('running', 'success', 'failure', 'cancelled'))
);

-- =============================================================================
-- POSTGREST ROLES AND PERMISSIONS
-- =============================================================================

-- Create anonymous role for read access (limited)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        CREATE ROLE web_anon NOLOGIN;
    END IF;
END
$$;

-- T050: Create analyst role with extended permissions
-- Analysts can access detailed scoring and financial data
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
END
$$;

-- Create api_user role for authenticated API access
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_user') THEN
        CREATE ROLE api_user NOLOGIN;
    END IF;
END
$$;

-- Validate that a real password was provided (reject known defaults)
DO $$
BEGIN
    IF :'AUTHENTICATOR_PASSWORD' IN ('postgrest_secret_change_me', 'password', 'changeme', '') THEN
        RAISE EXCEPTION 'AUTHENTICATOR_PASSWORD must be set to a real password, not a default/placeholder value. '
            'Pass via: psql -v AUTHENTICATOR_PASSWORD="''your_secure_password''"';
    END IF;
END
$$;

-- Create authenticator role
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        EXECUTE format('CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD %L', :'AUTHENTICATOR_PASSWORD');
    ELSE
        EXECUTE format('ALTER ROLE authenticator PASSWORD %L', :'AUTHENTICATOR_PASSWORD');
    END IF;
END
$$;

-- Grant roles to authenticator (for role switching via JWT)
GRANT web_anon TO authenticator;
GRANT analyst TO authenticator;
GRANT api_user TO authenticator;

-- Grant usage on api schema to all roles
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT USAGE ON SCHEMA api TO analyst;
GRANT USAGE ON SCHEMA api TO api_user;

-- Anonymous role: limited access (public views only)
GRANT SELECT ON ALL TABLES IN SCHEMA api TO web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO web_anon;

-- Analyst role: extended access to scoring and mart schemas
GRANT USAGE ON SCHEMA scoring TO analyst;
GRANT USAGE ON SCHEMA mart TO analyst;
GRANT USAGE ON SCHEMA meta TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA scoring TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA meta TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO analyst;

-- API user role: full read access
GRANT USAGE ON SCHEMA raw TO api_user;
GRANT USAGE ON SCHEMA staging TO api_user;
GRANT USAGE ON SCHEMA scoring TO api_user;
GRANT USAGE ON SCHEMA mart TO api_user;
GRANT USAGE ON SCHEMA meta TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA staging TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA scoring TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA meta TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO api_user;

-- =============================================================================
-- API SCHEMA VIEWS
-- Purpose: Views exposed via PostgREST
-- =============================================================================

-- View: Scored TAVR Clinic Targets
CREATE OR REPLACE VIEW api.targets AS
SELECT
    h.hospital_id,
    h.hospital_name,
    h.health_system_name,
    h.network_tier,
    h.state,
    h.city,
    s.total_trs,
    s.tier_classification,
    s.clinical_readiness_score,
    s.operational_readiness_score,
    s.strategic_alignment_score,
    s.financial_capacity_score,
    s.champion_access_score,
    s.data_completeness,
    s.score_date,
    f.estimated_total_volume AS latest_tavr_volume,
    f.tvt_star_rating
FROM mart.dim_hospital h
JOIN scoring.target_scores s ON h.hospital_key = s.hospital_key
LEFT JOIN mart.fact_tavr_program f ON h.hospital_key = f.hospital_key
    AND f.fiscal_year = (SELECT MAX(fiscal_year) FROM mart.fact_tavr_program WHERE hospital_key = h.hospital_key)
WHERE h.is_current = TRUE
  AND s.score_date = (
      SELECT MAX(score_date)
      FROM scoring.target_scores
      WHERE hospital_key = s.hospital_key
  );

-- View: Hospital Details with Certifications and Geographic Data
CREATE OR REPLACE VIEW api.hospitals AS
SELECT
    h.hospital_id,
    h.hospital_name,
    h.health_system_name,
    h.state,
    h.city,
    h.county,
    h.hospital_type,
    h.ownership_type,
    h.bed_count,
    h.has_tavr_certification,
    c.certification_type,
    c.certifying_body,
    c.is_active AS certification_active,
    g.is_hpsa_primary_care,
    g.is_mua,
    g.rural_status
FROM mart.dim_hospital h
LEFT JOIN staging.certifications c ON h.hospital_id = c.hospital_id AND c.is_active = TRUE
LEFT JOIN staging.geographic_designations g ON h.hospital_id = g.hospital_id
WHERE h.is_current = TRUE;

-- View: Data Catalog with Freshness Status
CREATE OR REPLACE VIEW api.data_catalog AS
SELECT
    ds.source_name,
    ds.source_type,
    ds.source_url,
    ds.description,
    ds.refresh_frequency,
    ds.last_successful_refresh,
    ds.record_count,
    dq.completeness_pct,
    dq.freshness_days,
    dq.quality_score,
    CASE
        WHEN dq.freshness_days IS NULL THEN 'unknown'
        WHEN dq.freshness_days <= 7 THEN 'fresh'
        WHEN dq.freshness_days <= 30 THEN 'stale'
        ELSE 'outdated'
    END AS freshness_status
FROM meta.data_sources ds
LEFT JOIN meta.data_quality dq ON ds.source_id = dq.source_id
    AND dq.check_date = (SELECT MAX(check_date) FROM meta.data_quality WHERE source_id = ds.source_id)
WHERE ds.is_active = TRUE;

-- View: Scoring Details (Factor Breakdown)
CREATE OR REPLACE VIEW api.scoring_details AS
SELECT
    h.hospital_id,
    h.hospital_name,
    sf.domain,
    sf.factor_name,
    sf.raw_value,
    sf.points_awarded,
    sf.max_points,
    sf.confidence_level,
    sf.data_source
FROM mart.dim_hospital h
JOIN scoring.target_scores s ON h.hospital_key = s.hospital_key
JOIN scoring.score_factors sf ON s.score_id = sf.score_id
WHERE h.is_current = TRUE
  AND s.score_date = (
      SELECT MAX(score_date)
      FROM scoring.target_scores
      WHERE hospital_key = s.hospital_key
  );

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_raw_cms_inpatient_provider ON raw.cms_medicare_inpatient(provider_id);
CREATE INDEX IF NOT EXISTS idx_raw_cms_inpatient_drg ON raw.cms_medicare_inpatient(drg_code);
CREATE INDEX IF NOT EXISTS idx_staging_tavr_volumes_hospital ON staging.tavr_volumes(hospital_id);
CREATE INDEX IF NOT EXISTS idx_scoring_target_scores_hospital ON scoring.target_scores(hospital_key);
CREATE INDEX IF NOT EXISTS idx_scoring_target_scores_date ON scoring.target_scores(score_date);
CREATE INDEX IF NOT EXISTS idx_scoring_score_factors_score ON scoring.score_factors(score_id);

-- T009: Indexes for catalog and health tracking performance
CREATE INDEX IF NOT EXISTS idx_data_sources_topic_tags ON meta.data_sources USING GIN(topic_tags);
CREATE INDEX IF NOT EXISTS idx_data_sources_active ON meta.data_sources(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_table_health_source_timestamp ON meta.table_health(source_id, check_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_table_health_status ON meta.table_health(health_status);
CREATE INDEX IF NOT EXISTS idx_batch_job_runs_job_started ON meta.batch_job_runs(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_batch_job_runs_status ON meta.batch_job_runs(status) WHERE status = 'running';

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Database initialization complete.';
    RAISE NOTICE 'Schemas created: raw, staging, mart, scoring, meta, api';
    RAISE NOTICE 'Roles created: web_anon, authenticator';
    RAISE NOTICE 'API views created: targets, hospitals, data_catalog, scoring_details';
    RAISE NOTICE 'New meta tables: table_health, batch_jobs, batch_job_runs';
    RAISE NOTICE 'Enhanced meta.data_sources with: topic_tags, column_descriptions, ai_description';
END
$$;
