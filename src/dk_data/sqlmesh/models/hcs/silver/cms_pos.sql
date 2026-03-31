-- SQLMesh Model: Silver CMS Provider of Services (POS)
-- Typed pass-through of CMS POS facility records from hcs_bronze.cms_pos.
-- Links facilities via CCN → hcs_bronze.cms_care_compare for quality/ownership
-- enrichment and hcs_bronze.cms_hospital_general_info for operational detail.
-- Consumers: facility_profile gold, geographic health analysis, network mapping.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_pos,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ccn))
    ),
    grain ccn
);

SELECT
    gen_random_uuid()               AS id,
    b.ccn,
    b.facility_name,
    b.street_address,
    b.city,
    b.state,
    b.zip_code,
    b.provider_type,
    b.beds,
    b.ownership_type,

    -- Quality ratings from Care Compare
    cc.facility_id,
    cc.overall_rating,
    cc.hospital_type,
    cc.emergency_services,

    -- Hospital general info cross-check
    h.telephone_number,
    h.county_parish,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_pos b
LEFT JOIN hcs_bronze.cms_care_compare cc ON b.ccn = cc.facility_id
LEFT JOIN hcs_bronze.cms_hospital_general_info h  ON b.ccn = h.facility_id
WHERE b.ccn IS NOT NULL
