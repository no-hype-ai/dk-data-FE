-- SQLMesh Model: Silver Molecules
-- Master molecule table with entity resolution using InChI Key
-- Silver columns use the SAME names as bronze. No renames.
-- Part of: 012-dk-data-platform

MODEL (
    name mol_silver.molecules,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key inchi_key
    ),
    cron '@daily',
    audits (
        not_null(columns := (inchi_key, pref_name)),
        unique_values(columns := (inchi_key))
    ),
    grain inchi_key
);

-- Source precedence: DrugBank (1) > ChEMBL (2) > PubChem (3) > Others

WITH source_molecules AS (
    -- ChEMBL as primary source (precedence 2)
    SELECT
        inchi_key,
        chembl_id,
        pref_name,
        molecule_type,
        max_phase,

        -- Structure (bronze names preserved)
        molecular_formula,
        molecular_weight,
        canonical_smiles,
        inchi,

        -- Chemical properties (bronze names preserved)
        alogp,
        hba,
        hbd,
        psa,
        num_ro5_violations,
        aromatic_rings,
        heavy_atoms,

        -- Classification (bronze names preserved)
        first_approval,
        indication_class,
        usan_stem,
        therapeutic_flag,
        prodrug,
        natural_product,

        -- Cross-references (bronze names preserved)
        synonyms,
        cross_references,

        -- Source tracking
        1.0 AS resolution_confidence,
        FALSE AS needs_review,
        jsonb_build_array('chembl') AS data_sources,
        'chembl' AS primary_source,
        2 AS source_precedence,
        source_updated_at,
        created_at
    FROM mol_bronze.chembl_molecules
    WHERE
        inchi_key IS NOT NULL
        AND processed_to_silver = FALSE
),

-- Deduplicate by InChI Key, keeping highest precedence source
deduplicated AS (
    SELECT DISTINCT ON (inchi_key)
        gen_random_uuid() AS molecule_id,
        inchi_key,
        chembl_id,
        NULL::TEXT AS drugbank_id,
        NULL::TEXT AS pubchem_cid,
        NULL::TEXT AS rxnorm_cui,
        NULL::TEXT AS unii,
        NULL::TEXT AS cas_number,
        pref_name,
        -- canonical_name: use pref_name as the canonical display name
        pref_name AS canonical_name,
        NULL::TEXT[] AS brand_names,
        NULL::TEXT[] AS generic_names,
        molecule_type,
        max_phase,

        -- Structure
        molecular_formula,
        molecular_weight,
        canonical_smiles,
        inchi,

        -- Chemical properties
        alogp,
        hba,
        hbd,
        psa,
        num_ro5_violations,
        aromatic_rings,
        heavy_atoms,

        -- Classification
        first_approval,
        indication_class,
        usan_stem,
        therapeutic_flag,
        prodrug,
        natural_product,

        -- Cross-references
        synonyms,
        cross_references,
        NULL::TEXT[] AS therapeutic_areas,
        NULL::TEXT[] AS atc_codes,
        NULL::TEXT AS mechanism_of_action,

        -- Derived / enriched columns
        resolution_confidence,
        needs_review,
        NULL::TEXT AS review_reason,
        1 AS source_count,
        data_sources,
        primary_source,
        NULL::TIMESTAMPTZ AS reviewed_at,
        NULL::TEXT AS reviewed_by,
        NOW() AS created_at,
        NOW() AS updated_at
    FROM source_molecules
    ORDER BY inchi_key, source_precedence ASC, source_updated_at DESC
)

SELECT * FROM deduplicated;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY (default: update all columns on match),
-- so reprocessing is idempotent.
