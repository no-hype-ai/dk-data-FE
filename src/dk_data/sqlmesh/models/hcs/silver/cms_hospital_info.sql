-- SQLMesh Model: Silver CMS Hospital Info
-- Typed pass-through of hcs_bronze.cms_hospital_info (legacy hospital general info source).
-- This bronze model reads from hcs_raw.cms_hospital_general_info via the older
-- cms_hospital_info.py loader. No upstream joins needed — this IS the facility reference data.
-- Consumers: facility lookup, hospital quality analysis, provider affiliation context.

MODEL (
    name hcs_silver.cms_hospital_info,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (provider_id))
    ),
    grain provider_id
);

SELECT
    gen_random_uuid()           AS id,
    b.provider_id,
    b.hospital_name,
    b.address,
    b.city,
    b.state,
    b.zip_code,
    b.county_name,
    b.phone_number,
    b.hospital_type,
    b.ownership,
    b.emergency_services,
    b.rating,
    b.source_hash,
    b.source,
    b.source_updated_at,
    NOW()                       AS created_at

FROM hcs_bronze.cms_hospital_info b
WHERE b.provider_id IS NOT NULL
