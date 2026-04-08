-- SQLMesh Model: Bronze WHO GHO Epidemiology
-- Extracts OData value[] array from raw WHO GHO API responses
-- Part of: 003-molecule-assessment-dashboard

MODEL (
    name mol_bronze.who_gho,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (indicator_code, spatial_dim, time_dim)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (indicator_code, time_dim))
    ),
    grain (indicator_code, spatial_dim, time_dim)
);

-- Each mol_raw.who_gho row is a single indicator record stored directly (not wrapped in an array).
-- The OData API returns {"value": [...]} pages, but the ingestion layer stores individual
-- records extracted from those pages — one record per row in mol_raw.
SELECT
    gen_random_uuid() AS id,

    -- Indicator fields (present on both indicator definitions and data values)
    response_body->>'IndicatorCode' AS indicator_code,
    response_body->>'SpatialDim' AS spatial_dim,
    (response_body->>'TimeDim')::INTEGER AS time_dim,
    (response_body->>'NumericValue')::DECIMAL(12,4) AS numeric_value,
    response_body->>'Dim1' AS dim1,              -- sex dimension (BTSX, MLE, FMLE)
    (response_body->>'Low')::DECIMAL(12,4) AS low,
    (response_body->>'High')::DECIMAL(12,4) AS high,

    -- Source tracking
    NULL::TEXT AS indication_query,
    response_body AS raw_json,
    r.id AS raw_source_id,
    'who_gho' AS source,
    ingested_at,
    ingested_at AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.who_gho r
WHERE
    response_body->>'IndicatorCode' IS NOT NULL
    AND ingested_at BETWEEN @start_dt AND @end_dt;
