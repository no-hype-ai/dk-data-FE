-- T039: hcs_silver.facility_names — facility name index
-- Canonical + alternative name variants for fuzzy resolution.

MODEL (
    name hcs_silver.facility_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (normalized_name, facility_id, source)
    ),
    grain (normalized_name, facility_id, source)
);

WITH pos_names AS (
    SELECT
        LOWER(TRIM(COALESCE(facility_name, organization_name, npi)))            AS normalized_name,
        ('x' || substr(md5(COALESCE(provider_transaction_access_number, npi, facility_name)), 1, 16))::bit(64)::bigint AS facility_id,
        'canonical'                                                              AS name_kind,
        'cms_pos'                                                                AS source,
        1.0                                                                      AS confidence,
        COALESCE(facility_name, organization_name, npi)                         AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_pos
    WHERE COALESCE(facility_name, organization_name) IS NOT NULL
      AND COALESCE(provider_transaction_access_number, npi, facility_name) IS NOT NULL
),

hospital_names AS (
    SELECT
        LOWER(TRIM(COALESCE(hospital_name, facility_name, provider_id)))        AS normalized_name,
        ('x' || substr(md5(COALESCE(ccn, provider_id, facility_name)), 1, 16))::bit(64)::bigint AS facility_id,
        'canonical'                                                              AS name_kind,
        'cms_hospital_info'                                                      AS source,
        1.0                                                                      AS confidence,
        COALESCE(hospital_name, facility_name, provider_id)                     AS display_name,
        ingested_at                                                              AS first_seen_at
    FROM hcs_bronze.cms_hospital_info
    WHERE COALESCE(hospital_name, facility_name) IS NOT NULL
),

all_names AS (
    SELECT * FROM pos_names
    UNION ALL
    SELECT * FROM hospital_names
)

SELECT DISTINCT ON (normalized_name, facility_id, source)
    normalized_name,
    facility_id,
    name_kind,
    source,
    confidence,
    display_name,
    COALESCE(first_seen_at, NOW()) AS first_seen_at
FROM all_names
WHERE normalized_name IS NOT NULL
  AND facility_id IS NOT NULL
ORDER BY normalized_name, facility_id, source, first_seen_at ASC;
