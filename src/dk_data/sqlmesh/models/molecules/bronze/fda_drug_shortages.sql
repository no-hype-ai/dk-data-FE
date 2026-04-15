-- SQLMesh Model: Bronze FDA Drug Shortages
-- Transforms raw openFDA Drug Shortages JSONB responses into typed bronze layer.
-- Source table: mol_raw.fda_drug_shortages (JSONB response_body)
-- Feature: 006-claims-engine-data-gaps (T032)

MODEL (
    name mol_bronze.fda_drug_shortages,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key shortage_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (shortage_id))
    ),
    grain (shortage_id)
);

SELECT
    COALESCE(
        r.response_body->>'id',
        r.request_id
    )::TEXT                                              AS shortage_id,
    (r.response_body->>'generic_name')::TEXT             AS generic_name,
    (r.response_body->>'brand_name')::TEXT               AS brand_name,
    COALESCE(
        r.response_body->>'company',
        r.response_body->>'firm_name',
        r.response_body->>'manufacturer'
    )::TEXT                                              AS company,
    COALESCE(
        r.response_body->>'status',
        r.response_body->>'shortage_status'
    )::TEXT                                              AS status,
    COALESCE(
        r.response_body->>'shortage_reason',
        r.response_body->>'reason_for_shortage'
    )::TEXT                                              AS shortage_reason,
    CASE
        WHEN r.response_body->>'shortage_start_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'shortage_start_date')::DATE
        WHEN r.response_body->>'start_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'start_date')::DATE
        ELSE NULL
    END                                                  AS shortage_start_date,
    CASE
        WHEN r.response_body->>'shortage_end_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'shortage_end_date')::DATE
        WHEN r.response_body->>'end_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'end_date')::DATE
        ELSE NULL
    END                                                  AS shortage_end_date,
    COALESCE(
        r.response_body->'affected_products',
        r.response_body->'products'
    )::JSONB                                             AS affected_products,
    (r.response_body->>'notes')::TEXT                    AS notes,

    -- Source tracking
    'fda_drug_shortages'                                 AS source,
    r.ingested_at                                        AS source_updated_at,
    FALSE                                                AS processed_to_silver,
    r.ingested_at                                        AS ingested_at

FROM mol_raw.fda_drug_shortages r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'id',
      r.request_id
  ) IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
