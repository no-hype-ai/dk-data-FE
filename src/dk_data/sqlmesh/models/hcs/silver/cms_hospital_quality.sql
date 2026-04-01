-- SQLMesh Model: Silver CMS Hospital Quality Ratings
-- Typed pass-through of CMS hospital quality measures from hcs_bronze.cms_hospital_quality.
-- Links to facility master via facility_id → hcs_bronze.cms_care_compare.
-- Consumers: facility_profile gold, cms_facility_360 gold.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_hospital_quality,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (facility_id))
    ),
    grain facility_id
);

SELECT
    gen_random_uuid()               AS id,
    b.facility_id,
    b.facility_name,
    b.overall_rating,
    b.mortality_rating,
    b.safety_rating,
    b.readmission_rating,
    b.patient_experience_rating,
    b.timeliness_rating,

    -- Facility context from Care Compare
    c.address,
    c.city,
    c.state,
    c.zip_code,
    c.hospital_type,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_hospital_quality b
LEFT JOIN hcs_bronze.cms_care_compare c ON b.facility_id = c.facility_id
WHERE b.facility_id IS NOT NULL
