-- Migration: 218_drop_web_anon_rollback
-- Feature: 002-external-integration-foundation (US-2, T078)
-- Purpose: Emergency rollback for migration 218_drop_web_anon.sql.
--
-- CRITICAL POLICY (F-D014): This rollback restores ONLY the minimum
-- grants needed to unblock a production failure. It does NOT restore
-- the full legacy grant set from migrations 086, 092, 117, 136, 043,
-- 055, or 061. Restoring the broad legacy grants would re-open every
-- hole migration 218 closed — the whole point of this rollback is to
-- be a smallest-possible revert, not a full undo of the security
-- improvement.
--
-- Minimum restoration:
--   - Role `web_anon` is re-created (NOLOGIN)
--   - USAGE granted on schema `api`
--   - SELECT granted on `api.health`   (for potential health probes)
--   - SELECT granted on `api.data_catalog` (for discovery / debugging)
--   - `web_anon` is re-granted to `authenticator` so PostgREST can
--     fall back to it when `PGRST_DB_ANON_ROLE` is restored
--   - Nothing else.
--
-- If the minimum rollback is insufficient to unblock whatever consumer
-- is failing, the correct next step is FORWARD-FIX: provision the
-- missing consumer API key in the metering proxy (not restore more
-- grants here).
--
-- k8s steps to complete the rollback (see docs/runbooks/rollback-web-anon-drop.md):
--   1. kubectl -n dk-data-prod edit configmap postgrest-config
--      Set: PGRST_DB_ANON_ROLE: "web_anon"
--   2. kubectl -n dk-data-prod rollout restart deployment/postgrest
--   3. curl https://data.behaviorlabs.ai/health → expect 200
--
-- Total rollback time target: ≤ 5 minutes (SC-020).
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/218_drop_web_anon_rollback.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
    -- 1. Re-create the role if it's gone.
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        CREATE ROLE web_anon NOLOGIN;
        RAISE NOTICE 'recreated web_anon role (NOLOGIN)';
    ELSE
        RAISE NOTICE 'web_anon role already exists — skipping CREATE ROLE';
    END IF;

    -- 2. Re-grant to authenticator so PostgREST can impersonate it.
    BEGIN
        GRANT web_anon TO authenticator;
        RAISE NOTICE 'granted web_anon to authenticator';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'could not grant web_anon to authenticator: % / %',
            SQLSTATE, SQLERRM;
    END;

    -- 3. Minimum grants only: USAGE on api, SELECT on health + data_catalog.
    --    NOTHING ELSE. Broader grants re-open the holes migration 218 closed.
    GRANT USAGE ON SCHEMA api TO web_anon;

    -- SELECT on api.health (if it exists — may be a view, may not be present)
    BEGIN
        GRANT SELECT ON api.health TO web_anon;
        RAISE NOTICE 'granted SELECT on api.health to web_anon';
    EXCEPTION WHEN undefined_table THEN
        RAISE NOTICE 'api.health does not exist — skipping';
    WHEN OTHERS THEN
        RAISE NOTICE 'could not grant SELECT on api.health: % / %',
            SQLSTATE, SQLERRM;
    END;

    -- SELECT on api.data_catalog
    BEGIN
        GRANT SELECT ON api.data_catalog TO web_anon;
        RAISE NOTICE 'granted SELECT on api.data_catalog to web_anon';
    EXCEPTION WHEN undefined_table THEN
        RAISE NOTICE 'api.data_catalog does not exist — skipping';
    WHEN OTHERS THEN
        RAISE NOTICE 'could not grant SELECT on api.data_catalog: % / %',
            SQLSTATE, SQLERRM;
    END;

    RAISE NOTICE '218_drop_web_anon_rollback complete: MINIMUM grants restored';
    RAISE NOTICE 'NEXT STEPS: restore PGRST_DB_ANON_ROLE="web_anon" in k8s configmap and roll PostgREST';
    RAISE NOTICE 'If this minimum is insufficient, do NOT broaden grants here — forward-fix by provisioning the missing consumer API key in the metering proxy';
END $$;

COMMIT;
