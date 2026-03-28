-- SQLMesh Model: Bronze PubChem
-- Transforms Raw PubChem Compound responses to Bronze typed columns
-- Part of: 012-dk-data-platform
--
-- mol_raw.pubchem schema (migration 028_raw_layer_tables.sql):
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
    name mol_bronze.pubchem,
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

-- Unnest PC_Compounds array from PubChem PUG REST JSON responses.
-- PubChem /compound/name/{name}/JSON returns {"PC_Compounds": [{id, atoms, bonds, props, ...}]}.
-- CID lives at compound->'id'->'id'->'cid'.
WITH compounds AS (
    SELECT
        raw.id              AS raw_source_id,
        raw.request_timestamp,
        cmp.value           AS cmp
    FROM mol_raw.pubchem AS raw
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN raw.response_body ? 'PC_Compounds'
            THEN raw.response_body->'PC_Compounds'
            ELSE jsonb_build_array(raw.response_body)
        END
    ) AS cmp(value)
    WHERE raw.response_status = 200
      AND raw.processed_to_bronze = FALSE
      AND raw.request_timestamp BETWEEN @start_dt AND @end_dt
)

SELECT
    gen_random_uuid()                                               AS id,

    -- PubChem Identifiers (PUG REST nested path: id.id.cid)
    (cmp->'id'->'id'->>'cid')::BIGINT                              AS cid,

    -- Structure fields — PUG REST doesn't return these directly; NULL for now
    NULL::TEXT                                                      AS canonical_smiles,
    NULL::TEXT                                                      AS isomeric_smiles,
    NULL::TEXT                                                      AS iupac_name,
    NULL::TEXT                                                      AS inchi,
    NULL::TEXT                                                      AS inchi_key,
    NULL::TEXT                                                      AS molecular_formula,
    NULL::NUMERIC                                                   AS molecular_weight,
    NULL::NUMERIC                                                   AS exact_mass,

    -- Properties
    NULL::NUMERIC                                                   AS xlogp,
    NULL::NUMERIC                                                   AS tpsa,
    NULL::NUMERIC                                                   AS complexity,
    (cmp->>'charge')::INTEGER                                       AS charge,
    NULL::INTEGER                                                   AS h_bond_donor_count,
    NULL::INTEGER                                                   AS h_bond_acceptor_count,
    NULL::INTEGER                                                   AS rotatable_bond_count,
    (cmp->'count'->>'heavy_atom')::INTEGER                         AS heavy_atom_count,
    (cmp->'count'->>'atom_chiral')::INTEGER                        AS atom_stereo_count,
    (cmp->'count'->>'bond_chiral')::INTEGER                        AS bond_stereo_count,
    (cmp->'count'->>'unit')::INTEGER                               AS covalent_unit_count,

    -- Names and cross-references (NULL — not in this endpoint)
    NULL::JSONB                                                     AS synonyms,
    NULL::JSONB                                                     AS mesh_headings,
    NULL::JSONB                                                     AS pharmacological_actions,
    NULL::TEXT                                                      AS cas_number,
    NULL::JSONB                                                     AS drugbank_ids,
    NULL::JSONB                                                     AS chembl_ids,
    NULL::TEXT                                                      AS unii,
    NULL::JSONB                                                     AS taxonomy,
    NULL::JSONB                                                     AS patents,
    NULL::JSONB                                                     AS assay_ids,
    NULL::INTEGER                                                   AS bioassay_count,

    -- Raw source tracking
    cmp                                                             AS raw_json,
    raw_source_id,
    'pubchem'                                                       AS source,
    request_timestamp,
    request_timestamp                                               AS source_updated_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM compounds
WHERE (cmp->'id'->'id'->>'cid') IS NOT NULL;
