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

    -- Hospital identifiers (facility_id maps to provider_id in downstream models)
    r.facility_id::TEXT AS provider_id,
    r.facility_name::TEXT AS hospital_name,

    -- Location
    r.address::TEXT AS address,
    r.city_town::TEXT AS city,
    r.state::TEXT AS state,
    r.zip_code::TEXT AS zip_code,
    r.county_parish::TEXT AS county_name,

    -- Contact
    r.telephone_number::TEXT AS phone_number,

    -- Classification
    r.hospital_type::TEXT AS hospital_type,
    r.hospital_ownership::TEXT AS ownership,

    -- Quality
    r.emergency_services::BOOLEAN AS emergency_services,
    r.hospital_overall_rating::INTEGER AS rating,

    -- Source tracking
    r._source_hash::TEXT AS source_hash,
    r._loaded_at::TIMESTAMPTZ AS source_updated_at,
    'cms_hospital_general_info' AS source,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.cms_hospital_general_info r
WHERE r.facility_id IS NOT NULL;
