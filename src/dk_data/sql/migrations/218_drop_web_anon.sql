-- Migration: 218_drop_web_anon
-- Feature: 002-external-integration-foundation (US-2, T077)
-- Purpose: Drop the legacy `web_anon` PostgreSQL role entirely.
--
-- Context: `web_anon` was the anonymous read role for PostgREST. It had
-- been granted USAGE + SELECT on a broad set of schemas — all of `api`,
-- all of `hcs_silver`/`hcs_gold`, `hcs_agents`/`mol_agents`/`agents`,
-- selected `hcs_raw` CMS PUF tables, every silver hub table across
-- mol/hcs/ind/hcp/ip, three materialized `api.*` views, and all 10 CI
-- publication views from migration 061. Any request to PostgREST without
-- a JWT was falling back to `web_anon` and reading all of the above
-- anonymously.
--
-- This migration revokes every grant held by `web_anon` across every
-- schema, detaches the role from the `authenticator` role chain so
-- PostgREST cannot impersonate it, and drops the role. After this
-- migration runs AND `PGRST_DB_ANON_ROLE` is unset in the k8s configmap,
-- every PostgREST request without a valid JWT returns 401.
--
-- Prerequisites (MUST be done before this migration runs):
--   1. Metering proxy API keys are provisioned for every active consumer
--      (T019). Without this, every consumer hits 401 the moment this
--      migration commits.
--   2. The FastAPI /data-platform router has `require_auth` applied at
--      the router level (T027). Already done.
--   3. Every consuming app has been migrated to present a valid JWT for
--      every dk-data read. (Tracked in each consumer app's own spec.)
--   4. A staging apply of this migration has been verified (T089).
--   5. A rollback procedure is documented and tested
--      (218_drop_web_anon_rollback.sql + docs/runbooks/rollback-web-anon-drop.md).
--   6. Any running sessions authenticated as web_anon have been
--      terminated via pg_terminate_backend (T088c).
--
-- k8s config change MUST happen alongside this migration:
--   k8s/apps/postgrest/base/configmap.yaml — remove or comment out
--   `PGRST_DB_ANON_ROLE: "web_anon"`. PostgREST must be rolled to pick
--   up the new config.
--
-- Rollback: 218_drop_web_anon_rollback.sql restores only the MINIMUM
-- grants needed to unblock (USAGE on api + SELECT on api.health +
-- SELECT on api.data_catalog). It does NOT restore the full legacy grant
-- set, because doing so re-opens every hole this migration closed.
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/218_drop_web_anon.sql

BEGIN;

SET LOCAL statement_timeout = '120s';  -- REVOKE ALL IN SCHEMA can be slow
SET LOCAL lock_timeout = '30s';

-- -----------------------------------------------------------------------------
-- 0. Bail out gracefully if the role is already gone.
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        RAISE NOTICE 'web_anon role does not exist — nothing to drop';
        RETURN;
    END IF;

    -- ---------------------------------------------------------------------
    -- 1. Revoke every grant held by web_anon across every schema.
    --
    -- Using information_schema.role_table_grants to find every schema
    -- web_anon currently has ANY grant on, then revoking schema-wide.
    -- This is more robust than hard-coding the schema list because:
    --   (a) it catches schemas added by migrations that post-date the
    --       brief's audit (e.g., hcs_raw PUF tables from migration 092),
    --   (b) it survives the schema list changing in the future before
    --       this migration actually runs.
    -- ---------------------------------------------------------------------
    DECLARE
        schema_name TEXT;
        schemas_touched INT := 0;
    BEGIN
        FOR schema_name IN
            SELECT DISTINCT table_schema
            FROM information_schema.role_table_grants
            WHERE grantee = 'web_anon'
            ORDER BY table_schema
        LOOP
            BEGIN
                EXECUTE format(
                    'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM web_anon',
                    schema_name
                );
                EXECUTE format(
                    'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM web_anon',
                    schema_name
                );
                EXECUTE format(
                    'REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA %I FROM web_anon',
                    schema_name
                );
                EXECUTE format(
                    'REVOKE USAGE ON SCHEMA %I FROM web_anon',
                    schema_name
                );
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM web_anon',
                    schema_name
                );
                schemas_touched := schemas_touched + 1;
                RAISE NOTICE 'revoked web_anon grants in schema %', schema_name;
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'could not revoke in schema % — % / %',
                    schema_name, SQLSTATE, SQLERRM;
            END;
        END LOOP;
        RAISE NOTICE 'processed % schemas', schemas_touched;
    END;

    -- ---------------------------------------------------------------------
    -- 2. Detach web_anon from the authenticator role chain so PostgREST
    --    cannot impersonate it even if the configmap still references it
    --    by name for any period before the rollout completes.
    -- ---------------------------------------------------------------------
    BEGIN
        REVOKE web_anon FROM authenticator;
        RAISE NOTICE 'revoked web_anon membership from authenticator';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'web_anon was not a member of authenticator: % / %',
            SQLSTATE, SQLERRM;
    END;

    -- ---------------------------------------------------------------------
    -- 3. Drop the role. Any remaining grants on objects owned by
    --    web_anon are caught by DROP ROLE itself (which errors if the
    --    role still has any dependencies). The schema-wide revokes above
    --    should have cleared everything, so this is the acid test.
    -- ---------------------------------------------------------------------
    DROP ROLE web_anon;
    RAISE NOTICE 'web_anon dropped successfully';
END $$;

-- -----------------------------------------------------------------------------
-- COMPLETION
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    RAISE NOTICE '218_drop_web_anon complete: all PostgREST requests now require a valid JWT';
    RAISE NOTICE 'NEXT STEPS:';
    RAISE NOTICE '  1. Unset PGRST_DB_ANON_ROLE in k8s/apps/postgrest/base/configmap.yaml';
    RAISE NOTICE '  2. Roll PostgREST deployment to pick up the config change';
    RAISE NOTICE '  3. Verify: curl https://data.behaviorlabs.ai/molecules returns 401';
    RAISE NOTICE '  4. Verify: curl https://data.behaviorlabs.ai/health returns 401 too (no carve-out)';
END
$$;

COMMIT;
