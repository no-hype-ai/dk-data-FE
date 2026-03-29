-- SQLMesh Model: Bronze CMS Hospital General Information
-- Transforms flat hcs_raw.cms_hospital_info typed columns to Bronze canonical schema
-- Part of: 015-assessment-dashboard-integration
--
-- Source: hcs_raw.cms_hospital_info (flat typed columns, populated by load_cms_hospital_info)
-- Grain: one row per provider_id

MODEL (
    name hcs_bronze.cms_hospital_info,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key provider_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id)),
        unique_values(columns := (provider_id))
    ),
    grain provider_id
);

SELECT
    gen_random_uuid() AS id,

    -- Provider identity
    r.provider_id::TEXT             AS provider_id,
    r.hospital_name::TEXT           AS hospital_name,

    -- Location
    r.address::TEXT                 AS address,
    r.city::TEXT                    AS city,
    r.state::TEXT                   AS state,
    r.zip_code::TEXT                AS zip_code,
    r.county_name::TEXT             AS county,

    -- Facility classification
    r.hospital_type::TEXT           AS hospital_type,
    r.hospital_ownership::TEXT      AS ownership,
    r.emergency_services::BOOLEAN   AS emergency_services,

    -- Quality rating (1–5 stars, NULL when not available)
    r.hospital_overall_rating::INTEGER  AS rating,

    -- Source tracking
    'cms_hospital_info'             AS source,
    r._loaded_at                    AS source_updated_at,
    FALSE                           AS processed_to_silver,
    NOW()                           AS created_at

FROM hcs_raw.cms_hospital_info r
WHERE
    r.provider_id IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
