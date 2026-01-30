-- SQLMesh Model: Bronze USPTO Patents
-- Transforms raw USPTO PatentsView API responses into typed bronze layer
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name bronze.uspto_patents,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7
    ),
    cron '@weekly',
    grain (patent_number),
    audits (
        not_null(patent_number),
        unique(patent_number)
    )
);

SELECT
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- Patent identification
    p->>'patent_number' AS patent_number,
    p->>'patent_title' AS patent_title,
    p->>'patent_abstract' AS patent_abstract,
    CASE
        WHEN p->>'patent_date' ~ '^\d{4}-\d{2}-\d{2}'
        THEN (p->>'patent_date')::DATE
        ELSE NULL
    END AS patent_date,

    -- Classification
    p->>'patent_type' AS patent_type,
    p->>'patent_kind' AS patent_kind,
    -- Extract CPC codes as JSONB array
    (
        SELECT jsonb_agg(DISTINCT cpc->>'cpc_group_id')
        FROM jsonb_array_elements(COALESCE(p->'cpcs', '[]'::jsonb)) AS cpc
        WHERE cpc->>'cpc_group_id' IS NOT NULL
    ) AS cpc_codes,

    -- Assignee info
    COALESCE(
        p->'assignees'->0->>'assignee_organization',
        (
            SELECT a->>'assignee_organization'
            FROM jsonb_array_elements(COALESCE(p->'assignees', '[]'::jsonb)) a
            WHERE a->>'assignee_organization' IS NOT NULL
            LIMIT 1
        )
    ) AS assignee_organization,
    COALESCE(
        p->'assignees'->0->>'assignee_type',
        (
            SELECT a->>'assignee_type'
            FROM jsonb_array_elements(COALESCE(p->'assignees', '[]'::jsonb)) a
            WHERE a->>'assignee_type' IS NOT NULL
            LIMIT 1
        )
    ) AS assignee_type,

    -- Inventors as JSONB
    (
        SELECT jsonb_agg(
            jsonb_build_object(
                'first_name', inv->>'inventor_first_name',
                'last_name', inv->>'inventor_last_name',
                'city', inv->>'inventor_city',
                'country', inv->>'inventor_country'
            )
        )
        FROM jsonb_array_elements(COALESCE(p->'inventors', '[]'::jsonb)) AS inv
        WHERE inv->>'inventor_last_name' IS NOT NULL
    ) AS inventors,

    -- Claims count
    (p->>'patent_num_claims')::INTEGER AS num_claims,

    -- Determine if pharma-related based on CPC codes
    EXISTS (
        SELECT 1
        FROM jsonb_array_elements(COALESCE(p->'cpcs', '[]'::jsonb)) AS cpc
        WHERE cpc->>'cpc_group_id' LIKE 'A61K%'
           OR cpc->>'cpc_group_id' LIKE 'A61P%'
           OR cpc->>'cpc_group_id' LIKE 'C07D%'
           OR cpc->>'cpc_group_id' LIKE 'C07K%'
    ) AS is_pharma_related,

    -- Processing metadata
    FALSE AS processed_to_silver,
    NOW() AS ingested_at

FROM raw.uspto_patents r,
     jsonb_array_elements(COALESCE(r.response_body->'patents', '[]'::jsonb)) AS p
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND p->>'patent_number' IS NOT NULL
