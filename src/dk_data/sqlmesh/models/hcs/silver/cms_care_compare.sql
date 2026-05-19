-- SQLMesh Model: Silver CMS Care Compare Facility Master
-- Typed pass-through of CMS Care Compare facility records from hcs_bronze.cms_care_compare.
-- Serves as the canonical facility master for HCS silver joins (quality, affiliation, etc.).
-- Consumers: facility_profile gold, cms_facility_360 gold, downstream silver enrichments.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_care_compare,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (facility_id))
    ),
    grain facility_id
);

SELECT DISTINCT ON (b.facility_id)
    gen_random_uuid()               AS id,
    b.facility_id,
    b.facility_name,
    b.address,
    b.city,
    b.state,
    b.zip_code,
    b.county_name,
    b.phone_number,
    b.hospital_type,
    b.hospital_ownership,
    b.emergency_services,
    b.overall_rating,

    b.source,
    b.ingested_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_care_compare b
WHERE b.facility_id IS NOT NULL
ORDER BY b.facility_id, b.ingested_at DESC
