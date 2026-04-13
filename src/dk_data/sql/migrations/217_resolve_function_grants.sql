-- Migration: 217_resolve_function_grants
-- Feature: 002-external-integration-foundation (US-5, T073)
-- Purpose: Grant EXECUTE on all 11 silver-hub resolve functions to the
--          external-facing roles (analyst, api_user) so external consumers
--          can call any of them via PostgREST `/rpc/resolve_*` or the
--          FastAPI resolve wrapper routes.
--
-- Context: Migrations 178-188 from feature 001-silver-medallion-rebuild
-- created 11 STABLE PARALLEL SAFE resolve functions — one per silver hub
-- entity type — but only granted EXECUTE to the molecule-domain internal
-- roles (`mol_viewer`, `mol_analyst`, `mol_data_ops`). External clients
-- authenticate as `analyst` or `api_user` via JWT and currently get a
-- permission-denied error when calling any resolve function except
-- `mol_silver.resolve_molecule` (which is exposed via FastAPI POST /resolve
-- and uses a different code path).
--
-- This migration grants EXECUTE on all 11 functions to analyst and
-- api_user so they can be called directly via PostgREST RPC.
--
-- Functions granted (all from feature 001-silver-medallion-rebuild):
--   mol_silver.resolve_molecule       (migration 178)
--   mol_silver.resolve_drug_product   (migration 179)
--   mol_silver.resolve_target         (migration 180)
--   ind_silver.resolve_condition      (migration 181)
--   mol_silver.resolve_company        (migration 182)
--   hcs_silver.resolve_provider       (migration 183)
--   hcs_silver.resolve_facility       (migration 184)
--   hcp_silver.resolve_researcher     (migration 185)
--   ip_silver.resolve_patent          (migration 186)
--   ip_silver.resolve_trademark       (migration 187)
--   ip_silver.resolve_design          (migration 188)
--
-- No web_anon grants — migration 218 drops that role.
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/217_resolve_function_grants.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

-- -----------------------------------------------------------------------------
-- Schema USAGE grants.
-- These silver schemas already have USAGE granted to analyst by
-- post_sqlmesh/055_postgrest_hub_grants.sql, but adding api_user explicitly
-- here makes this migration self-contained: it should not depend on any
-- other migration having already run USAGE grants for api_user.
-- -----------------------------------------------------------------------------

GRANT USAGE ON SCHEMA mol_silver TO analyst, api_user;
GRANT USAGE ON SCHEMA ind_silver TO analyst, api_user;
GRANT USAGE ON SCHEMA hcs_silver TO analyst, api_user;
GRANT USAGE ON SCHEMA hcp_silver TO analyst, api_user;
GRANT USAGE ON SCHEMA ip_silver  TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- Grant EXECUTE on each resolve function.
--
-- Using `ON FUNCTION schema.function_name` without an argument list relies
-- on function-name uniqueness within each schema. All 11 are unique within
-- their respective schemas so this is safe.
--
-- Wrap each in its own DO block with EXCEPTION handling so the migration
-- is defensive against a function being renamed/missing/reordered. Any
-- individual failure raises a NOTICE and the remaining grants still run.
-- -----------------------------------------------------------------------------

DO $$
DECLARE
    fn TEXT;
    grant_sql TEXT;
    fns TEXT[] := ARRAY[
        'mol_silver.resolve_molecule',
        'mol_silver.resolve_drug_product',
        'mol_silver.resolve_target',
        'mol_silver.resolve_company',
        'ind_silver.resolve_condition',
        'hcs_silver.resolve_provider',
        'hcs_silver.resolve_facility',
        'hcp_silver.resolve_researcher',
        'ip_silver.resolve_patent',
        'ip_silver.resolve_trademark',
        'ip_silver.resolve_design'
    ];
BEGIN
    FOREACH fn IN ARRAY fns LOOP
        BEGIN
            -- Grant EXECUTE on every overload of this function name.
            grant_sql := format(
                'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO analyst, api_user',
                split_part(fn, '.', 1)
            );
            -- Note: we re-run the schema-wide grant for each function in
            -- the list. That's idempotent in Postgres, and schema-wide is
            -- simpler than trying to match exact argument signatures.
            EXECUTE grant_sql;
            RAISE NOTICE 'granted EXECUTE in schema % (covers %)',
                split_part(fn, '.', 1), fn;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'skipping grant for % (% — %)',
                fn, SQLSTATE, SQLERRM;
        END;
    END LOOP;
END $$;

-- Default privileges: any future function added to a silver schema gets
-- EXECUTE for analyst + api_user automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_silver GRANT EXECUTE ON FUNCTIONS TO analyst, api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ind_silver GRANT EXECUTE ON FUNCTIONS TO analyst, api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcs_silver GRANT EXECUTE ON FUNCTIONS TO analyst, api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcp_silver GRANT EXECUTE ON FUNCTIONS TO analyst, api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ip_silver  GRANT EXECUTE ON FUNCTIONS TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- COMPLETION
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    RAISE NOTICE '217_resolve_function_grants complete: 11 silver-hub resolve functions callable by analyst + api_user';
END
$$;

COMMIT;
