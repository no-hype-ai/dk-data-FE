-- SQLMesh Model: Bronze TGA Orphan Drug Designations
-- Annual list of orphan-drug designations granted by TGA.
-- Grain: (designation_number, designation_date)

MODEL (
    name mol_bronze.tga_orphan_designations,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (designation_number, designation_date)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (designation_number))
    ),
    grain (designation_number, designation_date)
);

SELECT
    gen_random_uuid()                                           AS id,

    -- Natural key
    rec->>'Designation Number'                                  AS designation_number,

    -- Product / molecule
    rec->>'Active Ingredient'                                   AS active_ingredient,
    rec->>'Product Name'                                        AS product_name,

    -- Sponsor
    rec->>'Sponsor'                                             AS sponsor_name,

    -- Indication (disease/condition — silver calls resolve_condition())
    rec->>'Intended Indication'                                 AS intended_indication,
    rec->>'Orphan Condition'                                    AS orphan_condition,

    -- Date designation granted
    CASE WHEN rec->>'Designation Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'Designation Date')::DATE ELSE NULL END     AS designation_date,

    -- Status
    rec->>'Status'                                              AS status,

    -- Raw tracking
    rec                                                         AS raw_json,
    mol_raw.tga_orphan_designations.id::TEXT                    AS raw_source_id,
    'tga_orphan_designations'                                   AS source,
    request_timestamp,
    request_timestamp                                           AS source_updated_at,
    FALSE                                                       AS processed_to_silver,
    NOW()                                                       AS created_at

FROM mol_raw.tga_orphan_designations,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'Designation Number' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
