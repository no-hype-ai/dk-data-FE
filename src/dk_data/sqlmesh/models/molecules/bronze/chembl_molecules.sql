-- SQLMesh Model: Bronze ChEMBL Molecules
-- Transforms Raw ChEMBL API responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.chembl_molecules,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500,
        lookback 7
    ),
    cron '@daily',
    audits (
        not_null(columns := (chembl_id)),
        unique_values(columns := (chembl_id))
    ),
    grain chembl_id
);

-- Unnest paginated API responses: ChEMBL returns {"molecules": [...]} bulk lists
-- or single-molecule objects at root. Both shapes are handled.
WITH expanded AS (
    SELECT
        raw.id              AS raw_source_id,
        raw.request_timestamp,
        mol.value           AS m
    FROM mol_raw.chembl AS raw,
    LATERAL jsonb_array_elements(
        CASE
            WHEN raw.response_body ? 'molecules'        THEN raw.response_body->'molecules'
            WHEN raw.response_body ? 'molecule_chembl_id' THEN jsonb_build_array(raw.response_body)
            ELSE '[]'::jsonb
        END
    ) AS mol(value)
    WHERE raw.response_status = 200
      AND raw.processed_to_bronze = FALSE
      AND raw.request_timestamp BETWEEN @start_dt AND @end_dt
),
deduped AS (
    SELECT DISTINCT ON (m->>'molecule_chembl_id')
        raw_source_id, request_timestamp, m
    FROM expanded
    WHERE m->>'molecule_chembl_id' IS NOT NULL
    ORDER BY m->>'molecule_chembl_id', request_timestamp DESC
)

SELECT
    gen_random_uuid() AS id,

    -- ChEMBL Identifiers (names from actual API response)
    m->>'molecule_chembl_id' AS chembl_id,
    m->>'pref_name' AS pref_name,
    m->>'molecule_type' AS molecule_type,
    (m->>'max_phase')::NUMERIC::INTEGER AS max_phase,

    -- Structure
    m->'molecule_properties'->>'full_molformula' AS molecular_formula,
    (m->'molecule_properties'->>'full_mwt')::NUMERIC AS molecular_weight,
    m->'molecule_structures'->>'canonical_smiles' AS canonical_smiles,
    m->'molecule_structures'->>'standard_inchi' AS inchi,
    m->'molecule_structures'->>'standard_inchi_key' AS inchi_key,

    -- Properties
    (m->'molecule_properties'->>'alogp')::NUMERIC AS alogp,
    (m->'molecule_properties'->>'hba')::INTEGER AS hba,
    (m->'molecule_properties'->>'hbd')::INTEGER AS hbd,
    (m->'molecule_properties'->>'psa')::NUMERIC AS psa,
    (m->'molecule_properties'->>'num_ro5_violations')::INTEGER AS num_ro5_violations,
    (m->'molecule_properties'->>'aromatic_rings')::INTEGER AS aromatic_rings,
    (m->'molecule_properties'->>'heavy_atoms')::INTEGER AS heavy_atoms,

    -- Classification
    m->>'first_approval' AS first_approval,
    m->>'indication_class' AS indication_class,
    m->>'usan_stem' AS usan_stem,
    m->>'therapeutic_flag' AS therapeutic_flag,
    m->>'prodrug' AS prodrug,
    m->>'natural_product' AS natural_product,

    -- Synonyms
    m->'molecule_synonyms' AS synonyms,

    -- Cross-references
    m->'cross_references' AS cross_references,

    -- Raw source tracking
    m AS raw_json,
    raw_source_id,
    'chembl' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM deduped;
