-- SQLMesh Model: Bronze PubChem
-- Transforms Raw PubChem Compound responses to Bronze typed columns
-- Part of: 012-dk-data-platform
--
-- Source: PubChem SDQ agent endpoint (sdqagent.cgi?collection=compound&select=*)
-- Each mol_raw.pubchem row is a single flat compound record (CID-range paginated).
-- SDQ response fields (lowercase): cid, mf, mw, smiles, isomericsmiles, iupacname,
--   inchi, inchikey, xlogp, polararea, complexity, hbondacc, hbonddonor, heavycnt,
--   rotbonds, exactmass, charge, cmpdsynonym, aids

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

-- Aggregate cross-references per CID from mol_bronze.pubchem_xrefs (populated by load_pubchem_extended.py)
WITH cid_xrefs AS (
    SELECT
        cid,
        MAX(CASE WHEN xref_type = 'CAS' THEN xref_id END)             AS cas_number,
        jsonb_agg(xref_id) FILTER (WHERE xref_type = 'DrugBank')      AS drugbank_ids,
        jsonb_agg(xref_id) FILTER (WHERE xref_type = 'ChEMBL')        AS chembl_ids,
        MAX(CASE WHEN xref_type IN ('UNII', 'FDA UNII') THEN xref_id END) AS unii
    FROM mol_bronze.pubchem_xrefs
    GROUP BY cid
),

-- Aggregate bioassay counts per CID
cid_bioassays AS (
    SELECT
        cid,
        jsonb_agg(DISTINCT aid ORDER BY aid)  AS assay_ids,
        COUNT(DISTINCT aid)::INTEGER           AS bioassay_count
    FROM mol_bronze.pubchem_bioassays
    GROUP BY cid
),

-- Aggregate human-readable synonyms per CID
cid_synonyms AS (
    SELECT
        cid,
        jsonb_agg(synonym_name ORDER BY synonym_name) AS synonym_names
    FROM mol_bronze.pubchem_synonyms
    GROUP BY cid
)

SELECT
    gen_random_uuid()                                                               AS id,

    -- PubChem CID (flat key from SDQ response)
    (response_body->>'cid')::BIGINT                                                AS cid,

    -- Structure fields — direct flat keys from SDQ agent
    response_body->>'smiles'                                                       AS canonical_smiles,
    response_body->>'isomericsmiles'                                               AS isomeric_smiles,
    response_body->>'iupacname'                                                    AS iupac_name,
    response_body->>'inchi'                                                        AS inchi,
    response_body->>'inchikey'                                                     AS inchi_key,
    response_body->>'mf'                                                           AS molecular_formula,
    (response_body->>'mw')::NUMERIC                                                AS molecular_weight,
    (response_body->>'exactmass')::NUMERIC                                         AS exact_mass,

    -- Properties
    (response_body->>'xlogp')::NUMERIC                                             AS xlogp,
    (response_body->>'polararea')::NUMERIC                                         AS tpsa,
    (response_body->>'complexity')::NUMERIC                                        AS complexity,
    (response_body->>'charge')::INTEGER                                            AS charge,
    (response_body->>'hbonddonor')::INTEGER                                        AS h_bond_donor_count,
    (response_body->>'hbondacc')::INTEGER                                          AS h_bond_acceptor_count,
    (response_body->>'rotbonds')::INTEGER                                          AS rotatable_bond_count,
    (response_body->>'heavycnt')::INTEGER                                          AS heavy_atom_count,
    NULL::INTEGER                                                                  AS atom_stereo_count,
    NULL::INTEGER                                                                  AS bond_stereo_count,
    NULL::INTEGER                                                                  AS covalent_unit_count,

    -- Names and cross-references from side tables (populated by load_pubchem_extended.py)
    COALESCE(cs.synonym_names, '[]'::JSONB)                                       AS synonyms,
    NULL::JSONB                                                                    AS mesh_headings,
    NULL::JSONB                                                                    AS pharmacological_actions,
    cx.cas_number,
    cx.drugbank_ids,
    cx.chembl_ids,
    cx.unii,
    NULL::JSONB                                                                    AS taxonomy,
    NULL::JSONB                                                                    AS patents,
    cb.assay_ids,
    cb.bioassay_count,

    -- Raw source tracking
    response_body                                                                  AS raw_json,
    raw.id                                                                         AS raw_source_id,
    'pubchem'                                                                      AS source,
    request_timestamp,
    request_timestamp                                                              AS source_updated_at,
    FALSE                                                                          AS processed_to_silver,
    NOW()                                                                          AS created_at

FROM mol_raw.pubchem AS raw
LEFT JOIN cid_xrefs cx
    ON cx.cid = (raw.response_body->>'cid')::BIGINT
LEFT JOIN cid_bioassays cb
    ON cb.cid = (raw.response_body->>'cid')::BIGINT
LEFT JOIN cid_synonyms cs
    ON cs.cid = (raw.response_body->>'cid')::BIGINT
WHERE raw.response_status = 200
  AND raw.processed_to_bronze = FALSE
  AND raw.response_body->>'cid' IS NOT NULL
  AND raw.request_timestamp BETWEEN @start_dt AND @end_dt;
