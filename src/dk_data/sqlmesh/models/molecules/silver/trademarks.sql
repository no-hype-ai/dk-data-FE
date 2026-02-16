-- SQLMesh Model: Silver Trademarks
-- Unified trademark data from USPTO TSDR and EUIPO TMview/IBM Gateway
-- Part of: 014-uspto-euipo-model-datasource

MODEL (
    name silver.trademarks,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (trademark_identifier, source)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (trademark_identifier)),
        not_null(columns := (source))
    ),
    grain (trademark_identifier, source)
);

-- USPTO trademarks
WITH uspto AS (
    SELECT
        serial_number AS trademark_identifier,
        mark_element AS mark_name,
        mark_type,
        status,
        filing_date,
        registration_date,
        NULL::DATE AS expiry_date,
        owner_name,
        nice_classes,
        goods_and_services,
        is_pharma_related,
        'uspto_trademarks' AS source,
        ingested_at AS source_updated_at
    FROM bronze.uspto_trademarks
    WHERE processed_to_silver = FALSE
),

-- EUIPO trademarks
euipo AS (
    SELECT
        application_number AS trademark_identifier,
        mark_name,
        mark_kind AS mark_type,
        status,
        filing_date,
        registration_date,
        expiry_date,
        applicant_name AS owner_name,
        nice_classes,
        goods_and_services,
        is_pharma_related,
        'euipo_trademarks' AS source,
        ingested_at AS source_updated_at
    FROM bronze.euipo_trademarks
    WHERE processed_to_silver = FALSE
),

-- Combine both registries
combined AS (
    SELECT * FROM uspto
    UNION ALL
    SELECT * FROM euipo
)

-- Within-registry dedup only (no cross-registry dedup)
SELECT DISTINCT ON (trademark_identifier, source)
    gen_random_uuid() AS id,
    trademark_identifier,
    mark_name,
    mark_type,
    status,
    filing_date,
    registration_date,
    expiry_date,
    owner_name,
    nice_classes,
    goods_and_services,
    is_pharma_related,
    NULL::UUID AS molecule_id,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY trademark_identifier, source, source_updated_at DESC
