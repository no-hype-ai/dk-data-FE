-- Migration 069: Data Classification Table
-- Feature: 013-observability-governance (US5: Data Classification + Retention)
-- Tasks: T021
-- Purpose: Create meta.data_classification table with seed data for all known tables
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/069_data_classification.sql

BEGIN;

-- =============================================================================
-- meta.data_classification — Classification and retention policy per table
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.data_classification (
    id                SERIAL          PRIMARY KEY,
    schema_name       VARCHAR(50)     NOT NULL,
    table_name        VARCHAR(100)    NOT NULL,
    classification    VARCHAR(20)     NOT NULL CHECK (classification IN ('public', 'internal', 'pii', 'confidential')),
    pii_fields        TEXT[],
    retention_days    INTEGER,            -- NULL = perpetual
    retention_policy  VARCHAR(50)     CHECK (retention_policy IN ('rolling_window', 'archive_then_purge', 'perpetual')),
    notes             TEXT,
    classified_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    classified_by     VARCHAR(100)    DEFAULT 'seed',
    UNIQUE (schema_name, table_name)
);

CREATE INDEX IF NOT EXISTS idx_data_classification_class
    ON meta.data_classification (classification);

-- =============================================================================
-- Seed Classification Data
-- =============================================================================

-- CONFIDENTIAL: scoring and mart tables (retention_days=730, rolling_window)
INSERT INTO meta.data_classification (schema_name, table_name, classification, pii_fields, retention_days, retention_policy, notes)
VALUES
    ('scoring', 'score_history',        'confidential', NULL, 730, 'rolling_window',       'Proprietary hospital scoring history'),
    ('scoring', 'score_latest',         'confidential', NULL, 730, 'rolling_window',       'Current proprietary hospital scores'),
    ('mart',    'dim_hospital',         'confidential', NULL, 730, 'rolling_window',       'Hospital dimension with internal analytics'),
    ('mart',    'fact_tavr_program',    'confidential', NULL, 730, 'rolling_window',       'TAVR program fact table — internal metrics'),
    ('mart',    'fact_financial_metrics','confidential', NULL, 730, 'rolling_window',       'Financial metrics — sensitive business data'),
    ('staging', 'hospitals',            'confidential', NULL, 730, 'rolling_window',       'Staging hospital records with internal fields'),
    ('staging', 'certifications',       'confidential', NULL, 730, 'rolling_window',       'Hospital certification staging data'),
    ('staging', 'tavr_volumes',         'confidential', NULL, 730, 'rolling_window',       'TAVR volume staging — pre-aggregation'),
    ('staging', 'geographic_designations','confidential', NULL, 730, 'rolling_window',     'Geographic designation staging data')
ON CONFLICT (schema_name, table_name) DO NOTHING;

-- PII: raw.orcid (retention_days=365, rolling_window)
INSERT INTO meta.data_classification (schema_name, table_name, classification, pii_fields, retention_days, retention_policy, notes)
VALUES
    ('raw', 'orcid', 'pii',
     ARRAY['given_names', 'family_name', 'credit_name', 'biography', 'current_affiliations', 'external_ids'],
     365, 'rolling_window', 'Researcher PII — names, affiliations, biographical data')
ON CONFLICT (schema_name, table_name) DO NOTHING;

-- INTERNAL: CI and regulatory raw tables (retention_days=730, rolling_window)
INSERT INTO meta.data_classification (schema_name, table_name, classification, pii_fields, retention_days, retention_policy, notes)
VALUES
    ('raw', 'pubmed',           'internal', NULL, 730, 'rolling_window', 'PubMed literature — internal CI pipeline'),
    ('raw', 'openalex_ci',      'internal', NULL, 730, 'rolling_window', 'OpenAlex CI research works'),
    ('raw', 'journal_rss',      'internal', NULL, 730, 'rolling_window', 'Journal RSS feed entries'),
    ('raw', 'cochrane_reviews', 'internal', NULL, 730, 'rolling_window', 'Cochrane systematic reviews'),
    ('raw', 'medical_news',     'internal', NULL, 730, 'rolling_window', 'Medical news feed entries'),
    ('raw', 'sec_edgar',        'internal', NULL, 730, 'rolling_window', 'SEC EDGAR pharmaceutical filings'),
    ('raw', 'hta_decisions',    'internal', NULL, 730, 'rolling_window', 'HTA body decisions (NICE, G-BA, etc.)'),
    ('raw', 'ema_regulatory',   'internal', NULL, 730, 'rolling_window', 'EMA regulatory decisions and signals')
ON CONFLICT (schema_name, table_name) DO NOTHING;

-- PUBLIC: open-data raw tables (retention_days=NULL, perpetual)
INSERT INTO meta.data_classification (schema_name, table_name, classification, pii_fields, retention_days, retention_policy, notes)
VALUES
    ('raw', 'bindingdb',        'public', NULL, NULL, 'perpetual', 'BindingDB open binding affinity data'),
    ('raw', 'orange_book',      'public', NULL, NULL, 'perpetual', 'FDA Orange Book — public domain'),
    ('raw', 'sider',            'public', NULL, NULL, 'perpetual', 'SIDER side effects — public domain'),
    ('raw', 'tdc_admet',        'public', NULL, NULL, 'perpetual', 'TDC ADMET predictions — open data'),
    ('raw', 'ema',              'public', NULL, NULL, 'perpetual', 'EMA approved medicines — public data'),
    ('raw', 'rxnorm',           'public', NULL, NULL, 'perpetual', 'NLM RxNorm — public nomenclature'),
    ('raw', 'dailymed',         'public', NULL, NULL, 'perpetual', 'NLM DailyMed — public drug labels'),
    ('raw', 'fda_drugs',        'public', NULL, NULL, 'perpetual', 'FDA Drugs@FDA — public approvals'),
    ('raw', 'kegg_drug',        'public', NULL, NULL, 'perpetual', 'KEGG Drug — public pathways/targets'),
    ('raw', 'ttd',              'public', NULL, NULL, 'perpetual', 'TTD — public target-drug data'),
    ('raw', 'pharmgkb',         'public', NULL, NULL, 'perpetual', 'PharmGKB — public pharmacogenomics'),
    ('raw', 'imgt',             'public', NULL, NULL, 'perpetual', 'IMGT — public immunogenetics data'),
    ('raw', 'cdc_vaccines',     'public', NULL, NULL, 'perpetual', 'CDC vaccines — public health data'),
    ('raw', 'drugbank',         'public', NULL, NULL, 'perpetual', 'DrugBank — open drug data'),
    ('raw', 'chembl',           'public', NULL, NULL, 'perpetual', 'ChEMBL — open bioactivity data'),
    ('raw', 'pubchem',          'public', NULL, NULL, 'perpetual', 'PubChem — open chemical data'),
    ('raw', 'uniprot',          'public', NULL, NULL, 'perpetual', 'UniProt — open protein database'),
    ('raw', 'pdb',              'public', NULL, NULL, 'perpetual', 'RCSB PDB — open 3D structures'),
    ('raw', 'uspto_patents',    'public', NULL, NULL, 'perpetual', 'USPTO patents — public patent data'),
    ('raw', 'epo_patents',      'public', NULL, NULL, 'perpetual', 'EPO patents — public patent data'),
    ('raw', 'uspto_ci',         'public', NULL, NULL, 'perpetual', 'USPTO CI patents — public patent data')
ON CONFLICT (schema_name, table_name) DO NOTHING;

-- PUBLIC: molecule medallion schemas (retention_days=NULL, perpetual)
INSERT INTO meta.data_classification (schema_name, table_name, classification, pii_fields, retention_days, retention_policy, notes)
VALUES
    ('mol_raw',    '*', 'public', NULL, NULL, 'perpetual', 'Molecule raw layer — open-source compound data'),
    ('mol_bronze', '*', 'public', NULL, NULL, 'perpetual', 'Molecule bronze layer — deduplicated open data'),
    ('mol_silver', '*', 'public', NULL, NULL, 'perpetual', 'Molecule silver layer — conformed open data'),
    ('mol_gold',   '*', 'public', NULL, NULL, 'perpetual', 'Molecule gold layer — curated open data')
ON CONFLICT (schema_name, table_name) DO NOTHING;

COMMIT;

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Data classification migration complete (069_data_classification.sql)';
    RAISE NOTICE 'Table: meta.data_classification';
    RAISE NOTICE 'Seed data: confidential (9), pii (1), internal (8), public (25)';
    RAISE NOTICE 'Index: idx_data_classification_class';
END
$$;
