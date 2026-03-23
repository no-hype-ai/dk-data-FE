-- SQLMesh Model: Silver DrugBank
-- Promotes mol_bronze.drugbank into mol_silver.drugbank with molecule-level linkage.
-- Entity linking: LEFT JOIN mol_silver.molecules on inchi_key — most stable structural identifier.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Exposes DrugBank pharmacological data to xenon sections:
--   molecule_profile, mechanism_of_action

MODEL (
    name mol_silver.drugbank,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (drugbank_id))
    )
);

SELECT
    gen_random_uuid()                       AS drugbank_silver_id,
    m.molecule_id,
    b.drugbank_id,
    b.inchi_key,
    b.cas_number,
    b.unii,

    -- Names
    b.name,
    b.synonyms,
    b.international_brands,

    -- Drug classification
    b.drug_type,
    b.state,
    b.groups,
    b.classification,
    b.categories,
    b.atc_codes,

    -- Pharmacology (key fields for mechanism_of_action section)
    b.description,
    b.indication,
    b.pharmacodynamics,
    b.mechanism_of_action,
    b.absorption,
    b.protein_binding,
    b.metabolism,
    b.half_life,
    b.route_of_elimination,
    b.clearance,
    b.volume_of_distribution,

    -- Structure
    b.smiles,
    b.inchi,
    b.molecular_formula,
    b.average_mass,
    b.monoisotopic_mass,

    -- Source tracking
    'drugbank'                              AS source,
    b.created_at

FROM mol_bronze.drugbank b
LEFT JOIN mol_silver.molecules m ON LOWER(m.inchi_key) = LOWER(b.inchi_key)
WHERE b.drugbank_id IS NOT NULL;
