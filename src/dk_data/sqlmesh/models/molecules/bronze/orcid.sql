-- SQLMesh Model: Bronze ORCID Researchers
-- Transforms raw ORCID API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.orcid,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (orcid_id)),
        unique_values(columns := (orcid_id))
    ),
    grain orcid_id
);

SELECT
    gen_random_uuid() AS id,

    -- Researcher identifiers
    response_body->>'orcid-identifier' AS orcid_id,
    response_body->'person'->'name'->>'given-names' AS given_name,
    response_body->'person'->'name'->>'family-name' AS family_name,
    response_body->'activities-summary'->'employments' AS affiliations,
    (response_body->'activities-summary'->'works'->>'count')::INTEGER AS works_count,
    response_body->'activities-summary'->'research-resources' AS research_areas,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'orcid' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.orcid
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'orcid-identifier' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
