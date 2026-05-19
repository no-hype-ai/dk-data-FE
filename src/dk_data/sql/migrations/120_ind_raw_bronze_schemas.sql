-- Migration: 120_ind_raw_bronze_schemas
-- Feature: 019-cms-puf-platform-reconciliation (indication bronze layer)
-- Purpose: Create ind_raw and ind_bronze PostgreSQL schemas.
--          The ind domain previously had only ind_silver and ind_gold.
--          Adding bronze/raw layers gives the indication domain a full medallion
--          architecture with proper audit trail.
--
-- ind_raw   — stores raw API responses for indication/disease classification sources
-- ind_bronze — typed/promoted indication data, cross-domain reference from mol_bronze.who_icd
--
-- Note: ind_raw has no tables of its own yet (raw data lives in mol_raw.who_icd via WHO ICD
-- fetcher). Future sources (e.g., SNOMED CT, ICD-10-CM downloads) will add tables here.

BEGIN;

CREATE SCHEMA IF NOT EXISTS ind_raw;
CREATE SCHEMA IF NOT EXISTS ind_bronze;

-- Register in meta.data_sources if the table exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'meta' AND table_name = 'data_sources'
    ) THEN
        INSERT INTO meta.data_sources (source_name, source_type, description, refresh_frequency, is_active)
        VALUES
        (
            'ind_icd11',
            'api',
            'WHO ICD-11 disease classification codes promoted to indication domain (from mol_raw.who_icd)',
            'monthly',
            TRUE
        )
        ON CONFLICT (source_name) DO UPDATE SET
            description       = EXCLUDED.description,
            refresh_frequency = EXCLUDED.refresh_frequency,
            is_active         = EXCLUDED.is_active;
    END IF;
END $$;

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 120_ind_raw_bronze_schemas complete.';
    RAISE NOTICE 'Created schemas: ind_raw, ind_bronze';
    RAISE NOTICE 'Registered ind_icd11 in meta.data_sources';
END $$;
