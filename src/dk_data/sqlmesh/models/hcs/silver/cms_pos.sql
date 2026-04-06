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

SELECT DISTINCT ON (b.ccn)
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
    cc.hospital_ownership           AS cc_hospital_ownership,
    cc.emergency_services,
    cc.county_name,
    cc.phone_number                 AS cc_phone_number,

    -- Hospital general info cross-check (most recent year chosen by ORDER BY below)
    h.facility_name                 AS hgi_facility_name,
    h.address                       AS hgi_address,
    h.telephone_number,
    h.county_parish,
    h.hospital_ownership            AS hgi_hospital_ownership,
    h.hospital_overall_rating,
    h.hospital_overall_rating_footnote,
    h.meets_criteria_for_birthing_friendly_designation,
    h.emergency_services            AS hgi_emergency_services,

    b.source,
    b.ingested_at,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_pos b
LEFT JOIN hcs_bronze.cms_care_compare cc ON b.ccn = cc.facility_id
LEFT JOIN hcs_bronze.cms_hospital_general_info h  ON b.ccn = h.facility_id
WHERE b.ccn IS NOT NULL
ORDER BY b.ccn, h._source_year DESC NULLS LAST
