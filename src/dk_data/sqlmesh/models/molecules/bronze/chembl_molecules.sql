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

-- Unnest the molecules array from batch search API responses.
-- ChEMBL /molecule/search returns {"molecules": [...], "page_meta": {...}}.
-- Also handles legacy single-molecule rows (response_body has molecule_chembl_id directly).
-- Deduplication: the same chembl_id may appear in multiple batch pages; keep the latest row.
WITH molecules AS (
    SELECT
        raw.id          AS raw_source_id,
        raw.request_timestamp,
        mol.value       AS mol
    FROM mol_raw.chembl AS raw
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN raw.response_body ? 'molecules'
            THEN raw.response_body->'molecules'
            ELSE jsonb_build_array(raw.response_body)
        END
    ) AS mol(value)
    WHERE raw.response_status = 200
      AND raw.processed_to_bronze = FALSE
      AND raw.request_timestamp BETWEEN @start_dt AND @end_dt
),

deduped AS (
    SELECT DISTINCT ON (mol->>'molecule_chembl_id')
        raw_source_id,
        request_timestamp,
        mol
    FROM molecules
    WHERE mol->>'molecule_chembl_id' IS NOT NULL
    ORDER BY mol->>'molecule_chembl_id', request_timestamp DESC
)

SELECT
    gen_random_uuid()                                               AS id,

    -- ChEMBL Identifiers
    mol->>'molecule_chembl_id'                                      AS chembl_id,
    -- Strip ChEMBL bulk-loader version suffixes (e.g. "imatinib_v38" → "imatinib")
    REGEXP_REPLACE(mol->>'pref_name', '_v\d+$', '')                 AS pref_name,
    mol->>'molecule_type'                                           AS molecule_type,
    (mol->>'max_phase')::NUMERIC::INTEGER                           AS max_phase,

    -- Structure
    mol->'molecule_properties'->>'full_molformula'                  AS molecular_formula,
    (mol->'molecule_properties'->>'full_mwt')::NUMERIC              AS molecular_weight,
    mol->'molecule_structures'->>'canonical_smiles'                 AS canonical_smiles,
    mol->'molecule_structures'->>'standard_inchi'                   AS inchi,
    mol->'molecule_structures'->>'standard_inchi_key'               AS inchi_key,

    -- Properties (ChEMBL returns integers as floats, e.g. "3.0" — cast via NUMERIC)
    (mol->'molecule_properties'->>'alogp')::NUMERIC                 AS alogp,
    (mol->'molecule_properties'->>'hba')::NUMERIC::INTEGER          AS hba,
    (mol->'molecule_properties'->>'hbd')::NUMERIC::INTEGER          AS hbd,
    (mol->'molecule_properties'->>'psa')::NUMERIC                   AS psa,
    (mol->'molecule_properties'->>'num_ro5_violations')::NUMERIC::INTEGER AS num_ro5_violations,
    (mol->'molecule_properties'->>'aromatic_rings')::NUMERIC::INTEGER AS aromatic_rings,
    (mol->'molecule_properties'->>'heavy_atoms')::NUMERIC::INTEGER  AS heavy_atoms,

    -- Classification
    (mol->>'first_approval')::NUMERIC::INTEGER                      AS first_approval,
    mol->>'indication_class'                                        AS indication_class,
    mol->>'usan_stem'                                               AS usan_stem,

    -- Boolean flags (ChEMBL uses -1/0 or true/false; normalize both)
    CASE mol->>'therapeutic_flag' WHEN 'true' THEN TRUE WHEN '1' THEN TRUE WHEN '-1' THEN TRUE WHEN 'false' THEN FALSE WHEN '0' THEN FALSE ELSE NULL END AS therapeutic_flag,
    CASE mol->>'prodrug' WHEN 'true' THEN TRUE WHEN '1' THEN TRUE WHEN '-1' THEN TRUE WHEN 'false' THEN FALSE WHEN '0' THEN FALSE ELSE NULL END AS prodrug,
    CASE mol->>'natural_product' WHEN 'true' THEN TRUE WHEN '1' THEN TRUE WHEN '-1' THEN TRUE WHEN 'false' THEN FALSE WHEN '0' THEN FALSE ELSE NULL END AS natural_product,

    -- Synonyms and cross-references
    mol->'molecule_synonyms'                                        AS synonyms,
    mol->'cross_references'                                         AS cross_references,

    -- Raw source tracking
    mol                                                             AS raw_json,
    raw_source_id,
    'chembl'                                                        AS source,
    request_timestamp,
    request_timestamp                                               AS source_updated_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM deduped;
