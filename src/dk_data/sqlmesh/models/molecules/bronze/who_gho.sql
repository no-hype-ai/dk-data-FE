-- SQLMesh Model: Bronze WHO GHO Epidemiology
-- Extracts OData value[] array from raw WHO GHO API responses
-- Part of: 003-molecule-assessment-dashboard

MODEL (
    name mol_bronze.who_gho,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (indicator_code, time_dim))
    ),
    grain (indicator_code, spatial_dim, time_dim)
);

SELECT
    gen_random_uuid() AS id,

    -- OData value fields
    elem->>'IndicatorCode' AS indicator_code,
    elem->>'SpatialDim' AS spatial_dim,
    (elem->>'TimeDim')::INTEGER AS time_dim,
    (elem->>'NumericValue')::DECIMAL(12,4) AS numeric_value,
    elem->>'Dim1' AS dim1,              -- sex dimension (BTSX, MLE, FMLE)
    (elem->>'Low')::DECIMAL(12,4) AS low,
    (elem->>'High')::DECIMAL(12,4) AS high,

    -- Source tracking
    request_params->>'drug_name' AS indication_query,  -- the indication name used in the query
    response_body AS raw_json,
    r.id AS raw_source_id,
    'who_gho' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.who_gho r,
     jsonb_array_elements(response_body->'value') AS elem
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->'value' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
