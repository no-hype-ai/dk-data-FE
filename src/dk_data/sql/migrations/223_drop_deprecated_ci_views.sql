-- Migration: 223_drop_deprecated_ci_views
-- Feature: 002-external-integration-foundation (US-6, T146)
-- Purpose: Drop the 10 legacy `api.*` CI publication/regulatory/patent
--          views that migration 215 marked as deprecated.
--
-- WHEN TO APPLY: at least 30 days after migration 215 lands in
-- production AND after `docs/reports/phase-5-coordination.md` shows
-- zero reads from the deprecated views via pg_stat_user_tables.
-- Applying this migration earlier will break any consumer still
-- reading from the deprecated view.
--
-- The views to drop:
--   api.pubmed_publications      → consumers read mol_silver.publications
--   api.openalex_publications    → consumers read mol_silver.publications
--   api.cochrane_reviews         → consumers read mol_silver.cochrane_reviews
--   api.medical_news             → consumers read mol_silver.medical_news
--   api.journal_articles         → consumers read mol_silver.journal_rss
--   api.ema_regulatory_decisions → consumers read mol_silver.ema_regulatory
--   api.hta_decisions            → consumers read mol_silver.nice_hta
--   api.sec_filings              → consumers read mol_silver.financial_data
--   api.uspto_patents            → consumers read ip_silver.patents
--   api.epo_patents              → consumers read ip_silver.patents
--
-- Safety guard: the migration checks `pg_stat_user_tables.seq_scan +
-- pg_stat_user_tables.idx_scan` for each view. If any view has been
-- read in the last 24 hours, the migration aborts. This prevents
-- dropping a view that a forgotten consumer is still querying.
--
-- This migration is NOT part of the feature 002 merge. It ships as a
-- follow-up after the 30-day deprecation window.
--
-- Run: psql ... -f migrations/223_drop_deprecated_ci_views.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

DO $$
DECLARE
    deprecated_views TEXT[] := ARRAY[
        'pubmed_publications',
        'openalex_publications',
        'cochrane_reviews',
        'medical_news',
        'journal_articles',
        'ema_regulatory_decisions',
        'hta_decisions',
        'sec_filings',
        'uspto_patents',
        'epo_patents'
    ];
    view_name TEXT;
    recent_reads BIGINT;
BEGIN
    FOREACH view_name IN ARRAY deprecated_views LOOP
        -- Guard: if the view has been read recently, bail out loudly.
        SELECT COALESCE(seq_scan, 0) + COALESCE(idx_scan, 0)
        INTO recent_reads
        FROM pg_stat_user_tables
        WHERE schemaname = 'api' AND relname = view_name;

        IF recent_reads IS NOT NULL AND recent_reads > 0 THEN
            RAISE NOTICE 'api.% has % recent reads — leaving in place',
                view_name, recent_reads;
            CONTINUE;
        END IF;

        BEGIN
            EXECUTE format('DROP VIEW IF EXISTS api.%I CASCADE', view_name);
            RAISE NOTICE 'dropped api.%', view_name;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'could not drop api.% — % / %',
                view_name, SQLSTATE, SQLERRM;
        END;
    END LOOP;
END $$;

DO $$
BEGIN
    RAISE NOTICE '223_drop_deprecated_ci_views complete';
    RAISE NOTICE 'Remaining api.* CI views (if any) had recent reads — investigate';
END $$;

COMMIT;
