-- SQLMesh Model: Bronze TGA SARA Recalls
-- Covers both medicine and device recalls. regulatory_type distinguishes rows;
-- silver-layer models (mol_silver.tga_medicine_recalls / dev_silver.tga_device_recalls)
-- filter on it to route into the correct domain.
-- Grain: recall_number

MODEL (
    name mol_bronze.tga_sara_recalls,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key recall_number
    ),
    cron '@daily',
    audits (
        not_null(columns := (recall_number, regulatory_type))
    ),
    grain recall_number
);

SELECT
    gen_random_uuid()                                           AS id,

    -- Natural key
    rec->>'recallNumber'                                        AS recall_number,

    -- Classification
    rec->>'regulatoryType'                                      AS regulatory_type,   -- 'Medicine' | 'Medical device' | 'Biological' | 'OTC'
    rec->>'actionType'                                          AS action_type,       -- 'Recall' | 'Hazard alert' | 'Product correction'
    rec->>'riskClassification'                                  AS risk_classification, -- 'Class I' | 'Class II' | 'Class III'

    -- Product identity
    rec->>'productName'                                         AS product_name,
    rec->>'tradeName'                                           AS trade_name,
    rec->>'artgNumber'                                          AS artg_number,
    rec->>'batchNumbers'                                        AS batch_numbers,

    -- Sponsor
    rec->>'sponsorName'                                         AS sponsor_name,
    rec->>'manufacturerName'                                    AS manufacturer_name,

    -- Reason / description
    rec->>'recallReason'                                        AS recall_reason,
    rec->>'summary'                                             AS summary,
    rec->>'description'                                         AS description,

    -- Dates
    CASE WHEN rec->>'datePublished' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'datePublished')::DATE ELSE NULL END        AS date_published,
    CASE WHEN rec->>'dateInitiated' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'dateInitiated')::DATE ELSE NULL END        AS date_initiated,
    CASE WHEN rec->>'dateClosed' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'dateClosed')::DATE ELSE NULL END           AS date_closed,

    -- URL for detail
    rec->>'url'                                                 AS detail_url,

    -- Raw tracking
    rec                                                         AS raw_json,
    mol_raw.tga_sara_recalls.id::TEXT                           AS raw_source_id,
    'tga_sara_recalls'                                          AS source,
    request_timestamp,
    request_timestamp                                           AS source_updated_at,
    FALSE                                                       AS processed_to_silver,
    NOW()                                                       AS created_at

FROM mol_raw.tga_sara_recalls,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'recallNumber' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
