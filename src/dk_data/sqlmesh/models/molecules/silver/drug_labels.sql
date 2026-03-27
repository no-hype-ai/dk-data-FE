-- SQLMesh Model: Silver Drug Labels
-- Normalized FDA drug label data from Bronze OpenFDA Labels
-- Part of: 012-dk-data-platform

MODEL (
    name mol_silver.drug_labels,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key set_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (set_id)),
        unique_values(columns := (set_id))
    ),
    grain set_id
);

WITH source_labels AS (
    SELECT
        set_id,
        spl_version,
        spl_id,
        -- brand_name, generic_name, manufacturer_name are TEXT in bronze
        -- (already extracted from the first array element in the bronze model)
        brand_name,
        generic_name,
        manufacturer_name,
        product_type,
        -- routes, dosage_forms, pharm_class_epc, pharm_class_moa are JSONB arrays in bronze
        routes,
        dosage_forms,
        pharm_class_epc,
        pharm_class_moa,
        rxcui,
        unii,
        application_numbers,
        effective_date,
        -- Label sections are TEXT in bronze (already extracted from first array element)
        indications_and_usage,
        dosage_and_administration,
        contraindications,
        warnings,
        warnings_and_cautions,
        boxed_warning,
        adverse_reactions,
        drug_interactions,
        clinical_pharmacology,
        mechanism_of_action,
        pharmacokinetics,
        overdosage,
        description,
        clinical_studies,
        how_supplied,
        pregnancy,
        pediatric_use,
        geriatric_use,
        has_boxed_warning,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.openfda_labels
    WHERE
        processed_to_silver = FALSE
        AND set_id IS NOT NULL
),

-- Get latest version per set_id
latest_version AS (
    SELECT DISTINCT ON (set_id)
        *
    FROM source_labels
    ORDER BY set_id, spl_version DESC NULLS LAST, source_updated_at DESC
)

SELECT
    gen_random_uuid() AS id,
    set_id,
    spl_version,
    spl_id,
    brand_name,
    generic_name,
    manufacturer_name,
    product_type,
    routes,
    dosage_forms,
    pharm_class_epc,
    pharm_class_moa,
    rxcui,
    unii,
    application_numbers,
    effective_date,
    indications_and_usage,
    dosage_and_administration,
    contraindications,
    warnings,
    warnings_and_cautions,
    boxed_warning,
    adverse_reactions,
    drug_interactions,
    clinical_pharmacology,
    mechanism_of_action,
    pharmacokinetics,
    overdosage,
    description,
    clinical_studies,
    how_supplied,
    pregnancy,
    pediatric_use,
    geriatric_use,
    has_boxed_warning,
    NULL::UUID AS molecule_id,  -- To be linked by entity resolution
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM latest_version;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY with INCREMENTAL_BY_UNIQUE_KEY (default: update all columns on match),
-- so reprocessing is idempotent.
