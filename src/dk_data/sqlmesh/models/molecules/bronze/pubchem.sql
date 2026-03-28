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
--
-- Cross-reference fields (synonyms, cas_number, drugbank_ids, chembl_ids, unii, assay_ids,
-- bioassay_count) are populated by LEFT JOINing mol_bronze.pubchem_xrefs and
-- mol_bronze.pubchem_bioassays — populated by load_pubchem_extended.py.
-- taxonomy, mesh_headings, pharmacological_actions: not available from PubChem PUG REST
-- or the xref endpoint; genuinely unavailable.
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
),

-- Aggregate cross-references per CID from mol_bronze.pubchem_xrefs
-- xref_type values: 'DrugBank', 'ChEMBL', 'KEGG', 'PharmGKB', etc.
cid_xrefs AS (
    SELECT
        cid,
        -- Synonyms: collect all registered IDs as a JSONB array of {type, id} objects
        jsonb_agg(
            jsonb_build_object('type', xref_type, 'id', xref_id)
            ORDER BY xref_type, xref_id
        )                                                               AS all_xrefs,
        -- CAS: PubChem stores CAS as xref_type = 'RN' or within synonym endpoint;
        -- not available from the SourceName/RegistryID xref endpoint used by load_pubchem_extended
        MAX(CASE WHEN xref_type = 'CAS' THEN xref_id END)             AS cas_number,
        -- DrugBank IDs
        jsonb_agg(xref_id) FILTER (WHERE xref_type = 'DrugBank')      AS drugbank_ids,
        -- ChEMBL IDs
        jsonb_agg(xref_id) FILTER (WHERE xref_type = 'ChEMBL')        AS chembl_ids,
        -- UNII: FDA UNII is stored as 'FDA UNII' or 'UNII' xref type in PubChem
        MAX(CASE WHEN xref_type IN ('UNII', 'FDA UNII') THEN xref_id END) AS unii
    FROM mol_bronze.pubchem_xrefs
    GROUP BY cid
),

-- Aggregate bioassay counts per CID from mol_bronze.pubchem_bioassays
cid_bioassays AS (
    SELECT
        cid,
        jsonb_agg(DISTINCT aid ORDER BY aid)                           AS assay_ids,
        COUNT(DISTINCT aid)::INTEGER                                   AS bioassay_count
    FROM mol_bronze.pubchem_bioassays
    GROUP BY cid
)

SELECT
    gen_random_uuid()                                               AS id,

    -- PubChem Identifiers (PUG REST nested path: id.id.cid)
    (cmp->'id'->'id'->>'cid')::BIGINT                              AS cid,

    -- Structure fields — extracted from props array (label/name/value pattern)
    -- props[*].urn.label identifies the property type; value.sval = string value
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'SMILES' LIMIT 1)                        AS canonical_smiles,
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'SMILES' AND u->>'name' = 'Isomeric' LIMIT 1)  AS isomeric_smiles,
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'IUPAC Name' AND u->>'name' = 'Preferred' LIMIT 1) AS iupac_name,
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'InChI' LIMIT 1)                         AS inchi,
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'InChIKey' LIMIT 1)                      AS inchi_key,
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Molecular Formula' LIMIT 1)             AS molecular_formula,
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Molecular Weight' LIMIT 1)::NUMERIC     AS molecular_weight,
    (SELECT p->>'sval' FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Mass' AND u->>'name' = 'Exact' LIMIT 1)::NUMERIC AS exact_mass,

    -- Properties — from props array
    (SELECT (p->>'fval')::NUMERIC FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Log P' LIMIT 1)                         AS xlogp,
    (SELECT (p->>'fval')::NUMERIC FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Topological' AND u->>'name' = 'Polar Surface Area' LIMIT 1) AS tpsa,
    (SELECT (p->>'fval')::NUMERIC FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Compound Complexity' LIMIT 1)           AS complexity,
    (cmp->>'charge')::INTEGER                                       AS charge,
    (SELECT (p->>'ival')::INTEGER FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Count' AND u->>'name' = 'Hydrogen Bond Donor' LIMIT 1) AS h_bond_donor_count,
    (SELECT (p->>'ival')::INTEGER FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Count' AND u->>'name' = 'Hydrogen Bond Acceptor' LIMIT 1) AS h_bond_acceptor_count,
    (SELECT (p->>'ival')::INTEGER FROM jsonb_array_elements(cmp->'props') AS p_row,
            LATERAL (SELECT p_row->'value') AS v(p), LATERAL (SELECT p_row->'urn') AS u(u)
     WHERE u->>'label' = 'Count' AND u->>'name' = 'Rotatable Bond' LIMIT 1) AS rotatable_bond_count,
    (cmp->'count'->>'heavy_atom')::INTEGER                         AS heavy_atom_count,
    (cmp->'count'->>'atom_chiral')::INTEGER                        AS atom_stereo_count,
    (cmp->'count'->>'bond_chiral')::INTEGER                        AS bond_stereo_count,
    (cmp->'count'->>'unit')::INTEGER                               AS covalent_unit_count,

    -- Names and cross-references: populated from mol_bronze.pubchem_xrefs (load_pubchem_extended.py)
    -- synonyms: all xref entries as [{type, id}, ...]; PubChem synonym endpoint not yet called
    cx.all_xrefs                                                    AS synonyms,
    -- mesh_headings: not available from PubChem PUG REST or xref endpoint; genuinely unavailable
    NULL::JSONB                                                     AS mesh_headings,
    -- pharmacological_actions: not in PubChem PUG REST; would require PUG View pharmacology section
    NULL::JSONB                                                     AS pharmacological_actions,
    cx.cas_number,
    cx.drugbank_ids,
    cx.chembl_ids,
    cx.unii,
    -- taxonomy: not available from PubChem PUG REST or xref endpoint
    NULL::JSONB                                                     AS taxonomy,
    -- patents: not in PubChem xref endpoint used; would require patent-specific API calls
    NULL::JSONB                                                     AS patents,
    cb.assay_ids,
    cb.bioassay_count,

    -- Raw source tracking
    cmp                                                             AS raw_json,
    raw_source_id,
    'pubchem'                                                       AS source,
    request_timestamp,
    request_timestamp                                               AS source_updated_at,
    FALSE                                                           AS processed_to_silver,
    NOW()                                                           AS created_at

FROM compounds
LEFT JOIN cid_xrefs cx
    ON cx.cid = (cmp->'id'->'id'->>'cid')::BIGINT
LEFT JOIN cid_bioassays cb
    ON cb.cid = (cmp->'id'->'id'->>'cid')::BIGINT
WHERE (cmp->'id'->'id'->>'cid') IS NOT NULL;
