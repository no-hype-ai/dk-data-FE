-- SQLMesh Model: Bronze USPTO Trademarks
-- Transforms raw USPTO TSDR trademark data into typed bronze layer
-- Part of: 014-uspto-euipo-model-datasource

MODEL (
    name bronze.uspto_trademarks,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
    ),
    cron '@weekly',
    grain (serial_number),
    audits (
        not_null(columns := (serial_number)),
        unique_values(columns := (serial_number))
    )
);

SELECT
    gen_random_uuid() AS id,

    -- Trademark identification
    r.serial_number,
    r.mark_element,
    r.mark_type,

    -- Status
    r.status,
    r.status_code,
    r.status_date,

    -- Dates
    r.filing_date,
    r.registration_number,
    r.registration_date,

    -- Classification (Nice classes as JSONB for silver compatibility)
    CASE
        WHEN r.nice_classes IS NOT NULL
        THEN to_jsonb(r.nice_classes)
        ELSE NULL
    END AS nice_classes,

    -- US-specific classification
    CASE
        WHEN r.us_classes IS NOT NULL
        THEN to_jsonb(r.us_classes)
        ELSE NULL
    END AS us_classes,

    -- Ownership
    r.owner_name,
    r.owner_entity_type,

    -- Description
    r.goods_and_services,
    r.description_of_mark,

    -- Pharma relevance: Nice Class 5 = Pharmaceuticals
    5 = ANY(COALESCE(r.nice_classes, '{}')) AS is_pharma_related,

    -- Processing metadata
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at

FROM mol_raw.uspto_trademarks r
WHERE r.serial_number IS NOT NULL
  AND r.processed_to_bronze = FALSE
  AND _loaded_at BETWEEN @start_dt AND @end_dt
