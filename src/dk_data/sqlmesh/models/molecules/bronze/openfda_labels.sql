-- SQLMesh Model: Bronze OpenFDA Labels
-- Transforms Raw OpenFDA Drug Labels responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.openfda_labels,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
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
    (label->>'version')::INTEGER AS spl_version,
    label->>'id' AS spl_id,

    -- Drug Names (openfda fields are JSON arrays; extract first element as text)
    label->'openfda'->'brand_name'->>0 AS brand_name,
    label->'openfda'->'generic_name'->>0 AS generic_name,
    label->'openfda'->'manufacturer_name'->>0 AS manufacturer_name,

    -- Product Info
    label->>'product_type' AS product_type,
    -- route, dosage_form, pharm_class_epc, pharm_class_moa are arrays — keep as JSONB
    label->'openfda'->'route'::JSONB AS routes,
    label->'openfda'->'dosage_form'::JSONB AS dosage_forms,
    label->'openfda'->'pharm_class_epc'::JSONB AS pharm_class_epc,
    label->'openfda'->'pharm_class_moa'::JSONB AS pharm_class_moa,

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
