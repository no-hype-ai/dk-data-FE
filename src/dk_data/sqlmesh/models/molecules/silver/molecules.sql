-- SQLMesh Model: Silver Molecules
-- Master molecule table with entity resolution using InChI Key (structural)
-- or canonical name (biologics/DrugBank with no structural identifier)
-- Part of: 012-dk-data-platform

MODEL (
    name mol_silver.molecules,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key molecule_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (molecule_id, canonical_name)),
        unique_values(columns := (molecule_id))
    ),
    grain molecule_id
);

-- Source precedence for identity resolution:
--   1. ChEMBL with inchi_key  — small molecules, structural identity (confidence 1.0)
--   2. PubChem with inchi_key  — compounds not yet in ChEMBL, structural (confidence 0.8)
--   3. ChEMBL without inchi_key — biologics (mAbs, proteins, oligonucleotides, gene therapies)
--      that ChEMBL tracks but assigns no structural identifier (confidence 0.9)
--   4. DrugBank without inchi_key — approved drugs where XML fetcher has no structural data;
--      name-based identity only (confidence 0.6)
--
-- Identity key:
--   Structural molecules: COALESCE(inchi_key, ...) → inchi_key value
--   Biologics/name-only:  COALESCE(inchi_key, ...) → 'biologic:' || lower(canonical_name)
--
-- molecule_id is a deterministic UUID: md5(identity_key)::uuid
-- This ensures FK references in downstream tables remain stable across reprocessing.
--
-- NOTE: DrugBank inchi_key is always NULL — the XML fetcher does not extract structural
-- identifiers. DrugBank contributes name-based identity here (precedence 4) and also
-- populates identifier_mappings and molecule_aliases via name-based joins.

WITH source_molecules AS (
    -- -------------------------------------------------------------------------
    -- Source 1: ChEMBL structural (inchi_key IS NOT NULL)
    -- Covers: SMALL_MOLECULE and any biologic type where ChEMBL has a structure
    -- -------------------------------------------------------------------------
    SELECT
        inchi_key,
        COALESCE(inchi_key, 'biologic:' || LOWER(pref_name))   AS identity_key,
        COALESCE(pref_name, chembl_id)                          AS canonical_name,
        'chembl'                                                AS name_source,
        canonical_smiles,
        inchi,
        molecular_formula,
        molecular_weight,
        molecule_type,
        CASE
            WHEN max_phase = 4 THEN 'approved'
            WHEN max_phase = 3 THEN 'phase_3'
            WHEN max_phase = 2 THEN 'phase_2'
            WHEN max_phase = 1 THEN 'phase_1'
            ELSE 'preclinical'
        END                                                     AS development_status,
        max_phase,
        first_approval::INTEGER                                 AS first_approval_year,
        alogp,
        hba,
        hbd,
        psa,
        num_ro5_violations,
        aromatic_rings,
        heavy_atoms,
        NULL::NUMERIC                                           AS exact_mass,
        NULL::TEXT                                              AS isomeric_smiles,
        NULL::INTEGER                                           AS rotatable_bond_count,
        NULL::NUMERIC                                           AS complexity,
        NULL::INTEGER                                           AS charge,
        NULL::JSONB                                             AS mesh_headings,
        NULL::JSONB                                             AS pharmacological_actions,
        prodrug,
        natural_product,
        usan_stem,
        1.0                                                     AS resolution_confidence,
        FALSE                                                   AS needs_review,
        jsonb_build_array('chembl')                             AS data_sources,
        'chembl'                                                AS primary_source,
        1                                                       AS source_precedence,
        source_updated_at,
        created_at
    FROM mol_bronze.chembl_molecules
    WHERE
        inchi_key IS NOT NULL
        AND processed_to_silver = FALSE

    UNION ALL

    -- -------------------------------------------------------------------------
    -- Source 2: PubChem structural (inchi_key IS NOT NULL)
    -- Covers compounds not yet in ChEMBL; IUPAC name used as canonical
    -- -------------------------------------------------------------------------
    SELECT
        inchi_key,
        inchi_key                                               AS identity_key,
        iupac_name                                              AS canonical_name,
        'pubchem'                                               AS name_source,
        canonical_smiles,
        inchi,
        molecular_formula,
        molecular_weight,
        NULL::TEXT                                              AS molecule_type,
        'unknown'                                               AS development_status,
        NULL::INTEGER                                           AS max_phase,
        NULL::INTEGER                                           AS first_approval_year,
        xlogp                                                   AS alogp,
        h_bond_acceptor_count                                   AS hba,
        h_bond_donor_count                                      AS hbd,
        tpsa                                                    AS psa,
        NULL::INTEGER                                           AS num_ro5_violations,
        NULL::INTEGER                                           AS aromatic_rings,
        heavy_atom_count                                        AS heavy_atoms,
        exact_mass,
        isomeric_smiles,
        rotatable_bond_count,
        complexity,
        charge,
        mesh_headings,
        pharmacological_actions,
        NULL::BOOLEAN                                           AS prodrug,
        NULL::BOOLEAN                                           AS natural_product,
        NULL::TEXT                                              AS usan_stem,
        0.8                                                     AS resolution_confidence,
        FALSE                                                   AS needs_review,
        jsonb_build_array('pubchem')                            AS data_sources,
        'pubchem'                                               AS primary_source,
        2                                                       AS source_precedence,
        source_updated_at,
        created_at
    FROM mol_bronze.pubchem
    WHERE
        inchi_key IS NOT NULL
        AND processed_to_silver = FALSE
        AND iupac_name IS NOT NULL

    UNION ALL

    -- -------------------------------------------------------------------------
    -- Source 3: ChEMBL biologics (inchi_key IS NULL)
    -- Covers: PROTEIN, ANTIBODY, CELL, ENZYME, OLIGONUCLEOTIDE, OLIGOSACCHARIDE
    -- where ChEMBL does not assign a structural InChI identifier.
    -- Identity is name-based: 'biologic:' || lower(pref_name).
    -- High confidence because ChEMBL data quality is authoritative.
    -- -------------------------------------------------------------------------
    SELECT
        NULL::TEXT                                              AS inchi_key,
        'biologic:' || LOWER(pref_name)                        AS identity_key,
        pref_name                                               AS canonical_name,
        'chembl'                                                AS name_source,
        NULL::TEXT                                              AS canonical_smiles,
        NULL::TEXT                                              AS inchi,
        NULL::TEXT                                              AS molecular_formula,
        NULL::NUMERIC                                           AS molecular_weight,
        molecule_type,
        CASE
            WHEN max_phase = 4 THEN 'approved'
            WHEN max_phase = 3 THEN 'phase_3'
            WHEN max_phase = 2 THEN 'phase_2'
            WHEN max_phase = 1 THEN 'phase_1'
            ELSE 'preclinical'
        END                                                     AS development_status,
        max_phase,
        first_approval::INTEGER                                 AS first_approval_year,
        alogp,
        hba,
        hbd,
        psa,
        num_ro5_violations,
        aromatic_rings,
        heavy_atoms,
        NULL::NUMERIC                                           AS exact_mass,
        NULL::TEXT                                              AS isomeric_smiles,
        NULL::INTEGER                                           AS rotatable_bond_count,
        NULL::NUMERIC                                           AS complexity,
        NULL::INTEGER                                           AS charge,
        NULL::JSONB                                             AS mesh_headings,
        NULL::JSONB                                             AS pharmacological_actions,
        prodrug,
        natural_product,
        usan_stem,
        0.9                                                     AS resolution_confidence,
        FALSE                                                   AS needs_review,
        jsonb_build_array('chembl')                             AS data_sources,
        'chembl'                                                AS primary_source,
        3                                                       AS source_precedence,
        source_updated_at,
        created_at
    FROM mol_bronze.chembl_molecules
    WHERE
        inchi_key IS NULL
        AND pref_name IS NOT NULL
        AND processed_to_silver = FALSE

    UNION ALL

    -- -------------------------------------------------------------------------
    -- Source 4: DrugBank (inchi_key always NULL — XML fetcher limitation)
    -- Covers approved/investigational drugs in DrugBank not present in ChEMBL/PubChem.
    -- Name-based identity only. Lower resolution_confidence (0.6) reflects name-match uncertainty.
    -- -------------------------------------------------------------------------
    SELECT
        NULL::TEXT                                              AS inchi_key,
        'biologic:' || LOWER(name)                             AS identity_key,
        name                                                    AS canonical_name,
        'drugbank'                                              AS name_source,
        NULL::TEXT                                              AS canonical_smiles,
        NULL::TEXT                                              AS inchi,
        NULL::TEXT                                              AS molecular_formula,
        NULL::NUMERIC                                           AS molecular_weight,
        NULL::TEXT                                              AS molecule_type,
        'unknown'                                               AS development_status,
        NULL::INTEGER                                           AS max_phase,
        NULL::INTEGER                                           AS first_approval_year,
        NULL::NUMERIC                                           AS alogp,
        NULL::INTEGER                                           AS hba,
        NULL::INTEGER                                           AS hbd,
        NULL::NUMERIC                                           AS psa,
        NULL::INTEGER                                           AS num_ro5_violations,
        NULL::INTEGER                                           AS aromatic_rings,
        NULL::INTEGER                                           AS heavy_atoms,
        NULL::NUMERIC                                           AS exact_mass,
        NULL::TEXT                                              AS isomeric_smiles,
        NULL::INTEGER                                           AS rotatable_bond_count,
        NULL::NUMERIC                                           AS complexity,
        NULL::INTEGER                                           AS charge,
        NULL::JSONB                                             AS mesh_headings,
        NULL::JSONB                                             AS pharmacological_actions,
        NULL::BOOLEAN                                           AS prodrug,
        NULL::BOOLEAN                                           AS natural_product,
        NULL::TEXT                                              AS usan_stem,
        0.6                                                     AS resolution_confidence,
        FALSE                                                   AS needs_review,
        jsonb_build_array('drugbank')                           AS data_sources,
        'drugbank'                                              AS primary_source,
        4                                                       AS source_precedence,
        source_updated_at,
        created_at
    FROM mol_bronze.drugbank
    WHERE
        name IS NOT NULL
        AND processed_to_silver = FALSE
),

-- Deduplicate by identity_key, keeping the highest-precedence source.
-- Structural molecules dedup by inchi_key (via identity_key = inchi_key value).
-- Biologics dedup by 'biologic:' || lower(canonical_name).
-- molecule_id is deterministic: md5(identity_key)::uuid — stable across reprocessing.
deduplicated AS (
    SELECT DISTINCT ON (identity_key)
        md5(identity_key)::uuid                                 AS molecule_id,
        inchi_key,
        canonical_name,
        name_source,
        canonical_smiles,
        inchi,
        molecular_formula,
        molecular_weight,
        molecule_type,
        NULL::JSONB                                             AS therapeutic_areas,
        NULL::TEXT                                              AS mechanism_of_action,
        development_status,
        max_phase,
        first_approval_year,
        NULL::DATE                                              AS approval_date,
        prodrug,
        natural_product,
        usan_stem,
        alogp,
        hba,
        hbd,
        psa,
        num_ro5_violations,
        aromatic_rings,
        heavy_atoms,
        exact_mass,
        isomeric_smiles,
        rotatable_bond_count,
        complexity,
        charge,
        mesh_headings,
        pharmacological_actions,
        resolution_confidence,
        needs_review,
        NULL::TEXT                                              AS review_reason,
        data_sources,
        primary_source,
        NOW()                                                   AS created_at,
        NOW()                                                   AS updated_at
    FROM source_molecules
    ORDER BY identity_key, source_precedence ASC, source_updated_at DESC
),

-- Enrich with DrugBank pharmacology fields (description, pharmacodynamics, drug_categories).
-- Only populated where DrugBank has data; NULL for non-DrugBank molecules.
-- mechanism_of_action is NULL in current DrugBank bronze (XML fetcher doesn't extract it).
enriched AS (
    SELECT
        d.*,
        db.description,
        db.pharmacodynamics,
        db.categories AS drug_categories
    FROM deduplicated d
    LEFT JOIN mol_bronze.drugbank db
        ON LOWER(d.canonical_name) = LOWER(db.name)
)

SELECT * FROM enriched;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY (unique_key = molecule_id),
-- so reprocessing is idempotent — on conflict, all columns are updated.
