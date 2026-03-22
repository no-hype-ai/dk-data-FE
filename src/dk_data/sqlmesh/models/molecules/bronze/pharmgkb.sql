-- SQLMesh Model: Bronze PharmGKB
-- Transforms raw PharmGKB API responses into typed bronze layer.
-- Response: {"data": [{id, name, type, crossReferences, clinicalAnnotations, ...}]}
--        or a single entity at top level.
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.pharmgkb,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    grain pharmgkb_id,
    audits (
        not_null(columns := (pharmgkb_id))
    )
);

-- Unnest data array or treat single entity as array
WITH unnested AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        item
    FROM mol_raw.pharmgkb r,
         jsonb_array_elements(
             CASE
                 WHEN r.response_body->'data' IS NOT NULL AND jsonb_typeof(r.response_body->'data') = 'array'
                     THEN r.response_body->'data'
                 ELSE jsonb_build_array(r.response_body)
             END
         ) AS item
    WHERE r.response_status = 200
      AND r.response_body IS NOT NULL
)

SELECT DISTINCT ON (pharmgkb_id)
    gen_random_uuid()   AS id,
    raw_id,

    COALESCE(item->>'id', item->>'pharmgkbId') AS pharmgkb_id,
    item->>'name'                              AS name,
    COALESCE(item->>'type', item->>'objCls')   AS entity_type,

    -- Cross-references (crossReferences is an object keyed by database name)
    (item->'crossReferences'->'DrugBank'->0)::TEXT          AS drugbank_id,
    (item->'crossReferences'->'ChEMBL'->0)::TEXT            AS chembl_id,
    (item->'crossReferences'->'RxNorm'->0)::TEXT            AS rxnorm_id,
    (item->'crossReferences'->'PubChem Compound'->0)::BIGINT AS pubchem_cid,
    (item->'crossReferences'->'CAS'->0)::TEXT               AS cas_number,

    item->>'drugType'  AS drug_type,
    item->>'smiles'    AS smiles,
    item->>'inchiKey'  AS inchi_key,

    item->'clinicalAnnotations'  AS clinical_annotations,
    item->'dosingGuidelines'     AS dosing_guidelines,
    item->'drugLabels'           AS drug_labels,
    item->'variantAnnotations'   AS variant_annotations,
    item->'pathways'             AS pathways,

    FALSE               AS processed_to_silver,
    request_timestamp,
    request_timestamp   AS ingested_at,
    'pharmgkb'          AS source,
    request_timestamp   AS source_updated_at

FROM unnested
WHERE COALESCE(item->>'id', item->>'pharmgkbId') IS NOT NULL
ORDER BY pharmgkb_id, request_timestamp DESC NULLS LAST
