-- Migration: 226_pg_stat_statements
-- Feature: 002-external-integration-foundation (k8s/db audit)
-- Purpose: Enable the `pg_stat_statements` extension so we can see
--          actual production query latencies. Migration 172's
--          comment explicitly admits the application-level
--          `meta.transform_runs` table is "the application-side
--          substitute for pg_stat_statements (which is not
--          available)" — making it available now.
--
-- ## What pg_stat_statements gives us
--
-- A view (`public.pg_stat_statements`) that records, for every
-- normalized query the database has seen since the last reset:
--   - calls               — total invocations
--   - total_exec_time     — cumulative wall clock (ms)
--   - mean_exec_time      — average per call (ms)
--   - rows                — total rows returned
--   - shared_blks_hit     — buffer cache hits
--   - shared_blks_read    — disk reads
--   - wal_bytes           — WAL generated
--   - + 30 more columns
--
-- This is the canonical answer to "which query is slow", "which
-- query is generating WAL", "which query cache-misses". Without
-- it, finding the culprit of a cluster slowdown is guesswork.
--
-- ## ⚠️ Cluster-side requirement
--
-- The extension's data collection requires the C library to be
-- loaded at PostgreSQL startup. That means the CNPG cluster spec
-- in the infrastructure repo MUST include:
--
--     postgresql:
--       parameters:
--         shared_preload_libraries: pg_stat_statements
--         pg_stat_statements.track: all
--         pg_stat_statements.max: 5000
--
-- WITHOUT that change in the infra repo, this migration creates
-- the extension successfully but the view stays empty — there's
-- no harm but no benefit either. File a ticket to the infra team
-- referencing this migration before applying.
--
-- See docs/runbooks/postgres-tuning.md for the full list of
-- shared_preload_libraries and parameters dk-data depends on.
--
-- ## Idempotent / safe
--
-- - `CREATE EXTENSION IF NOT EXISTS` is a no-op on re-run.
-- - Read-only extension; no data migration.
-- - `GRANT SELECT` is idempotent.
-- - Wrapped in BEGIN/COMMIT (extension creation is fully
--   transactional — unlike CREATE INDEX CONCURRENTLY).
--
-- Run: psql ... -f migrations/226_pg_stat_statements.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

-- Create the extension. If shared_preload_libraries doesn't
-- include it, this call still SUCCEEDS but the view returns no
-- rows. The infra repo coordination is what unlocks the data.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Grant SELECT on the view to the dk-data analyst + api_user
-- roles so dashboards can scrape it without superuser. The view
-- is read-only and contains query text that can leak schema
-- info, so we DON'T grant it to web_anon (which is dropped
-- anyway by migration 218).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.views
        WHERE table_schema = 'public' AND table_name = 'pg_stat_statements'
    ) THEN
        EXECUTE 'GRANT SELECT ON public.pg_stat_statements TO analyst, api_user';
        RAISE NOTICE 'pg_stat_statements view present and granted';
    ELSE
        RAISE NOTICE 'pg_stat_statements view not yet present — extension created '
                     'but cluster needs shared_preload_libraries=pg_stat_statements '
                     'in postgresql.conf for the view to populate';
    END IF;
END $$;

-- Helper view: top 20 slowest queries by total_exec_time. Lives
-- in `meta` so it's discoverable alongside the rest of the
-- observability tables.
CREATE OR REPLACE VIEW meta.top_slow_queries AS
SELECT
    LEFT(query, 200) AS query_preview,
    calls,
    ROUND(total_exec_time::numeric, 1) AS total_ms,
    ROUND(mean_exec_time::numeric, 2) AS mean_ms,
    ROUND((total_exec_time / NULLIF(calls, 0))::numeric, 2) AS avg_ms,
    rows,
    shared_blks_hit + shared_blks_read AS blocks_touched,
    wal_bytes
FROM public.pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

GRANT SELECT ON meta.top_slow_queries TO analyst, api_user;

DO $$
BEGIN
    RAISE NOTICE '226_pg_stat_statements complete';
    RAISE NOTICE 'Next: confirm shared_preload_libraries=pg_stat_statements in CNPG cluster spec';
    RAISE NOTICE 'Query: SELECT * FROM meta.top_slow_queries;';
END
$$;

COMMIT;
