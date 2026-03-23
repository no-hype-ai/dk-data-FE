-- SQLMesh Model: Bronze EUIPO Trademarks
-- Extracts fields from response_body JSONB (authoritative raw API payload).
-- All fields come from response_body so new API fields are auto-available.
-- Part of: 014-uspto-euipo-model-datasource

MODEL (
    name mol_bronze.euipo_trademarks,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
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

    -- Trademark identification (extracted from response_body JSONB)
    r.response_body->>'application_number'   AS application_number,
    r.response_body->>'mark_name'            AS mark_name,

    -- EUIPO-specific classification fields
    r.response_body->>'mark_kind'            AS mark_kind,
    r.response_body->>'mark_feature'         AS mark_feature,
    r.response_body->>'mark_basis'           AS mark_basis,

    -- Applicant info
    r.response_body->>'applicant_name'       AS applicant_name,
    r.response_body->>'applicant_country'    AS applicant_country,
    r.response_body->>'representative_name'  AS representative_name,

    -- Status
    r.response_body->>'status'               AS status,

    -- Dates (cast from text; API returns ISO strings)
    CASE WHEN r.response_body->>'filing_date' ~ '^\d{4}-\d{2}-\d{2}'
         THEN (r.response_body->>'filing_date')::DATE ELSE NULL END AS filing_date,
    CASE WHEN r.response_body->>'registration_date' ~ '^\d{4}-\d{2}-\d{2}'
         THEN (r.response_body->>'registration_date')::DATE ELSE NULL END AS registration_date,
    CASE WHEN r.response_body->>'expiry_date' ~ '^\d{4}-\d{2}-\d{2}'
         THEN (r.response_body->>'expiry_date')::DATE ELSE NULL END AS expiry_date,

    -- Nice class classification (JSONB array — zero-copy, all raw values preserved)
    r.response_body->'nice_classes'          AS nice_classes,

    -- Goods and services description
    r.response_body->>'goods_and_services'   AS goods_and_services,

    -- Trademark image URL
    r.response_body->>'image_url'            AS image_url,

    -- Full raw response preserved for any additional fields
    r.response_body                          AS raw_json,

    -- Pharma relevance: Nice Class 5 = Pharmaceuticals
    EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(
            COALESCE(r.response_body->'nice_classes', '[]'::jsonb)
        ) AS c
        WHERE c::INTEGER = 5
    ) AS is_pharma_related,

    -- Processing metadata
    FALSE                                    AS processed_to_silver,
    r.ingested_at

FROM mol_raw.euipo_trademarks r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND (r.response_body->>'application_number') IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
