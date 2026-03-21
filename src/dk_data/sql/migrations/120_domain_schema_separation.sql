-- Migration: 120_domain_schema_separation.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Create domain-separated schemas for indication and HCP data.
--
-- Convention (schema IS the domain prefix, no prefix on table names):
--   mol_silver / mol_gold  — molecule data
--   ind_silver / ind_gold  — indication/disease data
--   hcp_silver / hcp_gold  — HCP/researcher data
--   hcs_silver / hcs_gold  — healthcare system (CMS) data (already exists)
--   xenon                  — xenon application data

-- ─── Create new domain schemas ──────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS ind_silver;
CREATE SCHEMA IF NOT EXISTS ind_gold;
CREATE SCHEMA IF NOT EXISTS hcp_silver;
CREATE SCHEMA IF NOT EXISTS hcp_gold;

-- ─── Grants: authenticator + analyst roles ──────────────────────────────────

DO $$
DECLARE
    v_schema TEXT;
BEGIN
    FOREACH v_schema IN ARRAY ARRAY[
        'ind_silver', 'ind_gold',
        'hcp_silver', 'hcp_gold'
    ] LOOP
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO authenticator', v_schema);
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO analyst', v_schema);
        EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO analyst', v_schema);
        -- Default privileges for future tables
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO analyst', v_schema);
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO web_anon', v_schema);
    END LOOP;
END $$;

-- ─── Also ensure web_anon can read all domain schemas ───────────────────────

DO $$
DECLARE
    v_schema TEXT;
BEGIN
    FOREACH v_schema IN ARRAY ARRAY[
        'mol_silver', 'mol_gold', 'mol_bronze', 'mol_raw',
        'ind_silver', 'ind_gold',
        'hcp_silver', 'hcp_gold',
        'hcs_silver', 'hcs_gold',
        'xenon', 'meta'
    ] LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = v_schema) THEN
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO web_anon', v_schema);
            EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO web_anon', v_schema);
        END IF;
    END LOOP;
END $$;

-- ─── PostgREST PGRST_DB_SCHEMAS must be updated to include: ────────────────
-- "api,mol_silver,mol_gold,mol_bronze,mol_raw,ind_silver,ind_gold,hcp_silver,hcp_gold,hcs_silver,hcs_gold,ops,xenon,meta"
