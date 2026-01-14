-- TAVR Data Platform - API Views for Catalog, Jobs, and Health
-- Feature: 001-data-layer-postgrest-gitops
-- Tasks: T012-T016
--
-- These views are exposed via PostgREST for API access.
-- Run after init_database.sql and migrations/001_catalog_health_jobs.sql

-- ============================================================================
-- T012: api.catalog view
-- Data catalog with health status for AI retrieval and monitoring
-- ============================================================================

CREATE OR REPLACE VIEW api.catalog AS
SELECT
    ds.source_id,
    ds.source_name,
    ds.source_type,
    ds.description,
    ds.ai_description,
    ds.topic_tags,
    ds.column_descriptions,
    ds.refresh_frequency,
    ds.last_successful_refresh,
    ds.record_count,
    ds.table_size_bytes,
    ds.staleness_threshold_hours,
    ds.target_tables,
    th.health_status,
    th.freshness_hours,
    th.null_rate,
    th.validation_error_count,
    th.check_timestamp AS health_checked_at,
    CASE
        WHEN th.health_status = 'healthy' THEN 'green'
        WHEN th.health_status = 'stale' THEN 'yellow'
        ELSE 'red'
    END AS status_color
FROM meta.data_sources ds
LEFT JOIN LATERAL (
    SELECT *
    FROM meta.table_health
    WHERE source_id = ds.source_id
    ORDER BY check_timestamp DESC
    LIMIT 1
) th ON TRUE
WHERE ds.is_active = TRUE;

COMMENT ON VIEW api.catalog IS 'Data catalog with health status, filterable by topic_tags, health_status, source_type';

-- ============================================================================
-- T013: api.jobs view
-- Batch job definitions with associated data sources
-- ============================================================================

CREATE OR REPLACE VIEW api.jobs AS
SELECT
    bj.job_id,
    bj.job_name,
    bj.description,
    bj.cron_schedule,
    bj.is_enabled,
    bj.last_run_at,
    bj.last_run_status,
    bj.last_run_duration_seconds,
    bj.next_scheduled_run,
    bj.created_at,
    bj.updated_at,
    COALESCE(
        (SELECT ARRAY_AGG(ds.source_name)
         FROM meta.data_sources ds
         WHERE ds.source_id = ANY(bj.source_ids)),
        '{}'::TEXT[]
    ) AS source_names
FROM meta.batch_jobs bj;

COMMENT ON VIEW api.jobs IS 'Batch job definitions with status and associated data sources';

-- ============================================================================
-- T014: api.job_runs view
-- Batch job execution history
-- ============================================================================

CREATE OR REPLACE VIEW api.job_runs AS
SELECT
    bjr.run_id,
    bj.job_name,
    bjr.triggered_by,
    bjr.triggered_by_user,
    bjr.started_at,
    bjr.completed_at,
    bjr.status,
    bjr.records_processed,
    bjr.error_message,
    bjr.k8s_job_name,
    CASE
        WHEN bjr.completed_at IS NOT NULL THEN
            EXTRACT(EPOCH FROM (bjr.completed_at - bjr.started_at))::INTEGER
        ELSE NULL
    END AS duration_seconds
FROM meta.batch_job_runs bjr
JOIN meta.batch_jobs bj ON bjr.job_id = bj.job_id
ORDER BY bjr.started_at DESC;

COMMENT ON VIEW api.job_runs IS 'Batch job execution history with duration and status';

-- ============================================================================
-- T015: api.health view
-- System health check aggregating catalog health metrics
-- ============================================================================

CREATE OR REPLACE VIEW api.health AS
SELECT
    CASE
        WHEN unhealthy_count > 0 THEN 'unhealthy'
        WHEN stale_count > 0 THEN 'degraded'
        ELSE 'healthy'
    END AS status,
    NOW() AS timestamp,
    jsonb_build_object(
        'database', 'up',
        'postgrest', 'up',
        'catalog', jsonb_build_object(
            'total_sources', total_count,
            'healthy_count', healthy_count,
            'stale_count', stale_count,
            'unhealthy_count', unhealthy_count
        ),
        'jobs', jsonb_build_object(
            'total_jobs', (SELECT COUNT(*) FROM meta.batch_jobs WHERE is_enabled = TRUE),
            'running_jobs', (SELECT COUNT(*) FROM meta.batch_job_runs WHERE status = 'running')
        )
    ) AS components
FROM (
    SELECT
        COUNT(*) AS total_count,
        COUNT(*) FILTER (WHERE c.health_status = 'healthy') AS healthy_count,
        COUNT(*) FILTER (WHERE c.health_status = 'stale') AS stale_count,
        COUNT(*) FILTER (WHERE c.health_status = 'unhealthy' OR c.health_status IS NULL) AS unhealthy_count
    FROM api.catalog c
) health_summary;

COMMENT ON VIEW api.health IS 'System health check with catalog and job status';

-- ============================================================================
-- T051: Restricted views for anonymous access
-- Anonymous users see limited data; authenticated users see full data
-- ============================================================================

-- Restricted catalog view for anonymous users (no column_descriptions, limited fields)
CREATE OR REPLACE VIEW api.catalog_public AS
SELECT
    ds.source_name,
    ds.source_type,
    ds.description,
    ds.topic_tags,
    ds.refresh_frequency,
    ds.last_successful_refresh,
    ds.record_count,
    th.health_status,
    th.freshness_hours,
    CASE
        WHEN th.health_status = 'healthy' THEN 'green'
        WHEN th.health_status = 'stale' THEN 'yellow'
        ELSE 'red'
    END AS status_color
FROM meta.data_sources ds
LEFT JOIN LATERAL (
    SELECT *
    FROM meta.table_health
    WHERE source_id = ds.source_id
    ORDER BY check_timestamp DESC
    LIMIT 1
) th ON TRUE
WHERE ds.is_active = TRUE;

COMMENT ON VIEW api.catalog_public IS 'Public catalog view with limited fields for anonymous access';

-- Restricted targets view for anonymous users (no scoring details)
CREATE OR REPLACE VIEW api.targets_public AS
SELECT
    h.hospital_id,
    h.hospital_name,
    h.health_system_name,
    h.state,
    h.city,
    s.tier_classification,
    s.score_date
FROM mart.dim_hospital h
JOIN scoring.target_scores s ON h.hospital_key = s.hospital_key
WHERE h.is_current = TRUE
  AND s.score_date = (
      SELECT MAX(score_date)
      FROM scoring.target_scores
      WHERE hospital_key = s.hospital_key
  );

COMMENT ON VIEW api.targets_public IS 'Public targets view without detailed scores for anonymous access';

-- ============================================================================
-- T016: Grant SELECT permissions on new API views
-- ============================================================================

-- Grant to anonymous role (web_anon) - public views only
GRANT SELECT ON api.catalog_public TO web_anon;
GRANT SELECT ON api.targets_public TO web_anon;
GRANT SELECT ON api.health TO web_anon;

-- Note: Full catalog/jobs/job_runs views are restricted to authenticated users

-- Create api_user role if not exists and grant permissions
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_user') THEN
        CREATE ROLE api_user NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA api TO api_user;
GRANT SELECT ON api.catalog TO api_user;
GRANT SELECT ON api.catalog_public TO api_user;
GRANT SELECT ON api.jobs TO api_user;
GRANT SELECT ON api.job_runs TO api_user;
GRANT SELECT ON api.health TO api_user;
GRANT SELECT ON api.targets_public TO api_user;

-- Grant to analyst role (full access to all views)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA api TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO analyst;

-- Verify views were created
DO $$
DECLARE
    view_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO view_count
    FROM information_schema.views
    WHERE table_schema = 'api'
      AND table_name IN ('catalog', 'catalog_public', 'jobs', 'job_runs', 'health', 'targets_public');

    IF view_count >= 4 THEN
        RAISE NOTICE 'SUCCESS: API views created (catalog, catalog_public, jobs, job_runs, health, targets_public)';
    ELSE
        RAISE WARNING 'WARNING: Expected 6 views, found %', view_count;
    END IF;
END $$;
