-- Migration: 103_platform_tables_raw_to_meta
-- Purpose: Move platform operational/metadata tables from raw.* to meta.*.
--
-- The raw.* schema must contain ONLY raw API response data.
-- Platform tracking tables (job state, schedules, transformation config)
-- belong in meta.*, alongside meta.data_sources and meta.schema_migrations.
--
-- Tables moved:
--   raw.sync_schedules            → meta.sync_schedules
--   raw.ingestion_jobs            → meta.ingestion_jobs
--   raw.silver_transformation_rules → meta.silver_transformation_rules
--   raw.generated_sqlmesh_models  → meta.generated_sqlmesh_models
--   raw.source_identifier_patterns → meta.source_identifier_patterns
--   raw.transformation_templates  → meta.transformation_templates
--
-- Tables defined only in Python (not yet in DB, created with CREATE TABLE IF NOT EXISTS):
--   raw.pipeline_jobs             → meta.pipeline_jobs
--   raw.initial_load_state        → meta.initial_load_state
--   raw.transformation_config     → meta.transformation_config
--   raw.identifier_types          → meta.identifier_types
--   raw.source_config             → meta.source_config
--   raw.field_mappings            → meta.field_mappings
--   raw.api_responses             → meta.api_responses
--
-- After this migration all Python code must use meta.* for these tables.
-- Depends on: 036_sync_scheduler_tables.sql, 051_dynamic_transformation_config.sql

BEGIN;

-- Drop raw.* views that depend on the tables being moved (036/051 created these in raw.*).
-- Must drop before ALTER TABLE SET SCHEMA or the table move will fail if views exist.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema = 'raw' AND table_name = 'source_status') THEN
        EXECUTE 'DROP VIEW raw.source_status CASCADE';
        RAISE NOTICE 'Dropped raw.source_status (will be recreated in meta.*)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema = 'raw' AND table_name = 'ingestion_job_stats') THEN
        EXECUTE 'DROP VIEW raw.ingestion_job_stats CASCADE';
        RAISE NOTICE 'Dropped raw.ingestion_job_stats (will be recreated in meta.*)';
    END IF;
END $$;

-- Move tables that physically exist in raw.* → meta.*
-- Guard: only move if source exists and destination does not yet exist.

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'sync_schedules',
        'ingestion_jobs',
        'silver_transformation_rules',
        'generated_sqlmesh_models',
        'source_identifier_patterns',
        'transformation_templates'
    ]
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'raw' AND table_name = t
        ) THEN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'meta' AND table_name = t
            ) THEN
                -- Destination exists: drop the source (data already in meta)
                EXECUTE format('DROP TABLE raw.%I CASCADE', t);
                RAISE NOTICE 'Dropped raw.% (already in meta.%)', t, t;
            ELSE
                -- Destination does not exist: move via SET SCHEMA
                EXECUTE format('ALTER TABLE raw.%I SET SCHEMA meta', t);
                RAISE NOTICE 'Moved raw.% → meta.%', t, t;
            END IF;
        ELSE
            RAISE NOTICE 'raw.% does not exist, skipping', t;
        END IF;
    END LOOP;
END $$;

-- Recreate views in meta.* that 036 created in raw.* (sync_schedules + ingestion_jobs now in meta.*)
-- Safe to run even on fresh deployments where tables were created in meta.* directly by the fixed 036.
CREATE OR REPLACE VIEW meta.source_status AS
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
FROM meta.sync_schedules ss
LEFT JOIN LATERAL (
    SELECT status, completed_at, records_processed, error_message
    FROM meta.ingestion_jobs
    WHERE source = ss.source
    ORDER BY started_at DESC
    LIMIT 1
) latest ON TRUE;

CREATE OR REPLACE VIEW meta.ingestion_job_stats AS
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
FROM meta.ingestion_jobs
WHERE started_at >= NOW() - INTERVAL '30 days'
GROUP BY source;

-- Migrate audit trigger function from raw.* → meta.* (created by old 051 in raw.*)
-- On fresh deployments (fixed 051), the function is already in meta.* — CREATE OR REPLACE is idempotent.
CREATE OR REPLACE FUNCTION meta.update_transformation_rule_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Re-attach trigger to silver_transformation_rules now in meta.* (if it exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'meta' AND table_name = 'silver_transformation_rules') THEN
        EXECUTE 'DROP TRIGGER IF EXISTS trigger_update_transformation_rule ON meta.silver_transformation_rules';
        EXECUTE 'CREATE TRIGGER trigger_update_transformation_rule
            BEFORE UPDATE ON meta.silver_transformation_rules
            FOR EACH ROW EXECUTE FUNCTION meta.update_transformation_rule_timestamp()';
        RAISE NOTICE 'Recreated trigger on meta.silver_transformation_rules';
    END IF;
END $$;

-- Drop raw.update_transformation_rule_timestamp if it was left behind by old 051
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
               WHERE n.nspname = 'raw' AND p.proname = 'update_transformation_rule_timestamp') THEN
        EXECUTE 'DROP FUNCTION IF EXISTS raw.update_transformation_rule_timestamp() CASCADE';
        RAISE NOTICE 'Dropped raw.update_transformation_rule_timestamp';
    END IF;
END $$;

-- For Python-created tables that don't exist in raw.* yet, create them in meta.*
-- so that when Python code runs with the new schema name it can CREATE TABLE IF NOT EXISTS
-- and find it in meta.* immediately.

-- meta.pipeline_jobs
CREATE TABLE IF NOT EXISTS meta.pipeline_jobs (
    id              SERIAL PRIMARY KEY,
    job_id          VARCHAR(100) UNIQUE NOT NULL,
    job_type        VARCHAR(100),
    source          VARCHAR(100),
    status          VARCHAR(50)  NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meta_pipeline_jobs_status    ON meta.pipeline_jobs(status);
CREATE INDEX IF NOT EXISTS idx_meta_pipeline_jobs_type      ON meta.pipeline_jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_meta_pipeline_jobs_started   ON meta.pipeline_jobs(started_at DESC);

-- meta.initial_load_state
CREATE TABLE IF NOT EXISTS meta.initial_load_state (
    id              SERIAL PRIMARY KEY,
    run_id          VARCHAR(100) UNIQUE NOT NULL,
    state           JSONB        NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meta_initial_load_state_ts ON meta.initial_load_state(updated_at DESC);

-- meta.transformation_config
CREATE TABLE IF NOT EXISTS meta.transformation_config (
    id              SERIAL PRIMARY KEY,
    config_key      VARCHAR(255) UNIQUE NOT NULL,
    config_value    JSONB        NOT NULL DEFAULT '{}',
    description     TEXT,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- meta.identifier_types
CREATE TABLE IF NOT EXISTS meta.identifier_types (
    id              SERIAL PRIMARY KEY,
    type_name       VARCHAR(100) UNIQUE NOT NULL,
    domain          VARCHAR(50),
    description     TEXT,
    pattern         TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- meta.source_config
CREATE TABLE IF NOT EXISTS meta.source_config (
    id              SERIAL PRIMARY KEY,
    source_name     VARCHAR(255) UNIQUE NOT NULL,
    config          JSONB        NOT NULL DEFAULT '{}',
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meta_source_config_enabled ON meta.source_config(enabled);

-- meta.field_mappings
CREATE TABLE IF NOT EXISTS meta.field_mappings (
    id              SERIAL PRIMARY KEY,
    source_name     VARCHAR(255) NOT NULL,
    source_field    VARCHAR(255) NOT NULL,
    target_schema   VARCHAR(100),
    target_table    VARCHAR(255),
    target_field    VARCHAR(255),
    transform_expr  TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(source_name, source_field)
);
CREATE INDEX IF NOT EXISTS idx_meta_field_mappings_source ON meta.field_mappings(source_name);

-- meta.api_responses (general purpose API response tracking)
CREATE TABLE IF NOT EXISTS meta.api_responses (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR(255) NOT NULL,
    endpoint        TEXT,
    status_code     INTEGER,
    response_size   BIGINT,
    duration_ms     INTEGER,
    recorded_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meta_api_responses_source ON meta.api_responses(source);
CREATE INDEX IF NOT EXISTS idx_meta_api_responses_ts     ON meta.api_responses(recorded_at DESC);

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 103_platform_tables_raw_to_meta complete.';
    RAISE NOTICE 'Platform tables moved (existing DBs): sync_schedules, ingestion_jobs,';
    RAISE NOTICE '  silver_transformation_rules, generated_sqlmesh_models,';
    RAISE NOTICE '  source_identifier_patterns, transformation_templates';
    RAISE NOTICE 'Views recreated in meta.*: source_status, ingestion_job_stats';
    RAISE NOTICE 'Trigger function migrated to meta.*: update_transformation_rule_timestamp';
    RAISE NOTICE 'Platform tables created in meta.*: pipeline_jobs, initial_load_state,';
    RAISE NOTICE '  transformation_config, identifier_types, source_config,';
    RAISE NOTICE '  field_mappings, api_responses';
    RAISE NOTICE 'All Python code must now use meta.* for these tables.';
END $$;
