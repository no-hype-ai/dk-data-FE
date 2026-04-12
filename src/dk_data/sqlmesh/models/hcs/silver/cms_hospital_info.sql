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
    grain provider_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.facility_id)
    b.facility_id,
    b.provider_id,
    b.facility_name,
    b.address,
    b.city_town,
    b.state,
    b.zip_code,
    b.county_parish,
    b.telephone_number,
    b.hospital_type,
    b.hospital_ownership,
    b.emergency_services,
    b.hospital_overall_rating,
    b.hospital_overall_rating_footnote,
    b.meets_criteria_for_birthing_friendly_designation,
    b.source_hash,
    b.source,
    b.source_updated_at
FROM hcs_bronze.cms_hospital_info b
WHERE b.facility_id IS NOT NULL
ORDER BY b.facility_id, b.source_updated_at DESC
