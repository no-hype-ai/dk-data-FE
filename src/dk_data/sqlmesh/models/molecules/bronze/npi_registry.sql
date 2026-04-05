-- SQLMesh Model: Bronze NPI Registry
-- Transforms raw NPI Registry (NPPES) API responses to Bronze typed columns.
-- API: https://npiregistry.cms.hhs.gov/api/
-- Response shape: {"result_count": N, "results": [{number, basic:{...}, taxonomies:[...], addresses:[...]}]}

MODEL (
    name mol_bronze.npi_registry,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi))
    ),
    grain npi
);

WITH expanded AS (
    SELECT
        r.id              AS raw_source_id,
        r.ingested_at,
        res.value         AS rec
    FROM mol_raw.npi_registry r,
         LATERAL jsonb_array_elements(
             CASE
                 WHEN r.response_body ? 'results' THEN r.response_body->'results'
                 ELSE jsonb_build_array(r.response_body)
             END
         ) AS res(value)
    WHERE r.response_body IS NOT NULL
      AND r.ingested_at BETWEEN @start_dt AND @end_dt
),

-- Primary taxonomy (first with primary=true, else first entry)
primary_taxonomy AS (
    SELECT DISTINCT ON (npi_val)
        rec->>'number' AS npi_val,
        tx.value AS taxonomy
    FROM expanded,
         LATERAL jsonb_array_elements(COALESCE(rec->'taxonomies', '[]'::jsonb)) AS tx(value)
    ORDER BY npi_val,
        CASE WHEN (tx.value->>'primary')::BOOLEAN = TRUE THEN 0 ELSE 1 END
),

-- Primary address (location type)
primary_address AS (
    SELECT DISTINCT ON (npi_val)
        rec->>'number' AS npi_val,
        addr.value AS address
    FROM expanded,
         LATERAL jsonb_array_elements(COALESCE(rec->'addresses', '[]'::jsonb)) AS addr(value)
    ORDER BY npi_val,
        CASE WHEN addr.value->>'address_purpose' = 'LOCATION' THEN 0 ELSE 1 END
)

SELECT DISTINCT ON (rec->>'number')
    gen_random_uuid()                                                           AS id,

    rec->>'number'                                                              AS npi,
    rec->>'enumeration_type'                                                    AS provider_type,

    -- Basic info
    COALESCE(rec->'basic'->>'first_name', rec->'basic'->>'authorized_official_first_name') AS first_name,
    COALESCE(rec->'basic'->>'last_name',  rec->'basic'->>'authorized_official_last_name')  AS last_name,
    COALESCE(rec->'basic'->>'organization_name', rec->'basic'->>'legal_business_name')     AS organization_name,
    rec->'basic'->>'credential'                                                AS credential,
    rec->'basic'->>'gender'                                                    AS gender,
    rec->'basic'->>'status'                                                    AS status,
    (rec->'basic'->>'enumeration_date')::DATE                                  AS enumeration_date,

    -- Primary taxonomy
    pt.taxonomy->>'code'                                                        AS taxonomy_code,
    pt.taxonomy->>'desc'                                                        AS taxonomy_description,
    (pt.taxonomy->>'primary')::BOOLEAN                                          AS is_primary_taxonomy,
    pt.taxonomy->>'state'                                                       AS license_state,
    pt.taxonomy->>'license'                                                     AS license_number,

    -- Primary practice address
    pa.address->>'city'                                                         AS practice_city,
    pa.address->>'state'                                                        AS practice_state,
    pa.address->>'postal_code'                                                  AS practice_zip,
    pa.address->>'country_code'                                                 AS practice_country,

    -- All taxonomies and addresses for downstream use
    rec->'taxonomies'                                                           AS taxonomies,
    rec->'addresses'                                                            AS addresses,

    -- Raw source tracking
    rec                                                                         AS raw_json,
    e.raw_source_id,
    'npi_registry'                                                              AS source,
    e.ingested_at,
    e.ingested_at                                                           AS source_updated_at,
    FALSE                                                                       AS processed_to_silver,
    NOW()                                                                       AS created_at

FROM expanded e
LEFT JOIN primary_taxonomy pt ON pt.npi_val = e.rec->>'number'
LEFT JOIN primary_address pa  ON pa.npi_val = e.rec->>'number'
WHERE e.rec->>'number' IS NOT NULL
ORDER BY e.rec->>'number', e.ingested_at DESC NULLS LAST;
