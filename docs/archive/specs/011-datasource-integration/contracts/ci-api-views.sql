-- =============================================================================
-- API View Contracts for Tier 4 CI Sources
-- Feature: 011-datasource-integration
--
-- These views expose CI source data via PostgREST.
-- Only Tier 4 CI sources get API views; molecule sources defer to SQLMesh gold views.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- PubMed Publications
-- Endpoint: GET /pubmed_publications
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
FROM raw.pubmed
ORDER BY publication_date DESC;

GRANT SELECT ON api.pubmed_publications TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- OpenAlex CI Publications
-- Endpoint: GET /openalex_publications
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
FROM raw.openalex_ci
ORDER BY publication_date DESC;

GRANT SELECT ON api.openalex_publications TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- EMA Regulatory Decisions
-- Endpoint: GET /ema_regulatory_decisions
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
FROM raw.ema_regulatory
ORDER BY decision_date DESC;

GRANT SELECT ON api.ema_regulatory_decisions TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- Journal RSS Articles
-- Endpoint: GET /journal_articles
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
FROM raw.journal_rss
ORDER BY publication_date DESC;

GRANT SELECT ON api.journal_articles TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- USPTO CI Patents
-- Endpoint: GET /uspto_patents
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
FROM raw.uspto_ci
ORDER BY grant_date DESC;

GRANT SELECT ON api.uspto_patents TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- HTA Decisions
-- Endpoint: GET /hta_decisions
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
FROM raw.hta_decisions
ORDER BY decision_date DESC;

GRANT SELECT ON api.hta_decisions TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- EPO Patents
-- Endpoint: GET /epo_patents
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
FROM raw.epo_patents
ORDER BY publication_date DESC;

GRANT SELECT ON api.epo_patents TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- Cochrane Reviews
-- Endpoint: GET /cochrane_reviews
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
FROM raw.cochrane_reviews
ORDER BY publication_date DESC;

GRANT SELECT ON api.cochrane_reviews TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- Medical News
-- Endpoint: GET /medical_news
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
FROM raw.medical_news
ORDER BY publication_date DESC;

GRANT SELECT ON api.medical_news TO analyst, api_user;

-- -----------------------------------------------------------------------------
-- SEC EDGAR Filings
-- Endpoint: GET /sec_filings
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
FROM raw.sec_edgar
ORDER BY filing_date DESC;

GRANT SELECT ON api.sec_filings TO analyst, api_user;
