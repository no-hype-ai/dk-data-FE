-- Migration: 118_schema_prefix_enforcement.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Enforce consistent schema prefixes across all tables.
--
-- Convention:
--   mol_*  = molecule-specific data (linked by molecule_id UUID)
--   hcs_*  = healthcare system data (providers, facilities, geographic — by NPI/CCN/state)
--   ops    = operational infrastructure (jobs, schedules, migrations)
--   meta   = monitoring/quality (tables prefixed ops_)
--   xenon  = xenon app tables (prefixed xenon_)
--
-- This migration handles fresh deployments. For existing deployments,
-- the schema moves were already done via direct SQL.

-- ─── Create new schemas ────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS hcs_raw;
CREATE SCHEMA IF NOT EXISTS hcs_silver;
CREATE SCHEMA IF NOT EXISTS hcs_gold;
CREATE SCHEMA IF NOT EXISTS ops;

-- ─── Grants ────────────────────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA hcs_raw TO analyst;
GRANT USAGE ON SCHEMA hcs_silver TO analyst;
GRANT USAGE ON SCHEMA hcs_gold TO analyst;
GRANT USAGE ON SCHEMA ops TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_raw TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_gold TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA ops TO analyst;

-- ─── Update PostgREST schema list ─────────────────────────────────────────────
-- PostgREST PGRST_DB_SCHEMAS should be updated to:
-- "api,hcs_gold,hcs_silver,mol_raw,mol_gold,mol_silver,ops,xenon,meta"
-- Remove: raw, bronze, silver, gold (now empty or prefixed)

-- ─── Schema inventory (for verification) ──────────────────────────────────────
-- mol_raw:     53 tables  (molecule API responses)
-- mol_bronze:  41 tables  (molecule typed columns)
-- mol_silver:  45 tables  (molecule entity-linked)
-- mol_gold:    28 tables  (molecule aggregated)
-- hcs_raw:     52 tables  (CMS/healthcare raw data)
-- hcs_silver:  12 tables  (CMS/healthcare silver)
-- hcs_gold:    13 views   (CMS/healthcare gold)
-- ops:          8 tables  (infrastructure: sync_schedules, jobs, etc.)
-- meta:        12 tables  (monitoring: ops_table_health, ops_data_quality, etc.)
-- xenon:        2 tables  (app: xenon_assessment_generated, xenon_publication_evidence)
