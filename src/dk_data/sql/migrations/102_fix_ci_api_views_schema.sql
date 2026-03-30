-- Migration: 102_fix_ci_api_views_schema
-- Feature: 019-cms-puf-platform-reconciliation
-- Purpose: Rebuild the 10 CI API views (originally created by 061_ci_api_views.sql)
--          to read from mol_raw.* instead of raw.*.
--
-- Background: Migration 099 moved tables raw.* → mol_raw.* for molecule sources,
--             but did not update the api.* views that reference those tables.
--             The views have been broken (returning nothing) since 099 ran.
--
-- Sources affected (all write to mol_raw.* via ingestion pipeline):
--   mol_raw.pubmed, mol_raw.openalex_ci, mol_raw.ema_regulatory,
--   mol_raw.journal_rss, mol_raw.uspto_ci, mol_raw.hta_decisions,
--   mol_raw.epo_patents, mol_raw.cochrane_reviews, mol_raw.medical_news,
--   mol_raw.sec_edgar
--
-- Depends on: 060_ci_source_tables.sql, 061_ci_api_views.sql, 099_schema_prefix_normalization.sql

BEGIN;

-- -----------------------------------------------------------------------------
-- Move raw.ema_regulatory → mol_raw.ema_regulatory if not already done
-- (Migration 099 moved the other CI sources but missed ema_regulatory)
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'raw' AND table_name = 'ema_regulatory'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mol_raw' AND table_name = 'ema_regulatory'
    ) THEN
        ALTER TABLE raw.ema_regulatory SET SCHEMA mol_raw;
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- PubMed Publications
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.pubmed_publications AS
SELECT
    pmid,
    title,
    abstract,
    authors,
    journal,
    publication_date,
    mesh_terms,
    doi,
    publication_types,
    keywords,
    _loaded_at
FROM mol_raw.pubmed
ORDER BY publication_date DESC;

GRANT SELECT ON api.pubmed_publications TO web_anon;
GRANT SELECT ON api.pubmed_publications TO analyst;

-- -----------------------------------------------------------------------------
-- OpenAlex CI Publications
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.openalex_publications AS
SELECT
    work_id,
    doi,
    title,
    abstract,
    publication_date,
    cited_by_count,
    concepts,
    authorships,
    primary_location,
    open_access,
    _loaded_at
FROM mol_raw.openalex_ci
ORDER BY publication_date DESC;

GRANT SELECT ON api.openalex_publications TO web_anon;
GRANT SELECT ON api.openalex_publications TO analyst;

-- -----------------------------------------------------------------------------
-- EMA Regulatory Decisions
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.ema_regulatory_decisions AS
SELECT
    document_id,
    document_type,
    product_name,
    active_substance,
    therapeutic_area,
    decision_date,
    decision_type,
    document_url,
    summary,
    _loaded_at
FROM mol_raw.ema_regulatory
ORDER BY decision_date DESC;

GRANT SELECT ON api.ema_regulatory_decisions TO web_anon;
GRANT SELECT ON api.ema_regulatory_decisions TO analyst;

-- -----------------------------------------------------------------------------
-- Journal RSS Articles
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.journal_articles AS
SELECT
    article_id,
    feed_source,
    title,
    authors,
    abstract,
    publication_date,
    link,
    doi,
    categories,
    _loaded_at
FROM mol_raw.journal_rss
ORDER BY publication_date DESC;

GRANT SELECT ON api.journal_articles TO web_anon;
GRANT SELECT ON api.journal_articles TO analyst;

-- -----------------------------------------------------------------------------
-- USPTO CI Patents
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.uspto_patents AS
SELECT
    patent_id,
    title,
    abstract,
    inventors,
    assignees,
    filing_date,
    grant_date,
    cpc_codes,
    claims_count,
    _loaded_at
FROM mol_raw.uspto_ci
ORDER BY grant_date DESC;

GRANT SELECT ON api.uspto_patents TO web_anon;
GRANT SELECT ON api.uspto_patents TO analyst;

-- -----------------------------------------------------------------------------
-- HTA Decisions
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.hta_decisions AS
SELECT
    decision_id,
    agency,
    drug_name,
    indication,
    decision_type,
    decision_date,
    document_url,
    summary,
    _loaded_at
FROM mol_raw.hta_decisions
ORDER BY decision_date DESC;

GRANT SELECT ON api.hta_decisions TO web_anon;
GRANT SELECT ON api.hta_decisions TO analyst;

-- -----------------------------------------------------------------------------
-- EPO Patents
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.epo_patents AS
SELECT
    publication_id,
    title,
    abstract,
    applicants,
    inventors,
    filing_date,
    publication_date,
    ipc_codes,
    family_id,
    _loaded_at
FROM mol_raw.epo_patents
ORDER BY publication_date DESC;

GRANT SELECT ON api.epo_patents TO web_anon;
GRANT SELECT ON api.epo_patents TO analyst;

-- -----------------------------------------------------------------------------
-- Cochrane Reviews
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.cochrane_reviews AS
SELECT
    review_id,
    title,
    authors,
    abstract,
    publication_date,
    review_type,
    interventions,
    conditions,
    conclusions,
    doi,
    _loaded_at
FROM mol_raw.cochrane_reviews
ORDER BY publication_date DESC;

GRANT SELECT ON api.cochrane_reviews TO web_anon;
GRANT SELECT ON api.cochrane_reviews TO analyst;

-- -----------------------------------------------------------------------------
-- Medical News
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.medical_news AS
SELECT
    article_id,
    source_name,
    title,
    summary,
    publication_date,
    url,
    drug_mentions,
    therapeutic_areas,
    _loaded_at
FROM mol_raw.medical_news
ORDER BY publication_date DESC;

GRANT SELECT ON api.medical_news TO web_anon;
GRANT SELECT ON api.medical_news TO analyst;

-- -----------------------------------------------------------------------------
-- SEC EDGAR Filings
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.sec_filings AS
SELECT
    accession_number,
    company_name,
    cik,
    filing_type,
    filing_date,
    document_url,
    description,
    _loaded_at
FROM mol_raw.sec_edgar
ORDER BY filing_date DESC;

GRANT SELECT ON api.sec_filings TO web_anon;
GRANT SELECT ON api.sec_filings TO analyst;

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 102_fix_ci_api_views_schema complete.';
    RAISE NOTICE 'Rebuilt 10 CI API views to read from mol_raw.* (was raw.*)';
    RAISE NOTICE 'Views fixed: pubmed_publications, openalex_publications,';
    RAISE NOTICE '             ema_regulatory_decisions, journal_articles,';
    RAISE NOTICE '             uspto_patents, hta_decisions, epo_patents,';
    RAISE NOTICE '             cochrane_reviews, medical_news, sec_filings';
END $$;
