-- Migration: 083_meta_data_sources_create
-- Purpose: Create meta.data_sources and meta.refresh_log base tables
-- These tables are prerequisites for migrations 001 and 022 but were never formally created.

CREATE TABLE IF NOT EXISTS meta.data_sources (
    source_id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) UNIQUE NOT NULL,
    source_type VARCHAR(50) NOT NULL DEFAULT 'api',
    source_url VARCHAR(500),
    description TEXT,
    refresh_frequency VARCHAR(20),
    last_successful_refresh TIMESTAMP,
    last_refresh_attempt TIMESTAMP,
    last_refresh_status VARCHAR(20),
    record_count INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.refresh_log (
    log_id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES meta.data_sources(source_id),
    refresh_started_at TIMESTAMP,
    refresh_completed_at TIMESTAMP,
    status VARCHAR(20),
    records_fetched INTEGER,
    records_inserted INTEGER,
    records_updated INTEGER,
    error_message TEXT,
    _logged_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Seed the 28 data sources (ON CONFLICT DO NOTHING for idempotency)
INSERT INTO meta.data_sources (source_name, source_type, description, refresh_frequency, is_active) VALUES
    ('clinicaltrials', 'api', 'ClinicalTrials.gov studies', 'daily', true),
    ('openfda_labels', 'api', 'OpenFDA drug labels', 'daily', true),
    ('openfda_faers', 'api', 'OpenFDA adverse event reports', 'daily', true),
    ('drugbank', 'file', 'DrugBank drug database', 'monthly', true),
    ('chembl', 'api', 'ChEMBL compounds', 'weekly', true),
    ('pubchem', 'api', 'PubChem compounds', 'monthly', true),
    ('pubmed', 'api', 'PubMed literature via NCBI E-utilities', 'daily', true),
    ('openalex_ci', 'api', 'OpenAlex pharmaceutical research works', 'daily', true),
    ('journal_rss', 'feed', 'Journal RSS feeds', 'daily', true),
    ('medical_news', 'feed', 'Medical news RSS feeds', 'daily', true),
    ('ema_regulatory', 'api', 'EMA regulatory decisions', 'weekly', true),
    ('hta_decisions', 'api', 'HTA body decisions', 'weekly', true),
    ('cochrane', 'api', 'Cochrane systematic reviews', 'monthly', true),
    ('sec_edgar', 'api', 'SEC EDGAR pharma filings', 'daily', true),
    ('uspto_patents', 'api', 'USPTO PatentsView patents', 'weekly', true),
    ('uspto_ci', 'api', 'USPTO PatentsView CI patents', 'weekly', true),
    ('uspto_trademarks', 'api', 'USPTO TSDR trademark data', 'weekly', true),
    ('euipo_trademarks', 'api', 'EUIPO trademark data', 'weekly', true),
    ('epo_ops', 'api', 'EPO Open Patent Services', 'weekly', true),
    ('uniprot', 'api', 'UniProt protein targets', 'weekly', true),
    ('pdb', 'api', 'RCSB PDB protein structures', 'weekly', true),
    ('orcid', 'api', 'ORCID researcher profiles', 'weekly', false),
    ('cms_medicare_inpatient', 'file', 'CMS Medicare inpatient data', 'weekly', true),
    ('cms_hospital_info', 'api', 'CMS Hospital General Information', 'weekly', true),
    ('cms_cost_reports', 'file', 'CMS Hospital Cost Reports', 'monthly', true),
    ('acc_tvc', 'api', 'ACC Transcatheter Valve Certification', 'weekly', true),
    ('hrsa_shortage_areas', 'api', 'HRSA Health Professional Shortage Areas', 'weekly', true),
    ('openalex', 'api', 'OpenAlex research works', 'daily', true)
ON CONFLICT (source_name) DO NOTHING;

DO $$ BEGIN RAISE NOTICE 'Migration 083: meta.data_sources and meta.refresh_log created/verified'; END $$;
