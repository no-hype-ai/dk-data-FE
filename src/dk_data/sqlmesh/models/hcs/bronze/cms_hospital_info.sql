-- SQLMesh Model: Bronze CMS Hospital Info
-- Transforms raw CMS Hospital General Information CSV data to Bronze typed columns
-- Source: hcs_raw.cms_hospital_general_info (flat typed table, loaded by cms_hospital_info.py)
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcs_bronze.cms_hospital_info,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key provider_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id))
    ),
    grain provider_id
);

SELECT
    gen_random_uuid() AS id,

    -- Raw column names retained verbatim per FR-001. The legacy `provider_id`
    -- alias is kept alongside `facility_id` for downstream compat.
    r.facility_id::TEXT                                      AS facility_id,
    r.facility_id::TEXT                                      AS provider_id,
    r.facility_name::TEXT                                    AS facility_name,
    r.address::TEXT                                          AS address,
    r.city_town::TEXT                                        AS city_town,
    r.state::TEXT                                            AS state,
    r.zip_code::TEXT                                         AS zip_code,
    r.county_parish::TEXT                                    AS county_parish,
    r.telephone_number::TEXT                                 AS telephone_number,
    r.hospital_type::TEXT                                    AS hospital_type,
    r.hospital_ownership::TEXT                               AS hospital_ownership,
    r.emergency_services::BOOLEAN                            AS emergency_services,
    r.hospital_overall_rating::INTEGER                       AS hospital_overall_rating,
    r.hospital_overall_rating_footnote::TEXT                 AS hospital_overall_rating_footnote,
    r.meets_criteria_for_birthing_friendly_designation::TEXT AS meets_criteria_for_birthing_friendly_designation,

    -- Source tracking
    r._source_hash::TEXT AS source_hash,
    r._loaded_at::TIMESTAMPTZ AS source_updated_at,
    'cms_hospital_general_info' AS source,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.cms_hospital_general_info r
WHERE r.facility_id IS NOT NULL
  AND r._loaded_at BETWEEN @start_dt AND @end_dt;
