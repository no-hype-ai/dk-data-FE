-- SQLMesh Model: Bronze CMS Part D Prescriber PUF
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_part_d_prescriber,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi, drug_brand_name, year))),
    grain (npi, drug_brand_name, year)
);

SELECT
    response_body->>'npi'                                   AS npi,
    response_body->>'drug_brand_name'                       AS drug_brand_name,
    response_body->>'drug_generic_name'                     AS drug_generic_name,
    response_body->>'prescriber_last_org_name'              AS prescriber_last_org_name,
    response_body->>'prescriber_first_name'                 AS prescriber_first_name,
    response_body->>'prescriber_state'                      AS prescriber_state,
    response_body->>'prescriber_type'                       AS prescriber_type,
    (response_body->>'total_claims')::INTEGER               AS total_claims,
    (response_body->>'total_30day_fills')::NUMERIC          AS total_30day_fills,
    (response_body->>'total_drug_cost')::NUMERIC(12,2)      AS total_drug_cost,
    (response_body->>'total_beneficiaries')::INTEGER        AS total_beneficiaries,
    (response_body->>'year')::INTEGER                       AS year,
    response_body                                           AS raw_json,
    id                                                      AS raw_source_id,
    'cms_part_d_prescriber'                                 AS source,
    ingested_at
FROM hcs_raw.cms_part_d_prescriber
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
