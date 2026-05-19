-- SQLMesh Model: Bronze EUIPO Trademarks
-- Transforms raw EUIPO TMview/IBM Gateway trademark data into typed bronze layer
-- Part of: 014-uspto-euipo-model-datasource
-- Migrated from mol_bronze → ip_bronze by 001-silver-medallion-rebuild (FR-006d)

MODEL (
    name ip_bronze.euipo_trademarks,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key application_number
    ),
    cron '@weekly',
    grain (application_number),
    audits (
        not_null(columns := (application_number)),
        unique_values(columns := (application_number))
    )
);

SELECT
    gen_random_uuid() AS id,

    -- Trademark identification
    r.application_number,
    r.mark_name,

    -- EUIPO-specific classification fields
    r.mark_kind,
    r.mark_feature,
    r.mark_basis,

    -- Applicant info
    r.applicant_name,
    r.applicant_country,
    r.representative_name,

    -- Status
    r.status,

    -- Dates
    r.filing_date,
    r.registration_date,
    r.expiry_date,

    -- Classification (ip_raw.euipo_trademarks.nice_classes is INTEGER[]; cast to JSONB for bronze)
    to_jsonb(r.nice_classes) AS nice_classes,

    -- Description
    r.goods_and_services,

    -- Trademark image
    r.image_url,

    -- Pharma relevance: Nice Class 5 = Pharmaceuticals
    to_jsonb(COALESCE(r.nice_classes, '{}')) @> '[5]'::jsonb AS is_pharma_related,

    -- Processing metadata
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at

FROM ip_raw.euipo_trademarks r
WHERE r.application_number IS NOT NULL
  AND _loaded_at BETWEEN @start_dt AND @end_dt
