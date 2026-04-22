-- SQLMesh Model: Bronze TGA ARTG Medical Devices
-- Unnests response_body->'results' into typed device rows.
-- Grain: artg_number

MODEL (
    name dev_bronze.tga_artg_devices,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key artg_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (artg_number))
    ),
    grain artg_number
);

SELECT
    gen_random_uuid()                                           AS id,

    -- Natural key
    rec->>'ARTG Number'                                         AS artg_number,

    -- Product/device identity
    rec->>'Product Name'                                        AS product_name,
    rec->>'Product Type'                                        AS product_type,          -- 'Medical device' etc.
    rec->>'Product Category'                                    AS product_category,

    -- Sponsor (company)
    rec->>'Sponsor'                                             AS sponsor_name,
    rec->>'Manufacturer'                                        AS manufacturer_name,

    -- Device classification
    rec->>'Device Classification'                               AS device_classification,  -- Class I/IIa/IIb/III/AIMD/IVD
    rec->>'GMDN Term'                                           AS gmdn_term,              -- Global Medical Device Nomenclature term
    rec->>'GMDN Code'                                           AS gmdn_code,
    rec->>'Intended Purpose'                                    AS intended_purpose,

    -- Regulatory
    rec->>'Conformity Assessment Procedures'                    AS conformity_assessment,
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
    dev_raw.tga_artg_devices.id::TEXT                           AS raw_source_id,
    'tga_artg_devices'                                          AS source,
    request_timestamp,
    request_timestamp                                           AS source_updated_at,
    FALSE                                                       AS processed_to_silver,
    NOW()                                                       AS created_at

FROM dev_raw.tga_artg_devices,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'ARTG Number' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
