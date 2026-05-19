-- Migration: 104_mol_raw_request_id_unique_constraints
-- Purpose: Fix mol_raw.* tables promoted from raw.* (migration 025+095) that have
--          non-unique request_id indexes but no UNIQUE constraint.
--
-- Problem: Loaders use ON CONFLICT (request_id) DO NOTHING / DO UPDATE which
--          requires a unique index or constraint on request_id. Without it,
--          PostgreSQL raises "there is no unique or exclusion constraint matching
--          the ON CONFLICT specification" at runtime.
--
-- Additionally, several tables have api_endpoint NOT NULL with no DEFAULT.
-- Loaders for rxnorm, who_inn, kegg_drug, tdc_admet do not supply api_endpoint,
-- causing "null value in column api_endpoint violates not-null constraint".
-- Fix: add source-appropriate DEFAULT values.
--
-- Tables fixed: mol_raw.rxnorm, mol_raw.who_inn, mol_raw.kegg_drug,
--               mol_raw.tdc_admet, mol_raw.bindingdb, mol_raw.pharmgkb
--
-- Depends on: 025_raw_schema_tables.sql, 095_legacy_sources_mol_raw_promotion.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Add UNIQUE constraints on request_id (idempotent: skips if already exists)
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['rxnorm', 'who_inn', 'kegg_drug', 'tdc_admet', 'bindingdb', 'pharmgkb']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema = 'mol_raw'
              AND table_name = tbl
              AND constraint_type = 'UNIQUE'
              AND constraint_name = 'mol_raw_' || tbl || '_request_id_key'
        ) THEN
            -- Check if a unique index already exists (separate from a named constraint)
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'mol_raw'
                  AND tablename = tbl
                  AND indexdef LIKE '%UNIQUE%'
                  AND indexdef LIKE '%request_id%'
            ) THEN
                EXECUTE format(
                    'ALTER TABLE mol_raw.%I ADD CONSTRAINT mol_raw_%s_request_id_key UNIQUE (request_id)',
                    tbl, tbl
                );
                RAISE NOTICE 'Added UNIQUE(request_id) to mol_raw.%', tbl;
            ELSE
                RAISE NOTICE 'mol_raw.% already has a unique index on request_id — skipping constraint add', tbl;
            END IF;
        ELSE
            RAISE NOTICE 'mol_raw.% UNIQUE constraint already exists — skipping', tbl;
        END IF;
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. Add DEFAULT values for api_endpoint where loaders do not supply it
-- ---------------------------------------------------------------------------

-- rxnorm: RxNorm REST API
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_raw' AND table_name='rxnorm'
               AND column_name='api_endpoint' AND column_default IS NULL) THEN
        ALTER TABLE mol_raw.rxnorm
            ALTER COLUMN api_endpoint SET DEFAULT 'https://rxnav.nlm.nih.gov/REST/';
        RAISE NOTICE 'Set api_endpoint DEFAULT on mol_raw.rxnorm';
    END IF;
END;
$$;

-- who_inn: WHO INN database
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_raw' AND table_name='who_inn'
               AND column_name='api_endpoint' AND column_default IS NULL) THEN
        ALTER TABLE mol_raw.who_inn
            ALTER COLUMN api_endpoint SET DEFAULT 'https://extranet.who.int/soinn/';
        RAISE NOTICE 'Set api_endpoint DEFAULT on mol_raw.who_inn';
    END IF;
END;
$$;

-- kegg_drug: KEGG REST API
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_raw' AND table_name='kegg_drug'
               AND column_name='api_endpoint' AND column_default IS NULL) THEN
        ALTER TABLE mol_raw.kegg_drug
            ALTER COLUMN api_endpoint SET DEFAULT 'https://rest.kegg.jp/';
        RAISE NOTICE 'Set api_endpoint DEFAULT on mol_raw.kegg_drug';
    END IF;
END;
$$;

-- tdc_admet: Harvard Dataverse TDC files
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_raw' AND table_name='tdc_admet'
               AND column_name='api_endpoint' AND column_default IS NULL) THEN
        ALTER TABLE mol_raw.tdc_admet
            ALTER COLUMN api_endpoint SET DEFAULT 'https://dataverse.harvard.edu/api/access/datafile/';
        RAISE NOTICE 'Set api_endpoint DEFAULT on mol_raw.tdc_admet';
    END IF;
END;
$$;

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 104_mol_raw_request_id_unique_constraints complete.';
    RAISE NOTICE 'UNIQUE(request_id) added to: rxnorm, who_inn, kegg_drug, tdc_admet, bindingdb, pharmgkb';
    RAISE NOTICE 'api_endpoint DEFAULT added to: rxnorm, who_inn, kegg_drug, tdc_admet';
END;
$$;
