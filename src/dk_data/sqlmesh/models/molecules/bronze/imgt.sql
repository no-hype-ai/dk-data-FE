-- SQLMesh Model: Bronze IMGT Antibody Structures
-- Transforms raw IMGT (ImMunoGeneTics) API responses to Bronze typed columns.
-- API: https://www.imgt.org/3Dstructure-DB/cgi/details.cgi
-- Response shape: JSON with antibody/structure details (pdb_code, chains, species, etc.)
-- Critical for biologic drug (antibody/ADC) characterisation.

MODEL (
    name mol_bronze.imgt,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (pdb_code))
    ),
    grain pdb_code
);

WITH normalised AS (
    SELECT
        r.id              AS raw_source_id,
        r.request_timestamp,
        CASE
            WHEN r.response_body ? 'data' AND jsonb_typeof(r.response_body->'data') = 'array'
            THEN jsonb_array_elements(r.response_body->'data')
            WHEN r.response_body ? 'structures'
            THEN jsonb_array_elements(r.response_body->'structures')
            ELSE r.response_body
        END AS rec
    FROM mol_raw.imgt r
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body IS NOT NULL
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
)

SELECT DISTINCT ON (
    COALESCE(rec->>'pdb_code', rec->>'pdbcode', rec->>'PDBcode', rec->>'id')
)
    gen_random_uuid()                                                               AS id,

    COALESCE(rec->>'pdb_code', rec->>'pdbcode', rec->>'PDBcode', rec->>'id')       AS pdb_code,
    COALESCE(rec->>'molecule', rec->>'antibody_name', rec->>'description')         AS molecule_name,
    rec->>'species'                                                                AS species,
    rec->>'receptor_type'                                                          AS receptor_type,

    -- Chain information
    rec->'chains'                                                                  AS chains,
    rec->>'heavy_chain_subgroup'                                                   AS heavy_chain_subgroup,
    rec->>'light_chain_subgroup'                                                   AS light_chain_subgroup,
    rec->>'light_chain_type'                                                       AS light_chain_type,

    -- Structure details
    COALESCE(rec->>'resolution', rec->>'resolution_ang')                           AS resolution,
    rec->>'experimental_method'                                                    AS experimental_method,

    -- Cross-references
    rec->>'uniprot_id'                                                             AS uniprot_id,
    rec->>'drug_name'                                                              AS drug_name,

    -- Raw source tracking
    rec                                                                            AS raw_json,
    raw_source_id,
    'imgt'                                                                         AS source,
    request_timestamp,
    request_timestamp                                                              AS source_updated_at,
    FALSE                                                                          AS processed_to_silver,
    NOW()                                                                          AS created_at

FROM normalised
WHERE COALESCE(rec->>'pdb_code', rec->>'pdbcode', rec->>'PDBcode', rec->>'id') IS NOT NULL
ORDER BY
    COALESCE(rec->>'pdb_code', rec->>'pdbcode', rec->>'PDBcode', rec->>'id'),
    request_timestamp DESC NULLS LAST;
