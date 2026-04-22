-- SQLMesh Model: Bronze TGA Medicine Shortages
-- From Medicine Shortages Information portal (MSI).
-- Grain: shortage_id

MODEL (
    name mol_bronze.tga_medicine_shortages,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key shortage_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (shortage_id))
    ),
    grain shortage_id
);

SELECT
    gen_random_uuid()                                           AS id,

    -- Natural key
    rec->>'shortageId'                                          AS shortage_id,

    -- Product
    rec->>'productName'                                         AS product_name,
    rec->>'brandName'                                           AS brand_name,
    rec->>'activeIngredient'                                    AS active_ingredient,
    rec->>'artgNumber'                                          AS artg_number,
    rec->>'schedule'                                            AS schedule,

    -- Sponsor
    rec->>'sponsorName'                                         AS sponsor_name,

    -- Shortage details
    rec->>'shortageStatus'                                      AS shortage_status,     -- current | resolved | anticipated
    rec->>'shortageType'                                        AS shortage_type,       -- limited | unavailable | discontinued
    rec->>'impact'                                              AS impact,              -- critical | significant | low
    rec->>'reason'                                              AS reason,
    rec->>'managementStrategy'                                  AS management_strategy,

    -- Dates
    CASE WHEN rec->>'dateReported' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'dateReported')::DATE ELSE NULL END         AS date_reported,
    CASE WHEN rec->>'expectedResolutionDate' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'expectedResolutionDate')::DATE ELSE NULL END AS expected_resolution_date,
    CASE WHEN rec->>'dateResolved' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'dateResolved')::DATE ELSE NULL END         AS date_resolved,

    -- Raw tracking
    rec                                                         AS raw_json,
    mol_raw.tga_medicine_shortages.id::TEXT                     AS raw_source_id,
    'tga_medicine_shortages'                                    AS source,
    request_timestamp,
    request_timestamp                                           AS source_updated_at,
    FALSE                                                       AS processed_to_silver,
    NOW()                                                       AS created_at

FROM mol_raw.tga_medicine_shortages,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'shortageId' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
