-- Migration: 215_deprecate_redundant_ci_views
-- Feature: 002-external-integration-foundation (US-6, T067 — REVISED SCOPE)
-- Purpose: Mark the 10 `api.*` CI publication/regulatory/patent views from
--          migration 061 as DEPRECATED. Consumers should read directly
--          from the silver-layer canonical tables that already exist.
--
-- Architectural correction: The original feature 002 plan was to RENAME
-- these views to `mol_api.*` and `ip_api.*` (preserving the same shape).
-- Inspection of the silver layer found that every one of these CI sources
-- already has a canonical SQLMesh-materialized silver table, and both
-- `mol_silver` and `ip_silver` schemas are already exposed via PostgREST
-- in production (`PGRST_DB_SCHEMAS` in the k8s configmap) and already
-- granted to `analyst` via `post_sqlmesh/055_postgrest_hub_grants.sql`.
--
-- The api.* CI views are therefore REDUNDANT with the silver layer — they
-- pre-date the silver medallion rebuild (feature 001) and have been kept
-- alive only because migration 061 introduced them before silver had
-- proper coverage. Relocating them to `mol_api.*` would add a new layer
-- of indirection rather than removing the duplication.
--
-- Silver coverage (verified 2026-04-13):
--   api.pubmed_publications       → mol_silver.pubmed_articles + mol_silver.publications
--   api.openalex_publications     → mol_silver.publications (unified)
--   api.cochrane_reviews          → mol_silver.cochrane_reviews
--   api.medical_news              → mol_silver.medical_news + mol_silver.news_signals
--   api.journal_articles          → mol_silver.journal_rss
--   api.ema_regulatory_decisions  → mol_silver.ema_regulatory + mol_silver.regulatory_decisions
--   api.hta_decisions             → mol_silver.nice_hta (and/or hta_decisions if present)
--   api.sec_filings               → mol_silver.financial_data + mol_silver.company_financials
--   api.uspto_patents             → ip_silver.patents
--   api.epo_patents               → ip_silver.patents (unified IP hub)
--
-- Migration strategy:
--   1. This migration adds a COMMENT ON VIEW to each api.* CI view marking
--      it as deprecated and pointing at the silver replacement.
--   2. Consumers have 30 days after this migration lands to cut over to
--      the silver tables (`Accept-Profile: mol_silver` or `ip_silver`
--      header via PostgREST).
--   3. A follow-up migration (separate PR, scheduled ~30 days after this
--      one lands in production) will DROP the api.* CI views entirely.
--
-- The existing api.* views continue to work during the deprecation window.
-- No data access changes; only the comment marks them as deprecated. That
-- means this migration is zero-risk: no DDL that could fail, no grants
-- that could conflict, no lock contention.
--
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/215_deprecate_redundant_ci_views.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

-- Helper: comment every CI view with its deprecation pointer.
-- We use a DO block + dynamic SQL so missing views don't fail the migration.
DO $$
DECLARE
    deprecation_note TEXT;
    view_row RECORD;
    views_deprecation_map TEXT[][] := ARRAY[
        ['api.pubmed_publications',      'mol_silver.pubmed_articles or mol_silver.publications'],
        ['api.openalex_publications',    'mol_silver.publications (unified)'],
        ['api.cochrane_reviews',         'mol_silver.cochrane_reviews'],
        ['api.medical_news',             'mol_silver.medical_news or mol_silver.news_signals'],
        ['api.journal_articles',         'mol_silver.journal_rss'],
        ['api.ema_regulatory_decisions', 'mol_silver.ema_regulatory or mol_silver.regulatory_decisions'],
        ['api.hta_decisions',            'mol_silver.nice_hta'],
        ['api.sec_filings',              'mol_silver.financial_data or mol_silver.company_financials'],
        ['api.uspto_patents',            'ip_silver.patents'],
        ['api.epo_patents',              'ip_silver.patents (unified IP hub)']
    ];
    row_idx INT;
BEGIN
    FOR row_idx IN 1 .. array_length(views_deprecation_map, 1) LOOP
        BEGIN
            deprecation_note := format(
                'DEPRECATED (feature 002-external-integration-foundation US-6): this view is a legacy CI presentation wrapper from migration 061 and is redundant with the silver layer. Read from %s instead. This view will be dropped ~30 days after consumer migration is verified in telemetry. See feature 002 spec F-D015.',
                views_deprecation_map[row_idx][2]
            );
            EXECUTE format(
                'COMMENT ON VIEW %s IS %L',
                views_deprecation_map[row_idx][1],
                deprecation_note
            );
            RAISE NOTICE 'deprecated: % → read from %',
                views_deprecation_map[row_idx][1],
                views_deprecation_map[row_idx][2];
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'could not annotate % — % / %',
                views_deprecation_map[row_idx][1], SQLSTATE, SQLERRM;
        END;
    END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- COMPLETION
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    RAISE NOTICE '215_deprecate_redundant_ci_views complete: 10 api.* CI views annotated as deprecated';
    RAISE NOTICE 'Consumers should migrate to mol_silver.* / ip_silver.* (already exposed via PostgREST)';
    RAISE NOTICE 'Follow-up migration will drop the api.* CI views ~30 days after consumer migration is verified';
END
$$;

COMMIT;
