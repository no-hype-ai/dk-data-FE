-- Migration: 225_trgm_indexes_for_search
-- Feature: 002-external-integration-foundation (perf pass)
-- Purpose: Add `pg_trgm` GIN indexes on canonical_name columns so
--          the client's `search` methods stop doing full sequential
--          scans on `ILIKE '%query%'`.
--
-- ## Why this is load-bearing for cluster stability
--
-- The dk-data-client ships `molecules.search`, `conditions.search`,
-- `publications.search`, and `patents.search`. Every one of those
-- translates to PostgREST `?title=ilike.*query*` or
-- `?canonical_name=ilike.*query*`, which becomes a PostgreSQL
-- `WHERE col ILIKE '%query%'` query. A leading-wildcard LIKE does
-- NOT use a B-tree index — it forces a sequential scan.
--
-- The fix is `CREATE INDEX ... USING GIN (col gin_trgm_ops)`. PG's
-- `pg_trgm` extension splits strings into overlapping 3-character
-- trigrams and builds a GIN index over them. A `WHERE col ILIKE '%query%'`
-- query can then use the index to find rows containing the trigrams
-- of `query`, yielding a bounded fast lookup (≤50ms on 15M rows).
--
-- ## Safety
--
-- - `CREATE EXTENSION IF NOT EXISTS pg_trgm` is idempotent.
-- - Each DO block checks whether the table exists before creating the
--   index — safe on a fresh CI database where hub tables are created
--   by bootstrap procedures (not migrations), so the table may not
--   exist yet. A RAISE NOTICE is emitted and the block continues.
-- - `IF NOT EXISTS` inside each block makes re-running a no-op.
-- - Regular (non-CONCURRENTLY) CREATE INDEX is used so the whole
--   migration can run inside a transaction. For the hub tables
--   (mol_silver.molecules etc.) this is safe — they are written only
--   by batch bootstrap procedures, not by live user traffic.
--   If a future operator needs to add these indexes online (CONCURRENTLY)
--   on a live table, they can do so manually; this migration records the
--   intent and will skip if the index already exists.
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data \
--      -f migrations/225_trgm_indexes_for_search.sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ----------------------------------------------------------------------------
-- mol_silver.molecules — molecules.search by canonical_name
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_silver' AND tablename = 'molecules') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'mol_silver'
                       AND indexname = 'idx_mol_silver_molecules_canonical_name_trgm') THEN
            CREATE INDEX idx_mol_silver_molecules_canonical_name_trgm
                ON mol_silver.molecules USING GIN (canonical_name gin_trgm_ops);
            RAISE NOTICE 'Created idx_mol_silver_molecules_canonical_name_trgm';
        ELSE
            RAISE NOTICE 'idx_mol_silver_molecules_canonical_name_trgm already exists — skip';
        END IF;
    ELSE
        RAISE NOTICE 'mol_silver.molecules does not exist yet — index will be created when table is bootstrapped';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- ind_silver.conditions — conditions.search by canonical_name
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'ind_silver' AND tablename = 'conditions') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'ind_silver'
                       AND indexname = 'idx_ind_silver_conditions_canonical_name_trgm') THEN
            CREATE INDEX idx_ind_silver_conditions_canonical_name_trgm
                ON ind_silver.conditions USING GIN (canonical_name gin_trgm_ops);
            RAISE NOTICE 'Created idx_ind_silver_conditions_canonical_name_trgm';
        ELSE
            RAISE NOTICE 'idx_ind_silver_conditions_canonical_name_trgm already exists — skip';
        END IF;
    ELSE
        RAISE NOTICE 'ind_silver.conditions does not exist yet — skip';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- mol_silver.companies — companies.resolve fallback by canonical_name
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_silver' AND tablename = 'companies') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'mol_silver'
                       AND indexname = 'idx_mol_silver_companies_canonical_name_trgm') THEN
            CREATE INDEX idx_mol_silver_companies_canonical_name_trgm
                ON mol_silver.companies USING GIN (canonical_name gin_trgm_ops);
            RAISE NOTICE 'Created idx_mol_silver_companies_canonical_name_trgm';
        ELSE
            RAISE NOTICE 'idx_mol_silver_companies_canonical_name_trgm already exists — skip';
        END IF;
    ELSE
        RAISE NOTICE 'mol_silver.companies does not exist yet — skip';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- mol_silver.publications — publications.search by title
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'mol_silver' AND tablename = 'publications') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'mol_silver'
                       AND indexname = 'idx_mol_silver_publications_title_trgm') THEN
            CREATE INDEX idx_mol_silver_publications_title_trgm
                ON mol_silver.publications USING GIN (title gin_trgm_ops);
            RAISE NOTICE 'Created idx_mol_silver_publications_title_trgm';
        ELSE
            RAISE NOTICE 'idx_mol_silver_publications_title_trgm already exists — skip';
        END IF;
    ELSE
        RAISE NOTICE 'mol_silver.publications does not exist yet — skip';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- ip_silver.patents — patents.search by title and assignee
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'ip_silver' AND tablename = 'patents') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'ip_silver'
                       AND indexname = 'idx_ip_silver_patents_title_trgm') THEN
            CREATE INDEX idx_ip_silver_patents_title_trgm
                ON ip_silver.patents USING GIN (title gin_trgm_ops);
            RAISE NOTICE 'Created idx_ip_silver_patents_title_trgm';
        ELSE
            RAISE NOTICE 'idx_ip_silver_patents_title_trgm already exists — skip';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'ip_silver'
                       AND indexname = 'idx_ip_silver_patents_assignee_trgm') THEN
            CREATE INDEX idx_ip_silver_patents_assignee_trgm
                ON ip_silver.patents USING GIN (assignee gin_trgm_ops);
            RAISE NOTICE 'Created idx_ip_silver_patents_assignee_trgm';
        ELSE
            RAISE NOTICE 'idx_ip_silver_patents_assignee_trgm already exists — skip';
        END IF;
    ELSE
        RAISE NOTICE 'ip_silver.patents does not exist yet — skip';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- hcs_silver.providers — providers.resolve fallback by canonical_name
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'hcs_silver' AND tablename = 'providers') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'hcs_silver'
                       AND indexname = 'idx_hcs_silver_providers_canonical_name_trgm') THEN
            CREATE INDEX idx_hcs_silver_providers_canonical_name_trgm
                ON hcs_silver.providers USING GIN (canonical_name gin_trgm_ops);
            RAISE NOTICE 'Created idx_hcs_silver_providers_canonical_name_trgm';
        ELSE
            RAISE NOTICE 'idx_hcs_silver_providers_canonical_name_trgm already exists — skip';
        END IF;
    ELSE
        RAISE NOTICE 'hcs_silver.providers does not exist yet — skip';
    END IF;
END $$;

COMMIT;
