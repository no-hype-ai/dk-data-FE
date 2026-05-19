-- SQLMesh Model: Bronze FDA Drugs (NDA/ANDA/BLA approvals — merged from fda_drugs + fda_drugsfda)
-- Transforms raw FDA Drugs@FDA API responses to Bronze typed columns.
-- Consolidated: previously split across mol_bronze.fda_drugs and mol_bronze.fda_drugsfda;
--   both read from mol_raw.fda_drugs (same source) so they are merged here.
-- Source: FDADrugsFetcher, API: https://api.fda.gov/drug/drugsfda.json
-- Response shape: {"results": [{application_number, sponsor_name, openfda:{}, products:[], submissions:[]}]}

MODEL (
    name mol_bronze.fda_drugs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key application_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (application_number))
    ),
    grain application_number
);

-- Each mol_raw.fda_drugs row is a single application record stored directly.
-- The FDA API returns {"results": [...]} pages, but the ingestion layer stores individual
-- application records extracted from those pages — one record per row in mol_raw.
WITH expanded AS (
    SELECT
        r.id             AS raw_source_id,
        r.request_timestamp,
        r.response_body  AS rec
    FROM mol_raw.fda_drugs r
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body->>'application_number' IS NOT NULL
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

    -- Application type derived from prefix (NDA, ANDA, BLA, NDF, etc.)
    REGEXP_REPLACE(rec->>'application_number', '[0-9]+', '')            AS application_type,

    rec->>'sponsor_name'                                                AS sponsor_name,
    rec->'openfda'->'generic_name'->>0                                  AS generic_name,
    rec->'openfda'->'brand_name'->>0                                    AS brand_name,
    rec->'openfda'->'substance_name'->>0                                AS substance_name,
    rec->'openfda'->'rxcui'->>0                                         AS rxcui,

    rec->'products'->0->>'dosage_form'                                  AS dosage_form,
    rec->'products'->0->>'route'                                        AS route,
    rec->'products'->0->>'marketing_status'                             AS marketing_status,
    rec->'products'->0->>'te_code'                                      AS te_code,
    rec->'products'->0->>'reference_drug'                               AS reference_drug,
    rec->'products'->0->>'reference_standard'                           AS reference_standard,

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
    e.request_timestamp                                                 AS ingested_at,
    e.request_timestamp                                                 AS source_updated_at,
    FALSE                                                               AS processed_to_silver,
    NOW()                                                               AS created_at

FROM expanded e
LEFT JOIN first_approval fa ON fa.app_num = e.rec->>'application_number'
WHERE e.rec->>'application_number' IS NOT NULL
ORDER BY e.rec->>'application_number', e.request_timestamp DESC NULLS LAST;
