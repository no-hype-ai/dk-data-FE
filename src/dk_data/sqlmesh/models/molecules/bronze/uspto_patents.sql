-- SQLMesh Model: Bronze USPTO Patents
-- Extracts fields from response_body JSONB (authoritative raw API payload).
-- All fields come from response_body so new PatentsView API fields are auto-available.
-- Part of: 014-uspto-euipo-model-datasource

MODEL (
    name mol_bronze.uspto_patents,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
    ),
    cron '@weekly',
    grain (patent_number),
    audits (
        not_null(columns := (patent_number)),
        unique_values(columns := (patent_number))
    )
);

SELECT
    gen_random_uuid() AS id,

    -- Patent identification
    r.response_body->>'patent_number'        AS patent_number,
    r.response_body->>'title'                AS patent_title,
    r.response_body->>'abstract'             AS patent_abstract,
    CASE WHEN r.response_body->>'filing_date' ~ '^\d{4}-\d{2}-\d{2}'
         THEN (r.response_body->>'filing_date')::DATE ELSE NULL END AS filing_date,
    CASE WHEN r.response_body->>'grant_date' ~ '^\d{4}-\d{2}-\d{2}'
         THEN (r.response_body->>'grant_date')::DATE ELSE NULL END AS patent_date,

    -- Classification
    NULL::TEXT                               AS patent_type,
    NULL::TEXT                               AS patent_kind,
    -- CPC codes as JSONB array (zero-copy from raw)
    r.response_body->'cpc_codes'             AS cpc_codes,

    -- Assignee info (API returns [{"organization": ..., "city": ..., ...}])
    r.response_body->'assignees'->0->>'organization' AS assignee_organization,
    NULL::TEXT                               AS assignee_type,

    -- Inventors as JSONB array
    r.response_body->'inventors'             AS inventors,

    -- Claims count
    (r.response_body->>'claims_count')::INTEGER AS num_claims,

    -- Full raw response preserved for any additional fields
    r.response_body                          AS raw_json,

    -- Pharma relevance: CPC codes A61K/A61P/C07D/C07K
    EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(
            COALESCE(r.response_body->'cpc_codes', '[]'::jsonb)
        ) AS code
        WHERE code LIKE 'A61K%' OR code LIKE 'A61P%'
           OR code LIKE 'C07D%' OR code LIKE 'C07K%'
    ) AS is_pharma_related,

    -- Processing metadata
    FALSE                                    AS processed_to_silver,
    r.ingested_at

FROM mol_raw.uspto_patents r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND (r.response_body->>'patent_number') IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
