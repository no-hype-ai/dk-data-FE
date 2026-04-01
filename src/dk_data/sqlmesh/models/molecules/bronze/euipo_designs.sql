-- SQLMesh Model: Bronze EUIPO Registered Community Designs
-- Transforms raw EUIPO design search API responses into typed bronze layer.
-- Source table: mol_raw.euipo_designs (populated by EUIPODesignsFetcher)
-- Part of: 014-uspto-euipo-model-datasource

MODEL (
    name mol_bronze.euipo_designs,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        lookback 7
    ),
    cron '@weekly',
    grain (application_number),
    audits (
        not_null(columns := (application_number)),
        unique_values(columns := (application_number))
    )
);

SELECT
    gen_random_uuid() AS id,

    -- Design identification
    r.response_body->>'application_number'   AS application_number,
    r.response_body->>'design_title'         AS design_title,

    -- Applicant info
    r.response_body->>'applicant_name'       AS applicant_name,
    r.response_body->>'applicant_country'    AS applicant_country,
    r.response_body->>'representative_name'  AS representative_name,
    r.response_body->>'designer_name'        AS designer_name,

    -- Status
    r.response_body->>'status'               AS status,

    -- Dates (stored as text; cast to DATE where non-null)
    CASE
        WHEN r.response_body->>'filing_date' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (r.response_body->>'filing_date')::DATE
        ELSE NULL
    END                                      AS filing_date,
    CASE
        WHEN r.response_body->>'registration_date' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (r.response_body->>'registration_date')::DATE
        ELSE NULL
    END                                      AS registration_date,
    CASE
        WHEN r.response_body->>'expiry_date' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (r.response_body->>'expiry_date')::DATE
        ELSE NULL
    END                                      AS expiry_date,
    CASE
        WHEN r.response_body->>'publication_date' ~ '^\d{4}-\d{2}-\d{2}$'
        THEN (r.response_body->>'publication_date')::DATE
        ELSE NULL
    END                                      AS publication_date,

    -- Classification (Locarno classes as JSONB array)
    CASE
        WHEN r.response_body->'locarno_classes' IS NOT NULL
        THEN r.response_body->'locarno_classes'
        ELSE NULL
    END                                      AS locarno_classes,

    -- Product description
    r.response_body->>'product_indication'   AS product_indication,

    -- Medical/pharma relevance: Locarno class 24 = medical equipment, 09 = packaging
    (
        r.response_body->'locarno_classes' @> '"24"'::jsonb
        OR r.response_body->'locarno_classes' @> '"09"'::jsonb
    )                                        AS is_healthcare_related,

    -- Design image
    r.response_body->>'image_url'            AS image_url,

    -- Number of individual designs in the application
    (r.response_body->>'number_of_designs')::INTEGER AS number_of_designs,

    -- Processing metadata
    FALSE                                    AS processed_to_silver,
    r._loaded_at

FROM mol_raw.euipo_designs r
WHERE r.response_body->>'application_number' IS NOT NULL
  AND r._loaded_at BETWEEN @start_dt AND @end_dt
