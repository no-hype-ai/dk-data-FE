-- SQLMesh Model: Silver CMS Magnet Hospital Designations
-- Typed pass-through of CMS Magnet designation records from hcs_bronze.cms_magnet.
-- Links facilities via (facility_name, city, state) → hcs_bronze.cms_care_compare
-- to resolve facility_id for downstream joins; fuzzy-safe with LOWER() normalization.
-- Consumers: facility_profile gold, quality benchmarking, network analysis.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_magnet,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (facility_name))
    ),
    grain (facility_name, city, state)
);

SELECT DISTINCT ON (b.facility_name, b.city, b.state)
    gen_random_uuid()               AS id,
    b.facility_name,
    b.city,
    b.state,
    b.designation_year,
    b.designation_date,

    -- Facility master linkage via name+city+state match
    cc.facility_id,
    cc.address,
    cc.zip_code,
    cc.county_name,
    cc.phone_number,
    cc.hospital_type,
    cc.hospital_ownership,
    cc.emergency_services,
    cc.overall_rating,

    b.source,
    b.ingested_at,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_magnet b
LEFT JOIN hcs_bronze.cms_care_compare cc
       ON LOWER(cc.facility_name) = LOWER(b.facility_name)
      AND LOWER(cc.city)          = LOWER(b.city)
      AND LOWER(cc.state)         = LOWER(b.state)
WHERE b.facility_name IS NOT NULL
ORDER BY b.facility_name, b.city, b.state, b.ingested_at DESC
