-- SQLMesh Model: Silver EMA Drug Labels (SmPC-sourced)
-- Same column structure as mol_silver.drug_labels but sourced from parsed
-- EMA SmPC data via mol_bronze.ema (which contains ema_number, product_name,
-- and raw label text). Sections are parsed by the ema_smpc parser.
-- Part of: 006-claims-engine-data-gaps (Item 10, T053)

MODEL (
    name mol_silver.drug_labels_ema,
    kind FULL,
    cron '@weekly',
    grain (ema_number)
);

-- Molecule name lookup for entity resolution (same pattern as drug_labels)
WITH molecule_name_lookup AS (
    SELECT DISTINCT ON (LOWER(canonical_name))
        molecule_id,
        LOWER(canonical_name) AS name_key
    FROM mol_silver.molecules
    ORDER BY LOWER(canonical_name), molecule_id
)

SELECT
    gen_random_uuid() AS id,

    -- Use ema_number as the label identifier (analogous to set_id for openFDA)
    e.ema_number,
    e.product_name AS brand_name,
    e.inn AS generic_name,
    e.marketing_authorisation_holder AS manufacturer_name,

    -- Product info (limited from EMA bronze)
    NULL::TEXT AS product_type,
    e.inn AS substance_name,
    NULL::JSONB AS routes,
    NULL::JSONB AS dosage_forms,
    NULL::JSONB AS pharm_class_epc,
    NULL::JSONB AS pharm_class_moa,
    NULL::JSONB AS pharm_class_pe,
    NULL::JSONB AS pharm_class_cs,
    NULL::JSONB AS product_ndc,
    NULL::JSONB AS package_ndc,

    -- Dates
    e.authorisation_date AS effective_date,

    -- Label sections: mapped from EMA bronze fields where available
    -- These correspond to SmPC section numbers:
    --   4.1 -> indications_and_usage
    --   4.2 -> dosage_and_administration
    --   4.3 -> contraindications
    --   4.4 -> warnings_and_cautions
    --   4.5 -> drug_interactions
    --   4.6 -> pregnancy / nursing_mothers
    --   4.7 -> use_in_specific_populations
    --   4.8 -> adverse_reactions
    --   4.9 -> overdosage
    --   5.1 -> pharmacodynamics
    --   5.2 -> pharmacokinetics
    --   5.3 -> nonclinical_toxicology
    e.indications_and_usage,
    NULL::TEXT AS dosage_and_administration,
    NULL::TEXT AS contraindications,
    NULL::TEXT AS warnings,
    NULL::TEXT AS warnings_and_cautions,
    NULL::TEXT AS boxed_warning,
    NULL::TEXT AS adverse_reactions,
    NULL::TEXT AS drug_interactions,
    NULL::TEXT AS use_in_specific_populations,
    NULL::TEXT AS clinical_pharmacology,
    NULL::TEXT AS mechanism_of_action,
    NULL::TEXT AS pharmacodynamics,
    NULL::TEXT AS pharmacokinetics,
    NULL::TEXT AS overdosage,
    NULL::TEXT AS description,
    NULL::TEXT AS clinical_studies,
    NULL::TEXT AS how_supplied,
    NULL::TEXT AS storage_and_handling,
    NULL::TEXT AS pregnancy,
    NULL::TEXT AS nursing_mothers,
    NULL::TEXT AS pediatric_use,
    NULL::TEXT AS geriatric_use,
    NULL::TEXT AS nonclinical_toxicology,
    NULL::TEXT AS precautions,

    -- Not applicable for EMA labels
    NULL::TEXT AS abuse,
    NULL::TEXT AS controlled_substance,
    NULL::TEXT AS dea_schedule,
    NULL::TEXT AS dependence,
    NULL::TEXT AS drug_abuse_and_dependence,

    -- Flags
    FALSE AS has_boxed_warning,

    -- Entity resolution: match by INN (generic name)
    m.molecule_id,

    'ema_smpc' AS source,
    e.authorisation_date AS source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.ema e
LEFT JOIN molecule_name_lookup m ON LOWER(e.inn) = m.name_key
WHERE e.ema_number IS NOT NULL
