-- Migration 031/042: Restrict web_anon access to api schema only
-- Feature: 001-silver-medallion-rebuild / T181
--
-- Revokes web_anon access from all non-api schemas and grants only:
--   USAGE ON SCHEMA api
--   SELECT ON ALL TABLES IN SCHEMA api
--
-- This ensures anonymous PostgREST requests cannot access raw/bronze/silver/gold
-- schemas directly — only the curated api.* views.

-- ----------------------------------------------------------------
-- Revoke from non-api schemas (defence-in-depth)
-- ----------------------------------------------------------------
DO $$
DECLARE
    schema_name TEXT;
BEGIN
    FOR schema_name IN
        SELECT nspname FROM pg_namespace
        WHERE nspname NOT IN ('api', 'pg_catalog', 'information_schema', 'pg_toast')
          AND nspname NOT LIKE 'pg_%'
    LOOP
        EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM web_anon', schema_name);
        EXECUTE format('REVOKE USAGE ON SCHEMA %I FROM web_anon', schema_name);
    END LOOP;
END;
$$;

-- ----------------------------------------------------------------
-- Grant api schema access
-- ----------------------------------------------------------------
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO web_anon;

-- Ensure future tables in api schema are accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO web_anon;
