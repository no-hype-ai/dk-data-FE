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

    -- Drug Names
    label->'openfda'->>'brand_name' AS brand_name,
    label->'openfda'->>'generic_name' AS generic_name,
    label->'openfda'->>'manufacturer_name' AS manufacturer_name,

    -- Product Info
    label->>'product_type' AS product_type,
    label->'openfda'->'route' AS routes,
    label->'openfda'->'dosage_form' AS dosage_forms,
    label->'openfda'->'pharm_class_epc' AS pharm_class_epc,
    label->'openfda'->'pharm_class_moa' AS pharm_class_moa,

    -- Cross-references
    label->'openfda'->'rxcui' AS rxcui,
    label->'openfda'->'unii' AS unii,
    label->'openfda'->'spl_set_id' AS spl_set_ids,
    label->'openfda'->'nui' AS nui,
    label->'openfda'->'application_number' AS application_numbers,

    -- Dates
    (label->>'effective_time')::DATE AS effective_date,

    -- Label Sections
    label->'indications_and_usage' AS indications_and_usage,
    label->'dosage_and_administration' AS dosage_and_administration,
    label->'contraindications' AS contraindications,
    label->'warnings' AS warnings,
    label->'warnings_and_cautions' AS warnings_and_cautions,
    label->'boxed_warning' AS boxed_warning,
    label->'adverse_reactions' AS adverse_reactions,
    label->'drug_interactions' AS drug_interactions,
    label->'use_in_specific_populations' AS use_in_specific_populations,
    label->'clinical_pharmacology' AS clinical_pharmacology,
    label->'mechanism_of_action' AS mechanism_of_action,
    label->'pharmacodynamics' AS pharmacodynamics,
    label->'pharmacokinetics' AS pharmacokinetics,
    label->'overdosage' AS overdosage,
    label->'description' AS description,
    label->'clinical_studies' AS clinical_studies,
    label->'how_supplied' AS how_supplied,
    label->'storage_and_handling' AS storage_and_handling,
    label->'package_label_principal_display_panel' AS principal_display_panel,

    -- Pregnancy/Nursing
    label->'pregnancy' AS pregnancy,
    label->'nursing_mothers' AS nursing_mothers,
    label->'pediatric_use' AS pediatric_use,
    label->'geriatric_use' AS geriatric_use,

    -- Flags
    (label->'boxed_warning' IS NOT NULL AND label->'boxed_warning' != 'null'::JSONB) AS has_boxed_warning,
    CASE jsonb_typeof(label->'openfda'->'is_original_packager')
        WHEN 'array'   THEN (label->'openfda'->'is_original_packager'->0)::TEXT::BOOLEAN
        WHEN 'boolean' THEN (label->'openfda'->'is_original_packager')::TEXT::BOOLEAN
        ELSE NULL
    END AS is_original_packager,

    -- Raw source tracking
    label AS raw_json,
    id AS raw_source_id,
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
