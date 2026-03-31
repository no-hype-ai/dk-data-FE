-- SQLMesh Model: Silver CMS Change of Ownership (CHOW)
-- Typed pass-through of CMS CHOW records from hcs_bronze.cms_chow.
-- Links facilities via CCN → hcs_bronze.cms_care_compare (facility master) and
-- hcs_bronze.cms_hospital_general_info for operational context.
-- Consumers: facility ownership chain analysis, M&A tracking, market intelligence.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_chow,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ccn, effective_date))
    ),
    grain (ccn, effective_date)
);

SELECT
    gen_random_uuid()               AS id,
    b.ccn,
    b.previous_owner,
    b.new_owner,
    b.effective_date,
    b.provider_type,

    -- Facility context from Care Compare (canonical facility master)
    cc.facility_id,
    cc.facility_name,
    cc.city,
    cc.state,
    cc.zip_code,
    cc.hospital_type,
    cc.hospital_ownership         AS current_ownership,

    -- Operational detail from hospital general info
    h.hospital_type               AS hgi_hospital_type,
    h.emergency_services,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_chow b
LEFT JOIN hcs_bronze.cms_care_compare cc ON b.ccn = cc.facility_id
LEFT JOIN hcs_bronze.cms_hospital_general_info h  ON b.ccn = h.facility_id
WHERE b.ccn IS NOT NULL
  AND b.effective_date IS NOT NULL
