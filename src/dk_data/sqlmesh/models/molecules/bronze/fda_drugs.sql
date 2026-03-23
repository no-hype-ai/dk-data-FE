-- SQLMesh Model: Bronze FDA Drugs (bulk approval feed)
-- Transforms raw FDA Drugs@FDA bulk API responses to Bronze typed columns.
-- Source: FDADrugsIngestion class, DataSource.FDA_DRUGS
-- API: https://api.fda.gov/drug/drugsfda.json (bulk/paginated, without drug-specific search)
-- Response shape: {"results": [{application_number, sponsor_name, openfda:{}, products:[], submissions:[]}]}
-- Note: mol_bronze.fda_drugsfda covers drug-specific lookups; this model covers bulk/batch ingestion.

MODEL (
    name mol_bronze.fda_drugs,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    audits (
        not_null(columns := (application_number))
    ),
    grain application_number
);

WITH expanded AS (
    SELECT
        r.id             AS raw_source_id,
        r.request_timestamp,
        res.value        AS rec
    FROM mol_raw.fda_drugs r,
         LATERAL jsonb_array_elements(
             CASE
                 WHEN r.response_body ? 'results' THEN r.response_body->'results'
                 ELSE '[]'::jsonb
             END
         ) AS res(value)
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body ? 'results'
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
),

first_approval AS (
    SELECT DISTINCT ON (app_num)
        rec->>'application_number'          AS app_num,
        sub->>'submission_status_date'      AS approval_date_raw
    FROM expanded,
         LATERAL jsonb_array_elements(COALESCE(rec->'submissions', '[]'::jsonb)) AS sub
    WHERE sub->>'submission_status' = 'AP'
      AND sub->>'submission_type' = 'ORIG'
    ORDER BY app_num, sub->>'submission_status_date' ASC NULLS LAST
)

SELECT DISTINCT ON (rec->>'application_number')
    gen_random_uuid()                                                   AS id,
    rec->>'application_number'                                          AS application_number,
    rec->>'sponsor_name'                                                AS sponsor_name,
    rec->'openfda'->'generic_name'->>0                                  AS generic_name,
    rec->'openfda'->'brand_name'->>0                                    AS brand_name,
    rec->'openfda'->'substance_name'->>0                                AS substance_name,
    rec->'openfda'->'rxcui'->>0                                         AS rxcui,
    rec->'products'->0->>'dosage_form'                                  AS dosage_form,
    rec->'products'->0->>'route'                                        AS route,
    rec->'products'->0->>'marketing_status'                             AS marketing_status,
    CASE
        WHEN fa.approval_date_raw ~ '^\d{8}$'
        THEN TO_DATE(fa.approval_date_raw, 'YYYYMMDD')
        ELSE NULL
    END                                                                 AS first_approval_date,
    rec->'products'                                                     AS products,
    rec->'submissions'                                                  AS submissions,
    rec                                                                 AS raw_json,
    e.raw_source_id,
    'fda_drugs'                                                         AS source,
    e.request_timestamp,
    e.request_timestamp                                                 AS source_updated_at,
    FALSE                                                               AS processed_to_silver,
    NOW()                                                               AS created_at

FROM expanded e
LEFT JOIN first_approval fa ON fa.app_num = e.rec->>'application_number'
WHERE e.rec->>'application_number' IS NOT NULL
ORDER BY e.rec->>'application_number', e.request_timestamp DESC NULLS LAST;
