-- SQLMesh Model: Bronze CMS Medicare Coverage Database
-- Feature: 021-post-deploy-fixes
--
-- Transforms raw CMS Coverage API responses to Bronze typed columns.
-- API: https://api.coverage.cms.gov/v1/data/
-- Endpoints: /data/ncd/, /data/nca/, /data/technology-assessment/
-- Each record tagged with _endpoint field for deduplication.
-- US equivalent of NICE HTA — authoritative Medicare coverage policy decisions.

MODEL (
    name mol_bronze.cms_coverage,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (coverage_id, endpoint)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (coverage_id))
    ),
    grain (coverage_id, endpoint)
);

SELECT
    gen_random_uuid()                                                    AS id,

    r.response_body->>'id'                                               AS coverage_id,
    r.response_body->>'_endpoint'                                        AS endpoint,

    -- Title / description
    COALESCE(
        r.response_body->>'title',
        r.response_body->>'name',
        r.response_body->>'ncdTitle',
        r.response_body->>'analysisTitle'
    )                                                                    AS title,

    -- Decision / status
    COALESCE(
        r.response_body->>'decision',
        r.response_body->>'status',
        r.response_body->>'coverageStatus',
        r.response_body->>'finalDecision'
    )                                                                    AS decision,

    -- Dates
    CASE
        WHEN (r.response_body->>'decisionDate') IS NOT NULL
             AND (r.response_body->>'decisionDate') ~ '^\d{4}'
        THEN (r.response_body->>'decisionDate')::DATE
        WHEN (r.response_body->>'dateOfDecision') IS NOT NULL
             AND (r.response_body->>'dateOfDecision') ~ '^\d{4}'
        THEN (r.response_body->>'dateOfDecision')::DATE
        WHEN (r.response_body->>'effectiveDate') IS NOT NULL
             AND (r.response_body->>'effectiveDate') ~ '^\d{4}'
        THEN (r.response_body->>'effectiveDate')::DATE
        WHEN (r.response_body->>'date') IS NOT NULL
             AND (r.response_body->>'date') ~ '^\d{4}'
        THEN (r.response_body->>'date')::DATE
        ELSE NULL
    END                                                                  AS decision_date,

    CASE
        WHEN (r.response_body->>'lastUpdated') IS NOT NULL
             AND (r.response_body->>'lastUpdated') ~ '^\d{4}'
        THEN (r.response_body->>'lastUpdated')::DATE
        ELSE NULL
    END                                                                  AS last_updated_date,

    -- NCD number / identifier
    COALESCE(
        r.response_body->>'ncdNumber',
        r.response_body->>'ncaNumber',
        r.response_body->>'taNumber',
        r.response_body->>'trackingNumber'
    )                                                                    AS source_number,

    -- Topic / indication
    COALESCE(
        r.response_body->>'topic',
        r.response_body->>'indication',
        r.response_body->>'subject'
    )                                                                    AS topic,

    -- Raw source tracking
    r.response_body                                                      AS raw_json,
    r.id::TEXT                                                           AS raw_source_id,
    'cms_coverage'                                                       AS source,
    r.ingested_at                                                        AS source_updated_at,
    FALSE                                                                AS processed_to_silver,
    NOW()                                                                AS created_at,
    r.ingested_at

FROM mol_raw.cms_coverage r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body->>'id' IS NOT NULL
  AND r.response_body->>'_endpoint' IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt;
