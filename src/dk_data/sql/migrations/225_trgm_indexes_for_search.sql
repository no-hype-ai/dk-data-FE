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
-- Tables like `mol_silver.molecules` (~2M rows) and
-- `mol_silver.publications` (~15M rows) are big enough that a
-- single uncached seq-scan eats 200–800ms of CPU and holds a
-- connection the whole time. 10 concurrent searches = 10 connections
-- pinned for ~500ms each = 5 connection-seconds of pool pressure
-- per search burst. On a 30-slot pool, it takes 6 concurrent users
-- to saturate.
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
-- - `CREATE INDEX CONCURRENTLY` builds the index without blocking
--   writers. Longer to build but no ACCESS EXCLUSIVE lock — safe
--   to run on a live database.
-- - `IF NOT EXISTS` so re-running is a no-op.
--
-- ## ⚠️ CONCURRENTLY requires running OUTSIDE a transaction
--
-- This migration uses `CREATE INDEX CONCURRENTLY` which CANNOT run
-- inside a BEGIN/COMMIT block. Each statement runs in its own
-- implicit transaction. The migration runner MUST be configured to
-- run this file without wrapping it in an explicit transaction.
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data \
--      --set=ON_ERROR_STOP=on \
--      -f migrations/225_trgm_indexes_for_search.sql
--
-- For dk-data's in-house `run_migration.py`, ensure the file is
-- marked as `no_transaction=True`.

-- ----------------------------------------------------------------------------
-- Extension
-- ----------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ----------------------------------------------------------------------------
-- Indexes
--
-- Each index targets a column the client searches via ILIKE.
-- GIN (trgm_ops) is the right choice for ILIKE with leading
-- wildcards. B-tree suffices for prefix-only search (rare in the
-- client surface) — we don't duplicate those.
-- ----------------------------------------------------------------------------

-- mol_silver.molecules — molecules.search by canonical_name
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_silver_molecules_canonical_name_trgm
    ON mol_silver.molecules
    USING GIN (canonical_name gin_trgm_ops);

-- ind_silver.conditions — conditions.search by canonical_name
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ind_silver_conditions_canonical_name_trgm
    ON ind_silver.conditions
    USING GIN (canonical_name gin_trgm_ops);

-- mol_silver.companies — companies.resolve fallback matches by canonical_name
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_silver_companies_canonical_name_trgm
    ON mol_silver.companies
    USING GIN (canonical_name gin_trgm_ops);

-- mol_silver.publications — publications.search by title
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mol_silver_publications_title_trgm
    ON mol_silver.publications
    USING GIN (title gin_trgm_ops);

-- ip_silver.patents — patents.search by title + assignee (two separate
-- indexes because consumers query either one; GIN cannot combine
-- them into a single `ILIKE` predicate)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ip_silver_patents_title_trgm
    ON ip_silver.patents
    USING GIN (title gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ip_silver_patents_assignee_trgm
    ON ip_silver.patents
    USING GIN (assignee gin_trgm_ops);

-- hcs_silver.providers — providers.resolve falls through to
-- canonical_name on fuzzy match
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hcs_silver_providers_canonical_name_trgm
    ON hcs_silver.providers
    USING GIN (canonical_name gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- Completion notice
-- ----------------------------------------------------------------------------

-- NB: No DO block, no RAISE NOTICE — those require a transaction,
-- and this file runs without one because of CREATE INDEX CONCURRENTLY.
-- The migration runner logs each statement's result instead.
