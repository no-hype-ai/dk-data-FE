-- Migration: 095_legacy_sources_mol_raw_promotion.sql
-- Purpose: Promote 6 legacy raw.* tables to mol_raw.* and register active sources
--          in meta.data_sources. Retire the websearch source.
-- Date: 2026-03-27
-- Feature: 019-cms-puf-platform-reconciliation (legacy source remediation)
--
-- Background: During initial platform build (migration 050), six molecule-centric
-- sources were created in the generic raw.* schema. The mol_raw.* schema was
-- introduced in migration 080 for molecule pipeline sources. This migration
-- moves the 6 tables into the correct schema using ALTER TABLE SET SCHEMA so that
-- the existing SQLMesh bronze models (which already reference mol_raw.*) work.
--
-- Sources promoted: rxnorm, who_inn, pharmgkb, kegg_drug, tdc_admet
-- Sources retired:  websearch (no longer actively maintained)

BEGIN;

-- ============================================================================
-- STEP 1: Move raw.* → mol_raw.* (schema rename, data preserved intact)
-- ============================================================================

-- RxNorm: NLM RxNorm REST API
ALTER TABLE IF EXISTS raw.rxnorm SET SCHEMA mol_raw;

-- WHO INN: WHO International Nonproprietary Names (via PubChem synonyms)
ALTER TABLE IF EXISTS raw.who_inn SET SCHEMA mol_raw;

-- PharmGKB: Pharmacogenomics knowledge base
ALTER TABLE IF EXISTS raw.pharmgkb SET SCHEMA mol_raw;

-- KEGG Drug: KEGG drug database
ALTER TABLE IF EXISTS raw.kegg_drug SET SCHEMA mol_raw;

-- TDC ADMET: Therapeutics Data Commons ADMET predictions
ALTER TABLE IF EXISTS raw.tdc_admet SET SCHEMA mol_raw;

-- Websearch: retired — move to mol_raw so data is preserved, but mark inactive
ALTER TABLE IF EXISTS raw.websearch SET SCHEMA mol_raw;

-- ============================================================================
-- STEP 2: Drop old bronze.* DDL tables that were created in migration 050
--         SQLMesh owns the mol_bronze.* tables; the bronze.* copies are dead code
-- ============================================================================

DROP TABLE IF EXISTS bronze.rxnorm CASCADE;
DROP TABLE IF EXISTS bronze.who_inn CASCADE;
DROP TABLE IF EXISTS bronze.pharmgkb CASCADE;
DROP TABLE IF EXISTS bronze.kegg_drug CASCADE;
DROP TABLE IF EXISTS bronze.tdc_admet CASCADE;
DROP TABLE IF EXISTS bronze.websearch CASCADE;

-- ============================================================================
-- STEP 3: Rebuild mol_raw indexes with correct schema references
--         (Indexes move automatically with the table on SET SCHEMA,
--          but we ensure they exist in case they were dropped)
-- ============================================================================

-- rxnorm indexes
CREATE INDEX IF NOT EXISTS idx_mol_raw_rxnorm_request_id     ON mol_raw.rxnorm(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_rxnorm_timestamp      ON mol_raw.rxnorm(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_mol_raw_rxnorm_processed      ON mol_raw.rxnorm(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_mol_raw_rxnorm_hash           ON mol_raw.rxnorm(response_body_hash);

-- who_inn indexes
CREATE INDEX IF NOT EXISTS idx_mol_raw_who_inn_request_id    ON mol_raw.who_inn(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_who_inn_timestamp     ON mol_raw.who_inn(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_mol_raw_who_inn_processed     ON mol_raw.who_inn(processed_to_bronze);

-- pharmgkb indexes
CREATE INDEX IF NOT EXISTS idx_mol_raw_pharmgkb_request_id   ON mol_raw.pharmgkb(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pharmgkb_timestamp    ON mol_raw.pharmgkb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pharmgkb_processed    ON mol_raw.pharmgkb(processed_to_bronze);

-- kegg_drug indexes
CREATE INDEX IF NOT EXISTS idx_mol_raw_kegg_drug_request_id  ON mol_raw.kegg_drug(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_kegg_drug_timestamp   ON mol_raw.kegg_drug(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_mol_raw_kegg_drug_processed   ON mol_raw.kegg_drug(processed_to_bronze);

-- tdc_admet indexes
CREATE INDEX IF NOT EXISTS idx_mol_raw_tdc_admet_request_id  ON mol_raw.tdc_admet(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tdc_admet_timestamp   ON mol_raw.tdc_admet(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_mol_raw_tdc_admet_processed   ON mol_raw.tdc_admet(processed_to_bronze);

-- ============================================================================
-- STEP 4: Register new active sources in meta.data_sources
-- ============================================================================

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES
    ('rxnorm',    'api',  'https://rxnav.nlm.nih.gov/REST',         'NLM RxNorm drug identifier vocabulary',               'weekly',  true),
    ('who_inn',   'api',  'https://pubchem.ncbi.nlm.nih.gov/rest',  'WHO International Nonproprietary Names via PubChem',  'weekly',  true),
    ('pharmgkb',  'api',  'https://api.pharmgkb.org/v1',            'PharmGKB pharmacogenomics knowledge base',            'weekly',  true),
    ('kegg_drug', 'api',  'https://rest.kegg.jp',                   'KEGG Drug compound and pathway database',             'weekly',  true),
    ('tdc_admet', 'file', 'https://tdcommons.ai',                   'TDC ADMET absorption/distribution/metabolism/excretion/toxicity predictions', 'monthly', true),
    ('websearch', 'api',  NULL,                                     'Generic web search results (RETIRED)',                'never',   false)
ON CONFLICT (source_name) DO UPDATE
    SET is_active          = EXCLUDED.is_active,
        source_url         = EXCLUDED.source_url,
        description        = EXCLUDED.description,
        refresh_frequency  = EXCLUDED.refresh_frequency;

COMMIT;
