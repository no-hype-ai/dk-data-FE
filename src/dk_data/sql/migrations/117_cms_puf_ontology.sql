-- Migration: 117_cms_puf_ontology.sql
-- Date: 2026-03-21
-- Feature: 003-molecule-assessment-dashboard
-- Description: Register CMS PUF gold views in Xenon data source ontology
--              so the orchestrator knows what to query and with what identifier.

-- ─── Data Source Ontology Entries for CMS PUF Gold Views ──────────────────────
-- These are healthcare system data (not molecule-specific).
-- Queried by drug_name/brand_name/NPI, not molecule_id.

INSERT INTO xenon.xenon_data_source_ontology (
    source_key, silver_table, display_name, category,
    ingest_source, query_field, query_transform,
    applicability_rules, refresh_hours, priority,
    min_rows, row_limit, strip_fields, dedup_keys, is_active
) VALUES
(
    'cms_drug_market', 'cms_drug_market', 'CMS Drug Market Profile (NDC-level)',
    'financial', NULL, 'drug_name', NULL,
    '{"marketing_status": ["approved"]}'::JSONB,
    720, 55, 1, 20,
    ARRAY[]::TEXT[], ARRAY['ndc']::TEXT[], true
),
(
    'cms_provider_360', 'cms_provider_360', 'CMS Provider 360 (NPI-level prescriber profiles)',
    'stakeholder', NULL, 'npi_from_payments', NULL,
    '{"marketing_status": ["approved"]}'::JSONB,
    720, 45, 1, 50,
    ARRAY[]::TEXT[], ARRAY['npi']::TEXT[], true
),
(
    'cms_market_analytics', 'cms_market_analytics', 'CMS Geographic Market Analytics',
    'financial', NULL, 'state', NULL,
    '{"always": true}'::JSONB,
    720, 35, 1, 10,
    ARRAY[]::TEXT[], ARRAY['state', 'county']::TEXT[], true
),
(
    'cms_provider_network', 'cms_provider_network', 'CMS Provider Referral Network',
    'stakeholder', NULL, 'npi_from_payments', NULL,
    '{"marketing_status": ["approved"]}'::JSONB,
    720, 30, 1, 20,
    ARRAY[]::TEXT[], ARRAY['source_npi', 'target_npi']::TEXT[], true
),
(
    'cms_facility_360', 'cms_facility_360', 'CMS Facility 360 (Hospital profiles)',
    'stakeholder', NULL, 'state', NULL,
    '{"always": true}'::JSONB,
    720, 25, 1, 20,
    ARRAY[]::TEXT[], ARRAY['ccn']::TEXT[], true
)
ON CONFLICT (source_key) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    applicability_rules = EXCLUDED.applicability_rules,
    refresh_hours = EXCLUDED.refresh_hours,
    priority = EXCLUDED.priority,
    min_rows = EXCLUDED.min_rows,
    row_limit = EXCLUDED.row_limit,
    dedup_keys = EXCLUDED.dedup_keys;
