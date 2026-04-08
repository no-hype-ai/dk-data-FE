-- SQLMesh Model: Bronze USPTO Patents
-- Transforms raw USPTO PatentSearch flat columns into typed bronze layer
-- Part of: 014-uspto-euipo-model-datasource (fixes broken JSONB extraction from 012)

MODEL (
    name mol_bronze.uspto_patents,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key patent_number
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

    -- Classification (mol_raw.uspto_patents does not carry patent_type; default to 'utility')
    'utility'::TEXT AS patent_type,
    NULL::TEXT AS patent_kind,
    to_jsonb(r.cpc_codes) AS cpc_codes,

    -- Assignee info (fetcher normalizes to {"organization": ..., "city": ..., ...})
    r.assignees->0->>'organization' AS assignee_organization,
    NULL::TEXT AS assignee_type,

    -- Inventors as JSONB
    r.inventors,

    -- Claims count
    r.claims_count AS num_claims,

    -- Determine if pharma-related based on CPC codes (mol_raw.uspto_patents.cpc_codes is TEXT[]; cast first)
    EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(COALESCE(to_jsonb(r.cpc_codes), '[]'::JSONB)) AS code
        WHERE code LIKE 'A61K%' OR code LIKE 'A61P%'
           OR code LIKE 'C07D%' OR code LIKE 'C07K%'
    ) AS is_pharma_related,

    -- Processing metadata
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at

FROM mol_raw.uspto_patents r
WHERE r.patent_number IS NOT NULL
  AND _loaded_at BETWEEN @start_dt AND @end_dt
