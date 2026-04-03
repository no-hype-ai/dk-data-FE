-- =============================================================================
-- Migration 147: HCS 6-Source Raw Table Schema Reconciliation (idempotent)
-- Feature: 026-fetcher-checkpoint-resume
-- Date: 2026-04-03
-- =============================================================================
-- Context:
--   Two prior migrations created incompatible schemas for 6 hcs_raw tables:
--
--   Migration 075 (PR #205): Created 4 of the 6 tables with wrong schemas
--     (Home Health Compare columns instead of CMS PUF provider×service grain).
--
--   Migration 094 (manually applied to prod via kubectl exec on 2026-03-27):
--     Dropped and recreated all 6 tables with hand-crafted typed schemas using
--     underscore-prefixed metadata columns (_source_year, _source_hash, etc.).
--
--   fetch_cms_puf.py (the active DCAT-based loader for these tables) creates
--     tables dynamically from CSV headers with all-TEXT data columns plus:
--       source_year  INT                    (no underscore prefix)
--       created_at   TIMESTAMPTZ DEFAULT NOW()
--
--   This is incompatible with both prior schemas. If migration 094 schema is
--   present, _create_table_if_needed() skips creation (IF NOT EXISTS), then
--   COPY fails because the column is named _source_year, not source_year.
--
-- Strategy:
--   DROP any table that has a schema incompatible with fetch_cms_puf.py.
--   Do NOT recreate — fetch_cms_puf.py owns the DDL and will CREATE on first run.
--   Conditional grants are applied at the end for tables that already exist
--   (e.g. post-first-load re-runs of this migration are safe).
--
-- Sentinels:
--   cms_certification_number  → migration 075 schema → DROP
--   _source_year              → migration 094 schema → DROP
--   source_year               → fetch_cms_puf.py schema → leave alone
--   table absent              → leave alone (loader creates on first run)
-- =============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS hcs_raw;

-- ============================================================================
-- 1. cms_home_health
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_home_health'
          AND column_name  IN ('cms_certification_number', '_source_year')
    ) THEN
        RAISE NOTICE 'cms_home_health: incompatible schema detected, dropping (fetch_cms_puf.py will recreate on first run)';
        DROP TABLE hcs_raw.cms_home_health CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 2. cms_hospice_puf
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_hospice_puf'
          AND column_name  IN ('cms_certification_number', '_source_year')
    ) THEN
        RAISE NOTICE 'cms_hospice_puf: incompatible schema detected, dropping (fetch_cms_puf.py will recreate on first run)';
        DROP TABLE hcs_raw.cms_hospice_puf CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 3. cms_snf_puf
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_snf_puf'
          AND column_name  IN ('cms_certification_number', '_source_year')
    ) THEN
        RAISE NOTICE 'cms_snf_puf: incompatible schema detected, dropping (fetch_cms_puf.py will recreate on first run)';
        DROP TABLE hcs_raw.cms_snf_puf CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 4. cms_dme_puf
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_dme_puf'
          AND column_name  IN ('nppes_provider_last_org_name', '_source_year')
    ) THEN
        RAISE NOTICE 'cms_dme_puf: incompatible schema detected, dropping (fetch_cms_puf.py will recreate on first run)';
        DROP TABLE hcs_raw.cms_dme_puf CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 5. cms_lab_services
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_lab_services'
          AND column_name  = '_source_year'
    ) THEN
        RAISE NOTICE 'cms_lab_services: incompatible schema detected (migration 094), dropping';
        DROP TABLE hcs_raw.cms_lab_services CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 6. cms_imaging_puf
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_imaging_puf'
          AND column_name  = '_source_year'
    ) THEN
        RAISE NOTICE 'cms_imaging_puf: incompatible schema detected (migration 094), dropping';
        DROP TABLE hcs_raw.cms_imaging_puf CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 7. Conditional grants
--    Applied only when tables already exist (idempotent re-runs after first
--    load). fetch_cms_puf.py does not grant permissions after creating tables,
--    so this migration is the authoritative source of those grants.
-- ============================================================================
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'cms_home_health', 'cms_hospice_puf', 'cms_snf_puf',
        'cms_dme_puf', 'cms_lab_services', 'cms_imaging_puf'
    ] LOOP
        IF to_regclass('hcs_raw.' || t) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT ON hcs_raw.%I TO web_anon', t);
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
                EXECUTE format('GRANT SELECT ON hcs_raw.%I TO analyst', t);
            END IF;
        END IF;
    END LOOP;
END $$;

COMMIT;
