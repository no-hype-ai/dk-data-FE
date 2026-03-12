-- Migration 096: Revoke web_anon access from protected API views
--
-- web_anon should only have SELECT on api.health and api.data_catalog.
-- Earlier migrations (002, 077) revoked access, but subsequent schema
-- changes may have re-granted via DEFAULT PRIVILEGES or direct grants.
-- This migration ensures the restriction is enforced.

DO $$
DECLARE
    v_name TEXT;
    v_protected TEXT[] := ARRAY[
        'targets', 'scoring', 'data_sources',
        'recommendations'
    ];
BEGIN
    FOREACH v_name IN ARRAY v_protected LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'api' AND table_name = v_name
        ) THEN
            EXECUTE format('REVOKE SELECT ON api.%I FROM web_anon', v_name);
            RAISE NOTICE 'Revoked web_anon SELECT on api.%', v_name;
        END IF;
    END LOOP;
END $$;

-- Defensive: revoke from any gold/silver/bronze schema tables that web_anon shouldn't access
-- (only api.health and api.data_catalog should be public)
DO $$
DECLARE
    v_name TEXT;
BEGIN
    FOR v_name IN
        SELECT table_name FROM information_schema.table_privileges
        WHERE grantee = 'web_anon'
          AND table_schema = 'api'
          AND table_name NOT IN ('health', 'data_catalog')
    LOOP
        EXECUTE format('REVOKE SELECT ON api.%I FROM web_anon', v_name);
        RAISE NOTICE 'Revoked web_anon SELECT on api.%', v_name;
    END LOOP;
END $$;
