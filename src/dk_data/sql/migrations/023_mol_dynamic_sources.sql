-- Migration: 023_mol_dynamic_sources.sql
-- Feature: 012-dk-data-platform
-- Description: Add dynamic fetcher configuration columns to meta.ops_data_sources
-- Date: 2026-01-27

-- =============================================================================
-- DYNAMIC FETCHER CONFIGURATION
-- =============================================================================

-- Add fetcher_class column for dynamic fetcher loading
-- This allows new sources to specify their fetcher class path in the database
-- Format: 'ingestion.fetchers.molecules.chembl.ChEMBLFetcher'
ALTER TABLE meta.ops_data_sources
ADD COLUMN IF NOT EXISTS fetcher_class VARCHAR(255);

COMMENT ON COLUMN meta.ops_data_sources.fetcher_class IS
'Python class path for the fetcher (e.g., ingestion.fetchers.molecules.chembl.ChEMBLFetcher). If NULL, uses FETCHER_REGISTRY lookup.';

-- Add fetcher_config column for fetcher-specific configuration
-- This allows source-specific parameters to be stored in the database
ALTER TABLE meta.ops_data_sources
ADD COLUMN IF NOT EXISTS fetcher_config JSONB DEFAULT '{}';

COMMENT ON COLUMN meta.ops_data_sources.fetcher_config IS
'JSON configuration passed to fetcher constructor (e.g., {"api_key_env": "CHEMBL_API_KEY", "rate_limit": 1.0})';

-- Add last_fetched_at column to track fetch timestamps
ALTER TABLE meta.ops_data_sources
ADD COLUMN IF NOT EXISTS last_fetched_at TIMESTAMPTZ;

COMMENT ON COLUMN meta.ops_data_sources.last_fetched_at IS
'Timestamp of the last successful fetch from this source';

-- Add enabled_layers to specify which pipeline layers this source feeds
ALTER TABLE meta.ops_data_sources
ADD COLUMN IF NOT EXISTS enabled_layers TEXT[] DEFAULT ARRAY['bronze'];

COMMENT ON COLUMN meta.ops_data_sources.enabled_layers IS
'Pipeline layers this source feeds (e.g., ["bronze", "silver"])';

-- =============================================================================
-- UPDATE EXISTING MOLECULE SOURCES WITH FETCHER CLASSES
-- =============================================================================

UPDATE meta.ops_data_sources
SET fetcher_class = 'ingestion.fetchers.molecules.chembl.ChEMBLFetcher',
    fetcher_config = '{"rate_limit": 1.0}'::jsonb,
    enabled_layers = ARRAY['bronze', 'silver', 'gold']
WHERE source_name = 'chembl';

UPDATE meta.ops_data_sources
SET fetcher_class = 'ingestion.fetchers.molecules.pubchem.PubChemFetcher',
    fetcher_config = '{"rate_limit": 5.0}'::jsonb,
    enabled_layers = ARRAY['bronze', 'silver', 'gold']
WHERE source_name = 'pubchem';

UPDATE meta.ops_data_sources
SET fetcher_class = 'ingestion.fetchers.molecules.clinicaltrials.ClinicalTrialsFetcher',
    fetcher_config = '{}'::jsonb,
    enabled_layers = ARRAY['bronze', 'silver', 'gold']
WHERE source_name = 'clinicaltrials';

UPDATE meta.ops_data_sources
SET fetcher_class = 'ingestion.fetchers.molecules.openfda.OpenFDALabelsFetcher',
    fetcher_config = '{"api_key_env": "OPENFDA_API_KEY"}'::jsonb,
    enabled_layers = ARRAY['bronze', 'silver', 'gold']
WHERE source_name = 'openfda_labels';

UPDATE meta.ops_data_sources
SET fetcher_class = 'ingestion.fetchers.molecules.openfda.OpenFDAFAERSFetcher',
    fetcher_config = '{"api_key_env": "OPENFDA_API_KEY"}'::jsonb,
    enabled_layers = ARRAY['bronze', 'silver', 'gold']
WHERE source_name = 'openfda_faers';

-- Sources without fetchers yet (placeholder for future implementation)
UPDATE meta.ops_data_sources
SET enabled_layers = ARRAY['bronze', 'silver', 'gold']
WHERE source_name IN ('drugbank', 'sider', 'uniprot', 'openalex')
  AND enabled_layers IS NULL;

-- =============================================================================
-- CREATE VIEW FOR ACTIVE MOLECULE SOURCES
-- =============================================================================

CREATE OR REPLACE VIEW mol_api.active_sources AS
SELECT
    source_id,
    source_name,
    source_type,
    source_url,
    description,
    refresh_frequency,
    is_active,
    topic_tags,
    staleness_threshold_hours,
    target_tables,
    fetcher_class,
    fetcher_config,
    enabled_layers,
    last_fetched_at,
    CASE
        WHEN last_fetched_at IS NULL THEN 'never'
        WHEN last_fetched_at > NOW() - (staleness_threshold_hours || ' hours')::INTERVAL THEN 'fresh'
        ELSE 'stale'
    END AS freshness_status,
    CASE
        WHEN fetcher_class IS NOT NULL THEN TRUE
        WHEN source_name IN ('chembl', 'pubchem', 'clinicaltrials', 'openfda_labels', 'openfda_faers') THEN TRUE
        ELSE FALSE
    END AS has_fetcher
FROM meta.ops_data_sources
WHERE is_active = TRUE
  AND (
    target_tables && ARRAY['mol_raw.chembl', 'mol_raw.pubchem', 'mol_raw.drugbank',
                           'mol_raw.clinicaltrials', 'mol_raw.openfda_labels',
                           'mol_raw.openfda_faers', 'mol_raw.sider', 'mol_raw.uniprot',
                           'mol_raw.openalex']::TEXT[]
    OR source_name IN ('chembl', 'pubchem', 'drugbank', 'clinicaltrials',
                       'openfda_labels', 'openfda_faers', 'sider', 'uniprot', 'openalex')
  )
ORDER BY source_name;

-- =============================================================================
-- CREATE FUNCTION TO REGISTER NEW SOURCE DYNAMICALLY
-- =============================================================================

CREATE OR REPLACE FUNCTION mol_api.register_source(
    p_source_name VARCHAR(100),
    p_source_type VARCHAR(20),
    p_source_url VARCHAR(500),
    p_description TEXT,
    p_refresh_frequency VARCHAR(20),
    p_fetcher_class VARCHAR(255) DEFAULT NULL,
    p_fetcher_config JSONB DEFAULT '{}',
    p_topic_tags TEXT[] DEFAULT '{}',
    p_staleness_hours INTEGER DEFAULT 24,
    p_target_tables TEXT[] DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    v_source_id INTEGER;
    v_target_tables TEXT[];
BEGIN
    -- Default target_tables to mol_raw.{source_name}
    v_target_tables := COALESCE(p_target_tables, ARRAY['mol_raw.' || p_source_name]);

    INSERT INTO meta.ops_data_sources (
        source_name,
        source_type,
        source_url,
        description,
        refresh_frequency,
        is_active,
        topic_tags,
        staleness_threshold_hours,
        target_tables,
        fetcher_class,
        fetcher_config,
        enabled_layers
    ) VALUES (
        p_source_name,
        p_source_type,
        p_source_url,
        p_description,
        p_refresh_frequency,
        TRUE,
        p_topic_tags,
        p_staleness_hours,
        v_target_tables,
        p_fetcher_class,
        p_fetcher_config,
        ARRAY['bronze', 'silver', 'gold']
    )
    ON CONFLICT (source_name) DO UPDATE SET
        source_url = EXCLUDED.source_url,
        description = EXCLUDED.description,
        refresh_frequency = EXCLUDED.refresh_frequency,
        fetcher_class = EXCLUDED.fetcher_class,
        fetcher_config = EXCLUDED.fetcher_config,
        target_tables = EXCLUDED.target_tables
    RETURNING source_id INTO v_source_id;

    RETURN v_source_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION mol_api.register_source IS
'Register a new molecule data source or update an existing one. Returns source_id.';

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 023_mol_dynamic_sources complete';
    RAISE NOTICE 'Added dynamic fetcher configuration columns to meta.ops_data_sources';
    RAISE NOTICE 'Created mol_api.active_sources view for querying available sources';
    RAISE NOTICE 'Created mol_api.register_source() function for dynamic source registration';
END
$$;
