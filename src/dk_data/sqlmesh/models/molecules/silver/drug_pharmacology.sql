-- SQLMesh Model: Silver Drug Pharmacology
-- DrugBank pharmacology data linked to mol_silver.molecules
-- Feature: 019-cms-puf-platform-reconciliation — zero column loss audit
--
-- Purpose: DrugBank bronze contains clinical pharmacology fields (description,
--   pharmacodynamics, categories, targets, enzymes) that could not fit cleanly in
--   mol_silver.molecules. This table exposes all DrugBank bronze columns in silver
--   via a molecule_id link so they are directly queryable.
--
-- Note: Many DrugBank fields (mechanism_of_action, absorption, metabolism, etc.) are
--   NULL in bronze because the XML fetcher does not extract them. These are preserved
--   as NULLs here so the schema is forward-compatible when the fetcher is extended.

MODEL (
    name mol_silver.drug_pharmacology,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key drugbank_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (drugbank_id)),
        unique_values(columns := (drugbank_id))
    ),
    grain drugbank_id
);

SELECT
    gen_random_uuid()                   AS id,

    -- Link to mol_silver.molecules via name-based join
    m.molecule_id,

    -- DrugBank identifiers (raw bronze column names)
    db.drugbank_id,
    db.cas_number,

    -- Names
    db.name,
    db.description,

    -- Pharmacology (description and pharmacodynamics populated by XML fetcher;
    -- all others NULL until fetcher is extended to extract full XML)
    db.indication,
    db.pharmacodynamics,
    db.mechanism_of_action,
    db.absorption,
    db.protein_binding,
    db.metabolism,
    db.half_life,
    db.route_of_elimination,
    db.clearance,
    db.volume_of_distribution,
    db.toxicity,

    -- Structured pharmacology data
    db.categories,
    db.targets,
    db.enzymes,
    db.carriers,
    db.transporters,
    db.pathways,

    -- Interaction data
    db.drug_interactions,
    db.food_interactions,

    -- Classification
    db.classification,
    db.atc_codes,
    db.groups,

    -- Identifiers and cross-references
    db.unii,
    db.external_links,
    db.external_identifiers,

    -- Regulatory
    db.fda_label,
    db.patents,

    -- Computed properties
    db.calculated_properties,

    -- Structural (always NULL from XML fetcher — preserved for schema completeness)
    db.smiles,
    db.inchi,
    db.inchi_key,
    db.molecular_formula,
    db.average_mass,
    db.monoisotopic_mass,
    db.drug_type,
    db.state,

    -- Synonyms and brands (NULL from current XML fetcher)
    db.synonyms,
    db.international_brands,
    db.products,

    -- Source tracking
    db.source,
    db.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.drugbank db
LEFT JOIN mol_silver.molecules m
    ON LOWER(db.name) = LOWER(m.canonical_name)
WHERE
    db.processed_to_silver = FALSE
    AND db.drugbank_id IS NOT NULL;
