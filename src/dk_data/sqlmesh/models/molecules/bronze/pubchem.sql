-- SQLMesh Model: Bronze PubChem
-- Transforms Raw PubChem Compound responses to Bronze typed columns
-- Part of: 012-dk-data-platform
--
-- raw.pubchem schema (migration 028_raw_layer_tables.sql):
--   id UUID, request_id, request_timestamp TIMESTAMPTZ,
--   response_status INTEGER, response_body JSONB,
--   processed_to_bronze BOOLEAN, ...
--
-- PubChem PUG REST API compound JSON field names
-- (endpoint: /compound/cid/{cid}/JSON → PropertyTable.Properties[0]):
--   CID (integer), MolecularFormula, MolecularWeight (string), ExactMass (string),
--   CanonicalSMILES, IsomericSMILES, IUPACName,
--   InChI, InChIKey,
--   XLogP (numeric), TPSA (numeric), Complexity (numeric),
--   Charge (integer), HBondDonorCount, HBondAcceptorCount,
--   RotatableBondCount, HeavyAtomCount,
--   AtomStereoCount, BondStereoCount, CovalentUnitCount
--
-- Cross-reference fields are normalized to lowercase snake_case when stored
-- in the response_body by the ingestion layer.

MODEL (
    name bronze.pubchem,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    audits (
        not_null(columns := (cid)),
        unique_values(columns := (cid))
    ),
    grain cid
);

SELECT
    gen_random_uuid()                                               AS id,

    -- PubChem Identifiers
    -- CID is an integer in PubChem API; stored as numeric in JSON
    (response_body->>'cid')::BIGINT                                 AS cid,

    -- Structure
    response_body->>'canonical_smiles'                              AS canonical_smiles,
    response_body->>'isomeric_smiles'                               AS isomeric_smiles,
    response_body->>'iupac_name'                                    AS iupac_name,
    response_body->>'inchi'                                         AS inchi,
    response_body->>'inchikey'                                      AS inchi_key,
    response_body->>'molecular_formula'                             AS molecular_formula,
    (response_body->>'molecular_weight')::NUMERIC                   AS molecular_weight,
    (response_body->>'exact_mass')::NUMERIC                         AS exact_mass,

    -- Properties (all numeric or integer — cast explicitly)
    (response_body->>'xlogp')::NUMERIC                              AS xlogp,
    (response_body->>'tpsa')::NUMERIC                               AS tpsa,
    (response_body->>'complexity')::NUMERIC                         AS complexity,
    (response_body->>'charge')::INTEGER                             AS charge,
    (response_body->>'h_bond_donor_count')::INTEGER                 AS h_bond_donor_count,
    (response_body->>'h_bond_acceptor_count')::INTEGER              AS h_bond_acceptor_count,
    (response_body->>'rotatable_bond_count')::INTEGER               AS rotatable_bond_count,
    (response_body->>'heavy_atom_count')::INTEGER                   AS heavy_atom_count,
    (response_body->>'atom_stereo_count')::INTEGER                  AS atom_stereo_count,
    (response_body->>'bond_stereo_count')::INTEGER                  AS bond_stereo_count,
    (response_body->>'covalent_unit_count')::INTEGER                AS covalent_unit_count,

    -- Names and Synonyms (JSONB arrays)
    response_body->'synonyms'                                       AS synonyms,
    response_body->'mesh_headings'                                  AS mesh_headings,
    response_body->'pharmacological_actions'                        AS pharmacological_actions,

    -- Cross-references
    response_body->>'cas_number'                                    AS cas_number,
    response_body->'drugbank_ids'                                   AS drugbank_ids,
    response_body->'chembl_ids'                                     AS chembl_ids,
    -- unii: scalar TEXT value, use ->> not -> to avoid returning JSONB
    response_body->>'unii'                                          AS unii,

    -- Classifications (JSONB arrays/objects)
    response_body->'taxonomy'                                       AS taxonomy,
    response_body->'patents'                                        AS patents,
    response_body->'assay_ids'                                      AS assay_ids,
    (response_body->>'bioassay_count')::INTEGER                     AS bioassay_count,

    -- Raw source tracking
    response_body                                                   AS raw_json,
    -- raw_source_id references the UUID primary key of raw.pubchem (not the generated id above)
    raw.id                                                          AS raw_source_id,
    'pubchem'                                                       AS source,
    request_timestamp,
    request_timestamp                                               AS source_updated_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM raw.pubchem AS raw
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'cid' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
