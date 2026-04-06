-- SQLMesh Model: Bronze NPI Registry
-- Transforms raw NPI Registry NPPES bulk CSV rows to Bronze typed columns.
-- Source: NPPES monthly bulk download (npidata_pfile_*.csv, ~4.5 GB uncompressed).
-- Each mol_raw.npi_registry row is a flat CSV record parsed from the bulk file.
-- CSV column names are normalised: lowercase + spaces→underscores; hyphens/parens preserved.
-- The "NPI" column is renamed to "number" by the fetcher for index compatibility.
-- Key column mappings (CSV header → normalised key):
--   NPI → number
--   Entity Type Code → entity_type_code  (1=individual, 2=organization)
--   Provider Last Name (Legal Name) → provider_last_name_(legal_name)
--   Provider First Name → provider_first_name
--   Provider Organization Name (Legal Business Name) → provider_organization_name_(legal_business_name)
--   Provider Credential Text → provider_credential_text
--   Provider Gender Code → provider_gender_code
--   Provider Enumeration Date → provider_enumeration_date
--   Provider Business Practice Location Address City Name → provider_business_practice_location_address_city_name
--   Provider Business Practice Location Address State Name → provider_business_practice_location_address_state_name
--   Provider Business Practice Location Address Postal Code → provider_business_practice_location_address_postal_code
--   Healthcare Provider Taxonomy Code_1.._15 → healthcare_provider_taxonomy_code_1.._15

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

-- Build a JSONB array of the first few non-null taxonomy codes from the 15 flat columns.
WITH taxonomy_agg AS (
    SELECT
        r.id AS raw_source_id,
        jsonb_strip_nulls(jsonb_build_array(
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_1', ''),
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_2', ''),
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_3', ''),
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_4', ''),
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_5', '')
        )) AS taxonomy_codes,
        -- Primary taxonomy: first non-null code
        COALESCE(
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_1', ''),
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_2', ''),
            NULLIF(r.response_body->>'healthcare_provider_taxonomy_code_3', '')
        ) AS primary_taxonomy_code
    FROM mol_raw.npi_registry r
    WHERE r.response_body->>'number' IS NOT NULL
      AND r.ingested_at BETWEEN @start_dt AND @end_dt
)

SELECT DISTINCT ON (r.response_body->>'number')
    gen_random_uuid()                                                                              AS id,

    r.response_body->>'number'                                                                    AS npi,

    -- Entity type: '1'=individual, '2'=organization
    r.response_body->>'entity_type_code'                                                          AS provider_type,

    -- Individual provider names
    r.response_body->>'provider_first_name'                                                       AS first_name,
    r.response_body->>'provider_last_name_(legal_name)'                                           AS last_name,

    -- Organization name (for entity_type_code='2')
    r.response_body->>'provider_organization_name_(legal_business_name)'                         AS organization_name,

    r.response_body->>'provider_credential_text'                                                  AS credential,
    r.response_body->>'provider_gender_code'                                                      AS gender,

    -- NPI status (from last update field; no direct status column in NPPES CSV)
    r.response_body->>'nppes_deactivation_reason_code'                                           AS status,

    (NULLIF(r.response_body->>'provider_enumeration_date', ''))::DATE                            AS enumeration_date,

    -- Primary taxonomy code (first non-null from _1.._15)
    t.primary_taxonomy_code                                                                       AS taxonomy_code,
    NULL::TEXT                                                                                    AS taxonomy_description,
    NULL::BOOLEAN                                                                                 AS is_primary_taxonomy,
    NULLIF(r.response_body->>'provider_business_practice_location_address_state_name', '')        AS license_state,
    NULL::TEXT                                                                                    AS license_number,

    -- Practice address
    NULLIF(r.response_body->>'provider_business_practice_location_address_city_name', '')         AS practice_city,
    NULLIF(r.response_body->>'provider_business_practice_location_address_state_name', '')        AS practice_state,
    NULLIF(r.response_body->>'provider_business_practice_location_address_postal_code', '')       AS practice_zip,
    NULLIF(r.response_body->>'provider_business_practice_location_address_country_code_(if_outside_u.s.)', '') AS practice_country,

    -- All taxonomy codes as a JSONB array (first 5); no nested address objects in flat CSV format
    t.taxonomy_codes                                                                              AS taxonomies,
    NULL::JSONB                                                                                   AS addresses,

    -- Raw source tracking
    r.response_body                                                                               AS raw_json,
    r.id                                                                                          AS raw_source_id,
    'npi_registry'                                                                                AS source,
    r.ingested_at,
    r.ingested_at                                                                                 AS source_updated_at,
    FALSE                                                                                         AS processed_to_silver,
    NOW()                                                                                         AS created_at

FROM mol_raw.npi_registry r
JOIN taxonomy_agg t ON t.raw_source_id = r.id
WHERE r.response_body->>'number' IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
ORDER BY r.response_body->>'number', r.ingested_at DESC NULLS LAST;
