-- SQLMesh Model: Silver Bioactivity
-- Normalized bioactivity data from ChEMBL
-- Part of: 012-dk-data-platform

MODEL (
    name mol_silver.bioactivity,
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
-- In production, there would be a mol_raw.chembl_activities table

-- NOTE: bioactivity data requires a separate ChEMBL Activities API endpoint
-- (/chembl/api/data/activity) which is not yet ingested. This model provides
-- the correct output schema as a placeholder. All rows are excluded via WHERE 1=0.
-- molecule_targets.sql depends on this model's column definitions.

WITH activity_data AS (
    SELECT
        gen_random_uuid()       AS id,
        chembl_id,
        inchi_key,

        -- molecule_id and target_id: linked via mol_silver.molecules and mol_silver.targets
        -- Will be populated once ChEMBL activities are ingested
        NULL::UUID              AS molecule_id,
        NULL::UUID              AS target_id,

        -- ChEMBL Activity API field names
        NULL::TEXT              AS activity_id,        -- activity_id in API
        NULL::TEXT              AS assay_chembl_id,
        NULL::TEXT              AS assay_type,          -- assay_type in API (B/F/A/T/P/U)
        NULL::TEXT              AS assay_description,
        NULL::TEXT              AS target_chembl_id,
        NULL::TEXT              AS target_name,
        NULL::TEXT              AS target_type,
        NULL::TEXT              AS target_organism,
        NULL::TEXT              AS uniprot_id,

        -- Activity measurements
        NULL::TEXT              AS activity_type,      -- standard_type in API (IC50, Ki, EC50...)
        NULL::NUMERIC           AS activity_value,     -- standard_value in API
        NULL::TEXT              AS activity_unit,      -- standard_units in API
        NULL::TEXT              AS standard_relation,
        NULL::NUMERIC           AS pchembl_value,

        -- Activity flags
        NULL::TEXT              AS activity_comment,
        NULL::TEXT              AS data_validity_comment,
        NULL::BOOLEAN           AS potential_duplicate,

        -- Document reference
        NULL::TEXT              AS document_chembl_id,
        NULL::BIGINT            AS pubmed_id,           -- pmid as BIGINT (matches mol_silver.publications)
        NULL::INTEGER           AS publication_year,

        'chembl'                AS source,
        source_updated_at,
        NOW()                   AS created_at

    FROM mol_bronze.chembl_molecules
    WHERE
        processed_to_silver = FALSE
        AND chembl_id IS NOT NULL
)

SELECT * FROM activity_data WHERE 1=0;  -- Placeholder - no ChEMBL activity data yet

-- In production, this would be:
-- SELECT
--     gen_random_uuid() AS id,
--     response_body->>'activity_id' AS activity_id,
--     ...
-- FROM mol_raw.chembl_activities
-- WHERE ...
