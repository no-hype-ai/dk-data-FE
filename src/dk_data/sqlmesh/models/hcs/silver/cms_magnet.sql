-- SQLMesh Model: Silver CMS Magnet Hospital Designations
-- Typed pass-through of CMS Magnet designation records from hcs_bronze.cms_magnet.
-- Links facilities via the facility hub (hcs_silver.facility_identifiers/facility_names)
-- and augments with contact/detail data from hcs_bronze.cms_care_compare.
--
-- Facility linkage (tiered):
--   Tier 1 (CCN equi-join): care_compare.facility_id = hcs_silver.facility_identifiers (source='ccn')
--   Tier 2 (name trigram fallback): similarity(fn.normalized_name, ...) >= 0.85
--
-- Consumers: facility_profile gold, quality benchmarking, network analysis.
-- Part of: issue #172 H3 / 001-silver-medallion-rebuild

MODEL (
    name hcs_silver.cms_magnet,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (facility_name))
    ),
    grain (facility_name, city, state),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.facility_name, b.city, b.state)
    gen_random_uuid()               AS id,
    b.facility_name,
    b.city,
    b.state,
    b.designation_year,
    b.designation_date,

    -- Facility hub linkage (CCN path, then name-similarity fallback)
    COALESCE(fi_link.facility_id, fn_link.facility_id) AS facility_id,

    -- Supplemental detail from care_compare (name+city+state match)
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
    NOW()                           AS created_at

FROM hcs_bronze.cms_magnet b

-- Join care_compare for supplemental details (name+city+state)
LEFT JOIN hcs_bronze.cms_care_compare cc
       ON LOWER(cc.facility_name) = LOWER(b.facility_name)
      AND LOWER(cc.city)          = LOWER(b.city)
      AND LOWER(cc.state)         = LOWER(b.state)

-- Tier 1: care_compare.facility_id → facility hub via CCN
LEFT JOIN LATERAL (
    SELECT fi.facility_id
    FROM hcs_silver.facility_identifiers fi
    WHERE fi.source = 'ccn'
      AND fi.identifier = cc.facility_id
    LIMIT 1
) fi_link ON TRUE

-- Tier 2: facility name trigram fallback (requires pg_trgm; threshold 0.85)
LEFT JOIN LATERAL (
    SELECT fn.facility_id
    FROM hcs_silver.facility_names fn
    WHERE fi_link.facility_id IS NULL
      AND b.facility_name IS NOT NULL
      AND similarity(
            fn.normalized_name,
            LOWER(REGEXP_REPLACE(b.facility_name, '[^a-zA-Z0-9 ]', '', 'g'))
          ) >= 0.85
    ORDER BY similarity(
               fn.normalized_name,
               LOWER(REGEXP_REPLACE(b.facility_name, '[^a-zA-Z0-9 ]', '', 'g'))
             ) DESC
    LIMIT 1
) fn_link ON TRUE

WHERE b.facility_name IS NOT NULL
ORDER BY b.facility_name, b.city, b.state, b.ingested_at DESC;
