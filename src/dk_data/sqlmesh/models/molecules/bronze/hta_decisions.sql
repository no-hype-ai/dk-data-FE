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
        response_body::jsonb->>'id',
        response_body::jsonb->>'guidance_id',
        (response_body::jsonb->>'agency') || '_' || (response_body::jsonb->>'drug_name') || '_' || COALESCE(response_body::jsonb->>'decision_date', 'unknown')
    ) AS decision_id,
    COALESCE(response_body::jsonb->>'agency', 'NICE') AS agency,
    response_body::jsonb->>'drug_name' AS drug_name,
    response_body::jsonb->>'indication' AS indication,
    response_body::jsonb->>'decision' AS decision,
    response_body::jsonb->>'decision_date' AS decision_date,
    response_body::jsonb->>'recommendation' AS recommendation,
    response_body::jsonb->>'recommendation_details' AS recommendation_details,
    response_body::jsonb->>'therapeutic_area' AS therapeutic_area,
    response_body::jsonb->>'guidance_id' AS guidance_id,
    response_body::jsonb->>'title' AS title,
    response_body::jsonb->>'url' AS url,
    response_body::jsonb->>'icer_value' AS icer_value,

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
    AND (response_body::jsonb->>'drug_name' IS NOT NULL OR response_body::jsonb->>'title' IS NOT NULL)
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
