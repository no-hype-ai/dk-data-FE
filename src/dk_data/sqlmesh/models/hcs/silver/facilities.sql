-- T039: hcs_silver.facilities — healthcare facility hub
-- Hub architecture: one row per unique facility, keyed by CCN (primary).
-- Columns: facility_id, ccn, npi_type2, ncdr_id, facility_name, city, state, zip,
--          ownership_type, first_seen_at, last_updated_at.

MODEL (
    name hcs_silver.facilities,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key facility_id
    ),
    grain facility_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH pos_facilities AS (
    SELECT
        ('x' || substr(md5(COALESCE(provider_transaction_access_number, npi, facility_name)), 1, 16))::bit(64)::bigint AS facility_id,
        NULLIF(provider_transaction_access_number, '')                           AS ccn,
        NULLIF(npi, '')                                                          AS npi_type2,
        NULL::text                                                               AS ncdr_id,
        COALESCE(facility_name, organization_name, npi)                         AS facility_name,
        NULLIF(city, '')                                                         AS city,
        NULLIF(state, '')                                                        AS state,
        NULLIF(zip, '')                                                          AS zip,
        NULLIF(ownership_type, '')                                               AS ownership_type,
        1                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pos
    WHERE COALESCE(provider_transaction_access_number, npi, facility_name) IS NOT NULL
),

hospital_info AS (
    SELECT
        ('x' || substr(md5(COALESCE(ccn, provider_id, facility_name)), 1, 16))::bit(64)::bigint AS facility_id,
        NULLIF(ccn, '')                                                          AS ccn,
        NULLIF(provider_id, '')                                                  AS npi_type2,
        NULL::text                                                               AS ncdr_id,
        COALESCE(hospital_name, facility_name, provider_id)                     AS facility_name,
        NULLIF(city, '')                                                         AS city,
        NULLIF(state, '')                                                        AS state,
        NULLIF(zip_code, '')                                                     AS zip,
        NULL::text                                                               AS ownership_type,
        2                                                                        AS src_priority,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_hospital_info
    WHERE COALESCE(ccn, provider_id, hospital_name) IS NOT NULL
),

all_facilities AS (
    SELECT * FROM pos_facilities
    UNION ALL
    SELECT * FROM hospital_info
),

deduped AS (
    SELECT DISTINCT ON (facility_id)
        facility_id,
        ccn,
        npi_type2,
        ncdr_id,
        facility_name,
        city,
        state,
        zip,
        ownership_type,
        first_seen_at
    FROM all_facilities
    ORDER BY facility_id, src_priority ASC
)

SELECT
    facility_id,
    ccn,
    npi_type2,
    ncdr_id,
    facility_name,
    city,
    state,
    zip,
    ownership_type,
    COALESCE(first_seen_at, NOW()) AS first_seen_at,
    NOW()                          AS last_updated_at
FROM deduped
WHERE facility_name IS NOT NULL;

-- CREATE INDEX IF NOT EXISTS hcs_silver_fac_name_idx ON hcs_silver.facilities (facility_name);
-- CREATE INDEX IF NOT EXISTS hcs_silver_fac_gin_idx ON hcs_silver.facilities USING GIN (LOWER(facility_name) gin_trgm_ops);
-- CREATE INDEX IF NOT EXISTS hcs_silver_fac_state_city_idx ON hcs_silver.facilities (state, city);
