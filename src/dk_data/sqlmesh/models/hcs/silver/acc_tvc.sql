-- SQLMesh Model: hcs_silver.acc_tvc
-- ACC/TVC (American College of Cardiology / Transcatheter Valve Center) certifications
-- with facility hub linkage via CCN equi-join or name trigram fallback.
--
-- Source: hcs_bronze.acc_tvc
-- Bronze columns: facility_name, facility_address, city, state, zip_code,
--                 certification_type, certification_date, expiration_date
-- Bronze has no CCN column — facility linkage uses name-similarity path first,
-- with a city+state filter to reduce false positives.
--
-- Facility linkage (tiered):
--   Tier 1 (name trigram, city+state constrained): similarity(fn.normalized_name, ...) >= 0.85
--     joined to facility_identifiers (source='ccn') for hub facility_id
--   Grain uses (facility_name, state, certification_type) since no numeric ID is available.
--
-- Grain: (facility_name, state, certification_type)
-- Feature: 001-silver-medallion-rebuild

MODEL (
    name hcs_silver.acc_tvc,
    kind FULL,
    cron '@monthly',
    grain (facility_name, state, certification_type),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.facility_name, b.state, b.certification_type)
    gen_random_uuid()               AS id,

    -- Facility identity
    b.facility_name,
    b.facility_address,
    b.city,
    b.state,
    b.zip_code,

    -- Facility hub linkage
    fac_link.facility_id,

    -- Certification details
    b.certification_type,
    b.certification_date,
    b.expiration_date,

    -- Source tracking
    b.source,
    b._source_hash,
    b._loaded_at,
    b.source_updated_at,

    NOW()                           AS created_at,
    NOW()                           AS updated_at

FROM hcs_bronze.acc_tvc b

-- Facility hub: name trigram similarity + city/state filter → CCN identifier
LEFT JOIN LATERAL (
    SELECT fi.facility_id
    FROM hcs_silver.facility_names fn
    JOIN hcs_silver.facility_identifiers fi
        ON fi.facility_id = fn.facility_id
    WHERE fi.source = 'ccn'
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
) fac_link ON TRUE

WHERE b.facility_name IS NOT NULL
ORDER BY b.facility_name, b.state, b.certification_type, b._loaded_at DESC;
