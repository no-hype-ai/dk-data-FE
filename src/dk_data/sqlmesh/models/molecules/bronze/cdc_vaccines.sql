-- SQLMesh Model: Bronze CDC Vaccines
-- Transforms raw CDC vaccine data (CVX + MVX codes) to Bronze typed columns.
-- Sources: CDC Open Data Portal Socrata API (data.cdc.gov)
--   CVX dataset (fhky-rtsk): vaccine code list — flat records with cvx_code, short_description, etc.
--   MVX dataset (n6hk-4tzf): manufacturer code list — flat records with mvx_code, manufacturer_name, etc.
-- Each mol_raw.cdc_vaccines row is a single flat Socrata record. The fetcher adds
-- a "_record_type" field ("cvx" or "mvx") to identify the source dataset.

MODEL (
    name mol_bronze.cdc_vaccines,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (vaccine_id))
    ),
    grain vaccine_id
);

SELECT DISTINCT ON (vaccine_id)
    gen_random_uuid()                                                               AS id,

    -- Vaccine/manufacturer identifier:
    -- CVX records have cvx_code (numeric string); MVX records have mvx_code (alpha).
    COALESCE(
        response_body->>'cvx_code',
        response_body->>'mvx_code',
        md5(response_body::TEXT)
    )                                                                               AS vaccine_id,

    response_body->>'_record_type'                                                  AS record_type,

    -- CVX fields
    response_body->>'short_description'                                             AS vaccine_name,
    response_body->>'full_vaccine_name'                                             AS full_vaccine_name,
    response_body->>'vaccine_status'                                                AS vaccine_status,
    response_body->>'notes'                                                         AS notes,
    response_body->>'nonvaccine'                                                    AS nonvaccine,
    response_body->>'update_date'                                                   AS update_date,

    -- MVX (manufacturer) fields
    response_body->>'manufacturer_name'                                             AS manufacturer,
    response_body->>'mvx_status'                                                    AS mvx_status,

    -- Schema-compatibility columns (present in mol_silver.cdc_vaccines linkage queries).
    -- Socrata CVX/MVX records do not carry openfda substance/route/generic/date fields;
    -- return NULL so downstream silver models can still compile and run.
    NULL::TEXT                                                                      AS active_substance,
    NULL::TEXT                                                                      AS generic_name,
    NULL::TEXT                                                                      AS route,
    NULL::TEXT                                                                      AS effective_date,

    -- Raw source tracking
    response_body                                                                   AS raw_json,
    r.id                                                                            AS raw_source_id,
    'cdc_vaccines'                                                                  AS source,
    request_timestamp,
    request_timestamp                                                               AS source_updated_at,
    FALSE                                                                           AS processed_to_silver,
    NOW()                                                                           AS created_at

FROM mol_raw.cdc_vaccines r
WHERE response_status = 200
  AND processed_to_bronze = FALSE
  AND COALESCE(
        response_body->>'cvx_code',
        response_body->>'mvx_code'
      ) IS NOT NULL
  AND request_timestamp BETWEEN @start_dt AND @end_dt
ORDER BY vaccine_id, request_timestamp DESC NULLS LAST;
