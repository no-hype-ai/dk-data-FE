-- SQLMesh Model: Bronze HTA Decisions
-- Transforms raw HTA agency decision responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration
-- Updated: reads from mol_raw.hta_decisions, extracts decision/date fields

MODEL (
    name mol_bronze.hta_decisions,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (decision_id)),
        unique_values(columns := (decision_id))
    ),
    grain decision_id
);

SELECT
    gen_random_uuid() AS id,

    -- Decision identifiers
    COALESCE(
        response_body->>'id',
        response_body->>'guidance_id',
        response_body->>'agency' || '_' || response_body->>'drug_name' || '_' || COALESCE(response_body->>'decision_date', 'unknown')
    ) AS decision_id,
    COALESCE(response_body->>'agency', 'NICE') AS agency,
    response_body->>'drug_name' AS drug_name,
    response_body->>'indication' AS indication,
    response_body->>'decision' AS decision,
    response_body->>'decision_date' AS decision_date,
    response_body->>'recommendation' AS recommendation,
    response_body->>'recommendation_details' AS recommendation_details,
    response_body->>'therapeutic_area' AS therapeutic_area,
    response_body->>'guidance_id' AS guidance_id,
    response_body->>'title' AS title,
    response_body->>'url' AS url,
    response_body->>'icer_value' AS icer_value,

    -- Raw source tracking
    response_body AS raw_json,
    r.id AS raw_source_id,
    'hta_decisions' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.hta_decisions r
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND (response_body->>'drug_name' IS NOT NULL OR response_body->>'title' IS NOT NULL)
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
