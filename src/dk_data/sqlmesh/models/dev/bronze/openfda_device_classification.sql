-- SQLMesh Model: Bronze OpenFDA Device Classification
-- Reference catalog: FDA product_code → device class, medical specialty, regulation.
-- Grain: product_code

MODEL (
    name dev_bronze.openfda_device_classification,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key product_code
    ),
    cron '@weekly',
    audits (
        not_null(columns := (product_code))
    ),
    grain product_code
);

SELECT
    gen_random_uuid()                                       AS id,

    rec->>'product_code'                                    AS product_code,
    rec->>'device_name'                                     AS device_name,
    rec->>'device_class'                                    AS device_class,
    rec->>'definition'                                      AS definition,
    rec->>'regulation_number'                               AS regulation_number,

    rec->>'medical_specialty'                               AS medical_specialty_code,
    rec->>'medical_specialty_description'                   AS medical_specialty_description,
    rec->>'review_panel'                                    AS review_panel,

    rec->>'submission_type_id'                              AS submission_type_id,
    rec->>'gmp_exempt_flag'                                 AS gmp_exempt_flag,
    rec->>'implant_flag'                                    AS implant_flag,
    rec->>'life_sustain_support_flag'                       AS life_sustain_support_flag,
    rec->>'third_party_flag'                                AS third_party_flag,
    rec->>'summary_malfunction_reporting'                   AS summary_malfunction_reporting,

    rec->'openfda'                                          AS openfda_raw,

    rec                                                     AS raw_json,
    dev_raw.openfda_device_classification.id::TEXT          AS raw_source_id,
    'openfda_device_classification'                         AS source,
    request_timestamp,
    request_timestamp                                       AS source_updated_at,
    FALSE                                                   AS processed_to_silver,
    NOW()                                                   AS created_at

FROM dev_raw.openfda_device_classification,
     jsonb_array_elements(response_body->'results') AS rec
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND rec->>'product_code' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
