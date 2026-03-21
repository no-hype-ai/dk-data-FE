-- SQLMesh Model: Bronze EMA (European Medicines Agency)
-- Transforms raw EMA API responses into typed bronze layer
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.ema,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
    ),
    cron '@weekly',
    grain (product_number),
    audits (
        not_null(columns := (product_number)),
        unique_values(columns := (product_number))
    )
);

SELECT
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- Medicine identification
    COALESCE(
        r.response_body->>'productNumber',
        r.response_body->>'product_number'
    ) AS product_number,
    COALESCE(
        r.response_body->>'name',
        r.response_body->>'product_name'
    ) AS product_name,
    COALESCE(
        r.response_body->>'activeSubstance',
        r.response_body->>'active_substance'
    ) AS active_substance,
    r.response_body->>'inn' AS inn,
    COALESCE(
        r.response_body->>'atcCode',
        r.response_body->>'atc_code'
    ) AS atc_code,

    -- Authorization info
    COALESCE(
        r.response_body->>'marketingAuthorisationHolder',
        r.response_body->>'holder'
    ) AS marketing_authorization_holder,
    COALESCE(
        r.response_body->>'authorizationStatus',
        r.response_body->>'status'
    ) AS authorization_status,
    CASE
        WHEN r.response_body->>'authorizationDate' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'authorizationDate')::DATE
        WHEN r.response_body->>'authorization_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'authorization_date')::DATE
        ELSE NULL
    END AS authorization_date,
    CASE
        WHEN r.response_body->>'revisionDate' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'revisionDate')::DATE
        WHEN r.response_body->>'revision_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'revision_date')::DATE
        ELSE NULL
    END AS revision_date,

    -- Product type
    COALESCE(
        r.response_body->>'medicineType',
        r.response_body->>'type'
    ) AS medicine_type,
    COALESCE(
        r.response_body->>'therapeuticArea',
        r.response_body->>'therapeutic_area'
    ) AS therapeutic_area,
    r.response_body->>'pharmacotherapeuticGroup' AS pharmacotherapeutic_group,

    -- Regulatory docs
    COALESCE(
        r.response_body->>'eparUrl',
        r.response_body->>'epar_url'
    ) AS epar_url,
    COALESCE(
        r.response_body->>'summaryUrl',
        r.response_body->>'summary_url'
    ) AS summary_url,

    -- Processing metadata
    FALSE AS processed_to_silver,
    NOW() AS ingested_at

FROM mol_raw.ema r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'productNumber',
      r.response_body->>'product_number'
  ) IS NOT NULL
