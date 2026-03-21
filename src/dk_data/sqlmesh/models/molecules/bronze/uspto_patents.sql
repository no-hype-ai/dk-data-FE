-- SQLMesh Model: Bronze USPTO Patents
-- Transforms raw USPTO PatentSearch flat columns into typed bronze layer
-- Part of: 014-uspto-euipo-model-datasource (fixes broken JSONB extraction from 012)

MODEL (
    name bronze.uspto_patents,
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
    r.patent_number,
    r.title AS patent_title,
    r.abstract AS patent_abstract,
    r.filing_date,
    r.grant_date AS patent_date,

    -- Classification
    NULL::TEXT AS patent_type,
    NULL::TEXT AS patent_kind,
    CASE
        WHEN r.cpc_codes IS NOT NULL
        THEN to_jsonb(r.cpc_codes)
        ELSE NULL
    END AS cpc_codes,

    -- Assignee info (fetcher normalizes to {"organization": ..., "city": ..., ...})
    r.assignees->0->>'organization' AS assignee_organization,
    NULL::TEXT AS assignee_type,

    -- Inventors as JSONB
    r.inventors,

    -- Claims count
    r.claims_count AS num_claims,

    -- Determine if pharma-related based on CPC codes
    EXISTS (
        SELECT 1 FROM unnest(COALESCE(r.cpc_codes, '{}')) AS code
        WHERE code LIKE 'A61K%' OR code LIKE 'A61P%'
           OR code LIKE 'C07D%' OR code LIKE 'C07K%'
    ) AS is_pharma_related,

    -- Processing metadata
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at

FROM mol_raw.uspto_patents r
WHERE r.patent_number IS NOT NULL
  AND r.processed_to_bronze = FALSE
  AND _loaded_at BETWEEN @start_dt AND @end_dt
