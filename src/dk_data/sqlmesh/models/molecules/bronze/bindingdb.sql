-- SQLMesh Model: Bronze BindingDB
-- Transforms raw BindingDB TSV data (stored as JSONB) into typed bronze layer
-- BindingDB provides drug-target binding affinity measurements
-- Part of DK Molecule Data Platform (012-dk-data-platform)
--
-- BindingDB TSV fields (stored verbatim as JSONB keys):
--   "BindingDB Reactant_set_id"  — internal BindingDB record ID
--   "Ligand InChIKey"            — standard InChIKey for the ligand
--   "Ligand SMILES"              — SMILES string
--   "PubChem CID"                — PubChem compound ID
--   "ChEMBL ID of Ligand"        — ChEMBL ID
--   "Target Name Assigned by Curator or DataSource"
--   "Target Source Organism According to Curator or DataSource"
--   "UniProt (SwissProt) Primary ID of Target Chain"
--   "Ki (nM)"                    — inhibition constant in nanomolar
--   "IC50 (nM)"                  — half maximal inhibitory concentration
--   "Kd (nM)"                    — dissociation constant
--   "EC50 (nM)"                  — half maximal effective concentration
--   "kon (M-1-s-1)"              — association rate constant
--   "koff (s-1)"                 — dissociation rate constant
--   "pH"                         — assay pH
--   "Temp (C)"                   — assay temperature
--   "Curation/DataSource"        — data source name
--   "Article DOI"                — publication DOI
--   "PMID"                       — PubMed ID
--   "PDB ID(s) for Ligand-Target Complex" — PDB co-crystal IDs

MODEL (
    name mol_bronze.bindingdb,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key bindingdb_id
    ),
    cron '@daily',
    grain (bindingdb_id),
    audits (
        not_null(columns := (bindingdb_id)),
        unique_values(columns := (bindingdb_id))
    )
);

SELECT
    uuid_generate_v4() AS id,
    r.id AS raw_id,

    -- BindingDB record identifier
    r.response_body->>'BindingDB Reactant_set_id' AS bindingdb_id,

    -- Ligand identifiers
    r.response_body->>'Ligand InChIKey' AS inchi_key,
    r.response_body->>'Ligand SMILES' AS smiles,
    (r.response_body->>'PubChem CID')::BIGINT AS pubchem_cid,
    r.response_body->>'ChEMBL ID of Ligand' AS chembl_id,

    -- Target information
    r.response_body->>'Target Name Assigned by Curator or DataSource' AS target_name,
    r.response_body->>'Target Source Organism According to Curator or DataSource' AS target_organism,
    r.response_body->>'UniProt (SwissProt) Primary ID of Target Chain' AS uniprot_id,

    -- Binding affinity measurements (all in nanomolar)
    -- BindingDB uses qualitative prefixes like ">79400" for values above detection limit.
    -- Strip any non-numeric prefix (>, <, ~, =, spaces) before casting to NUMERIC.
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS ki_nm,
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS ic50_nm,
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS kd_nm,
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS ec50_nm,

    -- Kinetics (optional)
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'kon (M-1-s-1)', ''), '[^0-9.eE+-]', '', 'g'), '')::NUMERIC AS kon,
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'koff (s-1)', ''), '[^0-9.eE+-]', '', 'g'), '')::NUMERIC AS koff,

    -- Assay conditions
    -- pH is always a plain numeric value in BindingDB
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'pH', ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS assay_ph,
    -- Temperature may include " C" suffix (e.g. "25.00 C") — strip non-numeric suffix
    NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Temp (C)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC AS assay_temp_c,

    -- Best available affinity value (prefer Ki > Kd > IC50 > EC50)
    -- Only classify as a type if the numeric value is usable (strip qualifier prefix check)
    CASE
        WHEN r.response_body->>'Ki (nM)' IS NOT NULL
             AND REGEXP_REPLACE(r.response_body->>'Ki (nM)', '[^0-9.]', '', 'g') != '' THEN 'Ki'
        WHEN r.response_body->>'Kd (nM)' IS NOT NULL
             AND REGEXP_REPLACE(r.response_body->>'Kd (nM)', '[^0-9.]', '', 'g') != '' THEN 'Kd'
        WHEN r.response_body->>'IC50 (nM)' IS NOT NULL
             AND REGEXP_REPLACE(r.response_body->>'IC50 (nM)', '[^0-9.]', '', 'g') != '' THEN 'IC50'
        WHEN r.response_body->>'EC50 (nM)' IS NOT NULL
             AND REGEXP_REPLACE(r.response_body->>'EC50 (nM)', '[^0-9.]', '', 'g') != '' THEN 'EC50'
        ELSE NULL
    END AS activity_type,
    COALESCE(
        NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Ki (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC,
        NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'Kd (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC,
        NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'IC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC,
        NULLIF(REGEXP_REPLACE(COALESCE(r.response_body->>'EC50 (nM)', ''), '[^0-9.]', '', 'g'), '')::NUMERIC
    ) AS activity_value,
    'nM' AS activity_unit,

    -- Source tracking
    r.response_body->>'PMID' AS pmid,
    r.response_body->>'Article DOI' AS doi,
    r.response_body->>'Curation/DataSource' AS data_source,
    r.response_body->>'PDB ID(s) for Ligand-Target Complex' AS pdb_ids,

    -- Processing metadata
    FALSE AS processed_to_silver,
    r.ingested_at

FROM mol_raw.bindingdb r
WHERE r.response_status = 200
  AND r.processed_to_bronze = FALSE
  AND r.response_body IS NOT NULL
  AND r.response_body->>'BindingDB Reactant_set_id' IS NOT NULL
  AND r.ingested_at BETWEEN @start_dt AND @end_dt
