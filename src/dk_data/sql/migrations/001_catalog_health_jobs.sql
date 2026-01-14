-- Migration: 001_catalog_health_jobs
-- Feature: 001-data-layer-postgrest-gitops
-- Purpose: Add catalog enhancements, health tracking, and batch job tables
-- Run: psql -h localhost -p 5433 -U postgres -d edwards_tavr -f migrations/001_catalog_health_jobs.sql

-- =============================================================================
-- T005: Enhance meta.data_sources with new columns
-- =============================================================================

ALTER TABLE meta.data_sources
ADD COLUMN IF NOT EXISTS topic_tags TEXT[] DEFAULT '{}';

ALTER TABLE meta.data_sources
ADD COLUMN IF NOT EXISTS column_descriptions JSONB DEFAULT '{}';

ALTER TABLE meta.data_sources
ADD COLUMN IF NOT EXISTS staleness_threshold_hours INTEGER DEFAULT 24;

ALTER TABLE meta.data_sources
ADD COLUMN IF NOT EXISTS table_size_bytes BIGINT;

ALTER TABLE meta.data_sources
ADD COLUMN IF NOT EXISTS ai_description TEXT;

ALTER TABLE meta.data_sources
ADD COLUMN IF NOT EXISTS target_tables TEXT[] DEFAULT '{}';

-- =============================================================================
-- T006: Create meta.table_health table
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
-- T007: Create meta.batch_jobs table
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
-- T008: Create meta.batch_job_runs table
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
-- T009: Create indexes for performance
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_data_sources_topic_tags ON meta.data_sources USING GIN(topic_tags);
CREATE INDEX IF NOT EXISTS idx_data_sources_active ON meta.data_sources(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_table_health_source_timestamp ON meta.table_health(source_id, check_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_table_health_status ON meta.table_health(health_status);
CREATE INDEX IF NOT EXISTS idx_batch_job_runs_job_started ON meta.batch_job_runs(job_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_batch_job_runs_status ON meta.batch_job_runs(status) WHERE status = 'running';

-- =============================================================================
-- Migration complete
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 001_catalog_health_jobs complete.';
    RAISE NOTICE 'Enhanced meta.data_sources with semantic metadata columns';
    RAISE NOTICE 'Created meta.table_health for health tracking';
    RAISE NOTICE 'Created meta.batch_jobs and meta.batch_job_runs for job management';
END
$$;
