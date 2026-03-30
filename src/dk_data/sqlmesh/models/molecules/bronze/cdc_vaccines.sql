-- SQLMesh Model: Bronze CDC Vaccines
-- Transforms raw CDC vaccine data API responses to Bronze typed columns.
-- Sources: CDC data.cdc.gov portal (schedule rows) + openFDA (vaccine drug labels)
-- Response shapes:
--   data.cdc.gov: {"meta": {...}, "data": [[row values...]]} or {"results": [...]}
--   openFDA:      {"results": [{openfda:{product_type:"VACCINE",...}, ...}]}

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

-- openFDA vaccine label format: {"results": [...]}
WITH from_openfda AS (
    SELECT
        r.id              AS raw_source_id,
        r.request_timestamp,
        res.value         AS rec,
        'openfda'         AS response_type
    FROM mol_raw.cdc_vaccines r,
         LATERAL jsonb_array_elements(r.response_body->'results') AS res(value)
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body ? 'results'
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
),

-- CDC rows format: {"data": [[...]]} — flat row arrays, first row is headers
from_cdc_rows AS (
    SELECT
        r.id              AS raw_source_id,
        r.request_timestamp,
        row_val.value     AS rec,
        'cdc_rows'        AS response_type
    FROM mol_raw.cdc_vaccines r,
         LATERAL jsonb_array_elements(
             COALESCE(r.response_body->'data', '[]'::jsonb)
         ) AS row_val(value)
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body ? 'data'
      AND NOT (r.response_body ? 'results')
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
),

combined AS (
    SELECT * FROM from_openfda
    UNION ALL
    SELECT * FROM from_cdc_rows
)

SELECT DISTINCT ON (vaccine_id)
    gen_random_uuid()                                                               AS id,

    -- Vaccine identifier: prefer openFDA application_number, fall back to set_id / row hash
    COALESCE(
        rec->'openfda'->>'application_number',
        rec->>'set_id',
        rec->>'application_number',
        -- For CDC row arrays, use position 0 as id
        CASE WHEN jsonb_typeof(rec) = 'array' THEN rec->>0 ELSE NULL END,
        md5(rec::TEXT)
    )                                                                               AS vaccine_id,

    COALESCE(
        rec->'openfda'->'brand_name'->>0,
        rec->>'brand_name',
        CASE WHEN jsonb_typeof(rec) = 'array' THEN rec->>1 ELSE NULL END
    )                                                                               AS vaccine_name,

    COALESCE(
        rec->'openfda'->'manufacturer_name'->>0,
        rec->>'manufacturer'
    )                                                                               AS manufacturer,

    COALESCE(
        rec->'openfda'->'substance_name'->>0,
        rec->>'substance'
    )                                                                               AS active_substance,

    rec->'openfda'->'route'->>0                                                    AS route,
    rec->'openfda'->'generic_name'->>0                                             AS generic_name,
    rec->>'effective_time'                                                         AS effective_date,

    -- CVX code (CDC vaccine code)
    rec->>'cvx_code'                                                               AS cvx_code,

    -- Raw source tracking
    rec                                                                            AS raw_json,
    raw_source_id,
    'cdc_vaccines'                                                                 AS source,
    request_timestamp,
    request_timestamp                                                              AS source_updated_at,
    FALSE                                                                          AS processed_to_silver,
    NOW()                                                                          AS created_at

FROM combined
WHERE COALESCE(
    rec->'openfda'->>'application_number',
    rec->>'set_id',
    rec->>'application_number',
    CASE WHEN jsonb_typeof(rec) = 'array' THEN rec->>0 ELSE NULL END,
    md5(rec::TEXT)
) IS NOT NULL
ORDER BY vaccine_id, request_timestamp DESC NULLS LAST;
