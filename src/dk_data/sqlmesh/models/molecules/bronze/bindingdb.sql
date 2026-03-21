-- SQLMesh Model: Bronze BindingDB
-- Transforms raw BindingDB API responses into typed bronze layer
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.bindingdb,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        lookback 7  -- days
    ),
    cron '@daily',
    grain (bindingdb_id),
    audits (
        not_null(columns := (bindingdb_id)),
        unique_values(columns := (bindingdb_id))
    )
);

SELECT
    -- Generate UUID for id
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- Ligand info
    COALESCE(
        r.response_body->>'monomerid',
        r.response_body->>'ligandid'
    ) AS bindingdb_id,
    r.response_body->>'name' AS ligand_name,
    r.response_body->>'smiles' AS smiles,
    r.response_body->>'inchi' AS inchi,
    COALESCE(
        r.response_body->>'inchi_key',
        r.response_body->>'inchikey'
    ) AS inchi_key,

    -- Target info
    COALESCE(
        r.response_body->>'target',
        r.response_body->>'target_name'
    ) AS target_name,
    COALESCE(
        r.response_body->>'target_source',
        'UniProt'
    ) AS target_source,
    COALESCE(
        r.response_body->>'uniprot_id',
        r.response_body->>'target_uniprot'
    ) AS target_source_id,
    r.response_body->>'organism' AS target_organism,

    -- Binding affinity data
    (r.response_body->>'ki_nm')::NUMERIC AS ki_nm,
    (r.response_body->>'kd_nm')::NUMERIC AS kd_nm,
    (r.response_body->>'ic50_nm')::NUMERIC AS ic50_nm,
    (r.response_body->>'ec50_nm')::NUMERIC AS ec50_nm,
    r.response_body->>'activity_type' AS activity_type,
    (r.response_body->>'activity_value')::NUMERIC AS activity_value,
    r.response_body->>'activity_unit' AS activity_unit,

    -- Source tracking
    COALESCE(
        r.response_body->>'pmid',
        r.response_body->>'pubmed_id'
    ) AS pmid,
    r.response_body->>'doi' AS doi,
    r.response_body->>'patent_id' AS patent_id,

    -- Processing metadata
    FALSE AS processed_to_silver,
    NOW() AS ingested_at

FROM mol_raw.bindingdb r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND COALESCE(
      r.response_body->>'monomerid',
      r.response_body->>'ligandid'
  ) IS NOT NULL
