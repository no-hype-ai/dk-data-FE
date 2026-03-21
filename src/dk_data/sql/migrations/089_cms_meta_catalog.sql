-- Migration 089: CMS Meta Catalog Entries (016-cms-puf-datasource-integration)
--
-- Registers all 30 CMS sources in meta.ops_data_sources + staleness detection config.
-- T106, T107, T108

BEGIN;

-- ─── CMS Source Catalog Entries ─────────────────────────────────────────────
-- Provider sources (Phase 2)
INSERT INTO meta.ops_data_sources (source_name, description, source_type, refresh_frequency, is_active)
VALUES
    ('cms_nppes', 'National Plan & Provider Enumeration System', 'api', 'weekly', TRUE),
    ('cms_part_d_prescriber', 'Medicare Part D prescriber drug utilization', 'api', 'annual', TRUE),
    ('cms_physician_puf', 'Medicare Physician & Other Practitioners', 'api', 'annual', TRUE),
    ('cms_open_payments', 'Industry payments to physicians', 'api', 'annual', TRUE),
    ('cms_care_compare', 'Hospital quality ratings', 'api', 'quarterly', TRUE),
    -- Facility sources (Phase 3)
    ('cms_pos', 'Provider of Services file', 'api', 'annual', TRUE),
    ('cms_pecos', 'Medicare Provider Supplier Enrollment', 'api', 'monthly', TRUE),
    ('cms_chow', 'Change of Ownership', 'api', 'monthly', TRUE),
    ('cms_hospital_affiliation', 'Hospital affiliations', 'api', 'quarterly', TRUE),
    ('cms_inpatient_puf', 'Medicare inpatient DRG volumes', 'api', 'annual', TRUE),
    ('cms_outpatient_puf', 'Medicare outpatient procedure volumes', 'api', 'annual', TRUE),
    ('cms_hospital_quality', 'Hospital star ratings', 'api', 'quarterly', TRUE),
    ('cms_hospital_general_info', 'Hospital general information', 'api', 'quarterly', TRUE),
    ('cms_hcris', 'Healthcare Cost Report Information System', 'file', 'annual', TRUE),
    ('cms_magnet', 'ANCC Magnet Recognition', 'scrape', 'monthly', TRUE),
    -- Drug/Market sources (Phase 4)
    ('cms_ndc', 'National Drug Code Directory', 'api', 'monthly', TRUE),
    ('cms_part_d_spending', 'Medicare Part D drug spending', 'api', 'annual', TRUE),
    ('cms_part_b_spending', 'Medicare Part B drug spending', 'api', 'annual', TRUE),
    ('cms_formulary', 'Medicare Plan Formulary', 'api', 'quarterly', TRUE),
    ('cms_rbcs', 'Restructured BETOS Classification', 'api', 'annual', TRUE),
    ('cms_usp', 'USP Drug Classification', 'scrape', 'annual', TRUE),
    ('cms_nucc', 'NUCC Provider Taxonomy', 'file', 'annual', TRUE),
    ('cms_geographic_variation', 'Medicare geographic comparisons', 'api', 'annual', TRUE),
    ('cms_chronic_conditions', 'Chronic conditions prevalence', 'api', 'annual', TRUE),
    ('cms_post_acute', 'Post-acute care utilization', 'api', 'annual', TRUE),
    ('cms_dmepos', 'Durable medical equipment utilization', 'api', 'annual', TRUE),
    ('cms_ddinter', 'Drug-drug interactions', 'api', 'monthly', TRUE),
    ('cms_stabilis', 'IV drug compatibility', 'scrape', 'monthly', TRUE)
ON CONFLICT (source_name) DO UPDATE SET
    description = EXCLUDED.description,
    refresh_frequency = EXCLUDED.refresh_frequency,
    is_active = EXCLUDED.is_active;

-- ─── Staleness Detection Config (T107) ──────────────────────────────────────
-- A source is stale if last_successful_refresh > 2x expected frequency
-- This is queried by the monitoring endpoint / Grafana dashboard

CREATE OR REPLACE VIEW meta.cms_staleness_report AS
SELECT
    ds.source_name,
    ds.description,
    ds.refresh_frequency,
    ds.last_successful_refresh,
    ds.last_refresh_status,
    CASE ds.refresh_frequency
        WHEN 'weekly' THEN INTERVAL '14 days'
        WHEN 'monthly' THEN INTERVAL '60 days'
        WHEN 'quarterly' THEN INTERVAL '180 days'
        WHEN 'annual' THEN INTERVAL '730 days'
        ELSE INTERVAL '60 days'
    END AS staleness_threshold,
    CASE
        WHEN ds.last_successful_refresh IS NULL THEN 'NEVER_LOADED'
        WHEN NOW() - ds.last_successful_refresh > CASE ds.refresh_frequency
            WHEN 'weekly' THEN INTERVAL '14 days'
            WHEN 'monthly' THEN INTERVAL '60 days'
            WHEN 'quarterly' THEN INTERVAL '180 days'
            WHEN 'annual' THEN INTERVAL '730 days'
            ELSE INTERVAL '60 days'
        END THEN 'STALE'
        ELSE 'FRESH'
    END AS freshness_status
FROM meta.ops_data_sources ds
WHERE ds.source_name LIKE 'cms_%'
    AND ds.is_active = TRUE
ORDER BY freshness_status DESC, ds.source_name;

COMMIT;
