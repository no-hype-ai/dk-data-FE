-- SQLMesh Model: Bronze EPO Patents
-- Transforms raw EPO Open Patent Services data into typed bronze layer
-- Part of: 014-uspto-euipo-model-datasource
-- Migrated from mol_bronze → ip_bronze by 001-silver-medallion-rebuild (FR-006d)

MODEL (
    name ip_bronze.epo_patents,
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

    -- Patent identification (publication_id → patent_number for schema consistency)
    r.publication_id AS patent_number,
    r.title AS patent_title,
    r.abstract AS patent_abstract,
    r.filing_date,
    r.publication_date AS patent_date,

    -- Classification: ipc_codes is TEXT[] in ip_raw.epo_patents; cpc_codes does not exist
    CASE
        WHEN r.ipc_codes IS NOT NULL
        THEN to_jsonb(r.ipc_codes)
        ELSE NULL
    END AS ipc_codes,
    NULL::JSONB AS cpc_codes,

    -- Assignee info (->> extracts text from JSONB array)
    r.applicants->>0 AS assignee_organization,

    -- Inventors as JSONB
    r.inventors,

    -- Claims count (not available from EPO OPS)
    NULL::INTEGER AS num_claims,

    -- EPO-specific: patent family ID
    r.family_id,

    -- Determine if pharma-related based on IPC codes (ipc_codes is TEXT[])
    (
        EXISTS (
            SELECT 1 FROM unnest(COALESCE(r.ipc_codes, '{}'::TEXT[])) AS code
            WHERE code LIKE 'A61K%' OR code LIKE 'A61P%'
               OR code LIKE 'C07D%' OR code LIKE 'C07K%'
        )
    ) AS is_pharma_related,

    -- Processing metadata
    FALSE AS processed_to_silver,
    r._loaded_at AS ingested_at

FROM ip_raw.epo_patents r
WHERE r.publication_id IS NOT NULL
  AND _loaded_at BETWEEN @start_dt AND @end_dt
