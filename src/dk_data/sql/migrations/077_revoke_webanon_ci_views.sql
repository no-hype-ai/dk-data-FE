-- Migration 077: Revoke web_anon access from CI source API views
-- Security fix: GitHub issue data-kinetic/behavior-labs-ai#550
--
-- Migration 061 granted web_anon SELECT on 10 CI source API views.
-- The security fix (commit 4b78e3c) restricted web_anon to ONLY
-- api.health and api.data_catalog. This migration ensures the
-- revocation persists even after migrations re-run.
--
-- web_anon MUST NOT have SELECT on any data views.

-- Revoke all stale web_anon grants from CI source views (migration 061)
DO $$
DECLARE
    v_name TEXT;
    v_views TEXT[] := ARRAY[
        'pubmed_publications', 'openalex_publications',
        'ema_regulatory_decisions', 'journal_articles',
        'uspto_patents', 'hta_decisions', 'epo_patents',
        'cochrane_reviews', 'medical_news', 'sec_filings'
    ];
BEGIN
    FOREACH v_name IN ARRAY v_views
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.views
            WHERE table_schema = 'api' AND table_name = v_name
        ) THEN
            EXECUTE format('REVOKE SELECT ON api.%I FROM web_anon', v_name);
            RAISE NOTICE 'Revoked web_anon SELECT on api.%', v_name;
        END IF;
    END LOOP;
END $$;

-- Defensive: revoke from any other api views that web_anon shouldn't have
-- Only api.health and api.data_catalog should be publicly accessible
DO $$
DECLARE
    v_name TEXT;
BEGIN
    FOR v_name IN
        SELECT table_name FROM information_schema.views
        WHERE table_schema = 'api'
        AND table_name NOT IN ('health', 'data_catalog')
    LOOP
        EXECUTE format('REVOKE SELECT ON api.%I FROM web_anon', v_name);
    END LOOP;
END $$;
