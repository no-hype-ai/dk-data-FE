-- SQLMesh Model: Bronze ChEMBL Molecules
-- Transforms Raw ChEMBL API responses to Bronze typed columns
-- Part of: 012-dk-data-platform
--
-- mol_raw.chembl schema (migration 028_raw_layer_tables.sql):
--   id UUID, request_id, request_timestamp TIMESTAMPTZ, api_endpoint,
--   api_version, request_params JSONB, request_headers JSONB,
--   response_status INTEGER, response_headers JSONB,
--   response_body JSONB, response_body_hash, response_size_bytes,
--   response_time_ms, processed_to_bronze BOOLEAN, processed_at,
--   processing_error, ingested_at, source_id
--
-- ChEMBL REST API molecule JSON field names (v1):
--   molecule_chembl_id, pref_name, molecule_type, max_phase,
--   molecule_properties.full_molformula, molecule_properties.full_mwt,
--   molecule_properties.alogp, molecule_properties.hba, molecule_properties.hbd,
--   molecule_properties.psa, molecule_properties.num_ro5_violations,
--   molecule_properties.aromatic_rings, molecule_properties.heavy_atoms,
--   molecule_structures.canonical_smiles, molecule_structures.standard_inchi,
--   molecule_structures.standard_inchi_key,
--   first_approval (integer year), indication_class, usan_stem,
--   therapeutic_flag (boolean), prodrug (boolean), natural_product (boolean),
--   molecule_synonyms (array), cross_references (array)

MODEL (
    name mol_bronze.chembl_molecules,
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
    gen_random_uuid()                                               AS id,

    -- ChEMBL Identifiers
    response_body->>'molecule_chembl_id'                            AS chembl_id,
    response_body->>'pref_name'                                     AS pref_name,
    response_body->>'molecule_type'                                 AS molecule_type,
    (response_body->>'max_phase')::INTEGER                          AS max_phase,

    -- Structure
    response_body->'molecule_properties'->>'full_molformula'        AS molecular_formula,
    (response_body->'molecule_properties'->>'full_mwt')::NUMERIC    AS molecular_weight,
    response_body->'molecule_structures'->>'canonical_smiles'       AS canonical_smiles,
    response_body->'molecule_structures'->>'standard_inchi'         AS inchi,
    response_body->'molecule_structures'->>'standard_inchi_key'     AS inchi_key,

    -- Properties (all numeric — cast explicitly)
    (response_body->'molecule_properties'->>'alogp')::NUMERIC       AS alogp,
    (response_body->'molecule_properties'->>'hba')::INTEGER         AS hba,
    (response_body->'molecule_properties'->>'hbd')::INTEGER         AS hbd,
    (response_body->'molecule_properties'->>'psa')::NUMERIC         AS psa,
    (response_body->'molecule_properties'->>'num_ro5_violations')::INTEGER  AS num_ro5_violations,
    (response_body->'molecule_properties'->>'aromatic_rings')::INTEGER      AS aromatic_rings,
    (response_body->'molecule_properties'->>'heavy_atoms')::INTEGER         AS heavy_atoms,

    -- Classification
    -- first_approval: ChEMBL returns an integer year (e.g. 1985) — cast to INTEGER
    (response_body->>'first_approval')::INTEGER                     AS first_approval,
    response_body->>'indication_class'                              AS indication_class,
    response_body->>'usan_stem'                                     AS usan_stem,

    -- Boolean flags: ChEMBL API returns true/false as JSON booleans
    (response_body->>'therapeutic_flag')::BOOLEAN                   AS therapeutic_flag,
    (response_body->>'prodrug')::BOOLEAN                            AS prodrug,
    (response_body->>'natural_product')::BOOLEAN                    AS natural_product,

    -- Synonyms (JSONB array of synonym objects with synonym_name, syn_type, etc.)
    response_body->'molecule_synonyms'                              AS synonyms,

    -- Cross-references (JSONB array)
    response_body->'cross_references'                               AS cross_references,

    -- Raw source tracking
    response_body                                                   AS raw_json,
    -- raw_source_id references the UUID primary key of mol_raw.chembl (not the generated id above)
    mol_raw.id                                                          AS raw_source_id,
    'chembl'                                                        AS source,
    request_timestamp,
    request_timestamp                                               AS source_updated_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM mol_raw.chembl AS raw
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'molecule_chembl_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
