-- Migration: 060_ci_source_tables
-- Feature: 011-datasource-integration
-- Purpose: Create raw tables for Tier 4 CI sources and ci_search_terms table
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/060_ci_source_tables.sql

-- =============================================================================
-- CI Search Terms (configurable query terms for scoped CI fetchers)
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.ci_search_terms (
    term_id SERIAL PRIMARY KEY,
    term_type VARCHAR(50) NOT NULL,
    term_value VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (term_type, term_value)
);

CREATE INDEX IF NOT EXISTS idx_ci_search_terms_active ON meta.ci_search_terms(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_ci_search_terms_type ON meta.ci_search_terms(term_type);

-- Seed initial search terms
INSERT INTO meta.ci_search_terms (term_type, term_value) VALUES
    ('therapeutic_area', 'cardiovascular'),
    ('therapeutic_area', 'oncology'),
    ('therapeutic_area', 'neurology'),
    ('therapeutic_area', 'immunology'),
    ('therapeutic_area', 'rare diseases'),
    ('therapeutic_area', 'infectious disease'),
    ('drug_name', 'pembrolizumab'),
    ('drug_name', 'trastuzumab'),
    ('drug_name', 'nivolumab'),
    ('drug_name', 'adalimumab'),
    ('drug_name', 'semaglutide'),
    ('mesh_term', 'Transcatheter Aortic Valve Replacement'),
    ('mesh_term', 'Immunotherapy'),
    ('mesh_term', 'Gene Therapy'),
    ('mesh_term', 'CAR-T Cell Therapy'),
    ('company', 'Pfizer'),
    ('company', 'Roche'),
    ('company', 'Novartis'),
    ('company', 'Merck'),
    ('company', 'Johnson and Johnson'),
    ('company', 'AbbVie'),
    ('company', 'Bristol-Myers Squibb'),
    ('company', 'AstraZeneca'),
    ('company', 'Eli Lilly'),
    ('company', 'Sanofi')
ON CONFLICT (term_type, term_value) DO NOTHING;

-- =============================================================================
-- raw.pubmed — PubMed/MEDLINE articles
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.pubmed (
    pmid VARCHAR(20) NOT NULL,
    title TEXT,
    abstract TEXT,
    authors JSONB,
    journal VARCHAR(500),
    publication_date DATE,
    mesh_terms TEXT[],
    doi VARCHAR(100),
    publication_types TEXT[],
    keywords TEXT[],
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (pmid)
);

CREATE INDEX IF NOT EXISTS idx_pubmed_date ON raw.pubmed(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_pubmed_doi ON raw.pubmed(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pubmed_mesh ON raw.pubmed USING GIN(mesh_terms);

-- =============================================================================
-- raw.openalex_ci — OpenAlex publications (CI)
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.openalex_ci (
    work_id VARCHAR(50) NOT NULL,
    doi VARCHAR(100),
    title TEXT,
    abstract TEXT,
    publication_date DATE,
    cited_by_count INTEGER,
    concepts JSONB,
    authorships JSONB,
    primary_location JSONB,
    open_access JSONB,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (work_id)
);

CREATE INDEX IF NOT EXISTS idx_openalex_ci_date ON raw.openalex_ci(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_openalex_ci_doi ON raw.openalex_ci(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_openalex_ci_citations ON raw.openalex_ci(cited_by_count DESC);

-- =============================================================================
-- raw.ema_regulatory — EMA regulatory decisions
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.ema_regulatory (
    document_id VARCHAR(100) NOT NULL,
    document_type VARCHAR(50),
    product_name VARCHAR(500),
    active_substance VARCHAR(500),
    therapeutic_area VARCHAR(500),
    decision_date DATE,
    decision_type VARCHAR(100),
    document_url TEXT,
    summary TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (document_id)
);

CREATE INDEX IF NOT EXISTS idx_ema_reg_date ON raw.ema_regulatory(decision_date DESC);
CREATE INDEX IF NOT EXISTS idx_ema_reg_type ON raw.ema_regulatory(document_type);
CREATE INDEX IF NOT EXISTS idx_ema_reg_substance ON raw.ema_regulatory(active_substance);

-- =============================================================================
-- raw.journal_rss — Journal RSS feed articles
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.journal_rss (
    article_id VARCHAR(255) NOT NULL,
    feed_source VARCHAR(100) NOT NULL,
    title TEXT,
    authors TEXT,
    abstract TEXT,
    publication_date DATE,
    link TEXT,
    doi VARCHAR(100),
    categories TEXT[],
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (article_id)
);

CREATE INDEX IF NOT EXISTS idx_journal_rss_date ON raw.journal_rss(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_journal_rss_source ON raw.journal_rss(feed_source);
CREATE INDEX IF NOT EXISTS idx_journal_rss_doi ON raw.journal_rss(doi) WHERE doi IS NOT NULL;

-- =============================================================================
-- raw.uspto_ci — USPTO PatentsView CI patents
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.uspto_ci (
    patent_id VARCHAR(50) NOT NULL,
    title TEXT,
    abstract TEXT,
    inventors JSONB,
    assignees JSONB,
    filing_date DATE,
    grant_date DATE,
    cpc_codes TEXT[],
    claims_count INTEGER,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (patent_id)
);

CREATE INDEX IF NOT EXISTS idx_uspto_ci_grant_date ON raw.uspto_ci(grant_date DESC);
CREATE INDEX IF NOT EXISTS idx_uspto_ci_cpc ON raw.uspto_ci USING GIN(cpc_codes);

-- =============================================================================
-- raw.hta_decisions — HTA body decisions
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.hta_decisions (
    decision_id VARCHAR(100) NOT NULL,
    agency VARCHAR(50) NOT NULL,
    drug_name VARCHAR(500),
    indication TEXT,
    decision_type VARCHAR(100),
    decision_date DATE,
    document_url TEXT,
    summary TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (decision_id)
);

CREATE INDEX IF NOT EXISTS idx_hta_date ON raw.hta_decisions(decision_date DESC);
CREATE INDEX IF NOT EXISTS idx_hta_agency ON raw.hta_decisions(agency);
CREATE INDEX IF NOT EXISTS idx_hta_drug ON raw.hta_decisions(drug_name);

-- =============================================================================
-- raw.epo_patents — EPO Open Patent Services
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.epo_patents (
    publication_id VARCHAR(50) NOT NULL,
    title TEXT,
    abstract TEXT,
    applicants JSONB,
    inventors JSONB,
    filing_date DATE,
    publication_date DATE,
    ipc_codes TEXT[],
    family_id VARCHAR(50),
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (publication_id)
);

CREATE INDEX IF NOT EXISTS idx_epo_pub_date ON raw.epo_patents(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_epo_family ON raw.epo_patents(family_id);
CREATE INDEX IF NOT EXISTS idx_epo_ipc ON raw.epo_patents USING GIN(ipc_codes);

-- =============================================================================
-- raw.cochrane_reviews — Cochrane Library systematic reviews
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.cochrane_reviews (
    review_id VARCHAR(100) NOT NULL,
    title TEXT,
    authors TEXT,
    abstract TEXT,
    publication_date DATE,
    review_type VARCHAR(50),
    interventions TEXT[],
    conditions TEXT[],
    conclusions TEXT,
    doi VARCHAR(100),
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (review_id)
);

CREATE INDEX IF NOT EXISTS idx_cochrane_date ON raw.cochrane_reviews(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_cochrane_type ON raw.cochrane_reviews(review_type);
CREATE INDEX IF NOT EXISTS idx_cochrane_interventions ON raw.cochrane_reviews USING GIN(interventions);

-- =============================================================================
-- raw.medical_news — Medical news articles
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.medical_news (
    article_id VARCHAR(255) NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    title TEXT,
    summary TEXT,
    publication_date DATE,
    url TEXT,
    drug_mentions TEXT[],
    therapeutic_areas TEXT[],
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (article_id)
);

CREATE INDEX IF NOT EXISTS idx_news_date ON raw.medical_news(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_source ON raw.medical_news(source_name);
CREATE INDEX IF NOT EXISTS idx_news_drugs ON raw.medical_news USING GIN(drug_mentions);

-- =============================================================================
-- raw.sec_edgar — SEC EDGAR pharmaceutical filings
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.sec_edgar (
    accession_number VARCHAR(50) NOT NULL,
    company_name VARCHAR(500),
    cik VARCHAR(20),
    filing_type VARCHAR(20) NOT NULL,
    filing_date DATE,
    document_url TEXT,
    description TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (accession_number)
);

CREATE INDEX IF NOT EXISTS idx_edgar_date ON raw.sec_edgar(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_edgar_type ON raw.sec_edgar(filing_type);
CREATE INDEX IF NOT EXISTS idx_edgar_cik ON raw.sec_edgar(cik);

-- =============================================================================
-- Migration complete
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 060_ci_source_tables complete.';
    RAISE NOTICE 'Created meta.ci_search_terms with initial seed data';
    RAISE NOTICE 'Created 10 raw.* tables for CI sources';
    RAISE NOTICE 'Created indexes for all CI tables';
END
$$;
