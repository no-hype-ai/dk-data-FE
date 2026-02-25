-- Migration: 076_analyst_grants
-- Feature: 015-assessment-dashboard-integration
-- Purpose: Grant analyst role access to mol_gold, mol_silver, xenon, meta schemas
-- Date: 2026-02-25
-- Constraint 7: Use existing analyst role (already granted to authenticator)

BEGIN;

-- =============================================================================
-- STEP 1: Schema USAGE grants — analyst can see objects in these schemas
-- =============================================================================

GRANT USAGE ON SCHEMA mol_gold TO analyst;
GRANT USAGE ON SCHEMA mol_silver TO analyst;
GRANT USAGE ON SCHEMA xenon TO analyst;
GRANT USAGE ON SCHEMA meta TO analyst;

-- =============================================================================
-- STEP 2: Read access — analyst can SELECT from all tables
-- =============================================================================

GRANT SELECT ON ALL TABLES IN SCHEMA mol_gold TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_silver TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA meta TO analyst;

-- =============================================================================
-- STEP 3: Read+write access — analyst can SELECT, INSERT, UPDATE on xenon
-- xenon stores application-written data (assessment content, publication evidence)
-- =============================================================================

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA xenon TO analyst;

-- =============================================================================
-- STEP 4: Default privileges for future tables
-- Ensures tables created after this migration inherit the same grants
-- =============================================================================

ALTER DEFAULT PRIVILEGES IN SCHEMA mol_gold GRANT SELECT ON TABLES TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_silver GRANT SELECT ON TABLES TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA xenon GRANT SELECT, INSERT, UPDATE ON TABLES TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta GRANT SELECT ON TABLES TO analyst;

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 076_analyst_grants complete.';
    RAISE NOTICE 'Granted analyst: SELECT on mol_gold/mol_silver/meta, SELECT+INSERT+UPDATE on xenon.';
END $$;
