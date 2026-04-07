-- SQLMesh Model: Silver ADMET Properties
-- Promotes mol_bronze.tdc_admet into mol_silver.admet_properties with molecule_id linkage.
-- Entity linking: inchi_key (from TDC ADMET data) → mol_silver.molecules.
-- ADMET = Absorption, Distribution, Metabolism, Excretion, Toxicity predictions.

MODEL (
    name mol_silver.admet_properties,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (compound_id, dataset_name))
    )
);

SELECT DISTINCT ON (b.compound_id, b.dataset_name)
    gen_random_uuid()                                                   AS id,

    -- Entity linking (priority order):
    --   1. InChIKey direct match (rarely populated in TDC ADMET source)
    --   2. ChEMBL ID via identifier_mappings (compound_id stores ChEMBL IDs
    --      with extra JSON quotes from raw_json extraction; strip them first)
    COALESCE(m_ik.molecule_id, m_chembl.molecule_id)                    AS molecule_id,

    b.compound_id,
    b.smiles,
    b.inchi_key,
    b.dataset_name,
    b.dataset_type,
    b.property_name,
    b.property_value,
    b.property_category,
    'tdc_admet'                                                         AS source,
    b.source_updated_at,
    b.ingested_at,
    NOW()                                                               AS created_at

FROM mol_bronze.tdc_admet b

-- Strategy 1: InChIKey (most precise; only available for a subset of TDC compounds)
LEFT JOIN mol_silver.molecules m_ik
       ON b.inchi_key IS NOT NULL
      AND m_ik.inchi_key = b.inchi_key

-- Strategy 2: ChEMBL ID via identifier_mappings
--   compound_id may be stored with surrounding quotes (e.g. '"CHEMBL472"'); strip them.
LEFT JOIN mol_silver.identifier_mappings m_chembl
       ON m_ik.molecule_id IS NULL
      AND b.compound_id IS NOT NULL
      AND b.compound_id LIKE '%CHEMBL%'
      AND m_chembl.identifier_type = 'chembl_id'
      AND m_chembl.identifier_value = TRIM('"' FROM b.compound_id)

WHERE b.compound_id IS NOT NULL
  AND b.dataset_name IS NOT NULL
ORDER BY b.compound_id, b.dataset_name, b.source_updated_at DESC NULLS LAST;
