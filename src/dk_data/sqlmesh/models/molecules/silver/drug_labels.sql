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
    ORDER BY set_id, version DESC NULLS LAST, ingested_at DESC
)

SELECT
    gen_random_uuid() AS label_id,
    NULL::UUID AS molecule_id,

    -- All bronze columns carried forward with SAME NAMES (API-derived)
    set_id,
    spl_id,
    version,
    effective_time,
    brand_name,
    generic_name,
    manufacturer_name,
    product_type,
    route,
    substance_name,

    -- openFDA enrichment fields (prefixed in bronze as openfda_*)
    openfda_application_number,
    openfda_brand_name,
    openfda_generic_name,
    openfda_manufacturer_name,
    openfda_product_type,
    openfda_route,
    openfda_substance_name,
    openfda_rxcui,
    openfda_spl_id,
    openfda_spl_set_id,
    openfda_unii,
    openfda_nui,
    openfda_pharm_class_cs,
    openfda_pharm_class_epc,
    openfda_pharm_class_moa,
    openfda_pharm_class_pe,
    openfda_is_original_packager,
    openfda_product_ndc,
    openfda_package_ndc,
    openfda_upc,

    -- Label sections (all carried forward)
    indications_and_usage,
    dosage_and_administration,
    dosage_forms_and_strengths,
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
    package_label_principal_display_panel,
    pregnancy,
    nursing_mothers,
    pediatric_use,
    geriatric_use,
    information_for_patients,
    spl_medguide,
    spl_patient_package_insert,
    spl_product_data_elements,
    spl_unclassified_section,
    nonclinical_toxicology,
    recent_major_changes,
    active_ingredient,
    inactive_ingredient,
    purpose,
    keep_out_of_reach_of_children,
    ask_doctor,
    ask_doctor_or_pharmacist,
    do_not_use,
    stop_use,
    questions,
    risks,
    instructions_for_use,
    animal_pharmacology_and_or_toxicology,
    references,
    carcinogenesis_and_mutagenesis_and_impairment_of_fertility,
    laboratory_tests,
    pregnancy_or_breast_feeding,
    pharmacogenomics,

    -- Source tracking
    id AS bronze_id,
    ingested_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM latest_version;
