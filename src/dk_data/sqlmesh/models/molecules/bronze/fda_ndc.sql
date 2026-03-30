-- SQLMesh Model: Bronze FDA NDC
-- Extracts NDC product records from mol_raw.fda_ndc.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Source: OpenFDA /drug/ndc endpoint.
-- Each mol_raw.fda_ndc row is one NDC product record.
--
-- OpenFDA /drug/ndc field names:
--   product_ndc, generic_name, brand_name, labeler_name,
--   product_type (HUMAN PRESCRIPTION DRUG / OTC / etc.),
--   dosage_form, route, marketing_status,
--   active_ingredients[].name, active_ingredients[].strength,
--   listing_expiration_date, finished, packaging[].package_ndc

MODEL (
    name mol_bronze.fda_ndc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 1000
    ),
    cron '@monthly',
    audits (
        not_null(columns := (product_ndc))
    ),
    grain product_ndc
);

WITH ndc_products AS (
    SELECT
        raw.id          AS raw_source_id,
        raw.ingested_at,
        raw.response_body AS prod
    FROM mol_raw.fda_ndc AS raw
    WHERE raw.response_status = 200
      AND raw.processed_to_bronze = FALSE
      AND raw.ingested_at BETWEEN @start_dt AND @end_dt
),

deduped AS (
    SELECT DISTINCT ON (prod->>'product_ndc')
        raw_source_id,
        ingested_at,
        prod
    FROM ndc_products
    WHERE prod->>'product_ndc' IS NOT NULL
    ORDER BY prod->>'product_ndc', ingested_at DESC
)

SELECT
    gen_random_uuid()                                                   AS id,

    prod->>'product_ndc'                                                AS product_ndc,
    prod->>'generic_name'                                               AS generic_name,
    prod->>'brand_name'                                                 AS brand_name,
    prod->>'labeler_name'                                               AS labeler_name,
    prod->>'product_type'                                               AS product_type,
    prod->>'dosage_form'                                                AS dosage_form,

    -- route is an array in OpenFDA; store first value as TEXT, full as JSONB
    (prod->'route'->>0)                                                 AS route,
    prod->'route'                                                       AS routes,

    prod->>'marketing_status'                                           AS marketing_status,

    -- Active ingredients: [{name, strength}]
    prod->'active_ingredients'                                          AS active_ingredients,

    -- Package NDCs (all package-level NDCs for this product)
    ARRAY(
        SELECT pkg->>'package_ndc'
        FROM jsonb_array_elements(COALESCE(prod->'packaging', '[]'::JSONB)) AS pkg
        WHERE pkg->>'package_ndc' IS NOT NULL
    )                                                                   AS package_ndcs,

    (prod->>'listing_expiration_date')::DATE                            AS listing_expiration_date,

    CASE prod->>'finished'
        WHEN 'true' THEN TRUE WHEN '1' THEN TRUE
        WHEN 'false' THEN FALSE WHEN '0' THEN FALSE
        ELSE NULL
    END                                                                 AS finished,

    -- Source tracking
    prod                                                                AS raw_json,
    raw_source_id,
    'fda_ndc'                                                           AS source,
    ingested_at,
    ingested_at                                                         AS source_updated_at,
    FALSE                                                               AS processed_to_silver,
    NOW()                                                               AS created_at

FROM deduped;
