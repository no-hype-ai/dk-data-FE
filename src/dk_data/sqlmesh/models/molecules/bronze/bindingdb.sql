-- SQLMesh Model: Bronze BindingDB
-- Transforms raw BindingDB API responses into typed bronze layer.
-- Response formats:
--   {"affinities": [{monomerid, name, smiles, Ki (nM), IC50 (nM), ...}]}
--   {"ligands": [{...}]}
--   Single-record flat object at root level
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.bindingdb,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 1000
    ),
    cron '@daily',
    grain bindingdb_id,
    audits (
        not_null(columns := (bindingdb_id))
    )
);

-- Unnest response arrays: affinities[], ligands[], or single flat record
WITH unnested AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        ligand,
        ligand AS raw_json
    FROM mol_raw.bindingdb r,
         jsonb_array_elements(
             CASE
                 WHEN r.response_body->'affinities' IS NOT NULL AND jsonb_typeof(r.response_body->'affinities') = 'array'
                     THEN r.response_body->'affinities'
                 WHEN r.response_body->'ligands' IS NOT NULL AND jsonb_typeof(r.response_body->'ligands') = 'array'
                     THEN r.response_body->'ligands'
                 ELSE jsonb_build_array(r.response_body)
             END
         ) AS ligand
    WHERE r.response_status = 200
      AND r.response_body IS NOT NULL
      AND r.processed_to_bronze = FALSE
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
)

SELECT DISTINCT ON (bindingdb_id)
    gen_random_uuid()   AS id,
    raw_id,

    COALESCE(
        ligand->>'monomerid',
        ligand->>'ligandid'
    ) AS bindingdb_id,

    COALESCE(ligand->>'name', ligand->>'ligand_name') AS ligand_name,
    ligand->>'smiles'   AS smiles,
    ligand->>'inchi'    AS inchi,
    COALESCE(ligand->>'inchi_key', ligand->>'inchikey') AS inchi_key,

    -- Target info
    COALESCE(ligand->>'target', ligand->>'target_name') AS target_name,
    COALESCE(ligand->>'target_source', 'UniProt')       AS target_source,
    COALESCE(ligand->>'uniprot_id', ligand->>'target_uniprot') AS target_source_id,
    COALESCE(ligand->>'organism', ligand->>'target_organism')  AS target_organism,

    -- Binding affinity — BindingDB uses both snake_case and display formats
    COALESCE(
        (ligand->>'ki_nm')::NUMERIC,
        (ligand->>'Ki (nM)')::NUMERIC
    ) AS ki_nm,
    COALESCE(
        (ligand->>'kd_nm')::NUMERIC,
        (ligand->>'Kd (nM)')::NUMERIC
    ) AS kd_nm,
    COALESCE(
        (ligand->>'ic50_nm')::NUMERIC,
        (ligand->>'IC50 (nM)')::NUMERIC
    ) AS ic50_nm,
    COALESCE(
        (ligand->>'ec50_nm')::NUMERIC,
        (ligand->>'EC50 (nM)')::NUMERIC
    ) AS ec50_nm,

    ligand->>'activity_type'                    AS activity_type,
    (ligand->>'activity_value')::NUMERIC        AS activity_value,
    ligand->>'activity_unit'                    AS activity_unit,

    COALESCE(ligand->>'pmid', ligand->>'pubmed_id') AS pmid,
    ligand->>'doi'        AS doi,
    ligand->>'patent_id'  AS patent_id,

    raw_json,
    FALSE               AS processed_to_silver,
    request_timestamp,
    request_timestamp   AS ingested_at,
    'bindingdb'         AS source,
    request_timestamp   AS source_updated_at

FROM unnested
WHERE COALESCE(ligand->>'monomerid', ligand->>'ligandid') IS NOT NULL
ORDER BY bindingdb_id, request_timestamp DESC NULLS LAST
