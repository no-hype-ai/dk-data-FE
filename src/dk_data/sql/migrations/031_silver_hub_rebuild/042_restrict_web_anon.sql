-- Migration 031/042: Restrict web_anon access to api schema only
-- Feature: 001-silver-medallion-rebuild / T181

DO $$
DECLARE
    schema_name TEXT;
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        RAISE NOTICE 'web_anon role does not exist — skipping';
        RETURN;
    END IF;

    -- Revoke from non-api schemas
    FOR schema_name IN
        SELECT nspname FROM pg_namespace
        WHERE nspname NOT IN ('api', 'pg_catalog', 'information_schema', 'pg_toast')
          AND nspname NOT LIKE 'pg_%'
    LOOP
        EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM web_anon', schema_name);
        EXECUTE format('REVOKE USAGE ON SCHEMA %I FROM web_anon', schema_name);
    END LOOP;

    -- Grant api schema access
    EXECUTE 'CREATE SCHEMA IF NOT EXISTS api';
    EXECUTE 'GRANT USAGE ON SCHEMA api TO web_anon';
    EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA api TO web_anon';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO web_anon';
END $$;
