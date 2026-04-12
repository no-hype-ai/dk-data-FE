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
    lv.routes,
    lv.dosage_forms,
    lv.pharm_class_epc,
    lv.pharm_class_moa,
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
