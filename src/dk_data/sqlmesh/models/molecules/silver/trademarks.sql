-- SQLMesh Model: Silver Trademarks
-- Unified trademark data from USPTO TSDR and EUIPO TMview/IBM Gateway
-- Part of: 014-uspto-euipo-model-datasource

-- Entity linking: LEFT JOIN mol_silver.molecules by canonical_name match in mark_name.
-- FULL refresh ensures molecule_id is always current when new molecules are added.

MODEL (
    name mol_silver.trademarks,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (trademark_identifier)),
        not_null(columns := (source))
    )
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
    FROM mol_bronze.uspto_trademarks
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
    FROM mol_bronze.euipo_trademarks
    WHERE TRUE
),

-- Combine both registries
combined AS (
    SELECT * FROM uspto
    UNION ALL
    SELECT * FROM euipo
)

-- Within-registry dedup only (no cross-registry dedup)
SELECT DISTINCT ON (c.trademark_identifier, c.source)
    gen_random_uuid() AS id,
    c.trademark_identifier,
    c.mark_name,
    c.mark_type,
    c.mark_feature,
    c.status,
    c.status_code,
    c.status_date,
    c.filing_date,
    c.registration_number,
    c.registration_date,
    c.expiry_date,
    c.owner_name,
    c.owner_entity_type,
    c.nice_classes,
    c.us_classes,
    c.goods_and_services,
    c.description_of_mark,
    c.representative_name,
    c.applicant_country,
    c.mark_basis,
    c.image_url,
    c.is_pharma_related,
    m.molecule_id,
    c.source,
    c.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM combined c
LEFT JOIN mol_silver.molecules m
       ON c.mark_name IS NOT NULL
      AND LOWER(c.mark_name) LIKE '%' || LOWER(m.canonical_name) || '%'
      AND LENGTH(m.canonical_name) > 4
ORDER BY c.trademark_identifier, c.source, c.source_updated_at DESC
