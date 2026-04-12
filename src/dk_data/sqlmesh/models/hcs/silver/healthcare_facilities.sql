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
    grain (provider_id, source),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH cms_inpatient AS (
    SELECT
        provider_id,
        provider_name                       AS facility_name,
        provider_street_address             AS address,
        provider_city                       AS city,
        provider_state                      AS state,
        provider_zip_code                   AS zip_code,
        provider_state_fips                 AS state_fips,
        provider_ruca                       AS ruca,
        hospital_referral_region_desc,
        NULL::TEXT                          AS facility_type,   -- DRG-level data; no facility type field
        NULL::INTEGER                       AS bed_count,       -- not in inpatient PUF
        total_discharges,
        average_covered_charges             AS avg_charges,
        average_total_payments              AS avg_total_payments,
        average_medicare_payments           AS avg_medicare_payments,
        drg_cd,
        drg_definition,
        NULL::TEXT                          AS county,
        NULL::TEXT                          AS phone_number,
        NULL::TEXT                          AS hospital_ownership,
        NULL::TEXT                          AS emergency_services,
        NULL::INTEGER                       AS hospital_overall_rating,
        NULL::JSONB                         AS certifications,
        NULL::INTEGER                       AS shortage_score,
        NULL::TEXT                          AS hpsa_name,
        NULL::TEXT                          AS hpsa_type,
        NULL::TEXT                          AS rural_status,
        NULL::TEXT                          AS facility_address,
        NULL::TEXT                          AS certification_type,
        NULL::DATE                          AS certification_date,
        NULL::DATE                          AS expiration_date,
        NULL::NUMERIC                       AS net_patient_revenue,
        NULL::NUMERIC                       AS total_operating_expenses,
        NULL::NUMERIC                       AS operating_margin,
        'cms_inpatient' AS source,
        _source_year,
        _source_hash,
        _loaded_at                          AS source_updated_at
    FROM hcs_bronze.cms_inpatient_puf
    WHERE provider_id IS NOT NULL
),

cms_hospital AS (
    SELECT
        facility_id                         AS provider_id,
        facility_name,
        address,
        city_town                           AS city,
        state,
        zip_code,
        NULL::TEXT                          AS state_fips,
        NULL::TEXT                          AS ruca,
        NULL::TEXT                          AS hospital_referral_region_desc,
        hospital_type                       AS facility_type,
        NULL::INTEGER                       AS bed_count,       -- not in hospital general info
        NULL::INTEGER                       AS total_discharges, -- not in hospital general info
        NULL::NUMERIC                       AS avg_charges,     -- not in hospital general info
        NULL::NUMERIC                       AS avg_total_payments,
        NULL::NUMERIC                       AS avg_medicare_payments,
        NULL::TEXT                          AS drg_cd,
        NULL::TEXT                          AS drg_definition,
        county_parish                       AS county,
        telephone_number                    AS phone_number,
        hospital_ownership,
        emergency_services,
        hospital_overall_rating,
        NULL::JSONB                         AS certifications,
        NULL::INTEGER                       AS shortage_score,
        NULL::TEXT                          AS hpsa_name,
        NULL::TEXT                          AS hpsa_type,
        NULL::TEXT                          AS rural_status,
        NULL::TEXT                          AS facility_address,
        NULL::TEXT                          AS certification_type,
        NULL::DATE                          AS certification_date,
        NULL::DATE                          AS expiration_date,
        NULL::NUMERIC                       AS net_patient_revenue,
        NULL::NUMERIC                       AS total_operating_expenses,
        NULL::NUMERIC                       AS operating_margin,
        'cms_hospital_info' AS source,
        _source_year,
        _source_hash,
        _loaded_at                          AS source_updated_at
    FROM hcs_bronze.cms_hospital_general_info
    WHERE facility_id IS NOT NULL
),

cms_costs AS (
    SELECT
        provider_id,
        hospital_name                       AS facility_name,
        NULL::TEXT                          AS address,
        city,
        state,
        zip_code,
        NULL::TEXT                          AS state_fips,
        NULL::TEXT                          AS ruca,
        NULL::TEXT                          AS hospital_referral_region_desc,
        NULL::TEXT                          AS facility_type,   -- not in cost reports PUF
        total_beds                          AS bed_count,
        total_discharges,
        NULL::NUMERIC                       AS avg_charges,
        NULL::NUMERIC                       AS avg_total_payments,
        NULL::NUMERIC                       AS avg_medicare_payments,
        NULL::TEXT                          AS drg_cd,
        NULL::TEXT                          AS drg_definition,
        NULL::TEXT                          AS county,
        NULL::TEXT                          AS phone_number,
        NULL::TEXT                          AS hospital_ownership,
        NULL::TEXT                          AS emergency_services,
        NULL::INTEGER                       AS hospital_overall_rating,
        NULL::JSONB                         AS certifications,
        NULL::INTEGER                       AS shortage_score,
        NULL::TEXT                          AS hpsa_name,
        NULL::TEXT                          AS hpsa_type,
        NULL::TEXT                          AS rural_status,
        NULL::TEXT                          AS facility_address,
        NULL::TEXT                          AS certification_type,
        NULL::DATE                          AS certification_date,
        NULL::DATE                          AS expiration_date,
        net_patient_revenue,
        total_operating_expenses,
        operating_margin,
        'cms_cost_reports' AS source,
        _source_year,
        _source_hash,
        _loaded_at                          AS source_updated_at
    FROM hcs_bronze.cms_cost_reports_puf
    WHERE provider_id IS NOT NULL
),

acc_tvc AS (
    SELECT
        -- facility_name + state used as provider_id; raw table has no numeric facility ID
        (facility_name || '_' || state)  AS provider_id,
        facility_name,
        facility_address                 AS address,
        city,
        state,
        zip_code,
        NULL::TEXT                       AS state_fips,
        NULL::TEXT                       AS ruca,
        NULL::TEXT                       AS hospital_referral_region_desc,
        certification_type               AS facility_type,
        NULL::INTEGER                    AS bed_count,
        NULL::INTEGER                    AS total_discharges,
        NULL::NUMERIC                    AS avg_charges,
        NULL::NUMERIC                    AS avg_total_payments,
        NULL::NUMERIC                    AS avg_medicare_payments,
        NULL::TEXT                       AS drg_cd,
        NULL::TEXT                       AS drg_definition,
        NULL::TEXT                       AS county,
        NULL::TEXT                       AS phone_number,
        NULL::TEXT                       AS hospital_ownership,
        NULL::TEXT                       AS emergency_services,
        NULL::INTEGER                    AS hospital_overall_rating,
        -- encode cert dates as JSONB; raw table has no volumes column
        jsonb_build_object(
            'certification_date', certification_date,
            'expiration_date',    expiration_date
        )                                AS certifications,
        NULL::INTEGER                    AS shortage_score,
        NULL::TEXT                       AS hpsa_name,
        NULL::TEXT                       AS hpsa_type,
        NULL::TEXT                       AS rural_status,
        facility_address                 AS facility_address,
        certification_type               AS certification_type,
        certification_date               AS certification_date,
        expiration_date                  AS expiration_date,
        NULL::NUMERIC                    AS net_patient_revenue,
        NULL::NUMERIC                    AS total_operating_expenses,
        NULL::NUMERIC                    AS operating_margin,
        'acc_tvc'                        AS source,
        NULL::INTEGER                    AS _source_year,
        _source_hash,
        source_updated_at
    FROM hcs_bronze.acc_tvc
    WHERE facility_name IS NOT NULL
),

hrsa AS (
    SELECT
        hpsa_id AS provider_id,
        hpsa_name AS facility_name,
        NULL::TEXT AS address,
        NULL::TEXT AS city,
        state,
        NULL::TEXT AS zip_code,
        NULL::TEXT AS state_fips,
        NULL::TEXT AS ruca,
        NULL::TEXT AS hospital_referral_region_desc,
        designation_type AS facility_type,
        NULL::INTEGER AS bed_count,
        NULL::INTEGER AS total_discharges,
        NULL::NUMERIC AS avg_charges,
        NULL::NUMERIC AS avg_total_payments,
        NULL::NUMERIC AS avg_medicare_payments,
        NULL::TEXT AS drg_cd,
        NULL::TEXT AS drg_definition,
        county,
        NULL::TEXT AS phone_number,
        NULL::TEXT AS hospital_ownership,
        NULL::TEXT AS emergency_services,
        NULL::INTEGER AS hospital_overall_rating,
        NULL::JSONB AS certifications,
        score AS shortage_score,
        hpsa_name,
        hpsa_type,
        rural_status,
        NULL::TEXT AS facility_address,
        NULL::TEXT AS certification_type,
        designation_date AS certification_date,
        NULL::DATE AS expiration_date,
        NULL::NUMERIC AS net_patient_revenue,
        NULL::NUMERIC AS total_operating_expenses,
        NULL::NUMERIC AS operating_margin,
        'hrsa' AS source,
        NULL::INTEGER AS _source_year,
        _source_hash,
        source_updated_at
    FROM hcs_bronze.hrsa
    WHERE hpsa_id IS NOT NULL
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
    address,
    city,
    state,
    zip_code,
    state_fips,
    ruca,
    hospital_referral_region_desc,
    facility_type,
    bed_count,
    total_discharges,
    avg_charges,
    avg_total_payments,
    avg_medicare_payments,
    drg_cd,
    drg_definition,
    county,
    phone_number,
    hospital_ownership,
    emergency_services,
    hospital_overall_rating,
    certifications,
    shortage_score,
    hpsa_name,
    hpsa_type,
    rural_status,
    facility_address,
    certification_type,
    certification_date,
    expiration_date,
    net_patient_revenue,
    total_operating_expenses,
    operating_margin,
    source,
    _source_year,
    _source_hash,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY provider_id, source, source_updated_at DESC NULLS LAST;
