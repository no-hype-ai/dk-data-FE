-- SQLMesh Model: Silver Drug Labels
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Picks latest SPL version per set_id. Adds: molecule_id linkage.

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

WITH latest_version AS (
    SELECT DISTINCT ON (set_id)
        *
    FROM mol_bronze.openfda_labels
    WHERE processed_to_silver = FALSE
      AND set_id IS NOT NULL
    ORDER BY set_id, spl_version DESC NULLS LAST, created_at DESC
)

SELECT
    gen_random_uuid() AS label_id,
    NULL::UUID AS molecule_id,

    -- Identifiers (bronze names preserved)
    set_id,
    spl_id,
    spl_version,
    effective_date,
    brand_name,
    generic_name,
    manufacturer_name,
    product_type,
    routes,
    dosage_forms,

    -- openFDA cross-reference fields (extracted in bronze, no openfda_ prefix)
    application_numbers,
    rxcui,
    spl_set_ids,
    unii,
    nui,
    pharm_class_epc,
    pharm_class_moa,
    is_original_packager,

    -- Label sections (carried forward from bronze)
    indications_and_usage,
    dosage_and_administration,
    contraindications,
    warnings,
    warnings_and_cautions,
    boxed_warning,
    adverse_reactions,
    drug_interactions,
    use_in_specific_populations,
    clinical_pharmacology,
    mechanism_of_action,
    pharmacodynamics,
    pharmacokinetics,
    overdosage,
    description,
    clinical_studies,
    how_supplied,
    storage_and_handling,
    principal_display_panel,
    pregnancy,
    nursing_mothers,
    pediatric_use,
    geriatric_use,
    has_boxed_warning,

    -- Source tracking
    id AS bronze_id,
    created_at AS ingested_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM latest_version;
