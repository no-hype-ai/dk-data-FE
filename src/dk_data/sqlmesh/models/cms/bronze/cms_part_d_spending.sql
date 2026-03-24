-- SQLMesh Model: Bronze CMS Part D Drug Spending
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_part_d_spending,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (brand_name, year))),
    grain (brand_name, year)
);

SELECT
    response_body->>'brand_name'                            AS brand_name,
    response_body->>'generic_name'                          AS generic_name,
    (response_body->>'total_spending')::NUMERIC(14,2)       AS total_spending,
    (response_body->>'total_claims')::INTEGER               AS total_claims,
    (response_body->>'total_beneficiaries')::INTEGER        AS total_beneficiaries,
    (response_body->>'avg_cost_per_claim')::NUMERIC(10,2)   AS avg_cost_per_claim,
    (response_body->>'year')::INTEGER                       AS year,
    response_body                                           AS raw_json,
    id                                                      AS raw_source_id,
    'cms_part_d_spending'                                   AS source,
    ingested_at
FROM hcs_raw.cms_part_d_spending
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
