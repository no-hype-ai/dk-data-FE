-- Migration: 036_sync_scheduler_tables.sql
-- Description: Create tables for sync scheduler and data freshness monitoring
-- Date: 2026-01-24
-- Part of: 012-dk-data-platform

-- ==========================================
-- Sync Schedules Table
-- ==========================================

CREATE TABLE IF NOT EXISTS raw.sync_schedules (
    source VARCHAR(50) PRIMARY KEY,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('daily', 'weekly', 'monthly', 'on_demand')),
    cron_expression VARCHAR(50) NOT NULL,
    priority VARCHAR(20) DEFAULT 'normal' CHECK (priority IN ('critical', 'high', 'normal', 'low')),
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    options JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================================
-- Ingestion Jobs Table (if not exists)
-- ==========================================

CREATE TABLE IF NOT EXISTS raw.ingestion_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    priority VARCHAR(20) DEFAULT 'normal',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    records_processed INTEGER DEFAULT 0,
    error_message TEXT,
    error_details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_source ON raw.ingestion_jobs(source);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON raw.ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_started ON raw.ingestion_jobs(started_at DESC);

-- ==========================================
-- Insert Default Schedules
-- ==========================================

INSERT INTO raw.sync_schedules (source, tier, cron_expression, priority) VALUES
    ('clinicaltrials_gov', 'daily', '0 2 * * *', 'critical'),
    ('openfda_faers', 'daily', '0 2 * * *', 'critical'),
    ('openfda_labels', 'daily', '30 2 * * *', 'high'),
    ('drugbank', 'weekly', '0 3 * * 0', 'normal'),
    ('chembl', 'weekly', '0 3 * * 0', 'normal'),
    ('openalex', 'weekly', '30 3 * * 0', 'low'),
    ('uniprot', 'monthly', '0 4 1 * *', 'low'),
    ('pubchem', 'monthly', '0 4 1 * *', 'low')
ON CONFLICT (source) DO NOTHING;

-- ==========================================
-- Source Status View
-- ==========================================

CREATE OR REPLACE VIEW raw.source_status AS
SELECT
    ss.source,
    ss.tier,
    ss.enabled,
    ss.last_run,
    ss.next_run,
    COALESCE(latest.status, 'unknown') as latest_job_status,
    latest.completed_at as latest_job_completed,
    latest.records_processed as latest_records_processed,
    latest.error_message as latest_error,
    CASE
        WHEN NOT ss.enabled THEN 'disabled'
        WHEN latest.status = 'processing' THEN 'refreshing'
        WHEN latest.status = 'failed' THEN 'error'
        WHEN ss.last_run IS NULL THEN 'unknown'
        WHEN ss.tier = 'daily' AND ss.last_run < NOW() - INTERVAL '36 hours' THEN 'stale'
        WHEN ss.tier = 'weekly' AND ss.last_run < NOW() - INTERVAL '8 days' THEN 'stale'
        WHEN ss.tier = 'monthly' AND ss.last_run < NOW() - INTERVAL '32 days' THEN 'stale'
        ELSE 'healthy'
    END as status
FROM raw.sync_schedules ss
LEFT JOIN LATERAL (
    SELECT status, completed_at, records_processed, error_message
    FROM raw.ingestion_jobs
    WHERE source = ss.source
    ORDER BY started_at DESC
    LIMIT 1
) latest ON TRUE;

-- ==========================================
-- Job Statistics View
-- ==========================================

CREATE OR REPLACE VIEW raw.ingestion_job_stats AS
SELECT
    source,
    COUNT(*) as total_jobs,
    COUNT(*) FILTER (WHERE status = 'completed') as successful_jobs,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_jobs,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))
        FILTER (WHERE completed_at IS NOT NULL) as avg_duration_seconds,
    SUM(records_processed) as total_records_processed,
    MAX(completed_at) FILTER (WHERE status = 'completed') as last_success,
    MAX(started_at) as last_run
FROM raw.ingestion_jobs
WHERE started_at >= NOW() - INTERVAL '30 days'
GROUP BY source;
