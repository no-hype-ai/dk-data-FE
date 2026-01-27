-- SQLMesh Model: Silver Drug Labels
-- Normalized FDA drug label data from Bronze OpenFDA Labels
-- Part of: 012-dk-data-platform

MODEL (
    name silver.drug_labels,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key set_id,
        when_matched_update_all TRUE
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
        -- Extract first value from arrays
        COALESCE(
            brand_name->0,
            brand_name::TEXT
        ) AS brand_name,
        COALESCE(
            generic_name->0,
            generic_name::TEXT
        ) AS generic_name,
        COALESCE(
            manufacturer_name->0,
            manufacturer_name::TEXT
        ) AS manufacturer_name,
        product_type,
        routes,
        dosage_forms,
        pharm_class_epc,
        pharm_class_moa,
        rxcui,
        unii,
        application_numbers,
        effective_date,
        -- Label sections (extract text from arrays)
        indications_and_usage->0 AS indications_and_usage,
        dosage_and_administration->0 AS dosage_and_administration,
        contraindications->0 AS contraindications,
        warnings->0 AS warnings,
        warnings_and_cautions->0 AS warnings_and_cautions,
        boxed_warning->0 AS boxed_warning,
        adverse_reactions->0 AS adverse_reactions,
        drug_interactions->0 AS drug_interactions,
        clinical_pharmacology->0 AS clinical_pharmacology,
        mechanism_of_action->0 AS mechanism_of_action,
        pharmacokinetics->0 AS pharmacokinetics,
        overdosage->0 AS overdosage,
        description->0 AS description,
        clinical_studies->0 AS clinical_studies,
        how_supplied->0 AS how_supplied,
        pregnancy->0 AS pregnancy,
        pediatric_use->0 AS pediatric_use,
        geriatric_use->0 AS geriatric_use,
        has_boxed_warning,
        source,
        source_updated_at,
        created_at
    FROM bronze.openfda_labels
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


-- Post-insert: Mark Bronze records as processed
@post_incremental(
    UPDATE bronze.openfda_labels
    SET processed_to_silver = TRUE
    WHERE processed_to_silver = FALSE
    AND set_id IN (SELECT set_id FROM silver.drug_labels)
);
