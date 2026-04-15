-- SQLMesh Model: Bronze CMS Hospital General Information
-- Typed pass-through from hcs_raw.cms_hospital_general_info
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_hospital_general_info,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (facility_id, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (facility_id, _source_year)
);

SELECT
    id,
    facility_id,
    facility_name,
    address,
    city_town,
    state,
    zip_code,
    county_parish,
    telephone_number,
    hospital_type,
    hospital_ownership,
    emergency_services,
    meets_criteria_for_birthing_friendly_designation,
    hospital_overall_rating,
    hospital_overall_rating_footnote,
    -- Item 27b: per-measure quality ratings
    mortality_heart_attack,
    mortality_heart_failure,
    mortality_pneumonia,
    mortality_stroke,
    mortality_copd,
    readmission_heart_attack,
    readmission_heart_failure,
    readmission_pneumonia,
    readmission_stroke,
    safety_of_care_rating,
    patient_experience_rating,
    timeliness_of_care_rating,
    efficient_use_of_imaging,
    hai_rate,
    overall_rating,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_hospital_general_info;
