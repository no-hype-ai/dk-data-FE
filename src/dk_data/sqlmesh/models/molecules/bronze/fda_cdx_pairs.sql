-- SQLMesh Model: Bronze FDA Companion Diagnostic (CDx) Pairs
-- Transforms raw JSONB scraped CDx records into typed bronze layer.
-- Source table: mol_raw.fda_cdx_pairs (JSONB response_body)
-- Feature: 006-claims-engine-data-gaps (T035)

MODEL (
    name mol_bronze.fda_cdx_pairs,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key cdx_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (cdx_id))
    ),
    grain (cdx_id)
);

SELECT
    COALESCE(
        r.response_body->>'id',
        r.request_id
    )::TEXT                                             AS cdx_id,
    COALESCE(
        r.response_body->>'device_name',
        r.response_body->>'diagnostic_name'
    )::TEXT                                             AS device_name,
    COALESCE(
        r.response_body->>'manufacturer',
        r.response_body->>'company'
    )::TEXT                                             AS manufacturer,
    (r.response_body->>'intended_use')::TEXT            AS intended_use,
    COALESCE(
        r.response_body->>'drug_trade_name',
        r.response_body->>'therapeutic_product'
    )::TEXT                                             AS drug_trade_name,
    COALESCE(
        r.response_body->>'drug_generic_name',
        r.response_body->>'active_ingredient'
    )::TEXT                                             AS drug_generic_name,
    CASE
        WHEN r.response_body->>'approval_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (r.response_body->>'approval_date')::DATE
        ELSE NULL
    END                                                 AS approval_date,
    COALESCE(
        r.response_body->>'submission_type',
        r.response_body->>'regulatory_pathway'
    )::TEXT                                             AS submission_type,
    COALESCE(
        r.response_body->>'source_url',
        'https://www.fda.gov/medical-devices/in-vitro-diagnostics/list-cleared-or-approved-companion-diagnostic-devices-in-vitro-and-imaging-tools'
    )::TEXT                                             AS source_url,

    -- Source tracking
    'fda_cdx_pairs'                                    AS source,
    r.ingested_at                                      AS source_updated_at,
    FALSE                                              AS processed_to_silver,
    r.ingested_at                                      AS ingested_at

FROM mol_raw.fda_cdx_pairs r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'id',
      r.request_id
  ) IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
