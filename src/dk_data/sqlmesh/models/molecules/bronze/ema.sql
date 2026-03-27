-- SQLMesh Model: Bronze EMA (European Medicines Agency)
-- Transforms raw EMA JSONB API responses into typed bronze layer
-- Part of DK Molecule Data Platform (012-dk-data-platform)
--
-- Source table: raw.ema (JSONB response_body, see migration 062_mol_source_raw_tables.sql)
-- Loaded by: src/dk_data/ingestion/sources/ema_regulatory.py
--
-- EMA API field mapping (camelCase and snake_case variants both covered):
--   productNumber / product_number -> product_number
--   name / product_name           -> product_name
--   activeSubstance / active_substance / inn -> active_substance
--   atcCode / atc_code            -> atc_code
--   marketingAuthorisationHolder / holder -> marketing_authorization_holder
--   authorizationStatus / status  -> authorization_status
--   authorizationDate / authorization_date -> authorization_date (DATE)
--   revisionDate / revision_date  -> revision_date (DATE)
--   medicineType / type           -> medicine_type
--   therapeuticArea / therapeutic_area -> therapeutic_area
--   pharmacotherapeuticGroup      -> pharmacotherapeutic_group
--   eparUrl / epar_url            -> epar_url
--   summaryUrl / summary_url      -> summary_url

MODEL (
    name bronze.ema,
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
    )::TEXT AS product_number,
    COALESCE(
        r.response_body->>'name',
        r.response_body->>'product_name'
    )::TEXT AS product_name,
    COALESCE(
        r.response_body->>'activeSubstance',
        r.response_body->>'active_substance',
        r.response_body->>'inn'
    )::TEXT AS active_substance,
    (r.response_body->>'inn')::TEXT AS inn,
    COALESCE(
        r.response_body->>'atcCode',
        r.response_body->>'atc_code'
    )::TEXT AS atc_code,

    -- Authorization info
    COALESCE(
        r.response_body->>'marketingAuthorisationHolder',
        r.response_body->>'holder'
    )::TEXT AS marketing_authorization_holder,
    COALESCE(
        r.response_body->>'authorizationStatus',
        r.response_body->>'status'
    )::TEXT AS authorization_status,
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
    )::TEXT AS medicine_type,
    COALESCE(
        r.response_body->>'therapeuticArea',
        r.response_body->>'therapeutic_area'
    )::TEXT AS therapeutic_area,
    (r.response_body->>'pharmacotherapeuticGroup')::TEXT AS pharmacotherapeutic_group,

    -- Regulatory docs
    COALESCE(
        r.response_body->>'eparUrl',
        r.response_body->>'epar_url'
    )::TEXT AS epar_url,
    COALESCE(
        r.response_body->>'summaryUrl',
        r.response_body->>'summary_url'
    )::TEXT AS summary_url,

    -- Source tracking
    'ema'                       AS source,
    r.ingested_at               AS source_updated_at,

    -- Processing metadata
    FALSE                       AS processed_to_silver,
    r.ingested_at               AS ingested_at

FROM raw.ema r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'productNumber',
      r.response_body->>'product_number'
  ) IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
