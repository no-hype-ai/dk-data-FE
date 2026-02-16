-- Migration 070: Add retention_days column to meta.data_sources
-- Feature: 013-observability-governance (US5: Data Classification + Retention)
-- Tasks: T022
-- Purpose: Add optional retention_days column to data_sources for per-source retention override
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/070_retention_column.sql

DO $$
BEGIN
    ALTER TABLE meta.data_sources ADD COLUMN IF NOT EXISTS retention_days INTEGER DEFAULT NULL;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'meta.data_sources does not exist yet — skipping retention_days column';
END
$$;

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Retention column migration complete (070_retention_column.sql)';
    RAISE NOTICE 'Column: meta.data_sources.retention_days (INTEGER, NULL = perpetual)';
END
$$;
