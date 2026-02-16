-- SQLMesh Model: Bronze ChEMBL Molecules
-- Transforms Raw ChEMBL API responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name bronze.chembl_molecules,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (chembl_id)),
        unique_values(columns := (chembl_id))
    ),
    grain chembl_id
);

SELECT
    gen_random_uuid() AS id,

    -- ChEMBL Identifiers
    response_body->>'molecule_chembl_id' AS chembl_id,
    response_body->>'pref_name' AS pref_name,
    response_body->>'molecule_type' AS molecule_type,
    (response_body->>'max_phase')::INTEGER AS max_phase,

    -- Structure
    response_body->'molecule_properties'->>'full_molformula' AS molecular_formula,
    (response_body->'molecule_properties'->>'full_mwt')::NUMERIC AS molecular_weight,
    response_body->'molecule_structures'->>'canonical_smiles' AS canonical_smiles,
    response_body->'molecule_structures'->>'standard_inchi' AS inchi,
    response_body->'molecule_structures'->>'standard_inchi_key' AS inchi_key,

    -- Properties
    (response_body->'molecule_properties'->>'alogp')::NUMERIC AS alogp,
    (response_body->'molecule_properties'->>'hba')::INTEGER AS hba,
    (response_body->'molecule_properties'->>'hbd')::INTEGER AS hbd,
    (response_body->'molecule_properties'->>'psa')::NUMERIC AS psa,
    (response_body->'molecule_properties'->>'num_ro5_violations')::INTEGER AS num_ro5_violations,
    (response_body->'molecule_properties'->>'aromatic_rings')::INTEGER AS aromatic_rings,
    (response_body->'molecule_properties'->>'heavy_atoms')::INTEGER AS heavy_atoms,

    -- Classification
    response_body->>'first_approval' AS first_approval,
    response_body->>'indication_class' AS indication_class,
    response_body->>'usan_stem' AS usan_stem,
    response_body->>'therapeutic_flag' AS therapeutic_flag,
    response_body->>'prodrug' AS prodrug,
    response_body->>'natural_product' AS natural_product,

    -- Synonyms
    response_body->'molecule_synonyms' AS synonyms,

    -- Cross-references
    response_body->'cross_references' AS cross_references,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'chembl' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.chembl
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'molecule_chembl_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
