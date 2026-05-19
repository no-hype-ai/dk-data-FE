-- SQLMesh Model: hcs_silver.hrsa
-- HRSA Health Professional Shortage Areas (HPSA) with facility hub linkage.
--
-- Source: hcs_bronze.hrsa (HPSA shortage area designations)
-- Bronze grain: hpsa_id — each row is a designated shortage area, not a specific facility.
-- hpsa_name is used for fuzzy facility matching where geographic areas overlap hospital names.
--
-- Facility linkage (trigram similarity):
--   hpsa_name → hcs_silver.facility_names (similarity >= 0.85) → facility_id via CCN
--   Note: shortage areas often correspond to counties/regions, not single facilities.
--         Match is best-effort; facility_id NULL is expected for geographic HPSA records.
--
-- Grain: hpsa_id
-- Feature: 001-silver-medallion-rebuild

MODEL (
    name hcs_silver.hrsa,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key hpsa_id
    ),
    cron '@monthly',
    grain hpsa_id
);

SELECT
    gen_random_uuid()               AS id,

    -- HPSA identifiers
    b.hpsa_id,
    b.hpsa_name,
    b.hpsa_type,
    b.designation_type,
    b.state_abbr,
    b.state,
    b.county_name,
    b.county,
    b.discipline,
    b.hpsa_score,
    b.score,
    b.designation_date,
    b.rural_status,
    b.status,

    -- Facility hub linkage via trigram similarity on hpsa_name → CCN
    fac_link.facility_id,

    -- Source tracking
    b.source,
    b._source_hash,
    b._fetched_at,
    b.source_updated_at,

    NOW()                           AS created_at,
    NOW()                           AS updated_at

FROM hcs_bronze.hrsa b

-- Facility linkage: hpsa_name trigram → facility_names → facility_identifiers (CCN)
LEFT JOIN LATERAL (
    SELECT fi.facility_id
    FROM hcs_silver.facility_names fn
    JOIN hcs_silver.facility_identifiers fi
        ON fi.facility_id = fn.facility_id
    WHERE fi.source = 'ccn'
      AND b.hpsa_name IS NOT NULL
      AND similarity(
            fn.normalized_name,
            LOWER(REGEXP_REPLACE(b.hpsa_name, '[^a-zA-Z0-9 ]', '', 'g'))
          ) >= 0.85
    ORDER BY similarity(
               fn.normalized_name,
               LOWER(REGEXP_REPLACE(b.hpsa_name, '[^a-zA-Z0-9 ]', '', 'g'))
             ) DESC
    LIMIT 1
) fac_link ON TRUE

WHERE b.hpsa_id IS NOT NULL;
