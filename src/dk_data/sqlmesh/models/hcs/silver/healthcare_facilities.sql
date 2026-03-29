-- SQLMesh Model: Silver Healthcare Facilities
-- Consolidated healthcare facility data from CMS, ACC/TVC, and HRSA sources
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcs_silver.healthcare_facilities,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, source)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, source))
    ),
    grain (provider_id, source)
);

WITH cms_inpatient AS (
    SELECT
        provider_id,
        provider_name                       AS facility_name,
        provider_city                       AS city,
        provider_state                      AS state,
        NULL::TEXT                          AS facility_type,   -- DRG-level data; no facility type field
        NULL::INTEGER                       AS bed_count,       -- not in inpatient PUF
        total_discharges,
        average_covered_charges             AS avg_charges,
        NULL::JSONB                         AS certifications,
        NULL::INTEGER                       AS shortage_score,
        'cms_inpatient' AS source,
        _loaded_at                          AS source_updated_at
    FROM hcs_bronze.cms_inpatient_puf
    WHERE processed_to_silver = FALSE
      AND provider_id IS NOT NULL
),

cms_hospital AS (
    SELECT
        facility_id                         AS provider_id,
        facility_name,
        city_town                           AS city,
        state,
        hospital_type                       AS facility_type,
        NULL::INTEGER                       AS bed_count,       -- not in hospital general info
        NULL::INTEGER                       AS total_discharges, -- not in hospital general info
        NULL::NUMERIC                       AS avg_charges,     -- not in hospital general info
        NULL::JSONB                         AS certifications,
        NULL::INTEGER                       AS shortage_score,
        'cms_hospital_info' AS source,
        _loaded_at                          AS source_updated_at
    FROM hcs_bronze.cms_hospital_general_info
    WHERE processed_to_silver = FALSE
      AND facility_id IS NOT NULL
),

cms_costs AS (
    SELECT
        provider_id,
        hospital_name                       AS facility_name,
        city,
        state,
        NULL::TEXT                          AS facility_type,   -- not in cost reports PUF
        total_beds                          AS bed_count,
        total_discharges,
        NULL::NUMERIC                       AS avg_charges,     -- avg_charges is billing data, not in cost reports
        NULL::JSONB                         AS certifications,
        NULL::INTEGER                       AS shortage_score,
        'cms_cost_reports' AS source,
        _loaded_at                          AS source_updated_at
    FROM hcs_bronze.cms_cost_reports_puf
    WHERE processed_to_silver = FALSE
      AND provider_id IS NOT NULL
),

acc_tvc AS (
    SELECT
        facility_id AS provider_id,
        facility_name,
        city,
        state,
        certification_type AS facility_type,
        NULL::INTEGER AS bed_count,
        NULL::INTEGER AS total_discharges,
        NULL::NUMERIC AS avg_charges,
        volumes AS certifications,
        NULL::INTEGER AS shortage_score,
        'acc_tvc' AS source,
        source_updated_at
    FROM hcs_bronze.acc_tvc
    WHERE processed_to_silver = FALSE
      AND facility_id IS NOT NULL
),

hrsa AS (
    SELECT
        hpsa_id AS provider_id,
        NULL::TEXT AS facility_name,
        NULL::TEXT AS city,
        state,
        designation_type AS facility_type,
        NULL::INTEGER AS bed_count,
        NULL::INTEGER AS total_discharges,
        NULL::NUMERIC AS avg_charges,
        NULL::JSONB AS certifications,
        score AS shortage_score,
        'hrsa' AS source,
        source_updated_at
    FROM hcs_bronze.hrsa
    WHERE processed_to_silver = FALSE
      AND hpsa_id IS NOT NULL
),

combined AS (
    SELECT * FROM cms_inpatient
    UNION ALL
    SELECT * FROM cms_hospital
    UNION ALL
    SELECT * FROM cms_costs
    UNION ALL
    SELECT * FROM acc_tvc
    UNION ALL
    SELECT * FROM hrsa
)

SELECT DISTINCT ON (provider_id, source)
    gen_random_uuid() AS id,
    provider_id,
    facility_name,
    city,
    state,
    facility_type,
    bed_count,
    total_discharges,
    avg_charges,
    certifications,
    shortage_score,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY provider_id, source, source_updated_at DESC NULLS LAST;
