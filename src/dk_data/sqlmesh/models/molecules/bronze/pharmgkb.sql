-- SQLMesh Model: Bronze PharmGKB
-- Transforms raw PharmGKB chemicals TSV bulk download into typed bronze layer.
-- Source: chemicals.zip bulk download (https://api.pharmgkb.org/v1/download/file/data/chemicals.zip)
-- Each mol_raw.pharmgkb row is one chemical record parsed from chemicals.tsv.
-- TSV column names are normalised to lowercase_with_underscores by the fetcher
-- (spaces → underscores; hyphens are preserved, so "Cross-references" → "cross-references").
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.pharmgkb,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key pharmgkb_id
    ),
    cron '@weekly',
    grain pharmgkb_id,
    audits (
        not_null(columns := (pharmgkb_id)),
        unique_values(columns := (pharmgkb_id))
    ),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (pharmgkb_id)
    gen_random_uuid()   AS id,
    r.id                AS raw_id,

    -- Primary identifier: TSV column "PharmGKB Accession Id" → normalised "pharmgkb_accession_id"
    response_body->>'pharmgkb_accession_id'          AS pharmgkb_id,
    response_body->>'name'                           AS name,
    response_body->>'type'                           AS entity_type,

    -- Cross-references: flat string columns (direct from TSV, not nested JSON)
    response_body->>'drugbank_id'                    AS drugbank_id,
    response_body->>'chembl_id'                      AS chembl_id,
    -- TSV column "RxNorm Identifier" → "rxnorm_identifier"
    response_body->>'rxnorm_identifier'              AS rxnorm_id,
    -- TSV column "PubChem CID" → "pubchem_cid"
    NULLIF(response_body->>'pubchem_cid', '')::BIGINT AS pubchem_cid,
    response_body->>'cas'                            AS cas_number,

    response_body->>'drug_type'                      AS drug_type,
    response_body->>'smiles'                         AS smiles,
    response_body->>'inchi_key'                      AS inchi_key,

    -- These annotation fields are not present in the TSV bulk download
    NULL::JSONB  AS clinical_annotations,
    NULL::JSONB  AS dosing_guidelines,
    NULL::JSONB  AS drug_labels,
    NULL::JSONB  AS variant_annotations,
    NULL::JSONB  AS pathways,

    response_body                                    AS raw_json,
    FALSE                                            AS processed_to_silver,
    ingested_at,
    'pharmgkb'                                       AS source,
    ingested_at                                      AS source_updated_at

FROM mol_raw.pharmgkb r
WHERE response_status = 200
  AND response_body->>'pharmgkb_accession_id' IS NOT NULL
ORDER BY pharmgkb_id, ingested_at DESC NULLS LAST
