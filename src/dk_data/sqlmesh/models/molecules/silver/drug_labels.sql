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

-- T133: openfda arrays available in mol_bronze.openfda_labels (unii, rxcui as JSONB arrays).
-- Tiered linkage: UNII (most specific) → RxCUI → canonical name fallback (FR-031).
WITH molecule_name_lookup AS (
    -- Stable molecule IDs indexed by lowercase canonical name for name-based entity resolution
    -- DISTINCT ON ensures one molecule_id per canonical name (prevents JOIN fan-out)
    SELECT DISTINCT ON (LOWER(canonical_name))
        molecule_id,
        LOWER(canonical_name) AS name_key
    FROM mol_silver.molecules
    ORDER BY LOWER(canonical_name), molecule_id
),

source_labels AS (
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
        substance_name,
        -- routes, dosage_forms, pharm_class_epc, pharm_class_moa are JSONB arrays in bronze
        routes,
        dosage_forms,
        pharm_class_epc,
        pharm_class_moa,
        pharm_class_pe,
        pharm_class_cs,
        product_ndc,
        package_ndc,
        original_packager_product_ndc,
        upc,
        openfda_spl_id,
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
        -- Rx Label Sections
        abuse,
        active_ingredient,
        animal_pharmacology_and_toxicology,
        carcinogenesis_mutagenesis_fertility,
        controlled_substance,
        dea_schedule,
        dependence,
        dosage_forms_and_strengths,
        drug_abuse_and_dependence,
        drug_or_lab_test_interactions,
        inactive_ingredient,
        information_for_patients,
        instructions_for_use,
        labor_and_delivery,
        laboratory_tests,
        microbiology,
        nonclinical_toxicology,
        nonteratogenic_effects,
        precautions,
        pregnancy_or_breast_feeding,
        recent_major_changes,
        label_references,
        teratogenic_effects,
        -- OTC Sections
        ask_doctor,
        ask_doctor_or_pharmacist,
        do_not_use,
        keep_out_of_reach_of_children,
        purpose,
        questions,
        stop_use,
        -- SPL Sections
        spl_medguide,
        spl_patient_package_insert,
        spl_product_data_elements,
        spl_unclassified_section,
        -- Table variants (JSONB)
        adverse_reactions_table,
        clinical_pharmacology_table,
        clinical_studies_table,
        description_table,
        dosage_and_administration_table,
        dosage_forms_and_strengths_table,
        drug_interactions_table,
        how_supplied_table,
        instructions_for_use_table,
        pharmacokinetics_table,
        recent_major_changes_table,
        spl_medguide_table,
        spl_patient_package_insert_table,
        spl_unclassified_section_table,
        has_boxed_warning,
        is_original_packager,
        spl_set_ids,
        nui,
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
    lv.set_id,
    lv.spl_version,
    lv.spl_id,
    lv.brand_name,
    lv.generic_name,
    lv.manufacturer_name,
    lv.product_type,
    lv.substance_name,
    lv.routes,
    lv.dosage_forms,
    lv.pharm_class_epc,
    lv.pharm_class_moa,
    lv.pharm_class_pe,
    lv.pharm_class_cs,
    lv.product_ndc,
    lv.package_ndc,
    lv.original_packager_product_ndc,
    lv.upc,
    lv.openfda_spl_id,
    lv.rxcui,
    lv.unii,
    lv.application_numbers,
    lv.effective_date,
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
    lv.abuse,
    lv.active_ingredient,
    lv.animal_pharmacology_and_toxicology,
    lv.carcinogenesis_mutagenesis_fertility,
    lv.controlled_substance,
    lv.dea_schedule,
    lv.dependence,
    lv.dosage_forms_and_strengths,
    lv.drug_abuse_and_dependence,
    lv.drug_or_lab_test_interactions,
    lv.inactive_ingredient,
    lv.information_for_patients,
    lv.instructions_for_use,
    lv.labor_and_delivery,
    lv.laboratory_tests,
    lv.microbiology,
    lv.nonclinical_toxicology,
    lv.nonteratogenic_effects,
    lv.precautions,
    lv.pregnancy_or_breast_feeding,
    lv.recent_major_changes,
    lv.label_references,
    lv.teratogenic_effects,
    lv.ask_doctor,
    lv.ask_doctor_or_pharmacist,
    lv.do_not_use,
    lv.keep_out_of_reach_of_children,
    lv.purpose,
    lv.questions,
    lv.stop_use,
    lv.spl_medguide,
    lv.spl_patient_package_insert,
    lv.spl_product_data_elements,
    lv.spl_unclassified_section,
    lv.adverse_reactions_table,
    lv.clinical_pharmacology_table,
    lv.clinical_studies_table,
    lv.description_table,
    lv.dosage_and_administration_table,
    lv.dosage_forms_and_strengths_table,
    lv.drug_interactions_table,
    lv.how_supplied_table,
    lv.instructions_for_use_table,
    lv.pharmacokinetics_table,
    lv.recent_major_changes_table,
    lv.spl_medguide_table,
    lv.spl_patient_package_insert_table,
    lv.spl_unclassified_section_table,
    lv.has_boxed_warning,
    lv.is_original_packager,
    lv.spl_set_ids,
    lv.nui,
    -- Entity resolution (FR-031): UNII → RxCUI → generic_name → brand_name
    -- UNII and RxCUI are JSONB arrays; use LATERAL to extract first element match.
    COALESCE(
        unii_link.molecule_id,
        rxcui_link.molecule_id,
        m_generic.molecule_id,
        m_brand.molecule_id
    ) AS molecule_id,
    lv.source,
    lv.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM latest_version lv
LEFT JOIN molecule_name_lookup m_generic ON LOWER(lv.generic_name) = m_generic.name_key
LEFT JOIN molecule_name_lookup m_brand   ON LOWER(lv.brand_name)   = m_brand.name_key

-- Tier 1: UNII match via molecule_identifiers (most specific — unique substance identifier)
LEFT JOIN LATERAL (
    SELECT mi.molecule_id
    FROM mol_silver.molecule_identifiers mi
    WHERE mi.source = 'unii'
      AND lv.unii IS NOT NULL
      AND mi.identifier = lv.unii->>'0'
    LIMIT 1
) unii_link ON TRUE

-- Tier 2: RxCUI match via molecule_identifiers (falls back when UNII not matched)
LEFT JOIN LATERAL (
    SELECT mi.molecule_id
    FROM mol_silver.molecule_identifiers mi
    WHERE unii_link.molecule_id IS NULL
      AND mi.source = 'rxnorm'
      AND lv.rxcui IS NOT NULL
      AND mi.identifier = lv.rxcui->>'0'
    LIMIT 1
) rxcui_link ON TRUE;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY with INCREMENTAL_BY_UNIQUE_KEY (default: update all columns on match),
-- so reprocessing is idempotent.
