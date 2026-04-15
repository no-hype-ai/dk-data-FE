-- SQLMesh Model: Bronze OpenFDA Labels
-- Transforms Raw OpenFDA Drug Labels responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.openfda_labels,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (set_id, spl_version)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (set_id))
    ),
    grain (set_id, spl_version)
);

SELECT
    gen_random_uuid() AS id,

    -- Identifiers
    label->>'set_id' AS set_id,
    (label->>'version')::BIGINT AS spl_version,
    label->>'id' AS spl_id,

    -- Drug Names (openfda fields are JSON arrays; extract first element as text)
    label->'openfda'->'brand_name'->>0 AS brand_name,
    label->'openfda'->'generic_name'->>0 AS generic_name,
    label->'openfda'->'manufacturer_name'->>0 AS manufacturer_name,

    -- Product Info
    label->'openfda'->'product_type'->>0 AS product_type,
    label->'openfda'->'substance_name'->>0 AS substance_name,
    -- route, dosage_form, pharm_class_epc, pharm_class_moa are arrays — keep as JSONB
    label->'openfda'->'route'::JSONB AS routes,
    label->'openfda'->'dosage_form'::JSONB AS dosage_forms,
    label->'openfda'->'pharm_class_epc'::JSONB AS pharm_class_epc,
    label->'openfda'->'pharm_class_moa'::JSONB AS pharm_class_moa,
    label->'openfda'->'pharm_class_pe'::JSONB AS pharm_class_pe,
    label->'openfda'->'pharm_class_cs'::JSONB AS pharm_class_cs,
    label->'openfda'->'product_ndc'::JSONB AS product_ndc,
    label->'openfda'->'package_ndc'::JSONB AS package_ndc,
    label->'openfda'->'original_packager_product_ndc'::JSONB AS original_packager_product_ndc,
    label->'openfda'->'upc'::JSONB AS upc,
    label->'openfda'->'spl_id'->>0 AS openfda_spl_id,

    -- Cross-references (all arrays — keep as JSONB)
    label->'openfda'->'rxcui'::JSONB AS rxcui,
    label->'openfda'->'unii'::JSONB AS unii,
    label->'openfda'->'spl_set_id'::JSONB AS spl_set_ids,
    label->'openfda'->'nui'::JSONB AS nui,
    label->'openfda'->'application_number'::JSONB AS application_numbers,

    -- Dates (effective_time is YYYYMMDD string in OpenFDA)
    TO_DATE(NULLIF(label->>'effective_time', ''), 'YYYYMMDD') AS effective_date,

    -- Label Sections (OpenFDA label sections are JSON arrays of strings; extract first element as text)
    label->'indications_and_usage'->>0 AS indications_and_usage,
    label->'dosage_and_administration'->>0 AS dosage_and_administration,
    label->'contraindications'->>0 AS contraindications,
    label->'warnings'->>0 AS warnings,
    label->'warnings_and_cautions'->>0 AS warnings_and_cautions,
    label->'boxed_warning'->>0 AS boxed_warning,
    label->'adverse_reactions'->>0 AS adverse_reactions,
    label->'drug_interactions'->>0 AS drug_interactions,
    label->'use_in_specific_populations'->>0 AS use_in_specific_populations,
    label->'clinical_pharmacology'->>0 AS clinical_pharmacology,
    label->'mechanism_of_action'->>0 AS mechanism_of_action,
    label->'pharmacodynamics'->>0 AS pharmacodynamics,
    label->'pharmacokinetics'->>0 AS pharmacokinetics,
    label->'overdosage'->>0 AS overdosage,
    label->'description'->>0 AS description,
    label->'clinical_studies'->>0 AS clinical_studies,
    label->'how_supplied'->>0 AS how_supplied,
    label->'storage_and_handling'->>0 AS storage_and_handling,
    label->'package_label_principal_display_panel'->>0 AS principal_display_panel,

    -- Pregnancy/Nursing
    label->'pregnancy'->>0 AS pregnancy,
    label->'nursing_mothers'->>0 AS nursing_mothers,
    label->'pediatric_use'->>0 AS pediatric_use,
    label->'geriatric_use'->>0 AS geriatric_use,

    -- Rx Label Sections
    label->'abuse'->>0 AS abuse,
    label->'active_ingredient'->>0 AS active_ingredient,
    label->'animal_pharmacology_and_or_toxicology'->>0 AS animal_pharmacology_and_toxicology,
    label->'carcinogenesis_and_mutagenesis_and_impairment_of_fertility'->>0 AS carcinogenesis_mutagenesis_fertility,
    label->'controlled_substance'->>0 AS controlled_substance,
    label->'dea_schedule'->>0 AS dea_schedule,
    label->'dependence'->>0 AS dependence,
    label->'dosage_forms_and_strengths'->>0 AS dosage_forms_and_strengths,
    label->'drug_abuse_and_dependence'->>0 AS drug_abuse_and_dependence,
    label->'drug_and_or_laboratory_test_interactions'->>0 AS drug_or_lab_test_interactions,
    label->'inactive_ingredient'->>0 AS inactive_ingredient,
    label->'information_for_patients'->>0 AS information_for_patients,
    label->'instructions_for_use'->>0 AS instructions_for_use,
    label->'labor_and_delivery'->>0 AS labor_and_delivery,
    label->'laboratory_tests'->>0 AS laboratory_tests,
    label->'microbiology'->>0 AS microbiology,
    label->'nonclinical_toxicology'->>0 AS nonclinical_toxicology,
    label->'nonteratogenic_effects'->>0 AS nonteratogenic_effects,
    label->'precautions'->>0 AS precautions,
    label->'pregnancy_or_breast_feeding'->>0 AS pregnancy_or_breast_feeding,
    label->'recent_major_changes'->>0 AS recent_major_changes,
    label->'references'->>0 AS label_references,
    label->'teratogenic_effects'->>0 AS teratogenic_effects,

    -- OTC Sections
    label->'ask_doctor'->>0 AS ask_doctor,
    label->'ask_doctor_or_pharmacist'->>0 AS ask_doctor_or_pharmacist,
    label->'do_not_use'->>0 AS do_not_use,
    label->'keep_out_of_reach_of_children'->>0 AS keep_out_of_reach_of_children,
    label->'purpose'->>0 AS purpose,
    label->'questions'->>0 AS questions,
    label->'stop_use'->>0 AS stop_use,

    -- SPL Sections
    label->'spl_medguide'->>0 AS spl_medguide,
    label->'spl_patient_package_insert'->>0 AS spl_patient_package_insert,
    label->'spl_product_data_elements'->>0 AS spl_product_data_elements,
    label->'spl_unclassified_section'->>0 AS spl_unclassified_section,

    -- Table variants (JSONB — preserve full HTML/structured content)
    label->'adverse_reactions_table'::JSONB AS adverse_reactions_table,
    label->'clinical_pharmacology_table'::JSONB AS clinical_pharmacology_table,
    label->'clinical_studies_table'::JSONB AS clinical_studies_table,
    label->'description_table'::JSONB AS description_table,
    label->'dosage_and_administration_table'::JSONB AS dosage_and_administration_table,
    label->'dosage_forms_and_strengths_table'::JSONB AS dosage_forms_and_strengths_table,
    label->'drug_interactions_table'::JSONB AS drug_interactions_table,
    label->'how_supplied_table'::JSONB AS how_supplied_table,
    label->'instructions_for_use_table'::JSONB AS instructions_for_use_table,
    label->'pharmacokinetics_table'::JSONB AS pharmacokinetics_table,
    label->'recent_major_changes_table'::JSONB AS recent_major_changes_table,
    label->'spl_medguide_table'::JSONB AS spl_medguide_table,
    label->'spl_patient_package_insert_table'::JSONB AS spl_patient_package_insert_table,
    label->'spl_unclassified_section_table'::JSONB AS spl_unclassified_section_table,

    -- Flags
    (label->'boxed_warning' IS NOT NULL AND label->'boxed_warning' != 'null'::JSONB) AS has_boxed_warning,
    -- is_original_packager is an array of strings like ['true']; extract first element
    (label->'openfda'->'is_original_packager'->>0 = 'true') AS is_original_packager,

    -- Raw source tracking
    label AS raw_json,
    -- raw_source_id references the raw table PK, not the generated bronze id
    mol_raw.openfda_labels.id AS raw_source_id,
    'openfda_labels' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.openfda_labels,
     jsonb_array_elements(response_body->'results') AS label
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND label->>'set_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
