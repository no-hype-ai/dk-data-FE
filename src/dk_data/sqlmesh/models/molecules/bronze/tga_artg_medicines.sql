-- SQLMesh Model: Bronze TGA ARTG Medicines
-- Unnests response_body->'results' (CSV rows as JSON objects) into typed rows.
-- medicine_type is carried on the response_body root and propagated to each row.
-- Grain: (artg_number, medicine_type)

MODEL (
    name mol_bronze.tga_artg_medicines,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (artg_number, medicine_type)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (artg_number, medicine_type))
    ),
    grain (artg_number, medicine_type)
);

SELECT
    gen_random_uuid()                                           AS id,

    -- Medicine subtype — propagated from the page blob (prescription/otc/biological/complementary)
    response_body->>'medicine_type'                             AS medicine_type,

    -- Natural key
    rec->>'ARTG Number'                                         AS artg_number,

    -- Product identity
    rec->>'Product Name'                                        AS product_name,
    rec->>'Product Type'                                        AS product_type,
    rec->>'Product Category'                                    AS product_category,

    -- Sponsor (company) — string at bronze; silver calls resolve_company(p_name => ...)
    rec->>'Sponsor'                                             AS sponsor_name,

    -- Active ingredients (pipe-delimited list in ARTG CSV)
    rec->>'Active Ingredients'                                  AS active_ingredients,

    -- Dosage and form
    rec->>'Dosage Form'                                         AS dosage_form,
    rec->>'Route of Administration'                             AS route_of_administration,
    rec->>'Strength'                                            AS strength,
    rec->>'Unit'                                                AS strength_unit,
    rec->>'Container'                                           AS container,
    rec->>'Pack Size'                                           AS pack_size,

    -- Scheduling / regulatory
    rec->>'Schedule'                                            AS schedule,
    rec->>'Status'                                              AS status,
    rec->>'Approval Area'                                       AS approval_area,

    -- Dates
    CASE WHEN rec->>'Registration Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'Registration Date')::DATE ELSE NULL END    AS registration_date,
    CASE WHEN rec->>'Commencement Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'Commencement Date')::DATE ELSE NULL END    AS commencement_date,
    CASE WHEN rec->>'Cancellation Date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (rec->>'Cancellation Date')::DATE ELSE NULL END    AS cancellation_date,

    -- Raw tracking
    rec                                                         AS raw_json,
    mol_raw.tga_artg_medicines.id::TEXT                         AS raw_source_id,
    'tga_artg_medicines'                                        AS source,
    request_timestamp,
    request_timestamp                                           AS source_updated_at,
    FALSE                                                       AS processed_to_silver,
    NOW()                                                       AS created_at

FROM mol_raw.tga_artg_medicines,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'ARTG Number' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
