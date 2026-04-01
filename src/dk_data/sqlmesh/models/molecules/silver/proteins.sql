-- SQLMesh Model: Silver Proteins
-- UniProt protein records linked to mol_silver.molecules via identifier_mappings
-- Feature: 019-cms-puf-platform-reconciliation — zero column loss audit
--
-- Purpose: UniProt bronze was entirely unconsumed by mol_silver. This table promotes
--   all UniProt bronze columns to silver so protein sequence, domain, GO term,
--   taxonomy, and annotation data are directly queryable.
--
-- Linkage: uniprot_id → mol_silver.identifier_mappings (identifier_type = 'uniprot')
--   to resolve molecule_id. Proteins with no drug link have molecule_id = NULL.

MODEL (
    name mol_silver.proteins,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key uniprot_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (uniprot_id)),
        unique_values(columns := (uniprot_id))
    ),
    grain uniprot_id
);

SELECT
    gen_random_uuid()           AS id,

    -- Link to mol_silver.molecules (may be NULL if protein has no small-molecule drug link)
    im.molecule_id,

    -- UniProt identifiers (exact bronze column names)
    u.uniprot_id,
    u.entry_name,
    u.entry_type,

    -- Protein names
    u.protein_name,
    u.short_name,
    u.alternative_names,
    u.submission_names,

    -- Gene names
    u.gene_name,
    u.genes,

    -- Organism
    u.organism_scientific,
    u.organism_common,
    u.taxonomy_id,
    u.lineage,

    -- Sequence
    u.sequence,
    u.sequence_length,
    u.molecular_weight,
    u.sequence_checksum,

    -- Function and annotation
    u.comments,
    u.features,
    u.keywords,
    u.go_terms,
    u.annotation_score,

    -- Cross-references and identifiers
    u.cross_references,
    u.secondary_accessions,
    u.pdb_structures,
    u.extra_attributes,

    -- Source tracking
    u.source,
    u.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.uniprot u
LEFT JOIN mol_silver.identifier_mappings im
    ON im.identifier_type = 'uniprot_id'
    AND im.identifier_value = u.uniprot_id
WHERE
    u.processed_to_silver = FALSE
    AND u.uniprot_id IS NOT NULL;
