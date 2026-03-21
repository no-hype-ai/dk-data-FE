-- Migration: 121_drop_unprefixed_schemas.sql
-- Date: 2026-03-21
-- Feature: 016-cms-puf-datasource-integration
-- Description: Drop all non-prefixed legacy schemas now that all SQLMesh models
--              have been redirected to canonical prefixed schemas:
--                bronze.*    → mol_bronze.* (mol sources) + hcs_bronze.* (CMS sources)
--                raw.*       → mol_raw.* (all molecule sources now routed there)
--                silver.*    → mol_silver.* (deprecated since migration 031)
--                gold.*      → mol_gold.*   (deprecated since migration 032)
--
-- Data safety:
--   - mol_raw.* holds all canonical molecule raw data (response_body JSONB)
--   - mol_bronze.* is in sync with bronze.* via migration 112 sync pipe
--   - mol_silver.* / mol_gold.* are canonical; silver.* / gold.* are empty legacy shells
--   - hcs_raw.* receives all future CMS raw data (tool_registry.py fix applied)
--   - CMS data in raw.* is re-fetchable from public CMS APIs
--
-- After this migration: only prefixed schemas exist.
--

-- ============================================================================
-- 1. Drop bronze.* schema
--    All mol SQLMesh bronze models now write to mol_bronze.* directly.
--    All CMS SQLMesh bronze models now write to hcs_bronze.*.
--    Migration 112 sync pipe populated mol_bronze.* from bronze.* — data safe.
-- ============================================================================
DROP SCHEMA IF EXISTS bronze CASCADE;

-- ============================================================================
-- 2. Move operational state tables out of raw.* → ops.* before dropping
--    raw.transformation_config, raw.initial_load_state, raw.api_responses
--    are operational metadata tables misplaced in raw.*. Move them first.
-- ============================================================================
DO $$
BEGIN
    -- transformation_config
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='raw' AND table_name='transformation_config') THEN
        CREATE TABLE IF NOT EXISTS ops.transformation_config (LIKE raw.transformation_config INCLUDING ALL);
        INSERT INTO ops.transformation_config SELECT * FROM raw.transformation_config ON CONFLICT DO NOTHING;
    END IF;

    -- initial_load_state
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='raw' AND table_name='initial_load_state') THEN
        CREATE TABLE IF NOT EXISTS ops.initial_load_state (LIKE raw.initial_load_state INCLUDING ALL);
        INSERT INTO ops.initial_load_state SELECT * FROM raw.initial_load_state ON CONFLICT DO NOTHING;
    END IF;

    -- api_responses
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='raw' AND table_name='api_responses') THEN
        CREATE TABLE IF NOT EXISTS ops.api_responses (LIKE raw.api_responses INCLUDING ALL);
        INSERT INTO ops.api_responses SELECT * FROM raw.api_responses ON CONFLICT DO NOTHING;
    END IF;
END $$;

-- ============================================================================
-- 3. Drop raw.* schema
--    Molecule sources always wrote to mol_raw.* (MOL_RAW_SOURCES list).
--    CMS/HCP sources are re-fetchable from public APIs.
--    hcs_raw.* receives all future CMS raw data.
--    Operational tables already moved to ops.* above.
-- ============================================================================
DROP SCHEMA IF EXISTS raw CASCADE;

-- ============================================================================
-- 3. Drop silver.* schema
--    Deprecated since migration 031. mol_silver.* is canonical.
--    No active SQLMesh models or application code reads from silver.*.
-- ============================================================================
DROP SCHEMA IF EXISTS silver CASCADE;

-- ============================================================================
-- 4. Drop gold.* schema
--    Deprecated since migration 032. mol_gold.* is canonical.
--    silver_gold_refresher.py was already marked DEPRECATED.
-- ============================================================================
DROP SCHEMA IF EXISTS gold CASCADE;

-- ============================================================================
-- 5. Drop staging / mart / scoring (scaffolding schemas, never populated)
-- ============================================================================
DROP SCHEMA IF EXISTS staging CASCADE;
DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS scoring CASCADE;

-- ============================================================================
-- Verify: only prefixed schemas remain
-- Expected: mol_raw, mol_bronze, mol_silver, mol_gold,
--           hcs_raw, hcs_bronze, hcs_silver, hcs_gold,
--           ind_raw, ind_silver, ind_gold,
--           hcp_raw, hcp_silver, hcp_gold,
--           ops, meta, xenon, api
-- ============================================================================
DO $$
DECLARE
    unprefixed TEXT;
BEGIN
    SELECT string_agg(schema_name, ', ')
    INTO unprefixed
    FROM information_schema.schemata
    WHERE schema_name NOT IN (
        'pg_catalog', 'information_schema', 'public', 'pg_toast',
        -- canonical prefixed schemas
        'mol_raw', 'mol_bronze', 'mol_silver', 'mol_gold',
        'hcs_raw', 'hcs_bronze', 'hcs_silver', 'hcs_gold',
        'ind_raw', 'ind_silver', 'ind_gold',
        'hcp_raw', 'hcp_silver', 'hcp_gold',
        'ops', 'meta', 'xenon', 'api'
    );
    IF unprefixed IS NOT NULL THEN
        RAISE WARNING 'Unexpected schemas still present after migration: %', unprefixed;
    ELSE
        RAISE NOTICE 'Migration 121 complete — only prefixed schemas remain.';
    END IF;
END $$;
