-- SQLMesh Model: Silver Bioactivity
-- Normalized bioactivity data from ChEMBL
-- Part of: 012-dk-data-platform

MODEL (
    name silver.bioactivity,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column source_updated_at,
        batch_size 1000
    ),
    cron '@weekly',
    audits (
        not_null(columns := (activity_id, chembl_id))
    ),
    grain activity_id
);

-- ChEMBL activity data comes from a separate API endpoint
-- For now, extract from cross_references in chembl_molecules
-- In production, there would be a raw.chembl_activities table

WITH activity_data AS (
    SELECT
        gen_random_uuid() AS id,
        chembl_id,
        inchi_key,

        -- Placeholder for actual activity data
        -- Would come from ChEMBL Activity API
        NULL::TEXT AS activity_id,
        NULL::TEXT AS assay_chembl_id,
        NULL::TEXT AS assay_type,
        NULL::TEXT AS assay_description,
        NULL::TEXT AS target_chembl_id,
        NULL::TEXT AS target_name,
        NULL::TEXT AS target_type,
        NULL::TEXT AS target_organism,
        NULL::TEXT AS uniprot_id,

        -- Activity measurements
        NULL::TEXT AS standard_type,
        NULL::NUMERIC AS standard_value,
        NULL::TEXT AS standard_units,
        NULL::TEXT AS standard_relation,
        NULL::NUMERIC AS pchembl_value,

        -- Activity flags
        NULL::TEXT AS activity_comment,
        NULL::TEXT AS data_validity_comment,
        NULL::BOOLEAN AS potential_duplicate,

        -- Document reference
        NULL::TEXT AS document_chembl_id,
        NULL::TEXT AS pubmed_id,
        NULL::INTEGER AS publication_year,

        'chembl' AS source,
        source_updated_at,
        NOW() AS created_at

    FROM bronze.chembl_molecules
    WHERE
        processed_to_silver = FALSE
        AND chembl_id IS NOT NULL
)

SELECT * FROM activity_data WHERE 1=0;  -- Placeholder - no actual data yet

-- In production, this would be:
-- SELECT
--     gen_random_uuid() AS id,
--     response_body->>'activity_id' AS activity_id,
--     ...
-- FROM raw.chembl_activities
-- WHERE ...
