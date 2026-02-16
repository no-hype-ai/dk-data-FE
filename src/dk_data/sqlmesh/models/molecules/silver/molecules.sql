-- SQLMesh Model: Silver Molecules
-- Master molecule table with entity resolution using InChI Key
-- Part of: 012-dk-data-platform

MODEL (
    name silver.molecules,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key inchi_key,
        when_matched_update_all TRUE
    ),
    cron '@daily',
    audits (
        not_null(columns := (inchi_key, canonical_name)),
        unique_values(columns := (inchi_key))
    ),
    grain inchi_key
);

-- Source precedence: DrugBank (1) > ChEMBL (2) > PubChem (3) > Others

WITH source_molecules AS (
    -- ChEMBL as primary source (precedence 2)
    SELECT
        inchi_key,
        pref_name AS canonical_name,
        'chembl' AS name_source,
        canonical_smiles,
        inchi,
        molecular_formula,
        molecular_weight,
        molecule_type,
        CASE
            WHEN max_phase = 4 THEN 'approved'
            WHEN max_phase = 3 THEN 'phase_3'
            WHEN max_phase = 2 THEN 'phase_2'
            WHEN max_phase = 1 THEN 'phase_1'
            ELSE 'preclinical'
        END AS development_status,
        max_phase,
        first_approval::INTEGER AS first_approval_year,
        1.0 AS resolution_confidence,
        FALSE AS needs_review,
        jsonb_build_array('chembl') AS data_sources,
        'chembl' AS primary_source,
        2 AS source_precedence,
        source_updated_at,
        created_at
    FROM bronze.chembl_molecules
    WHERE
        inchi_key IS NOT NULL
        AND processed_to_silver = FALSE
),

-- Deduplicate by InChI Key, keeping highest precedence source
deduplicated AS (
    SELECT DISTINCT ON (inchi_key)
        gen_random_uuid() AS id,
        inchi_key,
        canonical_name,
        name_source,
        canonical_smiles,
        inchi,
        molecular_formula,
        molecular_weight,
        molecule_type,
        NULL::JSONB AS therapeutic_areas,
        NULL::TEXT AS mechanism_of_action,
        development_status,
        max_phase,
        first_approval_year,
        NULL::DATE AS approval_date,
        resolution_confidence,
        needs_review,
        NULL::TEXT AS review_reason,
        data_sources,
        primary_source,
        NOW() AS created_at,
        NOW() AS updated_at
    FROM source_molecules
    ORDER BY inchi_key, source_precedence ASC, source_updated_at DESC
)

SELECT * FROM deduplicated;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY with when_matched_update_all,
-- so reprocessing is idempotent.
