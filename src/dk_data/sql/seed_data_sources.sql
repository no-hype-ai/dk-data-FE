-- Seed data for meta.data_sources
-- Initial configuration of data sources for the TAVR platform

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES
    ('cms_medicare_inpatient', 'csv', 'https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals',
     'CMS Medicare Inpatient data with TAVR procedure volumes by DRG code', 'quarterly', TRUE),

    ('cms_hospital_info', 'csv', 'https://data.cms.gov/provider-data/dataset/xubh-q36u',
     'CMS Hospital General Information including demographics, ownership, and quality ratings', 'monthly', TRUE),

    ('cms_cost_reports', 'csv', 'https://data.cms.gov/provider-compliance/cost-report',
     'CMS Hospital Cost Reports (HCRIS) with financial metrics', 'annual', TRUE),

    ('acc_tvc', 'csv', 'https://www.acc.org/tools-and-practice-support/quality-programs/transcatheter-valve-certification',
     'ACC Transcatheter Valve Certification data', 'quarterly', TRUE),

    ('hrsa_shortage_areas', 'api', 'https://data.hrsa.gov/api',
     'HRSA Health Professional Shortage Area (HPSA) designations', 'monthly', TRUE)

ON CONFLICT (source_name) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    description = EXCLUDED.description,
    refresh_frequency = EXCLUDED.refresh_frequency,
    is_active = EXCLUDED.is_active;

-- Set initial expected refresh frequencies
UPDATE meta.data_sources SET
    refresh_frequency = CASE source_name
        WHEN 'cms_medicare_inpatient' THEN 'quarterly'
        WHEN 'cms_hospital_info' THEN 'monthly'
        WHEN 'cms_cost_reports' THEN 'annual'
        WHEN 'acc_tvc' THEN 'quarterly'
        WHEN 'hrsa_shortage_areas' THEN 'monthly'
    END
WHERE source_name IN ('cms_medicare_inpatient', 'cms_hospital_info', 'cms_cost_reports', 'acc_tvc', 'hrsa_shortage_areas');

-- Output confirmation
DO $$
BEGIN
    RAISE NOTICE 'Data sources seeded successfully';
END
$$;
