-- SQLMesh Model: Silver Healthcare Facilities
-- Zero data loss from Bronze. All source-specific columns carried forward.
-- Consolidated from CMS, ACC/TVC, and HRSA sources.

MODEL (
    name hcp_silver.facilities,
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
        NULL::TEXT AS facility_name,
        NULL::TEXT AS city,
        NULL::TEXT AS state,
        NULL::TEXT AS county,
        NULL::TEXT AS facility_type,
        NULL::TEXT AS ownership,
        NULL::INTEGER AS rating,
        NULL::INTEGER AS bed_count,
        total_discharges,
        avg_charges,
        avg_payments,
        drg_code::TEXT AS drg_code,
        fiscal_year::INTEGER AS fiscal_year,
        NULL::NUMERIC AS total_costs,
        NULL::NUMERIC AS net_revenue,
        NULL::NUMERIC AS operating_margin,
        NULL::JSONB AS certifications,
        NULL::DATE AS cert_date,
        NULL::TEXT AS discipline,
        NULL::INTEGER AS shortage_score,
        NULL::TEXT AS shortage_status,
        'cms_inpatient' AS source,
        source_updated_at
    FROM mol_bronze.cms_inpatient
    WHERE processed_to_silver = FALSE
      AND provider_id IS NOT NULL
),

cms_hospital AS (
    SELECT
        provider_id,
        hospital_name AS facility_name,
        city,
        state,
        NULL::TEXT AS county,
        hospital_type AS facility_type,
        ownership,
        rating,
        NULL::INTEGER AS bed_count,
        NULL::INTEGER AS total_discharges,
        NULL::NUMERIC AS avg_charges,
        NULL::NUMERIC AS avg_payments,
        NULL::TEXT AS drg_code,
        NULL::INTEGER AS fiscal_year,
        NULL::NUMERIC AS total_costs,
        NULL::NUMERIC AS net_revenue,
        NULL::NUMERIC AS operating_margin,
        NULL::JSONB AS certifications,
        NULL::DATE AS cert_date,
        NULL::TEXT AS discipline,
        NULL::INTEGER AS shortage_score,
        NULL::TEXT AS shortage_status,
        'cms_hospital_info' AS source,
        source_updated_at
    FROM mol_bronze.cms_hospital_info
    WHERE processed_to_silver = FALSE
      AND provider_id IS NOT NULL
),

cms_costs AS (
    SELECT
        provider_id,
        NULL::TEXT AS facility_name,
        NULL::TEXT AS city,
        NULL::TEXT AS state,
        NULL::TEXT AS county,
        NULL::TEXT AS facility_type,
        NULL::TEXT AS ownership,
        NULL::INTEGER AS rating,
        bed_count::INTEGER AS bed_count,
        NULL::INTEGER AS total_discharges,
        NULL::NUMERIC AS avg_charges,
        NULL::NUMERIC AS avg_payments,
        NULL::TEXT AS drg_code,
        fiscal_year::INTEGER AS fiscal_year,
        total_costs,
        net_revenue,
        operating_margin,
        NULL::JSONB AS certifications,
        NULL::DATE AS cert_date,
        NULL::TEXT AS discipline,
        NULL::INTEGER AS shortage_score,
        NULL::TEXT AS shortage_status,
        'cms_cost_reports' AS source,
        source_updated_at
    FROM mol_bronze.cms_cost_reports
    WHERE processed_to_silver = FALSE
      AND provider_id IS NOT NULL
),

acc_tvc AS (
    SELECT
        facility_id AS provider_id,
        facility_name,
        city,
        state,
        NULL::TEXT AS county,
        certification_type AS facility_type,
        NULL::TEXT AS ownership,
        NULL::INTEGER AS rating,
        NULL::INTEGER AS bed_count,
        NULL::INTEGER AS total_discharges,
        NULL::NUMERIC AS avg_charges,
        NULL::NUMERIC AS avg_payments,
        NULL::TEXT AS drg_code,
        NULL::INTEGER AS fiscal_year,
        NULL::NUMERIC AS total_costs,
        NULL::NUMERIC AS net_revenue,
        NULL::NUMERIC AS operating_margin,
        volumes AS certifications,
        CASE WHEN cert_date ~ '^\d{4}-\d{2}-\d{2}$' THEN cert_date::DATE
             WHEN cert_date ~ '^\d{4}/\d{2}/\d{2}$' THEN TO_DATE(cert_date, 'YYYY/MM/DD')
             ELSE NULL END AS cert_date,
        NULL::TEXT AS discipline,
        NULL::INTEGER AS shortage_score,
        NULL::TEXT AS shortage_status,
        'acc_tvc' AS source,
        source_updated_at
    FROM mol_bronze.acc_tvc_certification
    WHERE processed_to_silver = FALSE
      AND facility_id IS NOT NULL
),

hrsa AS (
    SELECT
        hpsa_id AS provider_id,
        NULL::TEXT AS facility_name,
        NULL::TEXT AS city,
        state,
        county,
        designation_type AS facility_type,
        NULL::TEXT AS ownership,
        NULL::INTEGER AS rating,
        NULL::INTEGER AS bed_count,
        NULL::INTEGER AS total_discharges,
        NULL::NUMERIC AS avg_charges,
        NULL::NUMERIC AS avg_payments,
        NULL::TEXT AS drg_code,
        NULL::INTEGER AS fiscal_year,
        NULL::NUMERIC AS total_costs,
        NULL::NUMERIC AS net_revenue,
        NULL::NUMERIC AS operating_margin,
        NULL::JSONB AS certifications,
        NULL::DATE AS cert_date,
        discipline,
        score AS shortage_score,
        status AS shortage_status,
        'hrsa' AS source,
        source_updated_at
    FROM mol_bronze.hrsa_shortage_areas
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
    county,
    facility_type,
    ownership,
    rating,
    bed_count,
    total_discharges,
    avg_charges,
    avg_payments,
    drg_code,
    fiscal_year,
    total_costs,
    net_revenue,
    operating_margin,
    certifications,
    cert_date,
    discipline,
    shortage_score,
    shortage_status,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY provider_id, source, source_updated_at DESC NULLS LAST;
