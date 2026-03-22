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
    m.molecule_id,

    -- Identifiers (bronze names preserved)
    lv.set_id,
    lv.spl_id,
    lv.spl_version,
    lv.effective_date,
    lv.brand_name,
    lv.generic_name,
    lv.manufacturer_name,
    lv.product_type,
    lv.routes,
    lv.dosage_forms,

    -- openFDA cross-reference fields (extracted in bronze, no openfda_ prefix)
    lv.application_numbers,
    lv.rxcui,
    lv.spl_set_ids,
    lv.unii,
    lv.nui,
    lv.pharm_class_epc,
    lv.pharm_class_moa,
    lv.is_original_packager,

    -- Label sections (carried forward from bronze)
    lv.indications_and_usage,
    lv.dosage_and_administration,
    lv.contraindications,
    lv.warnings,
    lv.warnings_and_cautions,
    lv.boxed_warning,
    lv.adverse_reactions,
    lv.drug_interactions,
    lv.use_in_specific_populations,
    lv.clinical_pharmacology,
    lv.mechanism_of_action,
    lv.pharmacodynamics,
    lv.pharmacokinetics,
    lv.overdosage,
    lv.description,
    lv.clinical_studies,
    lv.how_supplied,
    lv.storage_and_handling,
    lv.principal_display_panel,
    lv.pregnancy,
    lv.nursing_mothers,
    lv.pediatric_use,
    lv.geriatric_use,
    lv.has_boxed_warning,

    -- Source tracking
    lv.id AS bronze_id,
    lv.created_at AS ingested_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM latest_version lv
LEFT JOIN mol_silver.molecules m ON (
  EXISTS (
    SELECT 1 FROM jsonb_array_elements_text(
      CASE WHEN lv.brand_name IS NOT NULL AND lv.brand_name LIKE '[%'
           THEN lv.brand_name::jsonb ELSE '[]'::jsonb END
    ) bn WHERE LOWER(bn) = m.canonical_name
  ) OR EXISTS (
    SELECT 1 FROM jsonb_array_elements_text(
      CASE WHEN lv.generic_name IS NOT NULL AND lv.generic_name LIKE '[%'
           THEN lv.generic_name::jsonb ELSE '[]'::jsonb END
    ) gn WHERE LOWER(gn) = m.canonical_name
  )
);
