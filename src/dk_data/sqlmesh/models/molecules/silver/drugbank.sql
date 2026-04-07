-- SQLMesh Model: Silver DrugBank
-- Promotes mol_bronze.drugbank into mol_silver.drugbank with molecule-level linkage.
-- Entity linking: inchi_key for small molecules; canonical_name fallback for biologics
-- (antibodies/proteins have no inchi_key in ChEMBL or DrugBank).
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

SELECT DISTINCT ON (b.drugbank_id)
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

    -- Molecular properties (from calculated_properties in bronze)
    b.alogp,
    b.hba,
    b.hbd,
    b.psa,
    b.rotatable_bond_count,
    b.heavy_atoms,
    b.aromatic_rings,
    b.isomeric_smiles,

    -- Pharmacology (additional fields)
    b.toxicity,

    -- Relational data
    b.drug_interactions,
    b.food_interactions,
    b.pathways,
    b.external_links,
    b.external_identifiers,
    b.calculated_properties,
    b.experimental_properties,
    b.fda_label,
    b.patents,
    b.products,

    -- Source tracking
    'drugbank'                              AS source,
    b.source_updated_at,
    b.loaded_at                             AS ingested_at,
    b.created_at

FROM mol_bronze.drugbank b
LEFT JOIN mol_silver.molecules m ON (
    -- Small molecules: match via InChI key (exact structural match)
    (b.inchi_key IS NOT NULL AND LOWER(m.inchi_key) = LOWER(b.inchi_key))
    -- Biologics (antibodies, proteins): no inchi_key, match via canonical name
    OR (b.inchi_key IS NULL AND LOWER(m.canonical_name) = LOWER(b.name))
)
WHERE b.drugbank_id IS NOT NULL
ORDER BY b.drugbank_id, b.source_updated_at DESC NULLS LAST;
