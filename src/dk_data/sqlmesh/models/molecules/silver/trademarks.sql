-- SQLMesh Model: Silver Trademarks
-- Unified trademark data from USPTO TSDR and EUIPO TMview/IBM Gateway
-- Part of: 014-uspto-euipo-model-datasource

MODEL (
    name mol_silver.trademarks,
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
        NULL::TEXT AS mark_feature,
        status,
        status_code,
        status_date,
        filing_date,
        registration_number,
        registration_date,
        NULL::DATE AS expiry_date,
        owner_name,
        owner_entity_type,
        nice_classes,
        us_classes,
        goods_and_services,
        description_of_mark,
        NULL::TEXT AS representative_name,
        NULL::TEXT AS applicant_country,
        NULL::TEXT AS mark_basis,
        NULL::TEXT AS image_url,
        is_pharma_related,
        'uspto_trademarks' AS source,
        ingested_at AS source_updated_at
    FROM mol_raw.uspto_trademarks
    WHERE TRUE
),

-- EUIPO trademarks
euipo AS (
    SELECT
        application_number AS trademark_identifier,
        mark_name,
        mark_kind AS mark_type,
        mark_feature,
        status,
        NULL::INTEGER AS status_code,
        NULL::DATE AS status_date,
        filing_date,
        NULL::TEXT AS registration_number,
        registration_date,
        expiry_date,
        applicant_name AS owner_name,
        NULL::TEXT AS owner_entity_type,
        nice_classes,
        NULL::JSONB AS us_classes,
        goods_and_services,
        NULL::TEXT AS description_of_mark,
        representative_name,
        applicant_country,
        mark_basis,
        image_url,
        is_pharma_related,
        'euipo_trademarks' AS source,
        ingested_at AS source_updated_at
    FROM mol_raw.euipo_trademarks
    WHERE TRUE
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
    mark_feature,
    status,
    status_code,
    status_date,
    filing_date,
    registration_number,
    registration_date,
    expiry_date,
    owner_name,
    owner_entity_type,
    nice_classes,
    us_classes,
    goods_and_services,
    description_of_mark,
    representative_name,
    applicant_country,
    mark_basis,
    image_url,
    is_pharma_related,
    NULL::UUID AS molecule_id,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined
ORDER BY trademark_identifier, source, source_updated_at DESC
