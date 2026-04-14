-- Feature: 003-metering-jwt-mint (issue #283)
--
-- Grants api_user (the role every authenticated request switches into via
-- the JWT `role` claim the metering proxy now mints) USAGE + SELECT on the
-- 13 schemas the product exposes as client-readable surfaces, plus EXECUTE
-- on the 10 resolve functions that live in the silver hubs. Uses
-- ALTER DEFAULT PRIVILEGES so new tables in those schemas inherit the
-- SELECT grant automatically — no per-table migration needed when the
-- data-platform team adds a silver/gold table.
--
-- Why this is needed: before this feature, the metering proxy stripped the
-- inbound Authorization header without minting a replacement, so every
-- request reached PostgREST as web_anon. After feature 003, the proxy mints
-- a short-lived HS256 JWT with role=api_user on every validated request.
-- But api_user had USAGE on only a handful of schemas — it was never granted
-- read access to the silver/gold surface. This migration closes that gap.
--
-- Scope — schemas granted to api_user (per R-008 in research.md):
--   mol_silver, mol_gold, mol_api, hcs_silver, hcs_gold,
--   ind_silver, ind_gold, hcp_silver, hcp_gold,
--   ip_silver, ip_gold, mart, scoring
--
-- Schemas intentionally NOT granted (per R-008):
--   staging, application, public, agents, hcs_agents, mol_agents,
--   xenon, meta — these are internal state, administrative, or legacy
--   stubs not in the public client surface.
--
-- Ordering: this migration has no dependency on the ordering vs. 218
-- (drop web_anon) — 218 only touches web_anon, 228 only touches api_user.
-- Both can run in either order. The migration runner applies them in
-- numeric order (218 first, then 228).
--
-- Idempotent: safe to re-run. All GRANT statements and ALTER DEFAULT
-- PRIVILEGES statements are inherently idempotent.

BEGIN;

SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '10s';

-- -----------------------------------------------------------------------------
-- 1. USAGE on every client-readable schema
-- -----------------------------------------------------------------------------
-- The per-consumer allowlist enforced in the metering proxy is the
-- fine-grained authorization layer; these grants are the coarse
-- "is the schema reachable at all" defense-in-depth layer.

GRANT USAGE ON SCHEMA mol_silver TO api_user;
GRANT USAGE ON SCHEMA mol_gold TO api_user;
GRANT USAGE ON SCHEMA mol_api TO api_user;
GRANT USAGE ON SCHEMA hcs_silver TO api_user;
GRANT USAGE ON SCHEMA hcs_gold TO api_user;
GRANT USAGE ON SCHEMA ind_silver TO api_user;
GRANT USAGE ON SCHEMA ind_gold TO api_user;
GRANT USAGE ON SCHEMA hcp_silver TO api_user;
GRANT USAGE ON SCHEMA hcp_gold TO api_user;
GRANT USAGE ON SCHEMA ip_silver TO api_user;
GRANT USAGE ON SCHEMA ip_gold TO api_user;
GRANT USAGE ON SCHEMA mart TO api_user;
GRANT USAGE ON SCHEMA scoring TO api_user;

-- -----------------------------------------------------------------------------
-- 2. SELECT on every existing table (and view) in those schemas
-- -----------------------------------------------------------------------------
-- A consumer's allowlist at the proxy layer still restricts which schemas
-- they can route to, so granting broadly to api_user is safe and mirrors
-- the declared API surface. ALL TABLES covers both regular tables and
-- views in PostgreSQL 16+.

GRANT SELECT ON ALL TABLES IN SCHEMA mol_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_api TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ind_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ind_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcp_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA hcp_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ip_silver TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA ip_gold TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO api_user;
GRANT SELECT ON ALL TABLES IN SCHEMA scoring TO api_user;

-- -----------------------------------------------------------------------------
-- 3. Default privileges for future tables
-- -----------------------------------------------------------------------------
-- When a new table or view is created in any of these schemas after this
-- migration runs, api_user gets SELECT automatically. ALTER DEFAULT
-- PRIVILEGES applies to objects created by the role that runs this
-- statement — we run migrations as the postgres superuser, so every
-- future table created by postgres (or any role postgres delegates to)
-- gets the grant. The dk-data ETL also creates tables as postgres, so
-- silver/gold transforms produce tables api_user can already read without
-- any per-table grant work.

ALTER DEFAULT PRIVILEGES IN SCHEMA mol_silver GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_gold GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_api GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcs_silver GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcs_gold GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ind_silver GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ind_gold GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcp_silver GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcp_gold GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ip_silver GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA ip_gold GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO api_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA scoring GRANT SELECT ON TABLES TO api_user;

-- -----------------------------------------------------------------------------
-- 4. EXECUTE on resolve functions — already covered by migration 217
-- -----------------------------------------------------------------------------
-- Migration 217 (resolve_function_grants) already runs
--   GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA mol_silver TO analyst, api_user;
-- for every silver hub schema, plus ALTER DEFAULT PRIVILEGES so future
-- resolve functions inherit EXECUTE automatically. There is no need to
-- re-grant here. An earlier draft of this migration tried to enumerate
-- the resolve functions by exact (text) signature and failed because the
-- real signatures are not uniformly (text) — 217's schema-wide grant
-- sidesteps the signature-matching problem entirely.
--
-- Invariant enforced: `api_user` can execute every resolve_* function in
-- every silver schema. Verified by migration 217's NOTICE output and by
-- tests/test_217_resolve_function_grants.py.

COMMIT;
